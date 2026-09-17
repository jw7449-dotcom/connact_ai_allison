import secrets
from datetime import datetime, timedelta, timezone
from app.config import settings
from app.db import Session
from app.auth_models import Invitation
from app.routers.auth import digest, _attempts


def invite(email):
    token = secrets.token_urlsafe(32)
    with Session() as db:
        db.add(Invitation(email=email, token_hash=digest(token), expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
        db.commit()
    return token


def test_invite_login_logout_and_customer_isolation(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "invite")
    _attempts.clear()
    assert client.get("/api/contacts").status_code == 401
    assert client.get("/api/config").status_code == 401
    first = {"email": "first@example.test", "password": "test-password-only-123", "invitation": invite("first@example.test")}
    joined = client.post("/api/auth/join", json=first)
    assert joined.status_code == 200, joined.text
    cookie = joined.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    workspace_a = joined.json()["workspace_id"]
    draft = client.post("/api/drafts", json={"subject": "Private draft"}).json()
    contact = client.post("/api/contacts", json={"name": "Private contact"}).json()
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/drafts").status_code == 401
    assert client.post("/api/auth/join", json=first).status_code == 400
    second = {"email": "second@example.test", "password": "test-password-only-456", "invitation": invite("second@example.test")}
    joined_b = client.post("/api/auth/join", json=second)
    assert joined_b.status_code == 200
    assert joined_b.json()["workspace_id"] != workspace_a
    assert client.get("/api/contacts").json() == []
    assert client.get("/api/drafts/" + draft["id"]).status_code == 404
    assert client.post("/api/drafts", json={"contact_id": contact["id"]}).status_code == 404
    client.post("/api/auth/logout")
    bad = client.post("/api/auth/login", json={"email": first["email"], "password": "wrong-password-123"})
    assert bad.status_code == 401
    good = client.post("/api/auth/login", json=first)
    assert good.status_code == 200
    assert client.get("/api/drafts/" + draft["id"]).status_code == 200


def test_invitation_bound_to_email_and_origin(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "invite")
    _attempts.clear()
    token = invite("intended@example.test")
    data = {"email": "someone@example.test", "password": "long-password-test", "invitation": token}
    assert client.post("/api/auth/join", json=data).status_code == 400
    data["email"] = "intended@example.test"
    assert client.post("/api/auth/join", json=data, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/auth/join", json=data).status_code == 200


def test_session_expiry_and_rate_limit(client, monkeypatch):
    from app.auth_models import LoginSession
    from sqlalchemy import select
    monkeypatch.setattr(settings, "auth_mode", "invite")
    _attempts.clear()
    data = {"email": "expiry@example.test", "password": "long-password-test", "invitation": invite("expiry@example.test")}
    assert client.post("/api/auth/join", json=data).status_code == 200
    with Session() as db:
        session = db.scalar(select(LoginSession))
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/drafts").status_code == 401
    for _ in range(9):
        assert client.post("/api/auth/login", json={"email": data["email"], "password": "invalid-password"}).status_code == 401
    assert client.post("/api/auth/login", json=data).status_code == 429
