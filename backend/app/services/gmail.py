"""Real Gmail transport and separate, browser-bound mailbox OAuth consent.

Never log token responses, persist plaintext credentials, or retry a provider
write. Gmail has no application idempotency key; a timed-out send is uncertain.
"""
import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import delete, select

from ..auth_models import LoginSession, User
from ..config import settings
from ..db import Session
from ..mail_models import GmailOAuthState, Mailbox
from ..models import now
from . import google_oauth
from .google_oauth import digest, utc

SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SYNC_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
OAUTH_COOKIE = "connact_gmail_oauth"
OAUTH_COOKIE_PATH = "/api/mailboxes"
STATE_SECONDS = 600
API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me/"


class GmailError(HTTPException):
    def __init__(self, status_code, detail, *, uncertain=False):
        self.uncertain = uncertain
        super().__init__(status_code, detail)


def _forbidden_message(response):
    """Classify documented reason fields; never expose Google's diagnostic text."""
    fallback = "Gmail permission was denied. Check consent and Gmail API access."
    try:
        payload = response.json()
    except ValueError:
        return fallback
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return fallback
    reasons = set()
    for field in ("errors", "details"):
        entries = error.get(field)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            reason = entry.get("reason") if isinstance(entry, dict) else None
            if isinstance(reason, str):
                reasons.add(reason.casefold())
    if reasons & {"service_disabled", "accessnotconfigured"}:
        return "Gmail API is not enabled for this OAuth client's Google Cloud project. Ask the administrator to enable Gmail API in that project, then try again."
    if reasons & {"access_token_scope_insufficient", "insufficientpermissions"}:
        return "Gmail authorization lacks the permission required for this action. Reconnect this mailbox and grant the requested Gmail permissions."
    if "domainpolicy" in reasons:
        return "A Google Workspace administrator's policy blocks this Gmail action. Ask the administrator to review this app's Gmail access."
    if reasons & {"ratelimitexceeded", "userratelimitexceeded"}:
        return "Gmail rate limit reached. Try again later."
    return fallback


def client_credentials():
    # Never combine half of a distinct client with half of the sign-in client.
    if settings.gmail_client_id or settings.gmail_client_secret:
        return settings.gmail_client_id.strip(), settings.gmail_client_secret.strip()
    return settings.google_client_id.strip(), settings.google_client_secret.strip()


def cipher():
    try:
        keys = [Fernet(k.strip().encode()) for k in settings.gmail_token_encryption_keys.split(",") if k.strip()]
        if not keys:
            raise ValueError()
        return MultiFernet(keys)
    except (ValueError, TypeError) as exc:
        raise GmailError(503, "Configure a valid GMAIL_TOKEN_ENCRYPTION_KEYS on the server before connecting Gmail.") from exc


def configured():
    client_id, secret = client_credentials()
    try:
        cipher()
    except GmailError:
        return False
    return bool(client_id and secret)


def encrypt_token(value):
    return cipher().encrypt(value.encode()).decode() if value else None


def decrypt_token(value):
    if not value:
        raise GmailError(409, "Reconnect this Gmail mailbox.")
    try:
        return cipher().decrypt(value.encode()).decode()
    except (InvalidToken, UnicodeError) as exc:
        raise GmailError(409, "The mailbox credential cannot be decrypted. Restore the encryption key or reconnect Gmail.") from exc


def callback_uri():
    return settings.public_origin.rstrip("/") + "/api/mailboxes/callback"


def _validate_tokens(tokens, require_scopes=False):
    if (not isinstance(tokens, dict) or not isinstance(tokens.get("access_token"), str)
        or not tokens["access_token"] or len(tokens["access_token"]) > 20000
        or (tokens.get("refresh_token") is not None and
            (not isinstance(tokens["refresh_token"], str) or not tokens["refresh_token"] or len(tokens["refresh_token"]) > 20000))
        or ((require_scopes or "scope" in tokens) and not isinstance(tokens.get("scope"), str))):
        raise GmailError(502, "gmail_invalid_token_response")
    return tokens


def begin(db, workspace_id, mode, user_id=None, session_hash=None):
    if not configured():
        raise GmailError(503, "Gmail is not configured. Set the OAuth client, callback URI and token encryption key on the server.")
    state, browser_token, nonce = (secrets.token_urlsafe(32) for _ in range(3))
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    db.execute(delete(GmailOAuthState).where(GmailOAuthState.expires_at <= now()))
    db.add(GmailOAuthState(
        workspace_id=workspace_id, state_hash=digest(state), browser_hash=digest(browser_token),
        nonce_hash=digest(nonce), code_verifier=verifier, mode=mode,
        user_id=user_id, session_hash=session_hash, expires_at=now() + timedelta(seconds=STATE_SECONDS),
    ))
    db.commit()
    return google_oauth.GOOGLE_AUTHORIZATION_URL + "?" + urlencode({
        "client_id": client_credentials()[0], "redirect_uri": callback_uri(),
        "response_type": "code", "scope": "openid email profile " + (SYNC_SCOPE if mode == "sync" else SEND_SCOPE),
        "state": state, "nonce": nonce, "code_challenge": challenge,
        "code_challenge_method": "S256", "access_type": "offline", "prompt": "consent select_account",
    }), browser_token


def consume_state(state, browser_token):
    if not state or not browser_token or len(state) > 200 or len(browser_token) > 200:
        raise GmailError(400, "gmail_invalid_state")
    with Session() as db:
        record = db.scalars(delete(GmailOAuthState).where(
            GmailOAuthState.state_hash == digest(state),
            GmailOAuthState.browser_hash == digest(browser_token),
        ).returning(GmailOAuthState)).one_or_none()
        db.commit()
        if record is None or utc(record.expires_at) <= now():
            raise GmailError(400, "gmail_invalid_state")
        return record


def exchange_code(code, state):
    if not code or len(code) > 4096:
        raise GmailError(400, "gmail_invalid_code")
    client_id, secret = client_credentials()
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            response = client.post(google_oauth.GOOGLE_TOKEN_URL, data={
                "client_id": client_id, "client_secret": secret,
                "code": code, "code_verifier": state.code_verifier,
                "redirect_uri": callback_uri(), "grant_type": "authorization_code",
            })
        if response.status_code != 200:
            raise GmailError(502, "gmail_authorization_failed")
        tokens = _validate_tokens(response.json(), require_scopes=True)
        claims = google_oauth.verify_id_token(tokens.get("id_token"), state.nonce_hash, audience=client_id)
        return tokens, claims
    except (httpx.HTTPError, ValueError, google_oauth.GoogleOAuthError) as exc:
        raise GmailError(502, "gmail_authorization_failed") from exc


def complete(db, state, code, current_session_token=""):
    # Strict app cookies may be absent on Google's cross-site callback. The live
    # initiating session in the one-use state remains the authority in that case.
    if state.user_id:
        user = db.get(User, state.user_id)
        session = db.scalar(select(LoginSession).where(
            LoginSession.user_id == state.user_id, LoginSession.token_hash == state.session_hash,
        ).with_for_update())
        if (not user or user.workspace_id != state.workspace_id or not session
            or utc(session.expires_at) <= now()
            or (current_session_token and not hmac.compare_digest(digest(current_session_token), state.session_hash))):
            raise GmailError(401, "gmail_session_expired")
    elif settings.auth_mode != "local" or state.workspace_id != settings.workspace_id:
        raise GmailError(401, "gmail_session_expired")
    tokens, claims = exchange_code(code, state)
    _validate_tokens(tokens, require_scopes=True)
    scopes = tokens.get("scope", "").split()
    required = SYNC_SCOPE if state.mode == "sync" else SEND_SCOPE
    if required not in scopes and not (state.mode == "send" and SYNC_SCOPE in scopes):
        raise GmailError(400, "gmail_missing_permissions")
    email = claims["email"].strip().lower()
    mailbox = db.scalar(select(Mailbox).where(
        Mailbox.workspace_id == state.workspace_id, Mailbox.email == email,
    ).with_for_update())
    if not mailbox:
        mailbox = Mailbox(workspace_id=state.workspace_id, email=email)
        db.add(mailbox)
    refresh = tokens.get("refresh_token")
    if not refresh and not mailbox.refresh_token_encrypted:
        raise GmailError(400, "gmail_offline_consent_required")
    mailbox.access_token_encrypted = encrypt_token(tokens["access_token"])
    if refresh:
        mailbox.refresh_token_encrypted = encrypt_token(refresh)
    try:
        mailbox.token_expires_at = now() + timedelta(seconds=max(0, min(int(tokens.get("expires_in", 3600)), 86400)))
    except (ValueError, TypeError) as exc:
        raise GmailError(502, "gmail_authorization_failed") from exc
    mailbox.scopes = scopes
    mailbox.sync_enabled = state.mode == "sync"
    mailbox.display_name = str(claims.get("name") or email)[:200]
    mailbox.status = "connected"
    mailbox.last_sync_error = None
    mailbox.sync_status = "idle"
    db.flush()
    return mailbox


class GmailClient:
    def __init__(self, mailbox, db):
        self.mailbox, self.db = mailbox, db

    def _reauthorize(self):
        self.mailbox.status = "reauth_required"
        self.mailbox.last_sync_error = "Gmail authorization expired or was revoked. Reconnect the mailbox."
        self.mailbox.access_token_encrypted = None
        self.db.flush()

    def _access_token(self, force=False):
        mailbox = self.mailbox
        # Serialize token refresh with disconnect/reconnect using the mailbox row.
        # Refreshing a stale ORM object must not restore credentials after a
        # disconnect committed in another request. PostgreSQL keeps this lock
        # until the caller commits its mail operation.
        self.db.refresh(mailbox, with_for_update=True)
        if mailbox.status != "connected":
            raise GmailError(409, "Reconnect this Gmail mailbox before continuing.")
        if not force and mailbox.access_token_encrypted and mailbox.token_expires_at and utc(mailbox.token_expires_at) > now() + timedelta(seconds=60):
            return decrypt_token(mailbox.access_token_encrypted)
        refresh = decrypt_token(mailbox.refresh_token_encrypted)
        client_id, secret = client_credentials()
        if not client_id or not secret:
            raise GmailError(503, "Gmail OAuth client is not configured.")
        try:
            with httpx.Client(timeout=20, follow_redirects=False) as client:
                response = client.post(google_oauth.GOOGLE_TOKEN_URL, data={
                    "client_id": client_id, "client_secret": secret,
                    "refresh_token": refresh, "grant_type": "refresh_token",
                })
            if response.status_code in (400, 401):
                self._reauthorize()
                raise GmailError(401, "Gmail authorization expired or was revoked. Reconnect the mailbox.")
            if response.status_code != 200:
                raise GmailError(502, "Gmail token refresh is temporarily unavailable.")
            tokens = _validate_tokens(response.json())
            mailbox.access_token_encrypted = encrypt_token(tokens["access_token"])
            mailbox.token_expires_at = now() + timedelta(seconds=max(0, min(int(tokens.get("expires_in", 3600)), 86400)))
            if tokens.get("refresh_token"):
                mailbox.refresh_token_encrypted = encrypt_token(tokens["refresh_token"])
            self.db.flush()
            return tokens["access_token"]
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise GmailError(502, "Gmail token refresh is temporarily unavailable.") from exc

    def request(self, method, path, params=None, json=None):
        method = method.upper()
        if path.startswith("/") or any(c in path for c in (":", "?", "#", "\\")) or ".." in path:
            raise GmailError(400, "Invalid Gmail resource path.")
        writing = method not in ("GET", "HEAD")
        token = self._access_token()
        for attempt in range(2 if not writing else 1):
            try:
                with httpx.Client(timeout=30, follow_redirects=False) as client:
                    response = client.request(method, API_BASE + path, params=params, json=json,
                                              headers={"Authorization": "Bearer " + token})
                if response.status_code == 401:
                    if not writing and attempt == 0:
                        token = self._access_token(force=True)
                        continue
                    self._reauthorize()
                    raise GmailError(401, "Gmail authorization failed. Reconnect this mailbox.")
                if response.status_code >= 400:
                    messages = {404: "Gmail resource or history cursor was not found.",
                                429: "Gmail rate limit reached. Try again later."}
                    detail = _forbidden_message(response) if response.status_code == 403 else messages.get(response.status_code, "Gmail could not complete the request.")
                    raise GmailError(response.status_code, detail,
                                     uncertain=writing and response.status_code >= 500)
                if response.status_code >= 300:
                    raise GmailError(502, "Gmail returned an unexpected redirect.", uncertain=writing)
                data = response.json() if response.content else {}
                if not isinstance(data, dict):
                    raise ValueError()
                return data
            except (httpx.HTTPError, ValueError) as exc:
                raise GmailError(502, "Gmail request did not return a valid response. Check delivery before retrying." if writing
                                 else "Gmail is temporarily unavailable.", uncertain=writing) from exc
        raise GmailError(401, "Reconnect this Gmail mailbox.")

    def profile(self):
        return self.request("GET", "profile")
