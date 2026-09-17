"""Workspace-only mail, schedules and manual follow-up API."""
from urllib.parse import quote
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..db import get_repo
from ..models import Contact, now
from ..mail_models import Mailbox, MailMessage, MailSend, MailSuppression, MailTask, MailThreadState
from ..mail_schemas import SendInput, ConfirmInput, MailboxUpdate, MessageUpdate, ThreadUpdate, TaskInput, TaskUpdate, SuppressionInput
from ..services import gmail
from ..services.contacts import row
from ..services.drafts import sanitize
from ..services.mail import (mailbox_json, sync_mailbox, visible_messages, thread_json, modify_message, attachment_bytes, send_draft, send_preview, send_json, update_send_status, suppress)

router = APIRouter()


@router.get("/mailboxes")
def mailboxes(repo=Depends(get_repo)):
    return {"configured": gmail.configured(), "callback_uri": gmail.callback_uri(), "mailboxes": [mailbox_json(m) for m in sorted(repo.all(Mailbox), key=lambda m: m.email)]}


@router.post("/mailboxes/{id}/sync")
def sync(id: str, repo=Depends(get_repo)):
    return sync_mailbox(repo, repo.get(Mailbox, id))


@router.patch("/mailboxes/{id}")
def update_mailbox(id: str, body: MailboxUpdate, repo=Depends(get_repo)):
    mailbox = repo.get(Mailbox, id)
    start = body.send_window_start if body.send_window_start is not None else mailbox.send_window_start
    end = body.send_window_end if body.send_window_end is not None else mailbox.send_window_end
    if start >= end:
        raise HTTPException(422, "The sending window must end after it starts; use 0 to 24 for all day.")
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(mailbox, key, sanitize(value) if key == "signature_html" else value)
    repo.session.flush()
    return mailbox_json(mailbox)


@router.get("/mail/messages")
def messages(mailbox_id: str | None = None, folder: str = "inbox", unread: bool = False,
             limit: int = Query(default=200, ge=1, le=1000), offset: int = Query(default=0, ge=0),
             email: str | None = Query(default=None, max_length=254),
             domain: str | None = Query(default=None, max_length=253), pending_reply: bool = False,
             intent: Literal["none", "interested", "not_now", "not_interested"] | None = None,
             repo=Depends(get_repo)):
    return visible_messages(repo, mailbox_id, folder, unread, limit, email=email, domain=domain,
                            pending_reply=pending_reply, intent=intent, offset=offset)


@router.get("/mail/threads/{thread_id}")
def conversation(thread_id: str, mailbox_id: str, repo=Depends(get_repo)):
    return thread_json(repo, repo.get(Mailbox, mailbox_id), thread_id)


@router.patch("/mail/threads/{thread_id}")
def update_conversation(thread_id: str, mailbox_id: str, body: ThreadUpdate, repo=Depends(get_repo)):
    mailbox = repo.get(Mailbox, mailbox_id)
    visible = thread_json(repo, mailbox, thread_id)
    state = repo.session.scalar(repo.query(MailThreadState).where(MailThreadState.mailbox_id == mailbox.id, MailThreadState.gmail_thread_id == thread_id))
    if not state:
        state = repo.add(MailThreadState, mailbox_id=mailbox.id, gmail_thread_id=thread_id)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(state, key, value)
    if body.intent == "not_interested":
        latest = next((m for m in reversed(visible["messages"]) if m["direction"] == "incoming"), visible["messages"][-1])
        suppress(repo, repo.get(Contact, latest["contact_id"]), "rejection", "Marked not interested in the contact conversation.")
    repo.session.flush()
    return thread_json(repo, mailbox, thread_id)


@router.patch("/mail/messages/{id}")
def patch_message(id: str, body: MessageUpdate, repo=Depends(get_repo)):
    return modify_message(repo, repo.get(MailMessage, id), body)


@router.get("/mail/messages/{id}/attachments/{attachment_id}")
def download_attachment(id: str, attachment_id: str, repo=Depends(get_repo)):
    data, attachment = attachment_bytes(repo, repo.get(MailMessage, id), attachment_id)
    # Always download. Never render sender-controlled HTML/SVG in the app origin.
    return Response(data, media_type="application/octet-stream", headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(attachment["filename"], safe=""), "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})


@router.get("/mail/send-preview")
def preview_send(mailbox_id: str, draft_id: str, reply_message_id: str | None = None, mode: Literal["send", "test"] = "send", repo=Depends(get_repo)):
    return send_preview(repo, mailbox_id, draft_id, reply_message_id, mode)


@router.post("/mail/send")
def send(body: SendInput, repo=Depends(get_repo)):
    return send_draft(repo, body)


@router.get("/mail/sends")
def sends(repo=Depends(get_repo)):
    return [send_json(repo, command) for command in repo.session.scalars(repo.query(MailSend).order_by(MailSend.created_at.desc()).limit(500)).all()]


@router.post("/mail/sends/{id}/cancel")
def cancel_send(id: str, repo=Depends(get_repo)):
    return update_send_status(repo, repo.get(MailSend, id), "cancel")


@router.post("/mail/sends/{id}/pause")
def pause_send(id: str, repo=Depends(get_repo)):
    return update_send_status(repo, repo.get(MailSend, id), "pause")


@router.post("/mail/sends/{id}/resume")
def resume_send(id: str, body: ConfirmInput, repo=Depends(get_repo)):
    return update_send_status(repo, repo.get(MailSend, id), "resume")


def _require_task_contact(repo, contact_id):
    contact = repo.get(Contact, contact_id)
    if not contact.saved:
        raise HTTPException(422, "Follow-up tasks require a saved workspace contact.")
    return contact


@router.get("/mail/tasks")
def tasks(repo=Depends(get_repo)):
    contacts = {c.id for c in repo.all(Contact, Contact.saved.is_(True))}
    return [row(task) for task in sorted(repo.all(MailTask), key=lambda t: t.due_at) if task.contact_id in contacts]


@router.post("/mail/tasks", status_code=201)
def create_task(body: TaskInput, repo=Depends(get_repo)):
    _require_task_contact(repo, body.contact_id)
    if body.thread_id and not body.mailbox_id:
        raise HTTPException(422, "A conversation follow-up requires its Gmail account.")
    if body.mailbox_id:
        mailbox = repo.get(Mailbox, body.mailbox_id)
        if body.thread_id:
            thread = thread_json(repo, mailbox, body.thread_id)
            if not any(m["contact_id"] == body.contact_id for m in thread["messages"]):
                raise HTTPException(422, "The follow-up contact does not belong to this conversation.")
    task = repo.add(MailTask, **body.model_dump(), completed_at=now() if body.status == "completed" else None)
    return row(task)


@router.patch("/mail/tasks/{id}")
def update_task(id: str, body: TaskUpdate, repo=Depends(get_repo)):
    task = repo.get(MailTask, id)
    _require_task_contact(repo, task.contact_id)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(task, key, value)
    if body.status:
        task.completed_at = now() if body.status == "completed" else None
    repo.session.flush()
    return row(task)


@router.get("/mail/suppressions")
def suppressions(repo=Depends(get_repo)):
    return [row(s) for s in repo.all(MailSuppression)]


@router.post("/mail/suppressions", status_code=201)
def create_suppression(body: SuppressionInput, repo=Depends(get_repo)):
    return row(suppress(repo, repo.get(Contact, body.contact_id), body.reason, body.notes))


@router.delete("/mail/suppressions/{id}")
def remove_suppression(id: str, repo=Depends(get_repo)):
    repo.session.delete(repo.get(MailSuppression, id))
    return {"deleted": True, "note": "Blocked schedules remain blocked until explicitly reviewed and resumed."}
