import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser

import pytest
from fastapi import HTTPException

from app.config import settings
from app.mail_models import Mailbox, MailMessage, MailSend, MailSuppression, MailTask
from app.mail_schemas import SendInput
from app.models import Contact, Draft
from test_mail_privacy import gmail_message, install_provider, mail_repo
from test_mail_sync import scheduled_command


def ready_draft(repo, contact, **changes):
    draft = repo.add(Draft, contact_id=contact.id, subject="A conversation", body_html="<p>Reviewed content.</p>", status="ready", revision=1, **changes)
    repo.session.commit()
    return draft


def send_input(mailbox, draft, **changes):
    return SendInput(**{"mailbox_id": mailbox.id, "draft_id": draft.id, "revision": draft.revision, "confirmed": True, "idempotency_key": "reviewed-request-key", **changes})


def mock_sender(monkeypatch, outcome=None):
    from app.services import mail
    sent = []
    class Sender:
        def profile(self):
            return {"emailAddress": "owner@gmail.com", "historyId": "101"}

        def request(self, method, path, **kwargs):
            if method == "GET" and path in ("messages", "history"):
                return {"messages": [], "history": [], "historyId": "101"}
            if method == "GET" and path.startswith("threads/"):
                return {"messages": []}
            assert method == "POST" and path == "messages/send"
            sent.append(kwargs["json"])
            if isinstance(outcome, Exception):
                raise outcome
            return {"id": f"provider-message-{len(sent)}", "threadId": "provider-thread"} if outcome is None else outcome
    monkeypatch.setattr(mail, "client_for", lambda *args: Sender())
    return mail, sent


def decoded_send(payload):
    encoded = payload["raw"]
    return BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))


def test_reviewed_send_is_idempotent_and_provider_acknowledgment_is_preserved(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    draft = ready_draft(repo, contact)
    mail, sent = mock_sender(monkeypatch)
    body = send_input(mailbox, draft)
    first = mail.send_draft(repo, body)
    assert first["status"] == "sent" and first["gmail_message_id"] == "provider-message-1"
    second = mail.send_draft(repo, body)
    assert second["id"] == first["id"]
    assert len(sent) == 1
    assert len(repo.all(MailSend)) == 1
    message = decoded_send(sent[0])
    assert message["To"] == contact.email and message["From"] == mailbox.email
    assert "Reviewed content." in message.get_body(preferencelist=("plain",)).get_content()
    with pytest.raises(HTTPException) as conflict:
        mail.send_draft(repo, body.model_copy(update={"mode": "test"}))
    assert conflict.value.status_code == 409
    assert len(sent) == 1


@pytest.mark.parametrize("outcome", [HTTPException(502, "Response timeout"), HTTPException(408, "Request timeout"), {}])
def test_uncertain_send_is_never_retried_by_duplicate_click_or_worker(mail_repo, monkeypatch, outcome):
    repo, mailbox, contact = mail_repo
    draft = ready_draft(repo, contact)
    mail, sent = mock_sender(monkeypatch, outcome)
    body = send_input(mailbox, draft)
    first = mail.send_draft(repo, body)
    assert first["status"] == "uncertain"
    assert mail.send_draft(repo, body)["id"] == first["id"]
    assert mail.process_send(first["id"]) is False
    mail.process_due_sends()
    assert len(sent) == 1
    assert repo.all(MailMessage) == []


def test_test_send_is_to_selected_sender_and_not_formal_contact_delivery(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    draft = ready_draft(repo, contact)
    mail, sent = mock_sender(monkeypatch)
    result = mail.send_draft(repo, send_input(mailbox, draft, mode="test"))
    assert result["status"] == "sent" and result["mode"] == "test"
    assert result["recipient_email"] == mailbox.email
    message = decoded_send(sent[0])
    assert message["To"] == mailbox.email
    assert message["Subject"].startswith("[Test]")
    assert repo.all(MailMessage) == []


@pytest.mark.parametrize("change", ["revision", "contact_email", "saved", "sender", "suppression"])
def test_scheduled_send_rechecks_review_snapshot_before_provider_write(mail_repo, monkeypatch, change):
    repo, mailbox, contact = mail_repo
    draft = ready_draft(repo, contact)
    mailbox.last_sync_at = datetime.now(timezone.utc)
    repo.session.commit()
    mail, sent = mock_sender(monkeypatch)
    body = send_input(mailbox, draft, mode="schedule", scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1))
    result = mail.send_draft(repo, body)
    command = repo.get(MailSend, result["id"])
    command.scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    if change == "revision":
        draft.revision += 1
        draft.body_html = "<p>Changed without another review.</p>"
    elif change == "contact_email":
        contact.email = "changed@example.test"
    elif change == "saved":
        contact.saved = False
    elif change == "sender":
        mailbox.email = "changed-sender@gmail.com"
    else:
        repo.add(MailSuppression, email=contact.email, reason="manual", contact_id=contact.id)
    repo.session.commit()
    mail.process_due_sends()
    repo.session.expire_all()
    assert repo.get(MailSend, result["id"]).status == "blocked"
    assert sent == []


def test_manual_followup_expiry_never_creates_or_sends_mail(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    task = repo.add(MailTask, contact_id=contact.id, mailbox_id=mailbox.id, title="Follow up manually", due_at=datetime.now(timezone.utc) - timedelta(days=2), status="pending")
    repo.session.commit()
    mail, sent = mock_sender(monkeypatch)
    mail.process_due_sends()
    mail.recover_mail_sends()
    repo.session.refresh(task)
    assert task.status == "pending"
    assert repo.all(MailSend) == []
    assert sent == []


def test_new_manual_reply_pauses_contact_schedules_across_mailboxes(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    second = repo.add(Mailbox, email="second@gmail.com", scopes=mailbox.scopes, sync_enabled=True)
    one = scheduled_command(repo, mailbox, contact, key="first-mailbox-schedule")
    two = scheduled_command(repo, second, contact, key="second-mailbox-schedule")
    repo.session.commit()
    reply = gmail_message("new-manual-reply", contact.email)
    reply["internalDate"] = str(int((datetime.now(timezone.utc) + timedelta(seconds=1)).timestamp() * 1000))
    mail, _ = install_provider(monkeypatch, [reply])
    mail.sync_mailbox(repo, mailbox)
    repo.session.refresh(one)
    repo.session.refresh(two)
    assert one.status == "paused"
    assert two.status == "paused"


def test_auto_reply_is_not_counted_as_manual_response(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    command = scheduled_command(repo, mailbox, contact)
    repo.session.commit()
    reply = gmail_message("automatic-reply", contact.email, headers={"Auto-Submitted": "auto-replied"})
    reply["internalDate"] = str(int((datetime.now(timezone.utc) + timedelta(seconds=1)).timestamp() * 1000))
    mail, _ = install_provider(monkeypatch, [reply])
    mail.sync_mailbox(repo, mailbox)
    assert repo.all(MailMessage)[0].is_automated
    repo.session.refresh(command)
    assert command.status == "paused"  # Protective pause does not classify the message as manual.


def test_original_thread_reply_has_matching_gmail_and_rfc_headers(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    mail, _ = install_provider(monkeypatch, [gmail_message("original", contact.email, thread_id="original-thread", headers={"References": "<ancestor@example.test>"})])
    mail.sync_mailbox(repo, mailbox)
    original = repo.all(MailMessage)[0]
    draft = ready_draft(repo, contact)
    mail, sent = mock_sender(monkeypatch)
    result = mail.send_draft(repo, send_input(mailbox, draft, reply_message_id=original.id))
    assert result["status"] == "sent"
    assert sent[0]["threadId"] == "original-thread"
    message = decoded_send(sent[0])
    assert message["In-Reply-To"] == "<original@example.test>"
    assert message["References"] == "<ancestor@example.test> <original@example.test>"
    assert message["Subject"] == original.subject


@pytest.mark.parametrize("change", ["mailbox", "contact", "reply_to", "subject"])
def test_reply_cannot_cross_original_mailbox_contact_or_redirect_address(mail_repo, monkeypatch, change):
    repo, mailbox, contact = mail_repo
    mail, _ = install_provider(monkeypatch, [gmail_message("original", contact.email)])
    mail.sync_mailbox(repo, mailbox)
    original = repo.all(MailMessage)[0]
    draft = ready_draft(repo, contact)
    if change == "mailbox":
        mailbox = repo.add(Mailbox, email="different@gmail.com", scopes=mailbox.scopes, sync_enabled=True)
    elif change == "contact":
        different = repo.add(Contact, name="Different recipient", email="different@example.test", saved=True)
        draft.contact_id = different.id
    elif change == "reply_to":
        original.reply_to = "different@example.test"
    else:
        draft.subject = "Unrelated subject"
    repo.session.commit()
    mail, sent = mock_sender(monkeypatch)
    with pytest.raises(HTTPException) as rejected:
        mail.send_draft(repo, send_input(mailbox, draft, reply_message_id=original.id))
    assert rejected.value.status_code == 422
    assert sent == []


def test_two_workers_claim_the_same_scheduled_delivery_only_once(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    draft = ready_draft(repo, contact)
    mailbox.last_sync_at = datetime.now(timezone.utc)
    repo.session.commit()
    mail, sent = mock_sender(monkeypatch)
    result = mail.send_draft(repo, send_input(mailbox, draft, mode="schedule", scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    command = repo.get(MailSend, result["id"])
    command.scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    repo.session.commit()
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(mail.process_send, [command.id, command.id]))
    repo.session.expire_all()
    assert repo.get(MailSend, command.id).status == "sent"
    assert len(sent) == 1


def test_daily_limit_prevents_an_additional_provider_call(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    draft = ready_draft(repo, contact)
    monkeypatch.setattr(settings, "gmail_daily_send_limit", 1)
    mail, sent = mock_sender(monkeypatch)
    first = mail.send_draft(repo, send_input(mailbox, draft))
    assert first["status"] == "sent"
    second = mail.send_draft(repo, send_input(mailbox, draft, idempotency_key="another-reviewed-request"))
    assert second["status"] == "blocked"
    assert "limit" in second["error"]
    assert len(sent) == 1


def test_verified_permanent_bounce_suppresses_contact_without_exposing_daemon_mail(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    mail, provider = install_provider(monkeypatch, [])
    mail.sync_mailbox(repo, mailbox)
    sent_command = scheduled_command(repo, mailbox, contact, key="accepted-earlier-send")
    sent_command.status = "sent"
    pending = scheduled_command(repo, mailbox, contact, key="later-followup-schedule")
    repo.session.commit()
    dsn = gmail_message("verified-dsn", "mailer-daemon@googlemail.com", headers={
        "Content-Type": "multipart/report; report-type=delivery-status",
        "In-Reply-To": sent_command.rfc_message_id,
    })
    dsn["payload"]["mimeType"] = "multipart/report"
    dsn["payload"]["parts"] = [{"mimeType": "message/delivery-status", "body": {"data": base64.urlsafe_b64encode(f"Final-Recipient: rfc822; {contact.email}\r\nAction: failed\r\nStatus: 5.1.1\r\n".encode()).decode()}}]
    provider.messages["verified-dsn"] = dsn
    provider.history = {"historyId": "102", "history": [{"id": "102", "messagesAdded": [{"message": {"id": "verified-dsn"}}]}]}
    mail.sync_mailbox(repo, mailbox)
    suppression = repo.all(MailSuppression)
    assert len(suppression) == 1 and suppression[0].reason == "hard_bounce"
    assert suppression[0].email == contact.email
    repo.session.refresh(pending)
    assert pending.status == "blocked"
    assert repo.all(MailMessage) == []
