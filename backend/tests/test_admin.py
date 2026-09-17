import shutil
from pathlib import Path
from sqlalchemy import select
from app.config import settings
from app.db import Session
from app.auth_models import User, Invitation
from app.bootstrap_admin import bootstrap_admin
from app.bootstrap_invite import bootstrap_invite
from app.routers.auth import password_hash, _attempts
from app.services.documents import stop_document_worker, process_document


def provision(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "open")
    monkeypatch.setattr(settings, "bootstrap_admin_password_hash", password_hash("ABCXYZ"))
    _attempts.clear()
    bootstrap_admin()


def login_admin(client):
    result = client.post("/api/auth/login", json={"email": "admin", "password": "ABCXYZ"})
    assert result.status_code == 200, result.text


def test_open_registration_ignores_invites_and_cannot_claim_admin(client, monkeypatch):
    provision(monkeypatch)
    monkeypatch.setattr(settings, "bootstrap_invite_token_hash", "invalid-old-setting")
    bootstrap_invite()  # Open mode tolerates obsolete invitation configuration.
    assert client.get("/api/auth/session").json()["mode"] == "open"
    for number in range(5):
        result = client.post("/api/auth/join", json={"email": f"member{number}@example.test",
            "password": "test-password-only-123", "is_admin": True})
        assert result.status_code == 200, result.text
        assert client.get("/api/auth/session").json()["is_admin"] is False
        assert client.get("/api/admin/overview").status_code == 403
        client.post("/api/auth/logout")
    assert client.post("/api/auth/join", json={"email": "admin", "password": "test-password-only-123"}).status_code == 422
    assert client.get("/api/admin/users").status_code == 401
    with Session() as db:
        assert db.scalar(select(Invitation)) is None
    login_admin(client)
    assert client.get("/api/config").json()["is_admin"] is True
    assert client.get("/api/admin/overview").json()["accounts"] == 6
    monkeypatch.setattr(settings, "bootstrap_admin_password_hash", password_hash("DIFFERENT"))
    bootstrap_admin()
    client.post("/api/auth/logout")
    login_admin(client)  # Redeploy never replaces the existing admin password.


def test_admin_inspects_saved_records_and_original_files_without_secret_leaks(client, monkeypatch):
    provision(monkeypatch)
    stop_document_worker()
    member = client.post("/api/auth/join", json={"email": "member@example.test", "password": "test-password-only-123"}).json()
    persona = client.post("/api/personas", json={"label": "Saved background", "data": {"name": "Member", "education": "Saved education"}}).json()
    contact = client.post("/api/contacts", json={"name": "Saved person", "notes": "Private notes"}).json()
    draft = client.post("/api/drafts", json={"subject": "Private draft", "body_html": "<p>Private body</p>"}).json()
    content = b"%PDF-not-valid-but-original-upload"
    doc = client.post("/api/documents/jobs", files={"file": ("中文简历.pdf", content)}).json()
    assert doc.get("id"), doc
    shutil.rmtree(Path(settings.upload_dir) / member["workspace_id"])
    assert client.get(f'/api/documents/{doc["id"]}/download').content == content
    process_document(doc["id"])
    assert client.get(f'/api/documents/{doc["id"]}/status').json()["status"] == "failed"
    client.post("/api/auth/logout")
    client.post("/api/auth/join", json={"email": "other@example.test", "password": "test-password-only-123"})
    assert client.get(f'/api/documents/{doc["id"]}/download').status_code == 404
    assert client.get(f'/api/drafts/{draft["id"]}').status_code == 404
    with Session() as db:
        user_id = db.scalar(select(User.id).where(User.email == "member@example.test"))
        other_id = db.scalar(select(User.id).where(User.email == "other@example.test"))
    assert client.get(f'/api/admin/users/{user_id}').status_code == 403
    assert client.get(f'/api/admin/users/{user_id}/data/personas').status_code == 403
    assert client.get(f'/api/admin/users/{user_id}/documents/{doc["id"]}/download').status_code == 403
    client.post("/api/auth/logout")
    login_admin(client)
    users = client.get("/api/admin/users?q=member&limit=1").json()
    assert users["total"] == 1 and users["items"][0]["email"] == "member@example.test"
    assert users["items"][0]["counts"]["documents"] == 1
    assert users["items"][0]["last_login_at"]
    assert client.get("/api/admin/users?q=%").json()["total"] == 0
    assert client.get("/api/admin/users?limit=1&offset=1").json()["offset"] == 1
    for section, needle in (("personas", "Saved education"), ("contacts", "Private notes"),
                            ("drafts", "Private draft"), ("persona_revisions", "Saved education")):
        result = client.get(f"/api/admin/users/{user_id}/data/{section}")
        assert result.status_code == 200 and needle in result.text
        assert "password_hash" not in result.text and "token_hash" not in result.text
    files = client.get(f"/api/admin/users/{user_id}/data/documents").json()
    assert files["items"][0]["file_available"] is True
    assert files["items"][0]["byte_size"] == len(content)
    assert "storage_key" not in files["items"][0]
    downloaded = client.get(files["items"][0]["download_url"])
    assert downloaded.content == content
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert client.get(f'/api/admin/users/{other_id}/documents/{doc["id"]}/download').status_code == 404
    assert client.get(f'/api/admin/users/{user_id}/data/login_sessions').status_code == 404
    with Session() as db:
        db.scalar(select(User).where(User.email == "admin")).is_admin = False
        db.commit()
    assert client.get("/api/admin/users").status_code == 403
