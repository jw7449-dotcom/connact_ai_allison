from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.config import Settings, settings
from app.db import Session
from app.auth_models import Invitation
from app.bootstrap_invite import bootstrap_invite
from app.routers.auth import digest, _attempts


def test_render_postgres_url_uses_installed_driver():
    for url in (
        "postgres://test:password@db.example/app",
        "postgresql://test:password@db.example/app",
    ):
        config = Settings(_env_file=None, database_url=url)
        assert (
            config.database_url == "postgresql+psycopg://test:password@db.example/app"
        )


def test_invitation_expiry_update_keeps_usage_and_fixed_deadline(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "invite")
    monkeypatch.setattr(settings, "bootstrap_invite_email", "")
    monkeypatch.setattr(settings, "bootstrap_invite_token_hash", "c" * 64)
    monkeypatch.setattr(settings, "bootstrap_invite_max_uses", 4)
    monkeypatch.setattr(settings, "bootstrap_invite_expires_at", None)
    before = datetime.now(timezone.utc)
    bootstrap_invite()
    with Session() as db:
        record = db.scalar(select(Invitation))
        initial_expiry = record.expires_at.replace(tzinfo=timezone.utc)
        assert timedelta(days=30) <= initial_expiry - before < timedelta(days=30, seconds=5)
        record.expires_at = before + timedelta(days=7)
        record.use_count = 1
        db.commit()
    deadline = before + timedelta(days=30)
    monkeypatch.setattr(settings, "bootstrap_invite_expires_at", deadline)
    bootstrap_invite()
    bootstrap_invite()
    with Session() as db:
        record = db.scalar(select(Invitation))
        assert record.expires_at.replace(tzinfo=timezone.utc) == deadline
        assert record.use_count == 1 and record.max_uses == 4
        assert record.used_at is None
        record.used_at = before
        record.use_count = 4
        db.commit()
    monkeypatch.setattr(settings, "bootstrap_invite_expires_at", deadline + timedelta(days=1))
    bootstrap_invite()
    with Session() as db:
        record = db.scalar(select(Invitation))
        assert record.expires_at.replace(tzinfo=timezone.utc) == deadline
        assert record.use_count == 4 and record.used_at is not None


def test_bootstrap_invitation_not_reissued_on_restart(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "invite")
    monkeypatch.setattr(settings, "bootstrap_invite_email", "Owner@example.test")
    monkeypatch.setattr(settings, "bootstrap_invite_token_hash", "a" * 64)
    bootstrap_invite()
    with Session() as db:
        record = db.scalar(select(Invitation))
        assert record.email == "owner@example.test"
        record.used_at = datetime.now(timezone.utc)
        record.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
        ident = record.id
    bootstrap_invite()
    with Session() as db:
        rows = db.scalars(select(Invitation)).all()
        assert len(rows) == 1 and rows[0].id == ident
        assert rows[0].used_at is not None
        assert rows[0].expires_at.replace(tzinfo=timezone.utc) < datetime.now(
            timezone.utc
        )


def test_short_bootstrap_code_is_case_sensitive_email_bound_and_single_use(client, monkeypatch):
    import secrets
    import string

    token = "".join(secrets.choice(string.ascii_uppercase) for _ in range(6))
    monkeypatch.setattr(settings, "auth_mode", "invite")
    monkeypatch.setattr(settings, "bootstrap_invite_email", "owner@example.test")
    monkeypatch.setattr(settings, "bootstrap_invite_token_hash", digest(token))
    _attempts.clear()
    bootstrap_invite()
    body = {"email": "wrong@example.test", "password": "test-password-only-123", "invitation": token}
    assert client.post("/api/auth/join", json=body).status_code == 400
    body["email"] = "owner@example.test"
    body["invitation"] = token.lower()
    assert client.post("/api/auth/join", json=body).status_code == 400
    body["invitation"] = token
    assert client.post("/api/auth/join", json=body).status_code == 200
    client.post("/api/auth/logout")
    bootstrap_invite()
    assert client.post("/api/auth/join", json=body).status_code == 400


def test_shared_invitation_admits_four_distinct_accounts_without_reset(client, monkeypatch):
    import secrets

    token = secrets.token_urlsafe(18)
    monkeypatch.setattr(settings, "auth_mode", "invite")
    monkeypatch.setattr(settings, "bootstrap_invite_email", "")
    monkeypatch.setattr(settings, "bootstrap_invite_token_hash", digest(token))
    monkeypatch.setattr(settings, "bootstrap_invite_max_uses", 4)
    _attempts.clear()
    bootstrap_invite()
    workspaces = set()
    for number in range(4):
        body = {"email": f"member{number}@example.test", "password": "test-password-only-123", "invitation": token}
        joined = client.post("/api/auth/join", json=body)
        assert joined.status_code == 200, joined.text
        workspaces.add(joined.json()["workspace_id"])
        if number == 0:
            assert client.post("/api/auth/join", json=body).status_code == 409
        client.post("/api/auth/logout")
        bootstrap_invite()
        with Session() as db:
            record = db.scalar(select(Invitation))
            assert record.use_count == number + 1
            assert record.max_uses == 4
            assert bool(record.used_at) == (number == 3)
    assert len(workspaces) == 4
    body["email"] = "fifth@example.test"
    assert client.post("/api/auth/join", json=body).status_code == 400


def test_expired_shared_invitation_cannot_register(client, monkeypatch):
    import secrets

    token = secrets.token_urlsafe(18)
    monkeypatch.setattr(settings, "auth_mode", "invite")
    _attempts.clear()
    with Session() as db:
        db.add(Invitation(email="", token_hash=digest(token), max_uses=4,
                          expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
    body = {"email": "member@example.test", "password": "test-password-only-123", "invitation": token}
    assert client.post("/api/auth/join", json=body).status_code == 400
