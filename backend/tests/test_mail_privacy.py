"""Gmail inbox privacy contracts using a deliberately overbroad fake provider.

The provider fake returns personal mail and mixed threads even when a Gmail
query was supplied. Application authorization must never trust search matches.
"""
import base64
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import settings
from app.db import Session, WorkspaceRepository
from app.models import Contact, Workspace
from app.mail_models import Mailbox, MailMessage, MailThreadState


def gmail_message(message_id, sender, recipient="owner@gmail.com", *,
                  thread_id=None, labels=None, body="Message body", headers=None):
    values = {
        "From": sender,
        "To": recipient,
        "Subject": "A conversation",
        "Message-ID": f"<{message_id}@example.test>",
        "Date": "Sun, 13 Sep 2026 12:00:00 +0000",
        **(headers or {}),
    }
    return {
        "id": message_id,
        "threadId": thread_id or f"thread-{message_id}",
        "historyId": "100",
        "internalDate": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        "labelIds": ["INBOX", "UNREAD"] if labels is None else labels,
        "snippet": body,
        "payload": {
            "mimeType": "text/html",
            "headers": [{"name": key, "value": value} for key, value in values.items()],
            "body": {"data": base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")},
        },
    }


class ProviderMailbox:
    def __init__(self, messages):
        self.messages = {message["id"]: message for message in messages}
        self.calls = []
        self.history = {"historyId": "101", "history": []}

    def client(self, mailbox, db):
        provider = self

        class FakeGmailClient:
            def request(self, method, path, *, params=None, json=None):
                return provider.request(method, path, params=params, json=json)

            def profile(self):
                return provider.request("GET", "profile")

        return FakeGmailClient()

    def request(self, method, path, *, params=None, json=None):
        self.calls.append((method, path, params or {}, json))
        if path == "profile":
            return {"emailAddress": "owner@gmail.com", "historyId": "101"}
        if path == "messages":
            return {"messages": [{"id": key, "threadId": value["threadId"]}
                                 for key, value in self.messages.items()]}
        if path == "history":
            return self.history
        if path.startswith("messages/") and method == "GET":
            return self.messages[path.split("/")[1]]
        if path.startswith("threads/") and method == "GET":
            return {"id": path.split("/")[1], "messages": [
                message for message in self.messages.values()
                if message["threadId"] == path.split("/")[1]
            ]}
        if path.endswith("/modify"):
            return {}
        raise AssertionError(f"Unexpected provider operation {method} {path}")


@pytest.fixture
def mail_repo(monkeypatch, request):
    monkeypatch.setattr(settings, "gmail_worker_enabled", False)
    monkeypatch.setattr(settings, "gmail_token_encryption_keys", Fernet.generate_key().decode())
    request.getfixturevalue("client")
    with Session() as db:
        repo = WorkspaceRepository(db, settings.workspace_id)
        mailbox = repo.add(
            Mailbox, email="owner@gmail.com", status="connected",
            scopes=["https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/gmail.send"],
            sync_enabled=True,
        )
        contact = repo.add(Contact, name="Saved person", email="person@example.test", saved=True)
        db.commit()
        yield repo, mailbox, contact


def install_provider(monkeypatch, messages):
    from app.services import mail
    provider = ProviderMailbox(messages)
    monkeypatch.setattr(mail, "client_for", provider.client)
    return mail, provider


def test_sync_stores_only_exact_saved_contacts_per_message(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    repo.add(Contact, name="Search result only", email="candidate@example.test", saved=False)
    other_workspace = Workspace(id=str(uuid4()), name="Other workspace")
    repo.session.add(other_workspace)
    repo.session.flush()
    repo.session.add(Contact(workspace_id=other_workspace.id, name="Other workspace contact", email="elsewhere@example.test", saved=True))
    repo.session.commit()
    mail, provider = install_provider(monkeypatch, [
        gmail_message("saved-in", 'Saved Person <PERSON@EXAMPLE.TEST>', thread_id="shared-thread"),
        gmail_message("saved-out", "owner@gmail.com", "person@example.test", labels=["SENT"]),
        gmail_message("stranger-same-thread", "private@example.test", thread_id="shared-thread", body="Private personal body"),
        gmail_message("candidate", "candidate@example.test"),
        gmail_message("workspace-other", "elsewhere@example.test"),
        gmail_message("substring", "notperson@example.test"),
        gmail_message("suffix", "person@example.test.attacker.test"),
        gmail_message("spoofed-display", '"person@example.test" <stranger@example.test>'),
        gmail_message("cc-contact", "stranger@example.test", headers={"Cc": "person@example.test"}),
    ])
    mail.sync_mailbox(repo, mailbox)
    stored = repo.all(MailMessage)
    assert {message.gmail_message_id for message in stored} == {"saved-in", "saved-out"}
    assert all(message.contact_id == contact.id for message in stored)
    assert "Private personal body" not in str([message.body_html for message in stored])
    full_reads = {path.split("/")[1] for method, path, params, _ in provider.calls if path.startswith("messages/") and params.get("format") == "full"}
    assert full_reads == {"saved-in", "saved-out"}
    thread = mail.thread_json(repo, mailbox, "shared-thread")
    assert "saved-in" in str(thread)
    assert "stranger-same-thread" not in str(thread)
    assert "Private personal body" not in str(thread)


@pytest.mark.parametrize("change", ["unsave", "email", "delete", "workspace"])
def test_existing_cache_is_hidden_immediately_when_contact_access_changes(mail_repo, monkeypatch, change):
    from fastapi import HTTPException
    repo, mailbox, contact = mail_repo
    mail, _ = install_provider(monkeypatch, [gmail_message("saved-in", contact.email)])
    mail.sync_mailbox(repo, mailbox)
    assert len(mail.visible_messages(repo, mailbox_id=mailbox.id)) == 1
    if change == "unsave":
        contact.saved = False
    elif change == "email":
        contact.email = "changed@example.test"
    elif change == "delete":
        repo.session.delete(contact)
    else:
        other_workspace = Workspace(id=str(uuid4()), name="Another workspace")
        repo.session.add(other_workspace)
        repo.session.flush()
        contact.workspace_id = other_workspace.id
    repo.session.commit()
    assert mail.visible_messages(repo, mailbox_id=mailbox.id) == []
    with pytest.raises(HTTPException) as denied:
        mail.thread_json(repo, mailbox, "thread-saved-in")
    assert denied.value.status_code == 404


def test_provider_full_response_cannot_change_the_metadata_authorized_contact(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    mail, provider = install_provider(monkeypatch, [gmail_message("changed-body", contact.email)])
    original = provider.request
    def response(method, path, *, params=None, json=None):
        if path == "messages/changed-body" and (params or {}).get("format") == "full":
            return gmail_message("changed-body", "private@example.test", body="Never store this private body")
        return original(method, path, params=params, json=json)
    provider.request = response
    mail.sync_mailbox(repo, mailbox)
    assert repo.all(MailMessage) == []


def test_html_tracking_and_executable_content_are_removed(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    mail, _ = install_provider(monkeypatch, [gmail_message(
        "html", contact.email,
        body='<p>Readable <strong>message</strong></p><img src="https://tracker.example/pixel"><script>alert(1)</script><a href="javascript:alert(1)">bad link</a><iframe src="https://tracker.example/frame"></iframe>',
    )])
    mail.sync_mailbox(repo, mailbox)
    stored = repo.all(MailMessage)[0]
    assert "Readable" in stored.body_html
    assert "<script" not in stored.body_html
    assert "<iframe" not in stored.body_html
    assert "<img" not in stored.body_html
    assert "javascript:" not in stored.body_html


def test_two_mailboxes_keep_same_provider_ids_separate_and_workspace_reads_isolated(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    second = repo.add(Mailbox, email="second@gmail.com", scopes=mailbox.scopes, status="connected", sync_enabled=True)
    mail, provider = install_provider(monkeypatch, [gmail_message("same-id", contact.email)])
    mail.sync_mailbox(repo, mailbox)
    mail.sync_mailbox(repo, second)
    assert len(repo.all(MailMessage)) == 2
    other = Workspace(id=str(uuid4()), name="Private other workspace")
    repo.session.add(other)
    repo.session.flush()
    isolated = WorkspaceRepository(repo.session, other.id)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as denied:
        mail.visible_messages(isolated, mailbox_id=mailbox.id)
    assert denied.value.status_code == 404


@pytest.mark.parametrize("operation", ["sync", "modify", "attachment"])
def test_revoked_authorization_state_and_schedule_block_survive_operation_rollback(mail_repo, monkeypatch, operation):
    from fastapi import HTTPException
    from app.mail_schemas import MessageUpdate
    from app.mail_models import MailSend
    from test_mail_sync import scheduled_command
    repo, mailbox, contact = mail_repo
    mail, provider = install_provider(monkeypatch, [gmail_message("revocation-message", contact.email)])
    mail.sync_mailbox(repo, mailbox)
    message = repo.all(MailMessage)[0]
    message.attachments = [{"id": "test-attachment", "filename": "test.txt", "size": 4, "mime_type": "text/plain"}]
    command = scheduled_command(repo, mailbox, contact)
    repo.session.commit()
    mailbox_id, command_id = mailbox.id, command.id
    class Revoked:
        def __init__(self, connection, db):
            self.connection, self.db = connection, db
        def profile(self):
            return self.request("GET", "profile")
        def request(self, *args, **kwargs):
            self.connection.status = "reauth_required"
            self.connection.access_token_encrypted = None
            self.db.flush()
            raise HTTPException(401, "Gmail permission revoked")
    monkeypatch.setattr(mail, "client_for", lambda mailbox, db: Revoked(mailbox, db))
    with pytest.raises(HTTPException):
        if operation == "sync":
            mail.sync_mailbox(repo, mailbox)
        elif operation == "modify":
            mail.modify_message(repo, message, MessageUpdate(is_unread=False))
        else:
            mail.attachment_bytes(repo, message, "test-attachment")
    repo.session.rollback()  # Mirrors get_repo's failed-request dependency cleanup.
    with Session() as db:
        assert db.get(Mailbox, mailbox_id).status == "reauth_required"
        assert db.get(MailSend, command_id).status == "blocked"


def test_email_and_domain_filters_are_exact_and_do_not_infer_finance(mail_repo, monkeypatch, request):
    repo, mailbox, contact = mail_repo
    client = request.getfixturevalue("client")
    outside = repo.add(Contact, name="Outside domain", email="analyst@outside.test", saved=True)
    lookalike = repo.add(Contact, name="Domain lookalike", email="person@example.test.attacker.test", saved=True)
    repo.session.commit()
    mail, _ = install_provider(monkeypatch, [
        gmail_message("exact-address", contact.email),
        gmail_message("outside-domain", outside.email),
        gmail_message("lookalike-domain", lookalike.email),
    ])
    mail.sync_mailbox(repo, mailbox)
    response = client.get("/api/mail/messages", params={"email": " PERSON@EXAMPLE.TEST "})
    assert response.status_code == 200, response.text
    assert [item["gmail_message_id"] for item in response.json()] == ["exact-address"]
    response = client.get("/api/mail/messages", params={"domain": " EXAMPLE.TEST "})
    assert response.status_code == 200, response.text
    assert [item["gmail_message_id"] for item in response.json()] == ["exact-address"]
    assert [item["gmail_message_id"] for item in client.get("/api/mail/messages", params={"domain": "outside.test"}).json()] == ["outside-domain"]
    assert client.get("/api/mail/messages", params={"domain": "finance.example"}).json() == []
    assert client.get("/api/mail/messages", params={"email": "person"}).status_code == 422
    assert client.get("/api/mail/messages", params={"domain": "https://example.test"}).status_code == 422


def test_pagination_applies_after_privacy_and_orders_equal_timestamps_deterministically(mail_repo, monkeypatch, request):
    repo, mailbox, contact = mail_repo
    client = request.getfixturevalue("client")
    hidden = repo.add(Contact, name="Later edited contact", email="old@example.test", saved=True)
    repo.session.commit()
    clock = datetime.now(timezone.utc)
    messages = [gmail_message(f"visible-{i}", contact.email) for i in range(4)]
    for message in messages:
        message["internalDate"] = str(int(clock.timestamp() * 1000))
    for i in range(2):
        message = gmail_message(f"hidden-{i}", hidden.email)
        message["internalDate"] = str(int((clock + timedelta(hours=1)).timestamp() * 1000))
        messages.append(message)
    mail, _ = install_provider(monkeypatch, messages)
    mail.sync_mailbox(repo, mailbox)
    hidden.email = "changed@example.test"
    repo.session.commit()
    expected_ids = sorted([message.id for message in repo.all(MailMessage) if message.contact_id == contact.id], reverse=True)
    first = client.get("/api/mail/messages", params={"limit": 2, "offset": 0}).json()
    second = client.get("/api/mail/messages", params={"limit": 2, "offset": 2}).json()
    again = client.get("/api/mail/messages", params={"limit": 2, "offset": 0}).json()
    assert [item["id"] for item in first] == expected_ids[:2]
    assert [item["id"] for item in second] == expected_ids[2:]
    assert again == first
    assert len({item["id"] for item in first + second}) == 4
    assert client.get("/api/mail/messages", params={"offset": 4}).json() == []
    assert client.get("/api/mail/messages", params={"offset": -1}).status_code == 422


def test_pending_reply_uses_latest_visible_message_in_the_same_mailbox_thread(mail_repo, monkeypatch, request):
    repo, mailbox, contact = mail_repo
    client = request.getfixturevalue("client")
    hidden = repo.add(Contact, name="Removed participant", email="removed@example.test", saved=True)
    second_mailbox = repo.add(Mailbox, email="second@gmail.com", scopes=mailbox.scopes, sync_enabled=True)
    repo.session.commit()
    clock = datetime.now(timezone.utc)
    incoming = gmail_message("pending-in", contact.email, thread_id="pending-thread")
    hidden_out = gmail_message("hidden-out", mailbox.email, hidden.email, thread_id="pending-thread", labels=["SENT"])
    answered_in = gmail_message("answered-in", contact.email, thread_id="answered-thread")
    answered_out = gmail_message("answered-out", mailbox.email, contact.email, thread_id="answered-thread", labels=["SENT"])
    automated = gmail_message("automated-only", contact.email, headers={"Auto-Submitted": "auto-replied"})
    for message in (incoming, answered_in, automated):
        message["internalDate"] = str(int(clock.timestamp() * 1000))
    for message in (hidden_out, answered_out):
        message["internalDate"] = str(int((clock + timedelta(seconds=1)).timestamp() * 1000))
    mail, _ = install_provider(monkeypatch, [incoming, hidden_out, answered_in, answered_out, automated])
    mail.sync_mailbox(repo, mailbox)
    source = next(message for message in repo.all(MailMessage) if message.gmail_message_id == "answered-out")
    copy = {column.key: getattr(source, column.key) for column in MailMessage.__table__.columns if column.key not in ("id", "workspace_id")}
    copy.update(mailbox_id=second_mailbox.id, from_email=second_mailbox.email, gmail_message_id="other-mailbox-out", gmail_thread_id="pending-thread")
    repo.add(MailMessage, **copy)
    hidden.saved = False
    repo.session.commit()
    response = client.get("/api/mail/messages", params={"pending_reply": True})
    assert response.status_code == 200, response.text
    assert [item["gmail_message_id"] for item in response.json()] == ["pending-in"]
    unfiltered = client.get("/api/mail/messages", params={"pending_reply": False}).json()
    assert {item["gmail_message_id"] for item in unfiltered} == {"pending-in", "answered-in", "automated-only"}


def test_intent_filter_uses_workspace_thread_state_and_missing_state_is_none(mail_repo, monkeypatch, request):
    repo, mailbox, contact = mail_repo
    client = request.getfixturevalue("client")
    mail, _ = install_provider(monkeypatch, [gmail_message("interested", contact.email), gmail_message("unclassified", contact.email)])
    mail.sync_mailbox(repo, mailbox)
    repo.add(MailThreadState, mailbox_id=mailbox.id, gmail_thread_id="thread-interested", intent="interested")
    repo.session.commit()
    interested = client.get("/api/mail/messages", params={"intent": "interested"})
    assert interested.status_code == 200, interested.text
    assert [item["gmail_message_id"] for item in interested.json()] == ["interested"]
    none = client.get("/api/mail/messages", params={"intent": "none"})
    assert [item["gmail_message_id"] for item in none.json()] == ["unclassified"]
    assert client.get("/api/mail/messages", params={"intent": "finance"}).status_code == 422


@pytest.mark.parametrize("phase", ["metadata", "full"])
@pytest.mark.parametrize("change", ["email", "unsave"])
def test_contact_changed_in_another_session_mid_sync_cannot_persist_message(mail_repo, monkeypatch, phase, change):
    repo, mailbox, contact = mail_repo
    contact_id = contact.id
    mail, provider = install_provider(monkeypatch, [gmail_message("in-flight", contact.email)])
    original = provider.request
    changed = False
    def response(method, path, *, params=None, json=None):
        nonlocal changed
        if not changed and path == "messages/in-flight" and (params or {}).get("format") == phase:
            with Session() as concurrent:
                current = concurrent.get(Contact, contact_id)
                if change == "email":
                    current.email = "changed-during-sync@example.test"
                else:
                    current.saved = False
                concurrent.commit()
            changed = True
        return original(method, path, params=params, json=json)
    provider.request = response
    mail.sync_mailbox(repo, mailbox)
    assert changed
    assert repo.all(MailMessage) == []
    assert mail.visible_messages(repo, mailbox_id=mailbox.id) == []
    full_reads = [call for call in provider.calls if call[1] == "messages/in-flight" and call[2].get("format") == "full"]
    assert len(full_reads) == (0 if phase == "metadata" else 1)
