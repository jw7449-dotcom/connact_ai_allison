from html import escape

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy import select, update

from ..db import Session
from ..mail_models import MailSend, MailSuppression
from ..models import Workspace
from ..services.mail_unsubscribe import verify_token

router = APIRouter(prefix="/mail/unsubscribe")


def _page(title, content):
    return HTMLResponse('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title><body><main><h1>' + title + '</h1>' + content + '</main></body></html>', headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    })


@router.get("/{token}", response_class=HTMLResponse)
def confirm_unsubscribe(token: str):
    workspace_id, email = verify_token(token)
    with Session() as db:
        if not db.get(Workspace, workspace_id):
            raise HTTPException(404, "This sender workspace no longer exists.")
    return _page("Stop emails from this sender", '<p>Stop this Connact.ai workspace from sending further emails to <strong>' + escape(email) + '</strong>. Other senders and your Gmail account are unaffected.</p><form method="post"><button type="submit">Confirm unsubscribe</button></form>')


@router.post("/{token}", response_class=HTMLResponse)
def unsubscribe(token: str):
    workspace_id, email = verify_token(token)
    with Session() as db:
        # One workspace lock serializes duplicate clicks without global locking.
        workspace = db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
        if not workspace:
            raise HTTPException(404, "This sender workspace no longer exists.")
        item = db.scalar(select(MailSuppression).where(MailSuppression.workspace_id == workspace_id, MailSuppression.email == email))
        if item:
            item.reason = "unsubscribe"
        else:
            db.add(MailSuppression(workspace_id=workspace_id, email=email, reason="unsubscribe", notes="Recipient confirmed the unsubscribe link."))
        db.execute(update(MailSend).where(MailSend.workspace_id == workspace_id, MailSend.recipient_email == email,
                   MailSend.status.in_(("queued", "scheduled", "paused", "blocked")), MailSend.mode != "test")
                   .values(status="blocked", error="The recipient unsubscribed from this workspace."))
        db.commit()
    return _page("Unsubscribed", "<p>This sender's Connact.ai workspace will no longer send emails to " + escape(email) + ".</p>")
