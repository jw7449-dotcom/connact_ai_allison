"""Google authorization-code sign-in; Google tokens are never persisted.

OIDC verification follows https://developers.google.com/identity/openid-connect/openid-connect.
Only fixed Google endpoints are contacted; neither request hosts nor JWT headers
may choose an issuer, callback URI, key URL, or token endpoint.
"""
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlencode, urlsplit
from uuid import uuid4

import httpx
import jwt
from sqlalchemy import delete, select

from ..auth_models import GoogleIdentity, GoogleOAuthState, Invitation, LoginSession, User
from ..config import settings
from ..db import Session
from ..models import Workspace

GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
OAUTH_COOKIE = "connact_google_oauth"
OAUTH_COOKIE_PATH = "/api/auth/google"
STATE_SECONDS = 600
_keys = jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_jwk_set=True, lifespan=300, timeout=10)


class GoogleOAuthError(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def configured():
    return bool(settings.google_client_id.strip() and settings.google_client_secret.strip())


def callback_uri():
    return settings.public_origin.rstrip("/") + "/api/auth/google/callback"


def safe_next(value):
    """Reject external, backslash, control-character, and encoded redirects."""
    value = value or "/finance"
    if not isinstance(value, str) or len(value) > 2000:
        return "/finance"
    decoded = value
    for _ in range(3):
        if (
            not decoded.startswith("/") or decoded.startswith("//")
            or "\\" in decoded or any(ord(c) < 32 or ord(c) == 127 for c in decoded)
        ):
            return "/finance"
        parsed = urlsplit(decoded)
        if parsed.scheme or parsed.netloc or parsed.path.startswith("/api/"):
            return "/finance"
        updated = unquote(decoded)
        if updated == decoded:
            return value
        decoded = updated
    return "/finance"


def set_state_cookie(response, browser_token):
    response.set_cookie(
        OAUTH_COOKIE, browser_token, max_age=STATE_SECONDS, httponly=True,
        secure=settings.public_origin.startswith("https://"), samesite="lax", path=OAUTH_COOKIE_PATH,
    )


def clear_state_cookie(response):
    response.delete_cookie(
        OAUTH_COOKIE, httponly=True, secure=settings.public_origin.startswith("https://"),
        samesite="lax", path=OAUTH_COOKIE_PATH,
    )


def begin(db, next_path, invitation="", linking_user_id=None, *, admin_email=None, admin_session_hash=None):
    state, browser_token, nonce = (secrets.token_urlsafe(32) for _ in range(3))
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    clock = datetime.now(timezone.utc)
    db.execute(delete(GoogleOAuthState).where(GoogleOAuthState.expires_at <= clock))
    db.add(GoogleOAuthState(
        state_hash=digest(state), browser_hash=digest(browser_token), nonce_hash=digest(nonce),
        code_verifier=verifier, next_path=safe_next(next_path),
        invitation_hash=digest(invitation) if invitation else None,
        linking_user_id=linking_user_id, purpose="admin_link" if admin_email else "signin",
        linking_email_hash=digest(admin_email) if admin_email else None,
        linking_session_hash=admin_session_hash,
        expires_at=clock + timedelta(seconds=STATE_SECONDS),
    ))
    db.commit()
    return GOOGLE_AUTHORIZATION_URL + "?" + urlencode({
        "client_id": settings.google_client_id.strip(), "redirect_uri": callback_uri(),
        "response_type": "code", "scope": "openid email profile", "state": state,
        "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256",
        "prompt": "select_account",
    }), browser_token


def consume_state(state, browser_token):
    if not state or not browser_token or len(state) > 200 or len(browser_token) > 200:
        raise GoogleOAuthError("invalid_state")
    with Session() as db:
        # DELETE RETURNING makes consumption atomic on both PostgreSQL and SQLite.
        # A wrong browser cannot consume another browser's authorization attempt.
        record = db.scalars(delete(GoogleOAuthState).where(
            GoogleOAuthState.state_hash == digest(state),
            GoogleOAuthState.browser_hash == digest(browser_token),
        ).returning(GoogleOAuthState)).one_or_none()
        db.commit()
        if record is None:
            raise GoogleOAuthError("invalid_state")
        if utc(record.expires_at) <= datetime.now(timezone.utc):
            raise GoogleOAuthError("expired")
        return record


def verify_id_token(encoded, nonce_hash, audience=None):
    if not isinstance(encoded, str) or not encoded or len(encoded) > 20000:
        raise GoogleOAuthError("invalid_identity")
    try:
        header = jwt.get_unverified_header(encoded)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise GoogleOAuthError("invalid_identity")
        # Pass the RSA key, not a header-selected algorithm or a remote header URL.
        key = _keys.get_signing_key_from_jwt(encoded).key
        claims = jwt.decode(
            encoded, key, algorithms=["RS256"], audience=audience or settings.google_client_id.strip(),
            issuer=["https://accounts.google.com", "accounts.google.com"],
            options={"require": ["iss", "aud", "exp", "iat", "sub", "nonce", "email", "email_verified"],
                     "strict_aud": True},
        )
    except jwt.PyJWKClientConnectionError as exc:
        raise GoogleOAuthError("unavailable") from exc
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise GoogleOAuthError("invalid_identity") from exc
    nonce = claims.get("nonce")
    subject = claims.get("sub")
    email = claims.get("email")
    if (
        not isinstance(nonce, str) or not hmac.compare_digest(digest(nonce), nonce_hash)
        or claims.get("email_verified") is not True
        or not isinstance(subject, str) or not subject or len(subject) > 255
        or not isinstance(email, str) or not 3 <= len(email) <= 250 or email.count("@") != 1
        or any(c.isspace() or ord(c) < 32 for c in email)
        or (claims.get("azp") is not None and claims["azp"] != (audience or settings.google_client_id.strip()))
    ):
        raise GoogleOAuthError("invalid_identity")
    return claims


def exchange_code(code, state):
    if not code or len(code) > 4096:
        raise GoogleOAuthError("invalid_identity")
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            result = client.post(GOOGLE_TOKEN_URL, data={
                "client_id": settings.google_client_id.strip(),
                "client_secret": settings.google_client_secret.strip(),
                "code": code, "code_verifier": state.code_verifier,
                "redirect_uri": callback_uri(), "grant_type": "authorization_code",
            })
        if result.status_code >= 500 or result.status_code == 429:
            raise GoogleOAuthError("unavailable")
        if result.status_code != 200:
            raise GoogleOAuthError("invalid_identity")
        tokens = result.json()
        encoded = tokens.get("id_token") if isinstance(tokens, dict) else None
    except (httpx.HTTPError, ValueError) as exc:
        raise GoogleOAuthError("unavailable") from exc
    # No userinfo fallback: a missing or invalid signed ID token always fails closed.
    return verify_id_token(encoded, state.nonce_hash)


def authoritative_email(claims):
    domain = claims["email"].strip().lower().rsplit("@", 1)[1]
    return domain in ("gmail.com", "googlemail.com") or (
        isinstance(claims.get("hd"), str) and claims["hd"].lower() == domain
    )


def resolve_admin_link(db, claims, state, current_session_token=""):
    """Link only an explicitly authenticated reserved admin, never promote a user.

    The Strict login cookie may be absent on Google's cross-site callback. Its
    initiating session remains bound into the one-use, browser-bound OAuth state
    and must still be live in the database when the verified callback arrives.
    """
    if state.purpose != "admin_link" or not state.linking_user_id or not state.linking_session_hash:
        raise GoogleOAuthError("admin_link_session")
    # Serialize attempts for one administrator before taking any session lock;
    # otherwise different initiating sessions can deadlock during revocation.
    user = db.scalar(select(User).where(User.id == state.linking_user_id).with_for_update())
    session = db.scalar(select(LoginSession).where(
        LoginSession.token_hash == state.linking_session_hash,
        LoginSession.user_id == state.linking_user_id,
    ).with_for_update())
    if (
        not session or utc(session.expires_at) <= datetime.now(timezone.utc)
        or not user or not user.is_admin or user.email != "admin"
        or (current_session_token and not hmac.compare_digest(digest(current_session_token), state.linking_session_hash))
    ):
        raise GoogleOAuthError("admin_link_session")
    email = claims["email"].strip().lower()
    if (
        not state.linking_email_hash or not hmac.compare_digest(digest(email), state.linking_email_hash)
        or not authoritative_email(claims)
    ):
        raise GoogleOAuthError("admin_link_email")
    # Existing accounts and identities must never be moved or merged implicitly.
    if (
        db.scalar(select(GoogleIdentity).where(GoogleIdentity.subject == claims["sub"]))
        or db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
        or db.scalar(select(User).where(User.email == email, User.id != user.id))
    ):
        raise GoogleOAuthError("identity_conflict")
    db.add(GoogleIdentity(user_id=user.id, subject=claims["sub"]))
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    # Keep the reserved username, workspace, role and password hash intact. This
    # preserves data and rollback, and bootstrap_admin cannot create a duplicate.
    db.flush()
    return user


def resolve_user(db, claims, state):
    subject, email = claims["sub"], claims["email"].strip().lower()
    identity = db.scalar(select(GoogleIdentity).where(GoogleIdentity.subject == subject))
    if identity:
        # A Google email may change; the stable subject still owns this workspace.
        return db.get(User, identity.user_id)
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    if user:
        linked = db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user.id))
        if linked:
            raise GoogleOAuthError("identity_conflict")
        # Google warns third-party email_verified claims can outlive ownership.
        # Existing-account linking needs a Google-hosted address or the account's
        # authenticated initiating browser; never grant admin by email matching.
        if not authoritative_email(claims) and state.linking_user_id != user.id:
            raise GoogleOAuthError("link_required")
        # Legacy registration did not verify email. Retaining old sessions when
        # the verified owner first links Google would allow account pre-hijacking.
        # The callback creates a fresh session in this same transaction.
        db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    else:
        invitation = None
        if settings.auth_mode == "invite":
            if not state.invitation_hash:
                raise GoogleOAuthError("invitation_required")
            invitation = db.scalar(select(Invitation).where(
                Invitation.token_hash == state.invitation_hash,
            ).with_for_update())
            if (
                not invitation or invitation.used_at or invitation.use_count >= invitation.max_uses
                or utc(invitation.expires_at) <= datetime.now(timezone.utc)
                or (invitation.email and invitation.email.lower() != email)
            ):
                raise GoogleOAuthError("invitation_invalid")
        workspace = Workspace(id=str(uuid4()), name="Personal workspace")
        db.add(workspace)
        db.flush()
        # This non-hash sentinel cannot authenticate through the password endpoint.
        user = User(email=email, password_hash="!google", workspace_id=workspace.id)
        db.add(user)
        db.flush()
        if invitation:
            invitation.use_count += 1
            if invitation.use_count >= invitation.max_uses:
                invitation.used_at = datetime.now(timezone.utc)
    db.add(GoogleIdentity(user_id=user.id, subject=subject))
    db.flush()
    return user
