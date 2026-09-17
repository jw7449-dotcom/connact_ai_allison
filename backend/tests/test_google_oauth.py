import base64
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError
from sqlalchemy import func, select

from app.auth_models import GoogleIdentity, GoogleOAuthState, Invitation, LoginSession, User
from app.config import Settings, settings
from app.db import Session
from app.models import Workspace
from app.routers.auth import _attempts, digest, password_hash
from app.services import google_oauth as oauth


@pytest.fixture
def google(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "open")
    monkeypatch.setattr(settings, "auth_provider", "google")
    monkeypatch.setattr(settings, "google_client_id", "test-client.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "test-only-client-secret")
    _attempts.clear()
    return client


def start(client, **body):
    response = client.post("/api/auth/google/start", json={"next": "/finance", **body})
    assert response.status_code == 200, response.text
    query = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    return {k: v[0] for k, v in query.items()}


def claims_for(query, **overrides):
    clock = int(datetime.now(timezone.utc).timestamp())
    return {"iss": "https://accounts.google.com", "aud": settings.google_client_id,
            "iat": clock, "exp": clock + 3600, "sub": "google-sub-123", "nonce": query["nonce"],
            "email": "person@gmail.com", "email_verified": True, **overrides}


@pytest.fixture
def signing(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(oauth._keys, "get_signing_key_from_jwt", lambda _: SimpleNamespace(key=key.public_key()))
    return lambda claims: jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})


def complete(client, query, monkeypatch, **claims):
    monkeypatch.setattr(oauth, "exchange_code", lambda code, state: claims_for(query, **claims))
    return client.get("/api/auth/google/callback", params={"state": query["state"], "code": "test-code"}, follow_redirects=False)


def legacy_user(email="person@gmail.com"):
    with Session() as db:
        workspace = Workspace(id=str(uuid4()), name="Existing workspace")
        db.add(workspace)
        db.flush()
        user = User(email=email, password_hash=password_hash("test-legacy-password"), workspace_id=workspace.id)
        db.add(user)
        db.commit()
        return user


def test_start_is_canonical_pkce_scoped_and_server_side(google, monkeypatch):
    response = google.get("/api/auth/google/start?next=/finance", headers={"X-Forwarded-Host": "evil.example"}, follow_redirects=False)
    assert response.status_code == 302
    query = {k: v[0] for k, v in parse_qs(urlsplit(response.headers["location"]).query).items()}
    assert query["redirect_uri"] == "http://127.0.0.1:3100/api/auth/google/callback"
    assert query["scope"] == "openid email profile"
    assert query["code_challenge_method"] == "S256"
    assert "client_secret" not in query and "access_type" not in query
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=600" in cookie
    assert "Path=/api/auth/google" in cookie
    with Session() as db:
        state = db.scalar(select(GoogleOAuthState))
        assert state.state_hash == digest(query["state"])
        assert state.nonce_hash == digest(query["nonce"])
        assert state.browser_hash == digest(google.cookies.get(oauth.OAUTH_COOKIE))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(state.code_verifier.encode()).digest()).decode().rstrip("=")
        assert challenge == query["code_challenge"]
    monkeypatch.setattr(settings, "public_origin", "https://app.example.test")
    response = google.post("/api/auth/google/start", json={})
    assert "Secure" in response.headers["set-cookie"]
    assert "https%3A%2F%2Fapp.example.test%2Fapi%2Fauth%2Fgoogle%2Fcallback" in response.json()["authorization_url"]


def test_signed_code_exchange_creates_session_and_discards_google_tokens(google, monkeypatch, signing):
    query = start(google, next="/finance?tab=people")
    real_client = httpx.Client
    requests = []

    def token_endpoint(request):
        requests.append(request)
        values = parse_qs(request.content.decode())
        assert str(request.url) == oauth.GOOGLE_TOKEN_URL
        assert values["redirect_uri"] == [oauth.callback_uri()]
        assert values["code"] == ["one-use-code"]
        assert values["client_secret"] == [settings.google_client_secret]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(values["code_verifier"][0].encode()).digest()).decode().rstrip("=")
        assert query["code_challenge"] == challenge
        return httpx.Response(200, json={"id_token": signing(claims_for(query)), "access_token": "discard-this", "refresh_token": "discard-this-too"})

    monkeypatch.setattr(oauth.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(token_endpoint), **kwargs))
    response = google.get("/api/auth/google/callback", params={"state": query["state"], "code": "one-use-code"}, follow_redirects=False)
    assert response.headers["location"] == "/finance?tab=people"
    assert len(requests) == 1
    session = google.get("/api/auth/session").json()
    assert session["authenticated"] and session["email"] == "person@gmail.com"
    assert session["provider"] == "google" and session["google_configured"]
    assert not session["is_admin"]
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(GoogleOAuthState)) == 0
        assert db.scalar(select(GoogleIdentity)).subject == "google-sub-123"
        assert db.scalar(select(User)).password_hash == "!google"
        assert db.scalar(select(LoginSession)).token_hash != google.cookies.get("connact_session")
    assert "discard-this" not in response.text + str(response.headers) + str(session)
    assert google.post("/api/auth/logout").status_code == 200
    assert not google.get("/api/auth/session").json()["authenticated"]


def test_missing_wrong_expired_and_replayed_state_never_exchanges(google, monkeypatch):
    def should_not_exchange(*args):
        raise AssertionError("OAuth code must not be exchanged")
    monkeypatch.setattr(oauth, "exchange_code", should_not_exchange)
    assert google.get("/api/auth/google/callback?code=code", follow_redirects=False).headers["location"] == "/?error=google_invalid_state"
    query = start(google)
    browser = google.cookies.get(oauth.OAUTH_COOKIE)
    google.cookies.clear()
    assert google.get("/api/auth/google/callback", params={"state": query["state"], "code": "code"}, follow_redirects=False).headers["location"] == "/?error=google_invalid_state"
    with Session() as db:
        record = db.scalar(select(GoogleOAuthState))
        assert record is not None  # Another browser cannot consume this state.
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    google.cookies.set(oauth.OAUTH_COOKIE, browser, path=oauth.OAUTH_COOKIE_PATH)
    assert google.get("/api/auth/google/callback", params={"state": query["state"]}, follow_redirects=False).headers["location"] == "/?error=google_expired"
    with pytest.raises(oauth.GoogleOAuthError, match="invalid_state"):
        oauth.consume_state(query["state"], browser)


def test_cancelled_and_token_error_consume_state(google, monkeypatch):
    query = start(google)
    response = google.get("/api/auth/google/callback", params={"state": query["state"], "error": "access_denied", "error_description": "Do not reflect me"}, follow_redirects=False)
    assert response.headers["location"] == "/?error=google_cancelled"
    assert "Do not reflect me" not in response.text
    query = start(google)
    browser = google.cookies.get(oauth.OAUTH_COOKIE)
    def failure(*args):
        raise oauth.GoogleOAuthError("unavailable")
    monkeypatch.setattr(oauth, "exchange_code", failure)
    response = google.get("/api/auth/google/callback", params={"state": query["state"], "code": "code"}, follow_redirects=False)
    assert response.headers["location"] == "/?error=google_unavailable"
    with pytest.raises(oauth.GoogleOAuthError, match="invalid_state"):
        oauth.consume_state(query["state"], browser)


@pytest.mark.parametrize("override", [
    {"iss": "https://evil.example"}, {"aud": "other-client"}, {"aud": ["test-client.apps.googleusercontent.com", "other"]},
    {"exp": 1}, {"iat": 4102444800}, {"nonce": "wrong"}, {"email_verified": False},
    {"email_verified": "true"}, {"azp": "other-client"}, {"sub": ""}, {"email": "not-an-email"},
])
def test_signed_invalid_claims_rejected(google, signing, override):
    query = {"nonce": "expected-nonce"}
    with pytest.raises(oauth.GoogleOAuthError, match="invalid_identity"):
        oauth.verify_id_token(signing(claims_for(query, **override)), digest(query["nonce"]))


def test_signature_missing_claims_and_algorithm_rejected(google, signing):
    query = {"nonce": "expected"}
    payload = claims_for(query)
    encoded = signing(payload)
    assert oauth.verify_id_token(encoded, digest(query["nonce"]))["sub"] == payload["sub"]
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wrong_signature = jwt.encode(payload, other_key, algorithm="RS256", headers={"kid": "test-key"})
    missing_claim = dict(payload)
    del missing_claim["exp"]
    hs_token = jwt.encode(payload, "test-only-signing-key-long-enough", algorithm="HS256", headers={"kid": "test-key"})
    for invalid in (wrong_signature, signing(missing_claim), hs_token, "not-a-jwt", None):
        with pytest.raises(oauth.GoogleOAuthError, match="invalid_identity"):
            oauth.verify_id_token(invalid, digest(query["nonce"]))


def test_existing_workspace_links_once_and_sub_survives_email_change(google, monkeypatch):
    user = legacy_user()
    monkeypatch.setattr(settings, "auth_provider", "password")
    assert google.post("/api/auth/login", json={"email": user.email, "password": "test-legacy-password"}).status_code == 200
    old_cookie = google.cookies.get("connact_session")
    draft = google.post("/api/drafts", json={"subject": "Keep my existing draft"}).json()
    contact = google.post("/api/contacts", json={"name": "Existing saved contact"}).json()
    monkeypatch.setattr(settings, "auth_provider", "google")
    query = start(google)
    assert complete(google, query, monkeypatch).headers["location"] == "/finance"
    assert google.get("/api/auth/session").json()["workspace_id"] == user.workspace_id
    assert google.cookies.get("connact_session") != old_cookie
    with Session() as db:
        assert db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(old_cookie))) is None
    assert google.get("/api/drafts/" + draft["id"]).json()["subject"] == "Keep my existing draft"
    assert any(row["id"] == contact["id"] for row in google.get("/api/contacts").json())
    google.post("/api/auth/logout")
    query = start(google)
    assert complete(google, query, monkeypatch, email="changed@gmail.com").headers["location"] == "/finance"
    assert google.get("/api/auth/session").json()["workspace_id"] == user.workspace_id
    google.post("/api/auth/logout")
    query = start(google)
    response = complete(google, query, monkeypatch, sub="different-google-sub")
    assert response.headers["location"] == "/?error=google_identity_conflict"
    assert not google.get("/api/auth/session").json()["authenticated"]


def test_third_party_email_link_needs_existing_session(google, monkeypatch):
    user = legacy_user("third-party@example.test")
    query = start(google)
    response = complete(google, query, monkeypatch, email=user.email)
    assert response.headers["location"] == "/?error=google_link_required"
    with Session() as db:
        assert db.scalar(select(GoogleIdentity)) is None
    monkeypatch.setattr(settings, "auth_provider", "password")
    assert google.post("/api/auth/login", json={"email": user.email, "password": "test-legacy-password"}).status_code == 200
    monkeypatch.setattr(settings, "auth_provider", "google")
    query = start(google)
    assert complete(google, query, monkeypatch, email=user.email).headers["location"] == "/finance"
    assert google.get("/api/auth/session").json()["workspace_id"] == user.workspace_id


def test_invitation_is_hashed_bound_consumed_only_on_new_valid_account(google, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "invite")
    query = start(google)
    assert complete(google, query, monkeypatch).headers["location"] == "/?error=google_invitation_required"
    invitation = "test-only-invitation"
    with Session() as db:
        db.add(Invitation(token_hash=digest(invitation), email="person@gmail.com", expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
    query = start(google, invitation=invitation)
    assert invitation not in str(query)
    with Session() as db:
        assert db.scalar(select(GoogleOAuthState)).invitation_hash == digest(invitation)
    assert complete(google, query, monkeypatch, email="other@gmail.com").headers["location"] == "/?error=google_invitation_invalid"
    with Session() as db:
        assert db.scalar(select(Invitation)).use_count == 0
        assert db.scalar(select(User)) is None
    query = start(google, invitation=invitation)
    assert complete(google, query, monkeypatch).headers["location"] == "/finance"
    with Session() as db:
        assert db.scalar(select(Invitation)).use_count == 1
    google.post("/api/auth/logout")
    query = start(google)
    assert complete(google, query, monkeypatch).headers["location"] == "/finance"


def test_google_signup_creates_isolated_workspaces(google, monkeypatch):
    query = start(google)
    complete(google, query, monkeypatch)
    first = google.get("/api/auth/session").json()
    private = google.post("/api/drafts", json={"subject": "Google user's private draft"}).json()
    google.post("/api/auth/logout")
    query = start(google)
    complete(google, query, monkeypatch, email="second@gmail.com", sub="second-sub")
    assert google.get("/api/auth/session").json()["workspace_id"] != first["workspace_id"]
    assert google.get("/api/drafts/" + private["id"]).status_code == 404


def test_google_does_not_migrate_username_admin_or_grant_role(google, monkeypatch):
    admin = legacy_user("admin")
    with Session() as db:
        db.get(User, admin.id).is_admin = True
        db.commit()
    query = start(google)
    assert complete(google, query, monkeypatch, email="admin@gmail.com").headers["location"] == "/finance"
    assert not google.get("/api/auth/session").json()["is_admin"]
    assert google.get("/api/admin/overview").status_code == 403
    with Session() as db:
        assert db.get(User, admin.id).is_admin
        assert db.get(User, admin.id).email == "admin"
        assert db.get(User, admin.id).workspace_id == admin.workspace_id
        assert db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == admin.id)) is None


def test_provider_gates_config_and_origin(google, monkeypatch):
    body = {"email": "person@gmail.com", "password": "test-long-password-123"}
    assert google.post("/api/auth/login", json=body).status_code == 409
    assert google.post("/api/auth/join", json=body).status_code == 409
    assert google.post("/api/auth/google/start", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    monkeypatch.setattr(settings, "google_client_secret", "")
    response = google.get("/api/auth/session").json()
    assert not response["google_configured"]
    assert "google_client_id" not in response and "google_client_secret" not in response
    assert google.post("/api/auth/google/start", json={}).status_code == 503
    monkeypatch.setattr(settings, "auth_provider", "password")
    assert google.get("/api/auth/google/start").status_code == 409


@pytest.mark.parametrize("next_path", ["https://evil.example", "//evil.example", "/\\evil.example", "/%2fevil.example", "/%255cevil.example", "/finance\n", "/api/auth/google/start", "/%61pi/auth/google/start"])
def test_unsafe_next_falls_back(next_path):
    assert oauth.safe_next(next_path) == "/finance"


@pytest.mark.parametrize("origin", ["http://app.example", "https://user:pass@app.example", "https://app.example/path", "https://app.example?x=1", "https://app.example/#fragment", "https://app.example\\evil", "https://app.example:bad"])
def test_public_origin_is_canonical(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, public_origin=origin)


def test_google_only_account_cannot_password_login_after_provider_switch(google, monkeypatch):
    query = start(google)
    complete(google, query, monkeypatch)
    google.post("/api/auth/logout")
    monkeypatch.setattr(settings, "auth_provider", "password")
    assert google.post("/api/auth/login", json={"email": "person@gmail.com", "password": "any-password"}).status_code == 401


def test_auth_access_logs_strip_callback_and_start_query():
    import logging
    from app.services.auth_logging import AuthQueryRedaction, configure_auth_log_redaction

    for path in ("/api/auth/google/callback?code=secret-code&state=secret-state", "/api/auth/google/start?next=%2Ffinance", "/api/auth/google/callback/?code=secret-code"):
        record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("client", "GET", path, "1.1", 302), None)
        assert AuthQueryRedaction().filter(record)
        assert "?" not in record.getMessage() and "secret-code" not in record.getMessage()
        assert path.split("?", 1)[0] in record.getMessage()
    configure_auth_log_redaction()
    configure_auth_log_redaction()
    assert sum(isinstance(f, AuthQueryRedaction) for f in logging.getLogger("uvicorn.access").filters) == 1
