"""Explicit administrator linking must preserve identity and fail closed."""
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select

from app.auth_models import GoogleIdentity, GoogleOAuthState, LoginSession, User
from app.bootstrap_admin import bootstrap_admin
from app.config import settings
from app.db import Session
from app.models import Workspace
from app.routers.auth import COOKIE, _attempts, digest, password_hash
from app.services import google_oauth as oauth


@pytest.fixture
def admin(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "open")
    monkeypatch.setattr(settings, "auth_provider", "password")
    monkeypatch.setattr(settings, "google_client_id", "test-admin-link.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "test-only-client-secret")
    monkeypatch.setattr(settings, "bootstrap_admin_password_hash", password_hash("admin-test-password"))
    _attempts.clear()
    bootstrap_admin()
    result = client.post("/api/auth/login", json={"email": "admin", "password": "admin-test-password"})
    assert result.status_code == 200
    return client


def begin(admin, email="owner@gmail.com"):
    response = admin.post("/api/auth/google/link-admin", json={"email": email})
    assert response.status_code == 200, response.text
    return {k: v[0] for k, v in parse_qs(urlsplit(response.json()["authorization_url"]).query).items()}


def complete(admin, query, monkeypatch, **overrides):
    claims = {"sub": "verified-admin-sub", "email": "owner@gmail.com", "email_verified": True, **overrides}
    monkeypatch.setattr(oauth, "exchange_code", lambda code, state: claims)
    return admin.get("/api/auth/google/callback", params={"state": query["state"], "code": "test-only-code"}, follow_redirects=False)


def assert_unlinked():
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(GoogleIdentity)) == 0
        assert db.scalar(select(User).where(User.email == "admin")).is_admin


def test_explicit_link_preserves_admin_workspace_and_bootstrap_then_google_login(admin, monkeypatch):
    before = admin.get("/api/auth/session").json()
    assert before["is_admin"] and not before["google_linked"]
    old_cookie = admin.cookies.get(COOKIE)
    draft = admin.post("/api/drafts", json={"subject": "Administrator's existing work"}).json()
    with Session() as db:
        original = db.scalar(select(User).where(User.email == "admin"))
    query = begin(admin, "  OWNER@gmail.com  ")
    with Session() as db:
        state = db.scalar(select(GoogleOAuthState))
        assert state.purpose == "admin_link"
        assert state.linking_user_id == original.id
        assert state.linking_session_hash == digest(old_cookie)
        assert state.linking_email_hash == digest("owner@gmail.com")
    # Real Google navigation omits SameSite=Strict login cookies. The initiating
    # DB session is still checked together with the Lax OAuth browser cookie.
    admin.cookies.delete(COOKIE)
    response = complete(admin, query, monkeypatch)
    assert response.headers["location"] == "/admin?google_link=success"
    after = admin.get("/api/auth/session").json()
    assert after["google_linked"] and after["is_admin"]
    assert after["email"] == "admin" and after["workspace_id"] == before["workspace_id"]
    assert admin.get("/api/drafts/" + draft["id"]).json()["subject"] == "Administrator's existing work"
    with Session() as db:
        user = db.scalar(select(User))
        assert user.id == original.id and user.password_hash == original.password_hash
        assert db.scalar(select(GoogleIdentity)).user_id == original.id
        assert db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(old_cookie))) is None
    bootstrap_admin()
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Workspace)) == 2  # Default app workspace + administrator.
    assert admin.post("/api/auth/google/link-admin", json={"email": "owner@gmail.com"}).status_code == 409
    admin.post("/api/auth/logout")
    monkeypatch.setattr(settings, "auth_provider", "google")
    response = admin.post("/api/auth/google/start", json={})
    query = {k: v[0] for k, v in parse_qs(urlsplit(response.json()["authorization_url"]).query).items()}
    assert complete(admin, query, monkeypatch).headers["location"] == "/finance"
    assert admin.get("/api/auth/session").json()["is_admin"]
    assert admin.get("/api/auth/session").json()["workspace_id"] == before["workspace_id"]
    assert admin.get("/api/admin/overview").status_code == 200


def test_link_requires_admin_config_and_same_origin(admin, monkeypatch):
    assert admin.post("/api/auth/google/link-admin", json={"email": "owner@gmail.com"}, headers={"Origin": "https://evil.example"}).status_code == 403
    monkeypatch.setattr(settings, "google_client_secret", "")
    assert admin.post("/api/auth/google/link-admin", json={"email": "owner@gmail.com"}).status_code == 503
    monkeypatch.setattr(settings, "google_client_secret", "test-only-secret")
    assert admin.post("/api/auth/google/link-admin", json={"email": "invalid"}).status_code == 422
    admin.post("/api/auth/logout")
    assert admin.post("/api/auth/google/link-admin", json={"email": "owner@gmail.com"}).status_code == 401
    assert admin.post("/api/auth/join", json={"email": "member@gmail.com", "password": "member-test-password"}).status_code == 200
    assert admin.post("/api/auth/google/link-admin", json={"email": "member@gmail.com"}).status_code == 403
    assert_unlinked()


@pytest.mark.parametrize("mutation", ["expired", "revoked", "demoted", "reassigned"])
def test_initiating_admin_session_must_still_be_live_and_same_user(admin, monkeypatch, mutation):
    query = begin(admin)
    with Session() as db:
        session = db.scalar(select(LoginSession))
        if mutation == "expired":
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif mutation == "revoked":
            db.delete(session)
        elif mutation == "demoted":
            db.scalar(select(User)).is_admin = False
        else:
            workspace = Workspace(name="Other workspace")
            db.add(workspace)
            db.flush()
            other = User(email="other@gmail.com", password_hash="!google", workspace_id=workspace.id)
            db.add(other)
            db.flush()
            session.user_id = other.id
        db.commit()
    admin.cookies.delete(COOKIE)
    response = complete(admin, query, monkeypatch)
    assert response.headers["location"] == "/admin?error=google_admin_link_session"
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(GoogleIdentity)) == 0


def test_another_login_cookie_on_callback_rejects_link(admin, monkeypatch):
    query = begin(admin)
    assert admin.post("/api/auth/join", json={"email": "other@gmail.com", "password": "member-test-password"}).status_code == 200
    assert complete(admin, query, monkeypatch).headers["location"] == "/admin?error=google_admin_link_session"
    assert not admin.get("/api/auth/session").json()["is_admin"]
    assert_unlinked()


@pytest.mark.parametrize("expected,claims", [
    ("owner@gmail.com", {"email": "wrong@gmail.com"}),
    ("owner@example.test", {"email": "owner@example.test"}),
    ("owner@example.test", {"email": "owner@example.test", "hd": "different.example"}),
])
def test_target_email_must_match_and_be_google_authoritative(admin, monkeypatch, expected, claims):
    query = begin(admin, expected)
    assert complete(admin, query, monkeypatch, **claims).headers["location"] == "/admin?error=google_admin_link_email"
    assert_unlinked()


def test_verified_workspace_email_can_link(admin, monkeypatch):
    query = begin(admin, "owner@example.test")
    assert complete(admin, query, monkeypatch, email="owner@example.test", hd="example.test").headers["location"] == "/admin?google_link=success"


def test_existing_user_or_subject_never_moves_into_admin(admin, monkeypatch):
    query = begin(admin)
    with Session() as db:
        workspace = Workspace(name="Existing member workspace")
        db.add(workspace)
        db.flush()
        member = User(email="other@gmail.com", password_hash="!google", workspace_id=workspace.id)
        db.add(member)
        db.flush()
        db.add(GoogleIdentity(user_id=member.id, subject="verified-admin-sub"))
        db.commit()
    assert complete(admin, query, monkeypatch).headers["location"] == "/admin?error=google_identity_conflict"
    with Session() as db:
        assert db.scalar(select(GoogleIdentity)).user_id == member.id
        assert not db.get(User, member.id).is_admin
        assert db.scalar(select(User).where(User.email == "admin")).is_admin
    assert admin.post("/api/auth/google/link-admin", json={"email": "other@gmail.com"}).status_code == 409


def test_member_claiming_email_after_begin_blocks_implicit_merge(admin, monkeypatch):
    query = begin(admin)
    with Session() as db:
        workspace = Workspace(name="Existing member workspace")
        db.add(workspace)
        db.flush()
        db.add(User(email="owner@gmail.com", password_hash="!google", workspace_id=workspace.id))
        db.commit()
    assert complete(admin, query, monkeypatch).headers["location"] == "/admin?error=google_identity_conflict"
    assert_unlinked()


def test_admin_link_state_is_browser_bound_expiring_and_one_use(admin, monkeypatch):
    query = begin(admin)
    browser_cookie = admin.cookies.get(oauth.OAUTH_COOKIE)
    admin.cookies.delete(oauth.OAUTH_COOKIE)
    assert complete(admin, query, monkeypatch).headers["location"] == "/?error=google_invalid_state"
    admin.cookies.set(oauth.OAUTH_COOKIE, browser_cookie, path=oauth.OAUTH_COOKIE_PATH)
    with Session() as db:
        db.scalar(select(GoogleOAuthState)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert complete(admin, query, monkeypatch).headers["location"] == "/?error=google_expired"
    admin.cookies.delete(oauth.OAUTH_COOKIE)
    query = begin(admin)
    assert complete(admin, query, monkeypatch).headers["location"] == "/admin?google_link=success"
    assert complete(admin, query, monkeypatch).headers["location"] == "/?error=google_invalid_state"


def test_password_mode_does_not_enable_normal_google_signin(admin, monkeypatch):
    assert admin.post("/api/auth/google/start", json={}).status_code == 409
    monkeypatch.setattr(settings, "auth_provider", "google")
    response = admin.post("/api/auth/google/start", json={})
    query = {k: v[0] for k, v in parse_qs(urlsplit(response.json()["authorization_url"]).query).items()}
    monkeypatch.setattr(settings, "auth_provider", "password")
    assert complete(admin, query, monkeypatch).headers["location"] == "/?error=google_not_configured"
    assert_unlinked()


def test_invalid_verified_identity_or_cancel_never_links_admin(admin, monkeypatch):
    query = begin(admin)
    def invalid_identity(code, state):
        raise oauth.GoogleOAuthError("invalid_identity")
    monkeypatch.setattr(oauth, "exchange_code", invalid_identity)
    response = admin.get("/api/auth/google/callback", params={"state": query["state"], "code": "invalid-code"}, follow_redirects=False)
    assert response.headers["location"] == "/admin?error=google_invalid_identity"
    query = begin(admin)
    response = admin.get("/api/auth/google/callback", params={"state": query["state"], "error": "access_denied"}, follow_redirects=False)
    assert response.headers["location"] == "/admin?error=google_cancelled"
    assert_unlinked()
