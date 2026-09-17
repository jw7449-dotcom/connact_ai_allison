"""Gmail mailbox authorization is independent of platform Google sign-in."""
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from ..db import Session, get_repo
from ..mail_models import Mailbox
from ..services import gmail
from .auth import COOKIE, digest, session_user

router = APIRouter(prefix="/mailboxes")


class ConnectInput(BaseModel):
    mode: Literal["send", "sync"] = "sync"


class DisconnectInput(BaseModel):
    delete_data: bool = True


@router.post("/connect")
def connect(body: ConnectInput, request: Request, response: Response, repo=Depends(get_repo)):
    user = session_user(repo.session, request)
    url, browser_token = gmail.begin(
        repo.session, repo.workspace_id, body.mode, user.id if user else None,
        digest(request.cookies[COOKIE]) if user else None,
    )
    response.set_cookie(gmail.OAUTH_COOKIE, browser_token, max_age=gmail.STATE_SECONDS,
                        httponly=True, secure=gmail.settings.public_origin.startswith("https://"),
                        samesite="lax", path=gmail.OAUTH_COOKIE_PATH)
    return {"authorization_url": url}


@router.get("/callback")
def callback(request: Request, state: str = "", code: str = "", error: str = ""):
    result = "connected"
    try:
        record = gmail.consume_state(state, request.cookies.get(gmail.OAUTH_COOKIE, ""))
        if error:
            raise gmail.GmailError(400, "gmail_consent_denied")
        with Session() as db:
            gmail.complete(db, record, code, request.cookies.get(COOKIE, ""))
            db.commit()
    except gmail.GmailError as exc:
        # Only stable local error codes may enter a URL; never provider text/tokens.
        result = str(exc.detail) if str(exc.detail).startswith("gmail_") else "gmail_connection_failed"
    except IntegrityError:
        result = "gmail_connection_failed"
    response = RedirectResponse("/mailboxes?gmail=" + result, status_code=303)
    response.delete_cookie(gmail.OAUTH_COOKIE, httponly=True,
                           secure=gmail.settings.public_origin.startswith("https://"),
                           samesite="lax", path=gmail.OAUTH_COOKIE_PATH)
    return response


@router.post("/{id}/disconnect")
def disconnect(id: str, body: DisconnectInput, repo=Depends(get_repo)):
    from ..services.mail import disconnect_mailbox
    mailbox = repo.get(Mailbox, id)
    repo.session.refresh(mailbox, with_for_update=True)
    disconnect_mailbox(repo, mailbox, body.delete_data)
    return {"status": "disconnected", "data_deleted": body.delete_data}
