"""Isolated browser-test API with real routes/database and an in-memory Gmail transport.

Run with backend/.venv/bin/python frontend/tests/mail-api-server.py. No real
credentials, user database, worker, or external Gmail requests are permitted.
"""
import base64
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))
sys.path.insert(0, str(root / "backend" / "tests"))
import conftest  # Installs blank credentials and a temporary SQLite database.

from app.main import app
from app.db import Base, Session, engine, WorkspaceRepository
from app.config import settings
from app.models import Workspace, Contact, Draft
from app.mail_models import Mailbox, MailMessage, MailThreadState, MailTask
from app.services import mail
from cryptography.fernet import Fernet

settings.public_origin = "http://127.0.0.1:3190"
settings.gmail_token_encryption_keys = Fernet.generate_key().decode()
deliveries = []
message_labels = {}


class GmailTestTransport:
    def profile(self):
        return {"emailAddress": "sender@example.test", "historyId": "101"}

    def request(self, method, path, **kwargs):
        if method == "POST" and path == "messages/send":
            deliveries.append(kwargs["json"])
            return {"id": f"test-delivery-{len(deliveries)}", "threadId": kwargs["json"].get("threadId", "new-thread")}
        if method == "POST" and path.endswith("/modify"):
            message_id = path.split("/")[1]
            labels = message_labels.setdefault(message_id, {"INBOX", "UNREAD"})
            labels.difference_update(kwargs["json"].get("removeLabelIds", []))
            labels.update(kwargs["json"].get("addLabelIds", []))
            return {"id": message_id, "labelIds": sorted(labels)}
        if method == "GET" and path in ("messages", "history"):
            return {"messages": [], "history": [], "historyId": "101"}
        if method == "GET" and "/attachments/" in path:
            return {"data": base64.urlsafe_b64encode(b"Contact attachment").decode()}
        raise AssertionError(f"Unimplemented test Gmail operation: {method} {path}")


mail.client_for = lambda *_args: GmailTestTransport()
Base.metadata.create_all(engine)
with Session() as session:
    session.add(Workspace(id=settings.workspace_id, name="Isolated mail browser test"))
    session.flush()
    repo = WorkspaceRepository(session)
    box = repo.add(Mailbox, id="test-mailbox", email="sender@example.test", display_name="Browser test", scopes=[mail.MODIFY_SCOPE], sync_enabled=True, last_sync_at=datetime.now(timezone.utc), signature_html="<p>Test signature</p>")
    contact = repo.add(Contact, id="test-contact", name="Saved Contact", email="contact@example.test", saved=True)
    hidden = repo.add(Contact, id="hidden-contact", name="Unsaved Person", email="hidden@example.test", saved=False)
    for person, message_id, text in [(contact, "visible-message", "A reply from the saved contact."), (hidden, "hidden-message", "PRIVATE UNSAVED MESSAGE")]:
        repo.add(MailMessage, id=message_id, mailbox_id=box.id, contact_id=person.id, contact_email=person.email, gmail_message_id=message_id, gmail_thread_id="shared-thread", from_email=person.email, to_emails=[box.email], subject="Original conversation", body_text=text, body_html='<img src="https://tracker.invalid/pixel"><script>alert(1)</script>', snippet=text, direction="incoming", is_unread=True, received_at=datetime.now(timezone.utc), rfc_message_id=f"<{message_id}@example.test>", attachments=[{"id": "test-attachment", "filename": "contact.txt", "size": 18, "mime_type": "text/plain"}] if person.saved else [])
    repo.add(Draft, id="test-draft", contact_id=contact.id, subject="Reviewed outreach", body_html="<p>Hello, saved contact.</p>", status="draft", revision=1)
    session.commit()


@app.get("/api/test-mail/deliveries")
def inspect_test_deliveries():
    from email import policy
    from email.parser import BytesParser
    result = []
    for delivery in deliveries:
        raw = delivery["raw"]
        message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        result.append({"to": str(message["To"]), "subject": str(message["Subject"]), "thread_id": delivery.get("threadId"), "in_reply_to": str(message["In-Reply-To"] or ""), "attachments": [part.get_filename() for part in message.iter_attachments()]})
    return result


@app.post("/api/test-mail/seed-pagination")
def seed_pagination():
    with Session() as session:
        repo = WorkspaceRepository(session)
        box = repo.add(Mailbox, id="pagination-mailbox", email="paging-sender@example.test", scopes=[mail.MODIFY_SCOPE], sync_enabled=True, last_sync_at=datetime.now(timezone.utc))
        contact = repo.add(Contact, id="pagination-contact", name="Pagination Contact", email="pages@pages.example.test", saved=True)
        other = repo.add(Contact, id="other-contact", name="Other Contact", email="other@other.example.test", saved=True)
        subdomain = repo.add(Contact, id="subdomain-contact", name="Subdomain Contact", email="sub@sub.pages.example.test", saved=True)
        stamp = datetime.now(timezone.utc)
        for index in range(202):
            repo.add(MailMessage, id=f"page-message-{index:03}", mailbox_id=box.id, contact_id=contact.id, contact_email=contact.email, gmail_message_id=f"page-message-{index}", gmail_thread_id="page-thread", from_email=contact.email, to_emails=[box.email], subject=f"Pagination message {index:03}", body_text=f"Saved contact page {index}", snippet=f"Saved contact page {index}", direction="incoming", received_at=stamp-timedelta(minutes=index), rfc_message_id=f"<page-{index}@example.test>")
        for person, name in [(other, "other"), (subdomain, "subdomain")]:
            repo.add(MailMessage, id=f"{name}-incoming", mailbox_id=box.id, contact_id=person.id, contact_email=person.email, gmail_message_id=f"{name}-incoming", gmail_thread_id=f"{name}-thread", from_email=person.email, to_emails=[box.email], subject=f"{name} incoming message", body_text=f"{name} incoming", snippet=f"{name} incoming", direction="incoming", received_at=stamp+timedelta(minutes=1))
        repo.add(MailMessage, id="other-outgoing", mailbox_id=box.id, contact_id=other.id, contact_email=other.email, gmail_message_id="other-outgoing", gmail_thread_id="other-thread", from_email=box.email, to_emails=[other.email], subject="Already answered", body_text="Sent answer", direction="outgoing", received_at=stamp+timedelta(minutes=2))
        repo.add(MailThreadState, mailbox_id=box.id, gmail_thread_id="page-thread", intent="interested")
        repo.add(MailTask, contact_id=contact.id, mailbox_id=box.id, thread_id="page-thread", title="Review the latest reply", due_at=stamp+timedelta(days=1), status="pending")
        session.commit()
    return {"seeded": 204}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18090, log_level="warning")
