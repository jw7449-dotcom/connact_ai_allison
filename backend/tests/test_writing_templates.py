from app.db import Session
from app.models import Workspace
from app.writing_template_models import WritingTemplate


def template_body(**overrides):
    return {
        "name": "A reusable introduction",
        "description": "For new conversations",
        "subject": "Hello {{name}}",
        "body_html": "<p>Hi {{name}},</p><p>Could we talk about {{company}}?</p>",
        **overrides,
    }


def test_template_library_persists_sanitizes_and_rejects_stale_updates(client):
    defaults = client.get("/api/writing-templates").json()
    assert len(defaults) == 3 and all(item["is_default"] for item in defaults)
    created = client.post("/api/writing-templates", json=template_body(
        body_html='<p onclick="alert(1)">Hi {{name}}</p><img src=x onerror="alert(1)"><a href="javascript:alert(1)">A link</a>'
    ))
    assert created.status_code == 201, created.text
    saved = created.json()
    assert not saved["is_default"] and saved["revision"] == 1
    assert "onclick" not in saved["body_html"] and "<img" not in saved["body_html"]
    assert "javascript:" not in saved["body_html"] and "{{name}}" in saved["body_html"]
    reloaded = next(item for item in client.get("/api/writing-templates").json() if item["id"] == saved["id"])
    assert reloaded["subject"] == saved["subject"] and reloaded["body_html"] == saved["body_html"]
    updated = client.put("/api/writing-templates/" + saved["id"], json={**saved, "subject": "New subject"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    stale = client.put("/api/writing-templates/" + saved["id"], json={**saved, "subject": "Stale subject"})
    assert stale.status_code == 409
    assert [item for item in client.get("/api/writing-templates").json() if item["id"] == saved["id"]][0]["subject"] == "New subject"


def test_template_validation_and_workspace_boundaries(client):
    for invalid in (template_body(name="  "), template_body(body_html="<p> </p>"), template_body(body_html="<img src=x>")):
        assert client.post("/api/writing-templates", json=invalid).status_code == 422
    with Session() as db:
        db.add(Workspace(id="other-writing", name="Other"))
        db.flush()
        private = WritingTemplate(workspace_id="other-writing", **template_body())
        db.add(private)
        db.commit()
        template_id = private.id
    assert all(item["id"] != template_id for item in client.get("/api/writing-templates").json())
    assert client.put("/api/writing-templates/" + template_id, json=template_body(revision=1)).status_code == 404
    assert client.delete("/api/writing-templates/" + template_id).status_code == 404
    assert client.delete("/api/writing-templates/default-networking").status_code == 404


def test_saved_template_can_be_reused_without_ai_or_contact(client):
    saved = client.post("/api/writing-templates", json=template_body()).json()
    draft = client.post("/api/drafts", json={"writing_mode": "template", "subject": saved["subject"], "body_html": saved["body_html"]}).json()
    assert draft["subject"] == "Hello {{name}}"
    preview = client.get(f'/api/drafts/{draft["id"]}/preview').json()
    assert set(preview["missing_variables"]) == {"name", "company"}
    assert not preview["can_mark_ready"]
    contact = client.post("/api/contacts", json={"name": "Jordan", "company": "Example"}).json()
    updated = client.put(f'/api/drafts/{draft["id"]}', json={**draft, "contact_id": contact["id"]})
    assert updated.status_code == 200
    preview = client.get(f'/api/drafts/{draft["id"]}/preview').json()
    assert preview["subject"] == "Hello Jordan"
    assert "Example" in preview["body_text"] and not preview["missing_variables"]
