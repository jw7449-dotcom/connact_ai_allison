"""Real Gmail mail flow. No mocks, implicit recipients, or automatic write retries.

Message lists and thread reads revalidate current saved contacts. Gmail bodies are
requested only after metadata passes that same boundary; a thread is never an
authorization boundary. Send commands preserve the exact reviewed draft snapshot.
"""
import base64
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import getaddresses, make_msgid
from html import escape
from threading import Event, Lock, Thread
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError

from ..db import Session, WorkspaceRepository
from ..config import settings
from ..models import Contact, Draft, now
from ..mail_models import Mailbox, MailMessage, MailSend, MailSuppression, MailTask, MailThreadState
from ..mail_schemas import SendInput
from .drafts import preview, plain_text, sanitize
from .mail_attachments import attach_to_message, freeze_attachments

MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
METADATA_HEADERS = ["From", "To", "Cc", "Subject", "Date", "Message-ID", "In-Reply-To", "References", "Reply-To", "Auto-Submitted", "Precedence", "X-Autoreply", "X-Autorespond", "Content-Type", "Final-Recipient", "Original-Recipient"]
EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}$")
PENDING = ("queued", "scheduled", "paused", "blocked")


class MailboxSyncBusy(HTTPException):
    def __init__(self):
        super().__init__(409, "This Gmail account is already synchronizing.")


def _failure_reason(exc):
    # The Gmail transport translates provider responses into fixed local messages;
    # raw response bodies and arbitrary exception strings must never be stored.
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Gmail could not complete the request."
        return f"HTTP {exc.status_code}: {detail[:800]}"
    return "Gmail could not complete the request."


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def normalize_email(value):
    value = (value or "").strip().lower()
    return value if len(value) <= 254 and EMAIL.fullmatch(value) else ""


def can_read(mailbox):
    return bool(mailbox.sync_enabled) and (MODIFY_SCOPE in (mailbox.scopes or []) or READ_SCOPE in (mailbox.scopes or []))


def can_send(mailbox):
    return MODIFY_SCOPE in (mailbox.scopes or []) or SEND_SCOPE in (mailbox.scopes or [])


def client_for(mailbox, session):
    from .gmail import GmailClient
    return GmailClient(mailbox, session)


def mailbox_json(mailbox):
    return {**{name: getattr(mailbox, name) for name in ("id", "provider", "email", "display_name", "status", "scopes", "sync_enabled", "signature_html", "timezone", "send_window_start", "send_window_end", "last_sync_at", "last_sync_error", "sync_status", "created_at")}, "can_send": can_send(mailbox), "can_receive": can_read(mailbox), "can_sync": can_read(mailbox)}


def saved_contacts(repo):
    # Stable choice when multiple saved cards have the same exact address.
    result = {}
    for contact in sorted(repo.all(Contact, Contact.saved.is_(True)), key=lambda c: c.id):
        address = normalize_email(contact.email)
        if address:
            result.setdefault(address, contact)
    return result


def contact_for_message(repo, message):
    contact = repo.session.scalar(repo.query(Contact).where(Contact.id == message.contact_id, Contact.saved.is_(True)).execution_options(populate_existing=True))
    return contact if _message_matches_contact(message, contact) else None


def _current_saved_contact(repo, contact_id, expected_email):
    contact = repo.session.scalar(repo.query(Contact).where(Contact.id == contact_id, Contact.saved.is_(True)).execution_options(populate_existing=True))
    return contact if contact and normalize_email(contact.email) == expected_email else None


def _message_matches_contact(message, contact):
    address = normalize_email(contact.email) if contact and contact.saved else ""
    if not address or address != message.contact_email:
        return False
    if message.direction == "incoming":
        return normalize_email(message.from_email) == address
    if message.direction == "outgoing":
        return address in (message.to_emails or [])
    return False


def require_visible_message(repo, message):
    repo.get(Mailbox, message.mailbox_id)
    if not contact_for_message(repo, message):
        raise HTTPException(404, "This message is no longer linked to a saved workspace contact.")
    return message


def message_json(message):
    return {name: getattr(message, name) for name in ("id", "mailbox_id", "gmail_message_id", "gmail_thread_id", "contact_id", "contact_email", "from_email", "to_emails", "subject", "snippet", "body_text", "body_html", "received_at", "direction", "is_unread", "is_archived", "attachments", "is_automated")}


def visible_messages(repo, mailbox_id=None, folder="inbox", unread=False, limit=200,
                     email=None, domain=None, pending_reply=False, intent=None, offset=0):
    conditions = []
    if mailbox_id:
        repo.get(Mailbox, mailbox_id)
        conditions.append(MailMessage.mailbox_id == mailbox_id)
    if folder not in ("inbox", "sent", "archive", "all"):
        raise HTTPException(422, "Unknown mail folder.")
    if intent is not None and intent not in ("none", "interested", "not_now", "not_interested"):
        raise HTTPException(422, "Unknown conversation intent.")
    if offset < 0 or not 1 <= limit <= 1000:
        raise HTTPException(422, "Use a nonnegative offset and a page size from 1 to 1000.")
    email_filter = normalize_email(email) if email else None
    if email and not email_filter:
        raise HTTPException(422, "Enter an exact valid contact email address.")
    domain_filter = domain.strip().lower() if domain else None
    if domain_filter and ("@" in domain_filter or not normalize_email("filter@" + domain_filter)):
        raise HTTPException(422, "Enter an exact email domain, such as example.com.")
    states = {(state.mailbox_id, state.gmail_thread_id): state.intent for state in repo.all(MailThreadState)} if intent is not None else {}
    # One joined, ordered stream validates both current contact and mailbox
    # ownership without one database lookup per message. For pending replies,
    # evaluate each thread's newest visible message BEFORE folder/email filters:
    # a sent reply or automatic response can remove an older Inbox item from
    # the pending set. Hidden personal mail cannot affect that decision.
    query = select(MailMessage, Contact).join(Contact, Contact.id == MailMessage.contact_id).join(
        Mailbox, Mailbox.id == MailMessage.mailbox_id
    ).where(MailMessage.workspace_id == repo.workspace_id,
        Contact.workspace_id == repo.workspace_id, Contact.saved.is_(True),
        Mailbox.workspace_id == repo.workspace_id, *conditions
    ).order_by(MailMessage.received_at.desc(), MailMessage.id.desc()).execution_options(populate_existing=True)
    result, skipped, latest_pending = [], 0, {}
    for message, contact in repo.session.execute(query).yield_per(100):
        if not _message_matches_contact(message, contact):
            continue
        thread_key = message.mailbox_id, message.gmail_thread_id
        if pending_reply:
            latest_pending.setdefault(thread_key, message.direction == "incoming" and not message.is_automated)
            if not latest_pending[thread_key]:
                continue
        if folder == "inbox" and (message.direction != "incoming" or message.is_archived):
            continue
        if folder == "sent" and message.direction != "outgoing":
            continue
        if folder == "archive" and (message.direction != "incoming" or not message.is_archived):
            continue
        if unread and not message.is_unread:
            continue
        if email_filter and message.contact_email != email_filter:
            continue
        if domain_filter and message.contact_email.rsplit("@", 1)[-1] != domain_filter:
            continue
        if intent is not None and states.get(thread_key, "none") != intent:
            continue
        if skipped < offset:
            skipped += 1
            continue
        result.append(message_json(message))
        if len(result) >= limit:
            break
    return result


def thread_json(repo, mailbox, thread_id):
    messages = [message for message in repo.all(MailMessage, MailMessage.mailbox_id == mailbox.id, MailMessage.gmail_thread_id == thread_id) if contact_for_message(repo, message)]
    if not messages:
        raise HTTPException(404, "No messages from saved contacts in this conversation.")
    state = repo.session.scalar(repo.query(MailThreadState).where(MailThreadState.mailbox_id == mailbox.id, MailThreadState.gmail_thread_id == thread_id))
    return {"messages": [message_json(m) for m in sorted(messages, key=lambda m: utc(m.received_at))], "notes": state.notes if state else "", "intent": state.intent if state else "none"}


def _headers(message):
    result = {}
    for item in message.get("payload", {}).get("headers", []):
        name = str(item.get("name", "")).lower()
        value = str(item.get("value", ""))
        try:
            value = str(make_header(decode_header(value)))
        except (LookupError, UnicodeError):
            pass
        result[name] = (result[name] + ", " + value) if name in result else value
    return result


def _addresses(header):
    return [address for _, raw in getaddresses([header or ""]) if (address := normalize_email(raw))]


def _match_metadata(mailbox, metadata, contacts):
    headers = _headers(metadata)
    senders = _addresses(headers.get("from"))
    if len(senders) != 1:
        return None
    sender = senders[0]
    recipients = _addresses(headers.get("to"))
    if sender == normalize_email(mailbox.email):
        candidates = [contacts[email] for email in recipients if email in contacts and contacts[email].saved and normalize_email(contacts[email].email) == email]
        return (candidates[0], "outgoing", sender, recipients, headers) if candidates else None
    if sender in contacts and contacts[sender].saved and normalize_email(contacts[sender].email) == sender:
        return contacts[sender], "incoming", sender, recipients, headers
    return None


def _decode(data):
    try:
        return base64.urlsafe_b64decode((data or "") + "=" * (-len(data or "") % 4))
    except (ValueError, TypeError):
        return b""


def _parts(payload):
    yield payload
    for part in payload.get("parts", []):
        yield from _parts(part)


def _content(payload):
    texts, htmls, attachments = [], [], []
    for part in _parts(payload):
        body, mime = part.get("body", {}), part.get("mimeType", "")
        filename = str(part.get("filename", ""))[:255]
        # An attachment is never executed or fetched during synchronization.
        if filename or body.get("attachmentId"):
            if body.get("attachmentId"):
                attachments.append({"id": body["attachmentId"], "filename": filename or "attachment", "mime_type": mime, "size": body.get("size", 0)})
            continue
        if mime not in ("text/plain", "text/html") or not body.get("data"):
            continue
        raw = _decode(body["data"])
        content_type = next((h.get("value", "") for h in part.get("headers", []) if h.get("name", "").lower() == "content-type"), "")
        charset_match = re.search(r'charset=["\']?([^\s;"\']+)', content_type, re.I)
        charset = charset_match.group(1) if charset_match else "utf-8"
        try:
            decoded = raw.decode(charset, errors="replace")
        except LookupError:
            decoded = raw.decode("utf-8", errors="replace")
        (htmls if mime == "text/html" else texts).append(decoded)
    html = sanitize("\n".join(htmls)[:200000])
    text = ("\n".join(texts) or plain_text(html))[:200000]
    return text, html or "<p>" + escape(text).replace("\n", "<br>") + "</p>", attachments


def _automated(headers):
    return bool((headers.get("auto-submitted", "no").lower() != "no") or headers.get("precedence", "").lower() in ("bulk", "list", "junk") or headers.get("x-autoreply") or headers.get("x-autorespond") or "multipart/report" in headers.get("content-type", "").lower())


def _pause_for_reply(repo, mailbox, contact, received_at):
    repo.session.execute(update(MailSend).where(
        MailSend.workspace_id == repo.workspace_id,
        MailSend.recipient_email == normalize_email(contact.email), MailSend.status.in_(("scheduled", "queued", "blocked")),
        MailSend.mode != "test", MailSend.created_at <= received_at
    ).values(status="paused", error="A new reply arrived from this contact. Review the conversation before resuming."))


def suppress(repo, contact, reason, notes=""):
    email = normalize_email(contact.email)
    if not contact.saved or not email:
        raise HTTPException(422, "Suppression requires a saved contact with a valid email.")
    item = repo.session.scalar(repo.query(MailSuppression).where(MailSuppression.email == email))
    if not item:
        item = repo.add(MailSuppression, contact_id=contact.id, email=email, reason=reason, notes=notes)
    else:
        item.reason, item.notes, item.contact_id = reason, notes, contact.id
    repo.session.execute(update(MailSend).where(MailSend.workspace_id == repo.workspace_id, MailSend.recipient_email == email, MailSend.status.in_(PENDING), MailSend.mode != "test").values(status="blocked", error="This recipient is on the workspace suppression list."))
    return item


def _bounce_candidate(repo, mailbox, headers):
    # Inspect DSN bodies only when a metadata reference links to our actual send.
    references = set(re.findall(r"<[^<>\s]+>", headers.get("in-reply-to", "") + " " + headers.get("references", "")))
    if not references or "multipart/report" not in headers.get("content-type", "").lower():
        return None
    return repo.session.scalar(repo.query(MailSend).where(MailSend.mailbox_id == mailbox.id, MailSend.rfc_message_id.in_(references), MailSend.status.in_(("sent", "uncertain")), MailSend.mode != "test"))


def _inspect_bounce(repo, mailbox, metadata, client):
    command = _bounce_candidate(repo, mailbox, _headers(metadata))
    if not command:
        return
    contact = _current_saved_contact(repo, command.contact_id, command.recipient_email)
    if not contact:
        return
    full = client.request("GET", "messages/" + metadata["id"], params={"format": "full"})
    contact = _current_saved_contact(repo, command.contact_id, command.recipient_email)
    if not contact:
        return
    for part in _parts(full.get("payload", {})):
        if part.get("mimeType") != "message/delivery-status":
            continue
        content = _decode(part.get("body", {}).get("data", "")).decode("utf-8", "replace")
        for block in re.split(r"\r?\n\r?\n", content):
            address = re.search(r"(?:Final|Original)-Recipient:\s*[^;\r\n]+;\s*([^\s\r\n]+)", block, re.I)
            if address and normalize_email(address.group(1)) == command.recipient_email and re.search(r"^Status:\s*5\.", block, re.M):
                suppress(repo, contact, "hard_bounce", "Gmail reported permanent delivery failure for a platform-sent message.")


def _import_message(repo, mailbox, message_id, client, contacts, metadata=None):
    existing = repo.session.scalar(repo.query(MailMessage).where(MailMessage.mailbox_id == mailbox.id, MailMessage.gmail_message_id == message_id))
    try:
        metadata = metadata or client.request("GET", "messages/" + message_id, params={"format": "metadata", "metadataHeaders": METADATA_HEADERS})
    except HTTPException as exc:
        if exc.status_code == 404:
            if existing:
                repo.session.delete(existing)
            return 0
        raise
    match = _match_metadata(mailbox, metadata, contacts)
    if not match or set(metadata.get("labelIds", [])) & {"SPAM", "TRASH"}:
        if existing:
            repo.session.delete(existing)
        if not match:
            _inspect_bounce(repo, mailbox, metadata, client)
        return 0
    contact, direction, sender, recipients, headers = match
    expected_email = normalize_email(contact.email)
    contact = _current_saved_contact(repo, contact.id, expected_email)
    if not contact:
        if existing:
            repo.session.delete(existing)
        return 0
    labels = metadata.get("labelIds", [])
    if existing and existing.content_synced and existing.contact_id == contact.id and existing.contact_email == normalize_email(contact.email):
        existing.labels, existing.is_unread, existing.is_archived = labels, "UNREAD" in labels, "INBOX" not in labels
        return 0
    full = client.request("GET", "messages/" + message_id, params={"format": "full"})
    # Contact changes can commit while Gmail is returning the body. Reload the
    # database row rather than trusting the earlier identity-map instance.
    contact = _current_saved_contact(repo, contact.id, expected_email)
    if not contact:
        if existing:
            repo.session.delete(existing)
        return 0
    # Gmail metadata and full response must independently pass the boundary.
    full_match = _match_metadata(mailbox, full, contacts)
    if not full_match or full_match[0].id != contact.id or full_match[1] != direction:
        return 0
    _, _, _, _, headers = full_match
    body_text, body_html, attachments = _content(full.get("payload", {}))
    received_at = datetime.fromtimestamp(int(full.get("internalDate", 0)) / 1000, timezone.utc)
    values = dict(mailbox_id=mailbox.id, gmail_message_id=message_id, gmail_thread_id=full.get("threadId", metadata.get("threadId", "")), contact_id=contact.id, contact_email=normalize_email(contact.email), from_email=sender, to_emails=recipients, subject=headers.get("subject", "")[:2000], snippet=plain_text(body_html)[:250], body_text=body_text, body_html=body_html, received_at=received_at, direction=direction, is_unread="UNREAD" in full.get("labelIds", labels), is_archived="INBOX" not in full.get("labelIds", labels), labels=full.get("labelIds", labels), rfc_message_id=headers.get("message-id", "")[:998], in_reply_to=headers.get("in-reply-to", "")[:10000], references=headers.get("references", "")[:10000], reply_to=(_addresses(headers.get("reply-to")) or [""])[0], attachments=attachments, is_automated=_automated(headers))
    if existing:
        for name, value in values.items():
            setattr(existing, name, value)
        existing.content_synced = True
    else:
        repo.add(MailMessage, **values)
    if direction == "incoming":
        _pause_for_reply(repo, mailbox, contact, received_at)
    return 1


def _pages(client, path, params):
    token, seen = None, set()
    while True:
        page = client.request("GET", path, params={**params, **({"pageToken": token} if token else {})})
        yield page
        token = page.get("nextPageToken")
        if not token:
            return
        if token in seen:
            raise HTTPException(502, "Gmail returned a repeated pagination token. Sync stopped safely.")
        seen.add(token)


def _block_schedules(repo, mailbox, reason):
    repo.session.execute(update(MailSend).where(MailSend.workspace_id == repo.workspace_id, MailSend.mailbox_id == mailbox.id, MailSend.status == "scheduled").values(status="blocked", error=reason))


def sync_mailbox(repo, mailbox):
    if mailbox.status != "connected":
        raise HTTPException(409, "Reconnect this Gmail account before synchronizing.")
    if not can_read(mailbox):
        raise HTTPException(409, "Reconnect with send and receive permission to synchronize Gmail.")
    claimed = repo.session.execute(update(Mailbox).where(Mailbox.id == mailbox.id, Mailbox.workspace_id == repo.workspace_id, or_(Mailbox.sync_status != "running", Mailbox.sync_started_at < now() - timedelta(minutes=15), Mailbox.sync_started_at.is_(None))).values(sync_status="running", sync_started_at=now()))
    if not claimed.rowcount:
        raise MailboxSyncBusy()
    repo.session.commit()
    repo.session.refresh(mailbox)
    try:
        contacts = saved_contacts(repo)
        fingerprint = hashlib.sha256(json.dumps(sorted((email, c.id) for email, c in contacts.items())).encode()).hexdigest()
        client = client_for(mailbox, repo.session)
        imported, seen = 0, set()
        full_sync = not mailbox.history_id or mailbox.contacts_fingerprint != fingerprint
        # Capture a cursor before full listing so mail arriving during pagination is
        # replayed in the next history pass rather than skipped.
        baseline = str(client.profile().get("historyId", ""))
        next_history = baseline
        if not full_sync:
            try:
                for page in _pages(client, "history", {"startHistoryId": mailbox.history_id, "maxResults": 500}):
                    for history in page.get("history", []):
                        for removed in history.get("messagesDeleted", []):
                            removed_id = removed.get("message", {}).get("id")
                            repo.session.execute(delete(MailMessage).where(MailMessage.workspace_id == repo.workspace_id, MailMessage.mailbox_id == mailbox.id, MailMessage.gmail_message_id == removed_id))
                        ids = {item.get("id") for item in history.get("messages", [])}
                        for kind in ("messagesAdded", "labelsAdded", "labelsRemoved"):
                            ids.update(item.get("message", {}).get("id") for item in history.get(kind, []))
                        for message_id in ids - seen - {None}:
                            imported += _import_message(repo, mailbox, message_id, client, contacts)
                            seen.add(message_id)
                    next_history = str(page.get("historyId", next_history))
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
                full_sync = True
                next_history = baseline
        if full_sync:
            emails = list(contacts)
            for start in range(0, len(emails), 12):
                clauses = " ".join("from:" + email + " to:" + email for email in emails[start:start + 12])
                query = "in:anywhere newer_than:30d -in:spam -in:trash {" + clauses + "}"
                for page in _pages(client, "messages", {"q": query, "maxResults": 100}):
                    for message in page.get("messages", []):
                        if message["id"] not in seen:
                            imported += _import_message(repo, mailbox, message["id"], client, contacts)
                            seen.add(message["id"])
            # Older tracked conversations remain available after cursor expiration.
            threads = set(repo.session.scalars(select(MailMessage.gmail_thread_id).where(MailMessage.workspace_id == repo.workspace_id, MailMessage.mailbox_id == mailbox.id)).all())
            threads.update(thread for thread in repo.session.scalars(select(MailSend.gmail_thread_id).where(MailSend.workspace_id == repo.workspace_id, MailSend.mailbox_id == mailbox.id, MailSend.gmail_thread_id.is_not(None))).all())
            for thread_id in threads:
                try:
                    thread = client.request("GET", "threads/" + thread_id, params={"format": "metadata", "metadataHeaders": METADATA_HEADERS})
                except HTTPException as exc:
                    if exc.status_code == 404:
                        repo.session.execute(delete(MailMessage).where(MailMessage.workspace_id == repo.workspace_id, MailMessage.mailbox_id == mailbox.id, MailMessage.gmail_thread_id == thread_id))
                        continue
                    raise
                for metadata in thread.get("messages", []):
                    if metadata["id"] not in seen:
                        imported += _import_message(repo, mailbox, metadata["id"], client, contacts, metadata)
                        seen.add(metadata["id"])
        # Purge historical messages invalidated by deleting/unsaving/editing contacts.
        for message in repo.all(MailMessage, MailMessage.mailbox_id == mailbox.id):
            if not contact_for_message(repo, message):
                repo.session.delete(message)
        mailbox.history_id, mailbox.contacts_fingerprint = next_history or mailbox.history_id, fingerprint
        mailbox.last_sync_at, mailbox.last_sync_error, mailbox.sync_status = now(), None, "idle"
        repo.session.commit()
        return {"status": "synced", "imported": imported, "history_id": mailbox.history_id, "last_sync_at": mailbox.last_sync_at}
    except Exception as exc:
        failed_status = mailbox.status
        repo.session.rollback()
        repo.session.refresh(mailbox)
        if failed_status == "reauth_required":
            mailbox.status = failed_status
            mailbox.access_token_encrypted = None
        mailbox.sync_status = "failed"
        mailbox.last_sync_error = "Gmail sync failed. " + _failure_reason(exc) + " Reconnect if authorization expired, then synchronize again. Scheduled sends are blocked until reviewed."
        _block_schedules(repo, mailbox, mailbox.last_sync_error)
        repo.session.commit()
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(502, mailbox.last_sync_error) from None


def modify_message(repo, message, body):
    require_visible_message(repo, message)
    mailbox = repo.get(Mailbox, message.mailbox_id)
    if mailbox.status != "connected" or not can_read(mailbox) or MODIFY_SCOPE not in (mailbox.scopes or []):
        raise HTTPException(409, "Reconnect Gmail with send and receive permission first.")
    add, remove = [], []
    if body.is_unread is not None:
        (add if body.is_unread else remove).append("UNREAD")
    if body.is_archived is not None:
        (remove if body.is_archived else add).append("INBOX")
    if add or remove:
        try:
            result = client_for(mailbox, repo.session).request("POST", "messages/" + message.gmail_message_id + "/modify", json={"addLabelIds": add, "removeLabelIds": remove})
        except HTTPException:
            _persist_reauthorization(repo, mailbox)
            raise
        labels = result.get("labelIds", sorted((set(message.labels) | set(add)) - set(remove)))
        message.labels, message.is_unread, message.is_archived = labels, "UNREAD" in labels, "INBOX" not in labels
    return message_json(message)


def attachment_bytes(repo, message, attachment_id):
    require_visible_message(repo, message)
    attachment = next((a for a in message.attachments if a["id"] == attachment_id), None)
    if not attachment:
        raise HTTPException(404, "Attachment not found for this contact message.")
    if attachment.get("size", 0) > 25 * 1024 * 1024:
        raise HTTPException(413, "Open Gmail to download attachments larger than 25 MB.")
    mailbox = repo.get(Mailbox, message.mailbox_id)
    if mailbox.status != "connected" or not can_read(mailbox):
        raise HTTPException(409, "Reconnect Gmail before downloading attachments.")
    try:
        result = client_for(mailbox, repo.session).request("GET", "messages/" + message.gmail_message_id + "/attachments/" + attachment_id)
    except HTTPException:
        _persist_reauthorization(repo, mailbox)
        raise
    return _decode(result.get("data", "")), attachment


def _persist_reauthorization(repo, mailbox):
    if mailbox.status == "reauth_required":
        mailbox.access_token_encrypted = None
        _block_schedules(repo, mailbox, "Gmail authorization expired. Reconnect, synchronize and review before resuming scheduled sends.")
        repo.session.commit()


def _base_subject(subject):
    return re.sub(r"^(?:\s*re\s*:\s*)+", "", subject, flags=re.I).strip()


def reviewed_snapshot(repo, mailbox, draft, revision, reply_message_id=None, test=False, attachments=None, require_ready=True):
    if mailbox.status != "connected" or not can_send(mailbox):
        raise HTTPException(409, "Connect a Gmail account with sending permission first.")
    if draft.revision != revision:
        raise HTTPException(409, "This draft changed. Review the latest version before sending.")
    if require_ready and draft.status != "ready":
        raise HTTPException(422, "Save the draft as ready after reviewing its content.")
    rendered = preview(repo, draft)
    if not rendered["can_mark_ready"]:
        raise HTTPException(422, "Complete the recipient, subject, body and variables before sending.")
    contact = repo.get(Contact, draft.contact_id)
    address = normalize_email(contact.email)
    if not contact.saved or not address:
        raise HTTPException(422, "The recipient must be a saved workspace contact with a valid email.")
    if not test and repo.session.scalar(repo.query(MailSuppression).where(MailSuppression.email == address)):
        raise HTTPException(409, "This recipient is on the workspace suppression list.")
    subject = rendered["subject"]
    if "\r" in subject or "\n" in subject:
        raise HTTPException(422, "Email subjects cannot contain line breaks.")
    signature = sanitize(mailbox.signature_html or "")
    body_html = rendered["body_html"] + ("<br>" + signature if plain_text(signature) else "")
    snapshot = {"draft_id": draft.id, "revision": revision, "contact_id": contact.id, "contact_email": address, "recipient_email": normalize_email(mailbox.email) if test else address, "mailbox_email": normalize_email(mailbox.email), "subject": subject, "body_html": body_html, "body_text": plain_text(body_html), "signature_html": signature, "attachments": deepcopy(attachments or []), "reply_message_id": reply_message_id, "gmail_thread_id": None, "in_reply_to": "", "references": ""}
    if reply_message_id:
        original = require_visible_message(repo, repo.get(MailMessage, reply_message_id))
        if original.mailbox_id != mailbox.id or original.contact_id != contact.id or original.contact_email != address:
            raise HTTPException(422, "The reply must use this conversation's Gmail account and saved contact.")
        target_address = original.reply_to or original.from_email if original.direction == "incoming" else original.contact_email
        if normalize_email(target_address) != address:
            raise HTTPException(422, "The original Reply-To address differs from the saved contact. Verify the contact before replying.")
        if _base_subject(subject) != _base_subject(original.subject):
            raise HTTPException(422, "Keep the original conversation subject when replying.")
        if not original.rfc_message_id or any(ch in original.rfc_message_id + original.references for ch in "\r\n"):
            raise HTTPException(422, "The original email has no valid reply headers. Start a new email instead.")
        if not test:
            snapshot.update(gmail_thread_id=original.gmail_thread_id, in_reply_to=original.rfc_message_id, references=" ".join(dict.fromkeys(re.findall(r"<[^<>\s]+>", original.references + " " + original.rfc_message_id))))
    if not test:
        from .mail_unsubscribe import append_footer
        append_footer(snapshot, repo.workspace_id)
    return snapshot


def send_preview(repo, mailbox_id, draft_id, reply_message_id=None, mode="send"):
    mailbox, draft = repo.get(Mailbox, mailbox_id), repo.get(Draft, draft_id)
    rendered = preview(repo, draft)
    try:
        snapshot = reviewed_snapshot(repo, mailbox, draft, draft.revision, reply_message_id, mode == "test", require_ready=False)
        issues = [] if draft.status == "ready" else ["Save the draft as ready after reviewing its content."]
        return {**snapshot, "can_send": not issues, "issues": issues}
    except HTTPException as exc:
        signature = sanitize(mailbox.signature_html or "")
        body_html = rendered["body_html"] + ("<br>" + signature if plain_text(signature) else "")
        return {**rendered, "body_html": body_html, "body_text": plain_text(body_html), "recipient_email": mailbox.email if mode == "test" else rendered["recipient_email"], "revision": draft.revision, "mailbox_email": mailbox.email, "can_send": False, "issues": [str(exc.detail)]}


def send_json(repo, command):
    mailbox = repo.get(Mailbox, command.mailbox_id)
    return {**{name: getattr(command, name) for name in ("id", "mailbox_id", "draft_id", "draft_revision", "contact_id", "recipient_email", "mode", "status", "subject", "scheduled_at", "created_at", "started_at", "sent_at", "gmail_message_id", "gmail_thread_id", "error", "idempotency_key")}, "mailbox_email": mailbox.email, "body_text": command.snapshot.get("body_text", ""), "attachments": [{key: item.get(key) for key in ("filename", "size", "mime_type")} for item in command.snapshot.get("attachments", [])]}


def send_draft(repo, body: SendInput):
    request_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    existing = repo.session.scalar(repo.query(MailSend).where(MailSend.idempotency_key == body.idempotency_key))
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, "This idempotency key belongs to a different send request.")
        return send_json(repo, existing)
    if body.mode == "schedule":
        if not body.scheduled_at or utc(body.scheduled_at) <= now():
            raise HTTPException(422, "Choose a future scheduled time with a timezone.")
    elif body.scheduled_at is not None:
        raise HTTPException(422, "Use schedule mode for a scheduled send.")
    mailbox, draft = repo.get(Mailbox, body.mailbox_id), repo.get(Draft, body.draft_id)
    snapshot = reviewed_snapshot(repo, mailbox, draft, body.revision, body.reply_message_id, body.mode == "test", freeze_attachments(body.attachments))
    if body.mode == "schedule" and not can_read(mailbox):
        raise HTTPException(422, "Scheduled sends require send and receive permission so new replies can stop delivery.")
    if body.mode == "schedule" and (mailbox.last_sync_error or not mailbox.last_sync_at):
        raise HTTPException(409, "Synchronize this Gmail account successfully before scheduling.")
    try:
        with repo.session.begin_nested():
            command = repo.add(MailSend, mailbox_id=mailbox.id, draft_id=draft.id, draft_revision=draft.revision, contact_id=draft.contact_id, recipient_email=snapshot["recipient_email"], idempotency_key=body.idempotency_key, request_hash=request_hash, mode=body.mode, status="scheduled" if body.mode == "schedule" else "queued", subject=snapshot["subject"], snapshot=snapshot, scheduled_at=body.scheduled_at, rfc_message_id=make_msgid(domain="connact.local"))
    except IntegrityError:
        command = repo.session.scalar(repo.query(MailSend).where(MailSend.idempotency_key == body.idempotency_key))
        if not command or command.request_hash != request_hash:
            raise HTTPException(409, "This idempotency key belongs to a different send request.") from None
        return send_json(repo, command)
    _mime(command)  # Validate complete MIME size before persisting a send command.
    command_id = command.id
    repo.session.commit()  # Persist intent before any provider write.
    if body.mode != "schedule":
        process_send(command_id)
    else:
        _wake.set()
    repo.session.expire_all()
    return send_json(repo, repo.get(MailSend, command_id))


def _mime(command):
    snapshot = command.snapshot
    message = EmailMessage(policy=policy.SMTP)
    message["From"], message["To"] = snapshot["mailbox_email"], snapshot["recipient_email"]
    message["Subject"] = ("[Test] " if command.mode == "test" else "") + snapshot["subject"]
    message["Message-ID"] = command.rfc_message_id
    if snapshot.get("unsubscribe_url"):
        message["List-Unsubscribe"] = "<" + snapshot["unsubscribe_url"] + ">"
    if snapshot.get("in_reply_to"):
        message["In-Reply-To"] = snapshot["in_reply_to"]
        message["References"] = snapshot["references"]
    message.set_content(snapshot["body_text"])
    message.add_alternative(snapshot["body_html"], subtype="html")
    attach_to_message(message, snapshot.get("attachments", []))
    return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("="), **({"threadId": snapshot["gmail_thread_id"]} if snapshot.get("gmail_thread_id") else {})}


def process_send(send_id):
    with Session() as db:
        command = db.get(MailSend, send_id)
        if not command or command.status not in ("queued", "scheduled"):
            return False
        repo = WorkspaceRepository(db, command.workspace_id)
        mailbox = repo.get(Mailbox, command.mailbox_id)
        if command.mode == "schedule":
            if not command.scheduled_at or utc(command.scheduled_at) > now():
                return False
            local_time = now().astimezone(ZoneInfo(mailbox.timezone or "UTC"))
            if not mailbox.send_window_start <= local_time.hour < mailbox.send_window_end:
                return False
            # Check live incoming mail directly before every scheduled delivery.
            # Sync may pause this command after a reply or block it on failure.
            try:
                sync_mailbox(repo, mailbox)
            except MailboxSyncBusy:
                db.rollback()
                return False  # Another worker owns the live pre-send check.
            except Exception:
                _block_schedules(repo, mailbox, "Gmail could not be checked before delivery. Synchronize and review before resuming.")
                db.commit()
                return False
            db.expire_all()
            command = repo.get(MailSend, send_id)
            mailbox = repo.get(Mailbox, command.mailbox_id)
            if command.status != "scheduled":
                return False
        try:
            # Lock the mailbox before counting claimed sends so concurrent workers
            # cannot overshoot the configured daily application limit.
            db.execute(update(Mailbox).where(Mailbox.id == mailbox.id).values(updated_at=Mailbox.updated_at))
            count = len(repo.all(MailSend, MailSend.mailbox_id == mailbox.id, MailSend.status.in_(("sent", "sending", "uncertain")), MailSend.started_at >= now() - timedelta(days=1)))
            if count >= settings.gmail_daily_send_limit:
                raise HTTPException(429, "The application daily limit for this Gmail account has been reached. Review this send after the limit resets.")
            if command.mode == "schedule":
                if not command.scheduled_at or utc(command.scheduled_at) > now():
                    return False
                if mailbox.last_sync_error or mailbox.sync_status != "idle" or not mailbox.last_sync_at or utc(mailbox.last_sync_at) < now() - timedelta(minutes=5):
                    raise HTTPException(409, "A recent successful Gmail sync is required. Synchronize and review before resuming.")
            draft = repo.get(Draft, command.draft_id)
            current = reviewed_snapshot(repo, mailbox, draft, command.draft_revision, command.snapshot.get("reply_message_id"), command.mode == "test", command.snapshot.get("attachments"))
            if current != command.snapshot:
                raise HTTPException(409, "The draft, recipient, sender or reply context changed after review. Create a new reviewed send.")
        except HTTPException as exc:
            db.execute(update(MailSend).where(MailSend.id == send_id, MailSend.status.in_(("queued", "scheduled"))).values(status="blocked", error=str(exc.detail)))
            db.commit()
            return False
        payload = _mime(command)
        claimed = db.execute(update(MailSend).where(MailSend.id == send_id, MailSend.status.in_(("queued", "scheduled"))).values(status="sending", started_at=now(), error=None))
        if not claimed.rowcount:
            db.rollback()
            return False
        db.commit()  # Once 'sending' is durable, an interruption is uncertain.
        try:
            result = client_for(mailbox, db).request("POST", "messages/send", json=payload)
            if not isinstance(result, dict) or not result.get("id"):
                raise ValueError("Provider did not acknowledge the send.")
            command.status, command.sent_at = "sent", now()
            command.gmail_message_id, command.gmail_thread_id = result["id"], result.get("threadId")
            command.error = None
            # Persist exactly what was sent; tests to self do not enter contact inbox.
            if command.mode != "test":
                snapshot = command.snapshot
                existing = db.scalar(repo.query(MailMessage).where(MailMessage.mailbox_id == mailbox.id, MailMessage.gmail_message_id == result["id"]))
                if not existing:
                    repo.add(MailMessage, mailbox_id=mailbox.id, gmail_message_id=result["id"], gmail_thread_id=result.get("threadId", result["id"]), contact_id=command.contact_id, contact_email=command.recipient_email, from_email=snapshot["mailbox_email"], to_emails=[command.recipient_email], subject=snapshot["subject"], snippet=snapshot["body_text"][:250], body_text=snapshot["body_text"], body_html=snapshot["body_html"], received_at=command.sent_at, direction="outgoing", is_unread=False, is_archived=True, labels=["SENT"], rfc_message_id=command.rfc_message_id, in_reply_to=snapshot.get("in_reply_to", ""), references=snapshot.get("references", ""), reply_to="", attachments=[], is_automated=False, content_synced=False)
            db.commit()
            return True
        except Exception as exc:
            # Gmail send has no provider idempotency guarantee. Network errors,
            # 408 and server failures may occur after acceptance; never requeue.
            failed_status = mailbox.status
            db.rollback()
            if failed_status == "reauth_required":
                mailbox.status = failed_status
                mailbox.access_token_encrypted = None
            command = db.get(MailSend, send_id)
            certain_rejection = isinstance(exc, HTTPException) and 400 <= exc.status_code < 500 and exc.status_code != 408 and not getattr(exc, "uncertain", False)
            command.status = "failed" if certain_rejection else "uncertain"
            command.error = ("Gmail rejected this send. " + _failure_reason(exc) + " Resolve the account or message issue and create a new reviewed request." if certain_rejection else "Gmail may have accepted this message. Check Gmail Sent before creating another send; this request will not be retried automatically.")
            _block_schedules(repo, mailbox, "An earlier send failed or has an uncertain outcome. Review Gmail Sent before resuming scheduled sends.")
            db.commit()
            return False


def update_send_status(repo, command, action):
    if action == "cancel":
        if command.status not in PENDING:
            raise HTTPException(409, "Only a pending send can be cancelled.")
        target, error = "cancelled", "Cancelled by the user."
    elif action == "pause":
        if command.status not in ("scheduled", "queued"):
            raise HTTPException(409, "Only a queued or scheduled send can be paused.")
        target, error = "paused", "Paused by the user."
    elif action == "resume":
        if command.status not in ("paused", "blocked") or command.mode != "schedule":
            raise HTTPException(409, "Only paused or blocked schedules can resume. Failed or uncertain sends require a new reviewed request.")
        mailbox = repo.get(Mailbox, command.mailbox_id)
        if mailbox.last_sync_error or not mailbox.last_sync_at or utc(mailbox.last_sync_at) < now() - timedelta(minutes=5):
            raise HTTPException(409, "Synchronize Gmail successfully before resuming this schedule.")
        snapshot = reviewed_snapshot(repo, mailbox, repo.get(Draft, command.draft_id), command.draft_revision, command.snapshot.get("reply_message_id"), attachments=command.snapshot.get("attachments"))
        if snapshot != command.snapshot:
            raise HTTPException(409, "The reviewed content changed. Cancel this schedule and create a new one.")
        target, error = "scheduled", None
    else:
        raise HTTPException(422, "Unknown send action.")
    changed = repo.session.execute(update(MailSend).where(MailSend.id == command.id, MailSend.workspace_id == repo.workspace_id, MailSend.status == command.status).values(status=target, error=error))
    if not changed.rowcount:
        raise HTTPException(409, "This send changed while the action was running. Refresh its status.")
    repo.session.flush()
    repo.session.refresh(command)
    _wake.set()
    return send_json(repo, command)


def disconnect_mailbox(repo, mailbox, delete_data=False):
    mailbox.status, mailbox.access_token_encrypted, mailbox.refresh_token_encrypted = "disconnected", None, None
    mailbox.token_expires_at, mailbox.sync_status = None, "idle"
    repo.session.execute(update(MailSend).where(MailSend.workspace_id == repo.workspace_id, MailSend.mailbox_id == mailbox.id, MailSend.status.in_(PENDING)).values(status="cancelled", error="Gmail account disconnected."))
    if delete_data:
        for model in (MailMessage, MailThreadState):
            repo.session.execute(delete(model).where(model.workspace_id == repo.workspace_id, model.mailbox_id == mailbox.id))
        mailbox.history_id, mailbox.contacts_fingerprint = None, ""
    return mailbox_json(mailbox)


def process_due_sends():
    with Session() as db:
        due = db.scalars(select(MailSend.id).where(MailSend.status == "scheduled", MailSend.scheduled_at <= now()).order_by(MailSend.scheduled_at).limit(100)).all()
    for send_id in due:
        process_send(send_id)


def recover_mail_sends():
    with Session() as db:
        affected = db.scalars(select(MailSend.mailbox_id).where(MailSend.status == "sending")).all()
        db.execute(update(MailSend).where(MailSend.status == "sending").values(status="uncertain", error="Server restarted during delivery. Check Gmail Sent; this request will never be retried automatically."))
        if affected:
            db.execute(update(MailSend).where(MailSend.mailbox_id.in_(affected), MailSend.status == "scheduled").values(status="blocked", error="A previous delivery has an uncertain outcome. Check Gmail Sent before resuming."))
        # A queued immediate command interrupted before its provider call requires
        # renewed review; schedules retain their explicitly approved future time.
        db.execute(update(MailSend).where(MailSend.status == "queued").values(status="blocked", error="Server restarted before sending. Review and create a new send request."))
        db.commit()


_worker = None
_worker_guard, _wake, _stop = Lock(), Event(), Event()


def _mail_loop():
    while not _stop.is_set():
        try:
            with Session() as db:
                ids = db.scalars(select(Mailbox.id).where(Mailbox.status == "connected")).all()
            for mailbox_id in ids:
                if _stop.is_set():
                    break
                with Session() as db:
                    mailbox = db.get(Mailbox, mailbox_id)
                    if not mailbox or not can_read(mailbox) or (mailbox.last_sync_at and utc(mailbox.last_sync_at) > now() - timedelta(seconds=settings.gmail_sync_interval_seconds) and not mailbox.last_sync_error):
                        continue
                    try:
                        sync_mailbox(WorkspaceRepository(db, mailbox.workspace_id), mailbox)
                    except Exception:
                        pass
            process_due_sends()
        except Exception:
            pass  # Database outages must not kill the persistent worker.
        _wake.wait(15)
        _wake.clear()


def start_mail_worker():
    global _worker
    if not settings.gmail_worker_enabled:
        return
    with _worker_guard:
        if _worker and _worker.is_alive():
            return
        recover_mail_sends()
        _stop.clear()
        _wake.clear()
        _worker = Thread(target=_mail_loop, name="gmail-sync-and-send", daemon=True)
        _worker.start()


def stop_mail_worker():
    _stop.set()
    _wake.set()
    if _worker:
        _worker.join(timeout=5)
