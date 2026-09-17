import base64
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.config import settings
from app.db import WorkspaceRepository
from app.mail_models import Mailbox, MailMessage, MailSend, MailSuppression
from app.models import Contact, Workspace
from app.services.mail_attachments import freeze_attachments, MAX_BYTES
from app.services.mail_unsubscribe import unsubscribe_url
from test_mail_delivery import decoded_send, mock_sender, ready_draft, send_input
from test_mail_privacy import gmail_message, install_provider, mail_repo
from test_mail_sync import scheduled_command


@pytest.mark.parametrize("filename", ["../secret.txt", "/etc/passwd", "dir\\secret.txt", "mail\r\nBcc: victim@example.test", "\x00hidden", ".", "..", " "])
def test_attachment_names_cannot_be_paths_or_inject_headers(filename):
    with pytest.raises(HTTPException) as invalid:
        freeze_attachments([{"filename": filename, "content_base64": "dGVzdA=="}])
    assert invalid.value.status_code == 422


@pytest.mark.parametrize("encoded", ["not base64!", "data:text/plain;base64,dGVzdA==", "", "dGVzdA==\n"])
def test_attachment_bytes_must_be_explicit_nonempty_strict_base64(encoded):
    with pytest.raises(HTTPException) as invalid:
        freeze_attachments([{"filename": "test.txt", "content_base64": encoded}])
    assert invalid.value.status_code == 422


def test_attachment_total_limit_applies_across_files_and_count():
    chunk = base64.b64encode(b"x" * (MAX_BYTES // 2 + 1)).decode()
    with pytest.raises(HTTPException) as large:
        freeze_attachments([{"filename": "first.bin", "content_base64": chunk}, {"filename": "second.bin", "content_base64": chunk}])
    assert large.value.status_code == 413
    with pytest.raises(HTTPException) as many:
        freeze_attachments([{"filename": f"part-{i}.txt", "content_base64": "dGVzdA=="} for i in range(6)])
    assert many.value.status_code == 422


def test_selected_attachment_bytes_and_filename_are_frozen_and_preserved_in_mime(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    draft = ready_draft(repo, contact)
    attachment = {"filename": "résumé.pdf", "content_base64": base64.b64encode(b"%PDF-test-fixture\x00\xff").decode()}
    mail, sent = mock_sender(monkeypatch)
    result = mail.send_draft(repo, send_input(mailbox, draft, attachments=[attachment]))
    assert result["status"] == "sent"
    mime = decoded_send(sent[0])
    parts = list(mime.iter_attachments())
    assert len(parts) == 1
    assert parts[0].get_filename() == "résumé.pdf"
    assert parts[0].get_payload(decode=True) == b"%PDF-test-fixture\x00\xff"
    command = repo.get(MailSend, result["id"])
    assert command.snapshot["attachments"][0]["size"] == len(b"%PDF-test-fixture\x00\xff")


def test_unsubscribe_get_is_readonly_post_is_idempotent_scoped_and_survives_contact_edit(mail_repo, request, monkeypatch):
    repo, mailbox, contact = mail_repo
    client = request.getfixturevalue("client")
    second = repo.add(Mailbox, email="second@gmail.com", scopes=mailbox.scopes, sync_enabled=True)
    first_command = scheduled_command(repo, mailbox, contact, key="unsubscribe-first")
    second_command = scheduled_command(repo, second, contact, key="unsubscribe-second")
    other_workspace = Workspace(id=str(uuid4()), name="Unaffected workspace")
    repo.session.add(other_workspace)
    repo.session.flush()
    other = WorkspaceRepository(repo.session, other_workspace.id)
    other_mailbox = other.add(Mailbox, email="third@gmail.com", scopes=mailbox.scopes, sync_enabled=True)
    other_contact = other.add(Contact, name="Same address elsewhere", email=contact.email, saved=True)
    other_command = scheduled_command(other, other_mailbox, other_contact, key="other-workspace-schedule")
    old_email = contact.email
    path = urlsplit(unsubscribe_url(repo.workspace_id, old_email)).path
    contact.email = "edited-contact@example.test"
    repo.session.commit()
    monkeypatch.setattr(settings, "auth_mode", "open")  # Recipient needs no platform login.
    response = client.get(path)
    assert response.status_code == 200 and old_email in response.text
    assert response.headers["referrer-policy"] == "no-referrer"
    assert repo.all(MailSuppression) == []
    assert client.post(path).status_code == 200
    assert client.post(path).status_code == 200
    repo.session.expire_all()
    suppression = repo.all(MailSuppression)
    assert len(suppression) == 1 and suppression[0].email == old_email
    assert suppression[0].reason == "unsubscribe"
    assert repo.get(MailSend, first_command.id).status == "blocked"
    assert repo.get(MailSend, second_command.id).status == "blocked"
    assert other.get(MailSend, other_command.id).status == "scheduled"
    assert other.all(MailSuppression) == []


def test_tampered_unsubscribe_token_cannot_suppress_anyone(mail_repo, request):
    repo, mailbox, contact = mail_repo
    client = request.getfixturevalue("client")
    path = urlsplit(unsubscribe_url(repo.workspace_id, contact.email)).path
    tampered = path[:-1] + ("0" if path[-1] != "0" else "1")
    assert client.get(tampered).status_code == 404
    assert client.post(tampered).status_code == 404
    assert repo.all(MailSuppression) == []


def test_first_sync_refreshes_sent_attachment_ids_once_then_uses_metadata(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    draft = ready_draft(repo, contact)
    attachment = {"filename": "reviewed.txt", "content_base64": base64.b64encode(b"attachment bytes").decode()}
    mail, sent = mock_sender(monkeypatch)
    result = mail.send_draft(repo, send_input(mailbox, draft, attachments=[attachment]))
    message = repo.all(MailMessage)[0]
    assert not message.content_synced
    full = gmail_message(result["gmail_message_id"], mailbox.email, contact.email, thread_id=result["gmail_thread_id"], labels=["SENT"])
    full["payload"]["parts"] = [{"mimeType": "text/plain", "filename": "reviewed.txt", "body": {"attachmentId": "gmail-attachment-id", "size": len(b"attachment bytes")}}]
    mail, provider = install_provider(monkeypatch, [full])
    mail.sync_mailbox(repo, mailbox)
    repo.session.refresh(message)
    assert message.content_synced
    assert message.attachments[0]["id"] == "gmail-attachment-id"
    assert message.attachments[0]["filename"] == "reviewed.txt"
    first_full_reads = len([call for call in provider.calls if call[2].get("format") == "full"])
    assert first_full_reads == 1
    provider.history = {"historyId": "102", "history": [{"id": "102", "labelsAdded": [{"message": {"id": result["gmail_message_id"]}}]}]}
    mail.sync_mailbox(repo, mailbox)
    assert len([call for call in provider.calls if call[2].get("format") == "full"]) == first_full_reads
