from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.mail_models import MailMessage, MailSend
from test_mail_privacy import gmail_message, install_provider, mail_repo


def scheduled_command(repo, mailbox, contact, *, key="existing-schedule"):
    return repo.add(
        MailSend, mailbox_id=mailbox.id, draft_id="schedule-draft", draft_revision=1,
        contact_id=contact.id, recipient_email=contact.email, idempotency_key=key,
        request_hash="test-hash", mode="schedule", status="scheduled", subject="A conversation",
        snapshot={}, scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
        rfc_message_id=f"<{key}@example.test>",
    )


def test_full_and_history_sync_paginate_and_deduplicate_without_losing_label_updates(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    messages = [gmail_message(f"message-{i}", contact.email) for i in range(3)]
    mail, provider = install_provider(monkeypatch, messages)
    original = provider.request
    history_pages = []
    def response(method, path, *, params=None, json=None):
        params = params or {}
        if path == "messages":
            provider.calls.append((method, path, params, json))
            if params.get("pageToken") == "full-page-2":
                return {"messages": [{"id": "message-1"}, {"id": "message-0"}]}
            return {"messages": [{"id": "message-0"}], "nextPageToken": "full-page-2"}
        if path == "history":
            history_pages.append(params)
            if params.get("pageToken") == "history-page-2":
                return {"historyId": "300", "history": [{"id": "251", "messagesAdded": [{"message": {"id": "message-2"}}], "labelsRemoved": [{"message": {"id": "message-0"}}]}]}
            return {"historyId": "250", "nextPageToken": "history-page-2", "history": [{"id": "210", "messages": [{"id": "message-2"}], "messagesAdded": [{"message": {"id": "message-2"}}]}]}
        return original(method, path, params=params, json=json)
    provider.request = response
    first = mail.sync_mailbox(repo, mailbox)
    assert first["imported"] == 2
    assert mailbox.history_id == "101"  # Profile was captured before full pagination.
    provider.messages["message-0"]["labelIds"] = []
    second = mail.sync_mailbox(repo, mailbox)
    assert second["imported"] == 1
    assert mailbox.history_id == "300"
    assert len(repo.all(MailMessage)) == 3
    assert history_pages == [{"startHistoryId": "101", "maxResults": 500}, {"startHistoryId": "101", "maxResults": 500, "pageToken": "history-page-2"}]
    archived = next(message for message in repo.all(MailMessage) if message.gmail_message_id == "message-0")
    assert archived.is_archived and not archived.is_unread


def test_expired_history_recovers_recent_mail_and_retains_old_tracked_threads(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    mail, provider = install_provider(monkeypatch, [gmail_message("old-in", contact.email, thread_id="old-thread")])
    mail.sync_mailbox(repo, mailbox)
    provider.messages["old-thread-reply"] = gmail_message("old-thread-reply", contact.email, thread_id="old-thread")
    provider.messages["new-in"] = gmail_message("new-in", contact.email)
    original = provider.request
    def response(method, path, *, params=None, json=None):
        if path == "history":
            raise HTTPException(404, "Expired Gmail history")
        if path == "messages":
            provider.calls.append((method, path, params or {}, json))
            return {"messages": [{"id": "new-in"}]}
        return original(method, path, params=params, json=json)
    provider.request = response
    result = mail.sync_mailbox(repo, mailbox)
    assert result["status"] == "synced"
    assert {message.gmail_message_id for message in repo.all(MailMessage)} == {"old-in", "old-thread-reply", "new-in"}
    assert any(path == "threads/old-thread" for _, path, _, _ in provider.calls)


def test_failed_second_history_page_does_not_advance_cursor_and_blocks_schedules(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    mail, provider = install_provider(monkeypatch, [gmail_message("initial", contact.email)])
    mail.sync_mailbox(repo, mailbox)
    command = scheduled_command(repo, mailbox, contact)
    repo.session.commit()
    original_cursor = mailbox.history_id
    original = provider.request
    def response(method, path, *, params=None, json=None):
        if path == "history":
            if (params or {}).get("pageToken"):
                raise HTTPException(503, "Temporary provider failure")
            return {"historyId": "999", "history": [], "nextPageToken": "fails"}
        return original(method, path, params=params, json=json)
    provider.request = response
    with pytest.raises(HTTPException):
        mail.sync_mailbox(repo, mailbox)
    repo.session.refresh(mailbox)
    repo.session.refresh(command)
    assert mailbox.history_id == original_cursor
    assert mailbox.sync_status == "failed" and mailbox.last_sync_error
    assert command.status == "blocked"


def test_repeating_page_tokens_fail_visibly_instead_of_looping(mail_repo, monkeypatch):
    repo, mailbox, contact = mail_repo
    mail, provider = install_provider(monkeypatch, [])
    original = provider.request
    def response(method, path, *, params=None, json=None):
        if path == "messages":
            return {"messages": [], "nextPageToken": "same-token"}
        return original(method, path, params=params, json=json)
    provider.request = response
    with pytest.raises(HTTPException) as failed:
        mail.sync_mailbox(repo, mailbox)
    assert failed.value.status_code == 502
    assert mailbox.history_id is None
    assert mailbox.last_sync_error
