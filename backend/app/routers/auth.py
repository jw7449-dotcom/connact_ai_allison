import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ..config import settings
from ..db import Session
from ..models import Workspace
from ..auth_models import User, LoginSession, Invitation, GoogleIdentity
from ..services import google_oauth

router = APIRouter(prefix="/auth")
COOKIE = "connact_session"
_attempts = defaultdict(deque)
_lock = threading.Lock()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ":" + value


def check_password(password, hashed):
    if ":" not in hashed:
        # Federated-only accounts have a non-password sentinel in this column.
        password_hash(password, "00" * 16)
        return False
    return hmac.compare_digest(password_hash(password, hashed.split(":")[0]), hashed)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def session_user(db, request):
    token = request.cookies.get(COOKIE, "")
    if not token:
        return None
    session = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token)))
    if not session or utc(session.expires_at) <= datetime.now(timezone.utc):
        return None
    return db.get(User, session.user_id)


def workspace_for_request(db, request):
    if settings.auth_mode == "local":
        return settings.workspace_id
    user = session_user(db, request)
    if not user:
        raise HTTPException(401, "Please sign in to your workspace.")
    return user.workspace_id


class LoginCredentials(BaseModel):
    email: str = Field(min_length=3, max_length=250)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def normalized_login(cls, value):
        return value.strip().lower()


class Credentials(LoginCredentials):
    email: str = Field(min_length=3, max_length=250)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalized(cls, value):
        value = value.strip().lower()
        if "@" not in value or any(c.isspace() for c in value):
            raise ValueError("Enter a valid email address.")
        return value


class Join(Credentials):
    invitation: str = Field(default="", max_length=200)


class GoogleStart(BaseModel):
    next: str = Field(default="/finance", max_length=2000)
    invitation: str = Field(default="", max_length=200)


class GoogleAdminLink(BaseModel):
    email: str = Field(min_length=3, max_length=250)

    @field_validator("email")
    @classmethod
    def normalized(cls, value):
        value = value.strip().lower()
        if value.count("@") != 1 or any(c.isspace() or ord(c) < 32 for c in value):
            raise ValueError("Enter the Google account email to link.")
        local, domain = value.split("@")
        if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("Enter the Google account email to link.")
        return value


def throttle(email, identity_limit=10):
    # Single-process invitation pilot. A shared limiter is required for replicas.
    with _lock:
        clock = time.monotonic()
        for key in ("global", digest(email)):
            q = _attempts[key]
            while q and q[0] < clock - 900:
                q.popleft()
            if len(q) >= (100 if key == "global" else identity_limit):
                raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.")
        _attempts["global"].append(clock)
        _attempts[digest(email)].append(clock)


def login_cookie(db, user, response):
    user.last_login_at = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=digest(token), user_id=user.id,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_days)))
    response.set_cookie(COOKIE, token, max_age=settings.session_days * 86400,
                        httponly=True, secure=settings.public_origin.startswith("https://"),
                        samesite="strict", path="/")


@router.get("/session")
def session(request: Request):
    provider = {"provider": settings.auth_provider, "google_configured": google_oauth.configured()}
    if settings.auth_mode == "local":
        return {**provider, "mode": "local", "authenticated": True, "email": None, "workspace_id": settings.workspace_id, "is_admin": False, "google_linked": False}
    with Session() as db:
        user = session_user(db, request)
        return {**provider, "mode": settings.auth_mode, "authenticated": bool(user),
                "email": user.email if user else None, "workspace_id": user.workspace_id if user else None,
                "is_admin": bool(user and user.is_admin),
                "google_linked": bool(user and db.scalar(select(GoogleIdentity.id).where(GoogleIdentity.user_id == user.id)))}


@router.post("/login")
def login(body: LoginCredentials, request: Request, response: Response):
    if settings.auth_provider == "google":
        raise HTTPException(409, "Use Continue with Google to sign in.")
    if settings.auth_mode == "local":
        raise HTTPException(409, "Sign-in is disabled in local mode.")
    throttle(body.email)
    with Session() as db:
        user = db.scalar(select(User).where(User.email == body.email))
        # Run the same expensive operation for an unknown account.
        hashed = user.password_hash if user else password_hash("unused-password", "00" * 16)
        valid = check_password(body.password, hashed)
        if not user or not valid:
            raise HTTPException(401, "Email or password is incorrect.")
        login_cookie(db, user, response)
        db.commit()
        return {"authenticated": True, "email": user.email, "workspace_id": user.workspace_id}


@router.post("/join")
def join(body: Join, response: Response):
    if settings.auth_provider == "google":
        raise HTTPException(409, "Use Continue with Google to create your account.")
    if settings.auth_mode == "local":
        raise HTTPException(409, "Registration is disabled in local mode.")
    throttle(body.email)
    with Session() as db:
        invitation = None
        if settings.auth_mode == "invite":
            invitation = db.scalar(select(Invitation).where(Invitation.token_hash == digest(body.invitation)).with_for_update())
            if (not invitation or invitation.used_at or invitation.use_count >= invitation.max_uses
                    or utc(invitation.expires_at) <= datetime.now(timezone.utc)
                    or (invitation.email and invitation.email != body.email)):
                raise HTTPException(400, "The invitation is invalid, expired, fully used, or belongs to another email.")
        workspace = Workspace(id=str(uuid4()), name="Personal workspace")
        db.add(workspace)
        db.flush()
        user = User(email=body.email, password_hash=password_hash(body.password), workspace_id=workspace.id)
        db.add(user)
        try:
            db.flush()
            # The invitation row remains locked until this account and its usage commit.
            # Failed or duplicate registrations roll back without consuming a place.
            if invitation:
                invitation.use_count += 1
                if invitation.use_count >= invitation.max_uses:
                    invitation.used_at = datetime.now(timezone.utc)
            login_cookie(db, user, response)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "An account already exists. Sign in instead.")
        return {"authenticated": True, "email": user.email, "workspace_id": user.workspace_id}


def begin_google(request, next_path, invitation=""):
    if settings.auth_mode == "local" or settings.auth_provider != "google":
        raise HTTPException(409, "Google sign-in is not enabled.")
    if not google_oauth.configured():
        raise HTTPException(503, "Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
    # Google has not authenticated an email yet. Apply the pilot's global limit;
    # the reverse proxy's shared IP must not impose a 10-attempt limit on all users.
    throttle("google", identity_limit=100)
    with Session() as db:
        user = session_user(db, request)
        return google_oauth.begin(db, next_path, invitation, user.id if user else None)


@router.get("/google/start")
def google_start(request: Request, next: str = "/finance"):
    url, browser_token = begin_google(request, next)
    response = RedirectResponse(url, status_code=302)
    google_oauth.set_state_cookie(response, browser_token)
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.post("/google/start")
def google_start_with_invitation(body: GoogleStart, request: Request, response: Response):
    url, browser_token = begin_google(request, body.next, body.invitation)
    google_oauth.set_state_cookie(response, browser_token)
    return {"authorization_url": url}


@router.post("/google/link-admin")
def google_link_admin(body: GoogleAdminLink, request: Request, response: Response):
    if settings.auth_mode == "local":
        raise HTTPException(409, "Administrator linking requires a signed-in account.")
    with Session() as db:
        user = session_user(db, request)
        if not user:
            raise HTTPException(401, "Sign in to the existing administrator account first.")
        if not user.is_admin or user.email != "admin":
            raise HTTPException(403, "Only the existing reserved administrator can link this account.")
        if not google_oauth.configured():
            raise HTTPException(503, "Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
        if db.scalar(select(GoogleIdentity.id).where(GoogleIdentity.user_id == user.id)):
            raise HTTPException(409, "This administrator already has a linked Google identity.")
        if db.scalar(select(User.id).where(User.email == body.email, User.id != user.id)):
            raise HTTPException(409, "This email already belongs to another account. Accounts cannot be merged here.")
        throttle("google-admin-link", identity_limit=10)
        url, browser_token = google_oauth.begin(
            db, "/admin?google_link=success", linking_user_id=user.id,
            admin_email=body.email, admin_session_hash=digest(request.cookies[COOKIE]),
        )
    google_oauth.set_state_cookie(response, browser_token)
    response.headers["Referrer-Policy"] = "no-referrer"
    return {"authorization_url": url}


def google_failure(reason, admin_link=False):
    response = RedirectResponse(("/admin" if admin_link else "/") + "?error=google_" + reason, status_code=302)
    google_oauth.clear_state_cookie(response)
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/google/callback")
def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    if settings.auth_mode == "local" or not google_oauth.configured():
        return google_failure("not_configured")
    admin_link = False
    try:
        attempt = google_oauth.consume_state(state, request.cookies.get(google_oauth.OAUTH_COOKIE, ""))
        admin_link = attempt.purpose == "admin_link"
        if settings.auth_provider != "google" and not admin_link:
            raise google_oauth.GoogleOAuthError("not_configured")
        if error:
            raise google_oauth.GoogleOAuthError("cancelled")
        claims = google_oauth.exchange_code(code, attempt)
        with Session() as db:
            user = (google_oauth.resolve_admin_link(db, claims, attempt, request.cookies.get(COOKIE, ""))
                    if admin_link else google_oauth.resolve_user(db, claims, attempt))
            response = RedirectResponse(google_oauth.safe_next(attempt.next_path), status_code=302)
            login_cookie(db, user, response)
            db.commit()
        google_oauth.clear_state_cookie(response)
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
    except google_oauth.GoogleOAuthError as exc:
        return google_failure(exc.reason, admin_link)
    except IntegrityError:
        # Concurrent registration/linking must not move identities between users.
        return google_failure("identity_conflict", admin_link)


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE, "")
    with Session() as db:
        session = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token)))
        if session:
            db.delete(session)
            db.commit()
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
    return {"authenticated": False}
