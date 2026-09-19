from sqlalchemy import delete

from app.db import Session
from app.models import Workspace, Persona, PersonaRevision
from app.writing_template_models import WritingTemplate


def make_persona(client, label="Finance"):
    return client.post("/api/personas", json={"label": label, "data": {}}).json()["id"]


def template_body(persona_id, **overrides):
    return {
        "persona_id": persona_id,
        "name": "A reusable introduction",
        "description": "For new conversations",
        "subject": "Hello {{name}}",
        "body_html": "<p>Hi {{name}},</p><p>Could we talk about {{company}}?</p>",
        **overrides,
    }


def library(client, persona_id):
    return client.get("/api/writing-templates", params={"persona_id": persona_id}).json()


def test_template_library_persists_sanitizes_and_rejects_stale_updates(client):
    persona = make_persona(client)
    defaults = library(client, persona)
    assert len(defaults) == 3 and all(item["is_default"] for item in defaults)
    created = client.post("/api/writing-templates", json=template_body(
        persona,
        body_html='<p onclick="alert(1)">Hi {{name}}</p><img src=x onerror="alert(1)"><a href="javascript:alert(1)">A link</a>'
    ))
    assert created.status_code == 201, created.text
    saved = created.json()
    assert not saved["is_default"] and saved["revision"] == 1
    assert "onclick" not in saved["body_html"] and "<img" not in saved["body_html"]
    assert "javascript:" not in saved["body_html"] and "{{name}}" in saved["body_html"]
    reloaded = next(item for item in library(client, persona) if item["id"] == saved["id"])
    assert reloaded["subject"] == saved["subject"] and reloaded["body_html"] == saved["body_html"]
    updated = client.put("/api/writing-templates/" + saved["id"], json={**saved, "subject": "New subject"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    stale = client.put("/api/writing-templates/" + saved["id"], json={**saved, "subject": "Stale subject"})
    assert stale.status_code == 409
    assert [item for item in library(client, persona) if item["id"] == saved["id"]][0]["subject"] == "New subject"


def test_template_validation_and_workspace_boundaries(client):
    persona = make_persona(client)
    for invalid in (
        template_body(persona, name="  "),
        template_body(persona, body_html="<p> </p>"),
        template_body(persona, body_html="<img src=x>"),
    ):
        assert client.post("/api/writing-templates", json=invalid).status_code == 422
    with Session() as db:
        db.add(Workspace(id="other-writing", name="Other"))
        db.flush()
        foreign_persona = Persona(workspace_id="other-writing", label="Theirs", data={})
        db.add(foreign_persona)
        db.flush()
        private = WritingTemplate(
            workspace_id="other-writing",
            **template_body(foreign_persona.id),
        )
        db.add(private)
        db.commit()
        template_id = private.id
    assert all(item["id"] != template_id for item in library(client, persona))
    assert client.put(
        "/api/writing-templates/" + template_id, json=template_body(persona, revision=1)
    ).status_code == 404
    assert client.delete("/api/writing-templates/" + template_id).status_code == 404
    assert client.delete("/api/writing-templates/default-networking").status_code == 404


def test_templates_are_scoped_to_one_persona(client):
    first, second = make_persona(client, "Finance"), make_persona(client, "Academic")
    saved = client.post("/api/writing-templates", json=template_body(first)).json()

    assert saved["id"] in [item["id"] for item in library(client, first)]

    other = library(client, second)
    assert saved["id"] not in [item["id"] for item in other]
    # The three code-constant starters stay visible under every persona.
    assert [item["id"] for item in other] == [
        "default-networking",
        "default-interview",
        "default-followup",
    ]


def test_template_requires_a_persona_the_caller_owns(client):
    persona = make_persona(client)
    no_persona = {k: v for k, v in template_body(persona).items() if k != "persona_id"}
    assert client.post("/api/writing-templates", json=no_persona).status_code == 422
    assert client.get("/api/writing-templates").status_code == 422

    with Session() as db:
        db.add(Workspace(id="other-persona-ws", name="Other"))
        db.flush()
        foreign = Persona(workspace_id="other-persona-ws", label="Theirs", data={})
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
    assert client.post(
        "/api/writing-templates", json=template_body(foreign_id)
    ).status_code == 404
    assert client.get(
        "/api/writing-templates", params={"persona_id": foreign_id}
    ).status_code == 404


def test_deleting_a_persona_deletes_its_templates(client):
    persona = make_persona(client)
    saved = client.post("/api/writing-templates", json=template_body(persona)).json()
    with Session() as db:
        # Creating a persona through the API also writes a revision row, and that
        # table has no cascade. Clear it so this exercises the template cascade.
        db.execute(delete(PersonaRevision).where(PersonaRevision.persona_id == persona))
        db.delete(db.get(Persona, persona))
        db.commit()
        assert db.get(WritingTemplate, saved["id"]) is None


def test_saved_template_can_be_reused_without_ai_or_contact(client):
    persona = make_persona(client)
    saved = client.post("/api/writing-templates", json=template_body(persona)).json()
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
