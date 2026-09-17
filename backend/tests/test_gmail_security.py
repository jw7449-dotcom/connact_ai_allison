"""OAuth and transport contracts. No test calls Google or sends live mail."""
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import settings
from app.db import Session
from app.mail_models import GmailOAuthState, Mailbox
from app.auth_models import LoginSession, User
from app.models import Workspace
from app.routers.auth import digest


@pytest.fixture
def gmail_configured(monkeypatch, request):
    monkeypatch.setattr(settings, "gmail_worker_enabled", False)
    monkeypatch.setattr(settings, "gmail_client_id", "test-gmail-client.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "gmail_client_secret", "test-only-gmail-secret")
    monkeypatch.setattr(settings, "gmail_token_encryption_keys", Fernet.generate_key().decode())
    return request.getfixturevalue("client")


def start(client, mode="sync"):
    response = client.post("/api/mailboxes/connect", json={"mode": mode})
    assert response.status_code == 200, response.text
    query = {key: value[0] for key, value in parse_qs(urlsplit(response.json()["authorization_url"]).query).items()}
    return response, query


@pytest.mark.parametrize("mode", ["send", "sync"])
def test_gmail_start_is_separate_canonical_offline_pkce_and_server_scoped(gmail_configured, mode):
    from app.services import gmail
    response, query = start(gmail_configured, mode)
    assert query["client_id"] == settings.gmail_client_id
    assert query["redirect_uri"] == "http://127.0.0.1:3100/api/mailboxes/callback"
    assert query["code_challenge_method"] == "S256"
    assert query["access_type"] == "offline"
    assert "client_secret" not in query and "workspace_id" not in query
    scopes = set(query["scope"].split())
    if mode == "send":
        assert "https://www.googleapis.com/auth/gmail.send" in scopes
        assert "https://www.googleapis.com/auth/gmail.modify" not in scopes
        assert "https://www.googleapis.com/auth/gmail.readonly" not in scopes
    else:
        assert "https://www.googleapis.com/auth/gmail.modify" in scopes
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/api/mailboxes" in cookie
    with Session() as db:
        state = db.scalar(select(GmailOAuthState))
        assert state.workspace_id == settings.workspace_id
        assert state.state_hash == digest(query["state"])
        assert state.nonce_hash == digest(query["nonce"])
        assert state.browser_hash == digest(gmail_configured.cookies.get(gmail.OAUTH_COOKIE))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(state.code_verifier.encode()).digest()).decode().rstrip("=")
        assert challenge == query["code_challenge"]
        assert state.mode == mode


def test_wrong_browser_cannot_consume_and_state_is_single_use(gmail_configured):
    from app.services import gmail
    _, query = start(gmail_configured)
    browser = gmail_configured.cookies.get(gmail.OAUTH_COOKIE)
    with pytest.raises(Exception) as denied:
        gmail.consume_state(query["state"], "wrong-browser-token")
    assert "state" in str(denied.value)
    with Session() as db:
        assert db.scalar(select(GmailOAuthState)) is not None
    consumed = gmail.consume_state(query["state"], browser)
    assert consumed.workspace_id == settings.workspace_id
    with pytest.raises(Exception) as replayed:
        gmail.consume_state(query["state"], browser)
    assert "state" in str(replayed.value)


def test_expired_state_rejected_before_code_exchange(gmail_configured, monkeypatch):
    from app.services import gmail
    _, query = start(gmail_configured)
    with Session() as db:
        state = db.scalar(select(GmailOAuthState))
        state.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    def forbidden(*args, **kwargs):
        raise AssertionError("Expired authorization cannot exchange a code")
    monkeypatch.setattr(gmail, "exchange_code", forbidden)
    response = gmail_configured.get("/api/mailboxes/callback", params={"state": query["state"], "code": "secret-code"}, follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "gmail_invalid_state" in response.headers["location"]
    assert "secret-code" not in str(response.headers) + response.text


def test_tokens_encrypted_with_rotation_and_invalid_key_fails_closed(gmail_configured, monkeypatch):
    from app.services import gmail
    first_key = settings.gmail_token_encryption_keys
    secret = "test-only-refresh-token-never-public"
    encrypted = gmail.encrypt_token(secret)
    assert secret not in encrypted and encrypted != secret
    assert gmail.decrypt_token(encrypted) == secret
    second_key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "gmail_token_encryption_keys", second_key + "," + first_key)
    assert gmail.decrypt_token(encrypted) == secret
    assert Fernet(second_key.encode()).decrypt(gmail.encrypt_token(secret).encode()).decode() == secret
    monkeypatch.setattr(settings, "gmail_token_encryption_keys", second_key)
    with pytest.raises(Exception):
        gmail.decrypt_token(encrypted)


def test_mailbox_listing_never_exposes_encrypted_or_plain_credentials(gmail_configured):
    from app.services import gmail
    access, refresh = "test-access-secret", "test-refresh-secret"
    with Session() as db:
        mailbox = Mailbox(
            workspace_id=settings.workspace_id, email="separate-mailbox@gmail.com",
            access_token_encrypted=gmail.encrypt_token(access),
            refresh_token_encrypted=gmail.encrypt_token(refresh),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/gmail.modify"],
        )
        db.add(mailbox)
        db.commit()
        encrypted_access = mailbox.access_token_encrypted
        encrypted_refresh = mailbox.refresh_token_encrypted
    response = gmail_configured.get("/api/mailboxes")
    assert response.status_code == 200
    assert "separate-mailbox@gmail.com" in response.text
    for value in (access, refresh, encrypted_access, encrypted_refresh, "access_token_encrypted", "refresh_token_encrypted"):
        assert value not in response.text


def test_callback_connects_distinct_mailbox_and_does_not_change_platform_identity(gmail_configured, monkeypatch):
    from app.services import gmail
    _, query = start(gmail_configured)
    monkeypatch.setattr(gmail, "exchange_code", lambda *args: (
        {"access_token": "new-access", "refresh_token": "new-refresh", "scope": gmail.SYNC_SCOPE, "expires_in": 3600},
        {"sub": "separate-mailbox-subject", "email": "another-mailbox@gmail.com", "name": "Other Mailbox"},
    ))
    response = gmail_configured.get("/api/mailboxes/callback", params={"state": query["state"], "code": "one-use-code"}, follow_redirects=False)
    assert response.headers["location"] == "/mailboxes?gmail=connected"
    with Session() as db:
        mailbox = db.scalar(select(Mailbox))
        assert mailbox.email == "another-mailbox@gmail.com"
        assert mailbox.workspace_id == settings.workspace_id
        assert gmail.decrypt_token(mailbox.access_token_encrypted) == "new-access"
        assert gmail.decrypt_token(mailbox.refresh_token_encrypted) == "new-refresh"
        assert db.scalar(select(User)) is None
    assert "new-access" not in response.text + str(response.headers)
    assert gmail_configured.get("/api/auth/session").json()["workspace_id"] == settings.workspace_id
    replay = gmail_configured.get("/api/mailboxes/callback", params={"state": query["state"], "code": "one-use-code"}, follow_redirects=False)
    assert "gmail_invalid_state" in replay.headers["location"]


@pytest.mark.parametrize("failure", ["revoked", "expired", "switched", "workspace_changed"])
def test_connect_state_is_bound_to_live_initiating_session(gmail_configured, monkeypatch, failure):
    from app.services import gmail
    monkeypatch.setattr(settings, "auth_mode", "open")
    with Session() as db:
        workspace = Workspace(id=str(uuid4()), name="Authenticated workspace")
        db.add(workspace)
        db.flush()
        user = User(email="login@example.test", password_hash="!google", workspace_id=workspace.id)
        db.add(user)
        db.flush()
        login = LoginSession(user_id=user.id, token_hash=digest("session-token"), expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        db.add(login)
        db.commit()
        url, browser = gmail.begin(db, workspace.id, "sync", user.id, login.token_hash)
        state_token = parse_qs(urlsplit(url).query)["state"][0]
        state = gmail.consume_state(state_token, browser)
        if failure == "revoked":
            db.delete(login)
        elif failure == "expired":
            login.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif failure == "workspace_changed":
            user.workspace_id = settings.workspace_id
        db.commit()
        def forbidden(*args, **kwargs):
            raise AssertionError("Changed or expired app session cannot exchange Gmail code")
        monkeypatch.setattr(gmail, "exchange_code", forbidden)
        with pytest.raises(gmail.GmailError) as denied:
            gmail.complete(db, state, "code", "another-user-session" if failure == "switched" else "")
        assert denied.value.status_code == 401
        assert db.scalar(select(Mailbox)) is None


def transport_mailbox(db):
    from app.services import gmail
    mailbox = Mailbox(
        workspace_id=settings.workspace_id, email="owner@gmail.com", status="connected",
        access_token_encrypted=gmail.encrypt_token("valid-access"),
        refresh_token_encrypted=gmail.encrypt_token("valid-refresh"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1), scopes=[gmail.SYNC_SCOPE],
    )
    db.add(mailbox)
    db.commit()
    return mailbox


@pytest.mark.parametrize("outcome", ["timeout", "server_error", "invalid_json"])
def test_provider_writes_with_uncertain_outcomes_are_never_retried(gmail_configured, monkeypatch, outcome):
    from app.services import gmail
    calls = []
    real_client = httpx.Client
    def upstream(request):
        calls.append(request)
        if outcome == "timeout":
            raise httpx.ReadTimeout("provider response lost", request=request)
        if outcome == "server_error":
            return httpx.Response(503, json={"error": "private upstream diagnostic"})
        return httpx.Response(200, text="not-json")
    monkeypatch.setattr(gmail.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs))
    with Session() as db:
        mailbox = transport_mailbox(db)
        with pytest.raises(gmail.GmailError) as failed:
            gmail.GmailClient(mailbox, db).request("POST", "messages/send", json={"raw": "test-only-body"})
        assert failed.value.uncertain
        assert len(calls) == 1
        assert "private upstream diagnostic" not in failed.value.detail


def test_expired_access_refreshes_once_and_persists_only_encrypted_tokens(gmail_configured, monkeypatch):
    from app.services import gmail
    calls = []
    real_client = httpx.Client
    def upstream(request):
        calls.append(request)
        if str(request.url) == gmail.google_oauth.GOOGLE_TOKEN_URL:
            assert parse_qs(request.content.decode())["refresh_token"] == ["valid-refresh"]
            return httpx.Response(200, json={"access_token": "refreshed-access", "refresh_token": "rotated-refresh", "expires_in": 3600})
        assert request.headers["authorization"] == "Bearer refreshed-access"
        return httpx.Response(200, json={"messages": []})
    monkeypatch.setattr(gmail.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs))
    with Session() as db:
        mailbox = transport_mailbox(db)
        mailbox.token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        assert gmail.GmailClient(mailbox, db).request("GET", "messages") == {"messages": []}
        assert len(calls) == 2
        assert gmail.decrypt_token(mailbox.access_token_encrypted) == "refreshed-access"
        assert gmail.decrypt_token(mailbox.refresh_token_encrypted) == "rotated-refresh"
        assert "refreshed-access" not in mailbox.access_token_encrypted


def test_revoked_refresh_marks_mailbox_for_reauthorization_without_sending(gmail_configured, monkeypatch):
    from app.services import gmail
    calls = []
    real_client = httpx.Client
    def upstream(request):
        calls.append(request)
        assert str(request.url) == gmail.google_oauth.GOOGLE_TOKEN_URL
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "private revocation diagnostic"})
    monkeypatch.setattr(gmail.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs))
    with Session() as db:
        mailbox = transport_mailbox(db)
        mailbox.token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        with pytest.raises(gmail.GmailError) as failed:
            gmail.GmailClient(mailbox, db).request("POST", "messages/send", json={"raw": "test"})
        assert mailbox.status == "reauth_required"
        assert mailbox.access_token_encrypted is None
        assert not failed.value.uncertain
        assert len(calls) == 1


def test_concurrent_callback_state_consumption_has_one_winner(gmail_configured):
    from app.services import gmail
    _, query = start(gmail_configured)
    browser = gmail_configured.cookies.get(gmail.OAUTH_COOKIE)
    def consume(_):
        try:
            gmail.consume_state(query["state"], browser)
            return "consumed"
        except gmail.GmailError:
            return "denied"
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(consume, range(2)))
    assert sorted(outcomes) == ["consumed", "denied"]


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_unauthorized_provider_read_can_refresh_but_write_is_never_replayed(gmail_configured, monkeypatch, method):
    from app.services import gmail
    calls = []
    real_client = httpx.Client
    def upstream(request):
        calls.append(request)
        if str(request.url) == gmail.google_oauth.GOOGLE_TOKEN_URL:
            return httpx.Response(200, json={"access_token": "retried-read-token", "expires_in": 3600})
        if request.headers["authorization"] == "Bearer valid-access":
            return httpx.Response(401, json={"error": "expired"})
        assert method == "GET"
        return httpx.Response(200, json={"messages": []})
    monkeypatch.setattr(gmail.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs))
    with Session() as db:
        mailbox = transport_mailbox(db)
        api = gmail.GmailClient(mailbox, db)
        if method == "GET":
            assert api.request("GET", "messages") == {"messages": []}
            assert len(calls) == 3
        else:
            with pytest.raises(gmail.GmailError):
                api.request("POST", "messages/send", json={"raw": "test"})
            assert len(calls) == 1
            assert mailbox.status == "reauth_required"


@pytest.mark.parametrize("path", ["https://evil.test/messages", "//evil.test", "../messages", "messages?access_token=bad", "messages#fragment"])
def test_gmail_transport_never_accepts_arbitrary_upstream_urls(gmail_configured, path):
    from app.services import gmail
    with Session() as db:
        mailbox = transport_mailbox(db)
        with pytest.raises(gmail.GmailError) as rejected:
            gmail.GmailClient(mailbox, db).request("GET", path)
        assert rejected.value.status_code == 400


@pytest.mark.parametrize("change", [
    pytest.param({"access_token": ""}, id="empty-access"),
    pytest.param({"access_token": "x" * 20001}, id="oversized-access"),
    pytest.param({"refresh_token": {}}, id="object-refresh"),
    pytest.param({"refresh_token": ""}, id="empty-refresh"),
    pytest.param({"scope": ["https://www.googleapis.com/auth/gmail.modify"]}, id="array-scope"),
])
def test_malformed_oauth_token_response_fails_closed_without_creating_mailbox(gmail_configured, monkeypatch, change):
    from app.services import gmail
    _, query = start(gmail_configured)
    real_client = httpx.Client
    tokens = {"access_token": "valid-access", "refresh_token": "valid-refresh", "scope": gmail.SYNC_SCOPE, **change}
    calls = []
    def upstream(request):
        calls.append(request)
        assert str(request.url) == gmail.google_oauth.GOOGLE_TOKEN_URL
        return httpx.Response(200, json=tokens)
    monkeypatch.setattr(gmail.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs))
    def forbidden(*args, **kwargs):
        raise AssertionError("Malformed OAuth tokens must fail before identity verification")
    monkeypatch.setattr(gmail.google_oauth, "verify_id_token", forbidden)
    response = gmail_configured.get("/api/mailboxes/callback", params={"state": query["state"], "code": "test-code"}, follow_redirects=False)
    assert response.headers["location"] == "/mailboxes?gmail=gmail_invalid_token_response"
    assert len(calls) == 1
    with Session() as db:
        assert db.scalar(select(Mailbox)) is None


@pytest.mark.parametrize("change", [
    pytest.param({"access_token": ""}, id="empty-access"),
    pytest.param({"refresh_token": {}}, id="object-refresh"),
    pytest.param({"scope": {}}, id="object-scope"),
])
def test_malformed_refresh_response_never_reaches_mail_provider(gmail_configured, monkeypatch, change):
    from app.services import gmail
    real_client = httpx.Client
    calls = []
    def upstream(request):
        calls.append(request)
        assert str(request.url) == gmail.google_oauth.GOOGLE_TOKEN_URL
        return httpx.Response(200, json={"access_token": "refreshed-access", **change})
    monkeypatch.setattr(gmail.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs))
    with Session() as db:
        mailbox = transport_mailbox(db)
        mailbox.token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        with pytest.raises(gmail.GmailError) as rejected:
            gmail.GmailClient(mailbox, db).request("GET", "messages")
        assert rejected.value.status_code == 502
        assert len(calls) == 1


@pytest.mark.parametrize("reason,field,method,expected", [
    ("SERVICE_DISABLED", "details", "GET", "Gmail API is not enabled for this OAuth client's Google Cloud project. Ask the administrator to enable Gmail API in that project, then try again."),
    ("accessNotConfigured", "errors", "POST", "Gmail API is not enabled for this OAuth client's Google Cloud project. Ask the administrator to enable Gmail API in that project, then try again."),
    ("ACCESS_TOKEN_SCOPE_INSUFFICIENT", "details", "POST", "Gmail authorization lacks the permission required for this action. Reconnect this mailbox and grant the requested Gmail permissions."),
    ("insufficientPermissions", "errors", "GET", "Gmail authorization lacks the permission required for this action. Reconnect this mailbox and grant the requested Gmail permissions."),
    ("domainPolicy", "errors", "GET", "A Google Workspace administrator's policy blocks this Gmail action. Ask the administrator to review this app's Gmail access."),
    ("rateLimitExceeded", "errors", "POST", "Gmail rate limit reached. Try again later."),
    ("userRateLimitExceeded", "errors", "GET", "Gmail rate limit reached. Try again later."),
])
def test_structured_gmail_403_reasons_are_actionable_redacted_and_never_retried(gmail_configured, monkeypatch, reason, field, method, expected):
    from app.services import gmail
    real_client, calls = httpx.Client, []
    private = "private-diagnostic https://private.example/token?access_token=secret-token"
    def upstream(request):
        calls.append(request)
        return httpx.Response(403, json={"error": {"message": private, field: [
            {"reason": reason, "message": private, "metadata": {"activationUrl": private}},
        ]}})
    monkeypatch.setattr(gmail.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs))
    with Session() as db:
        mailbox = transport_mailbox(db)
        with pytest.raises(gmail.GmailError) as rejected:
            gmail.GmailClient(mailbox, db).request(method, "messages/send" if method == "POST" else "profile", json={"raw": "test"} if method == "POST" else None)
        assert rejected.value.status_code == 403
        assert rejected.value.detail == expected
        assert not rejected.value.uncertain
        assert mailbox.status == "connected"
        assert len(calls) == 1
        assert all(value not in rejected.value.detail for value in ("private-diagnostic", "private.example", "secret-token"))


@pytest.mark.parametrize("body", [
    {"error": {"message": "SERVICE_DISABLED private diagnostic", "errors": [{"reason": "unknownReason"}]}},
    {"error": {"errors": {"reason": "SERVICE_DISABLED"}, "details": [None, {"reason": {"nested": "SERVICE_DISABLED"}}]}},
    ["private malformed error"],
    "not-json private diagnostic",
])
def test_unknown_or_malformed_403_keeps_safe_permission_error_without_changing_delivery_outcome(gmail_configured, monkeypatch, body):
    from app.services import gmail
    real_client, calls = httpx.Client, []
    def upstream(request):
        calls.append(request)
        return httpx.Response(403, text=body) if isinstance(body, str) else httpx.Response(403, json=body)
    monkeypatch.setattr(gmail.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(upstream), **kwargs))
    with Session() as db:
        mailbox = transport_mailbox(db)
        with pytest.raises(gmail.GmailError) as rejected:
            gmail.GmailClient(mailbox, db).request("POST", "messages/send", json={"raw": "test"})
        assert rejected.value.status_code == 403
        assert rejected.value.detail == "Gmail permission was denied. Check consent and Gmail API access."
        assert not rejected.value.uncertain
        assert mailbox.status == "connected"
        assert len(calls) == 1
