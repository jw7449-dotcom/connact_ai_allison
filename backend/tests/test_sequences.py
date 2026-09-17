from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from app.config import settings
from app.db import Session
from app.models import Contact, Draft, Workspace
from app.sequence_models import Sequence, SequenceJob, SequenceTemplate
from app.providers.ai import CompatibleAI, MockAI
from app.services.sequences import process_sequence_job, recover_sequence_jobs, stop_sequence_worker


@pytest.fixture
def paused_client(client):
    stop_sequence_worker()
    yield client
    stop_sequence_worker()


def create(client, **values):
    response = client.post("/api/sequences", json={"name": "Career outreach", **values})
    assert response.status_code == 201, response.text
    return response.json()


def draft(client, **values):
    response = client.post("/api/drafts", json={"subject": "A conversation", "body_html": "<p>A useful email.</p>", **values})
    assert response.status_code == 200, response.text
    return response.json()


def queue(client, sequence, **values):
    response = client.post(f'/api/sequences/{sequence["id"]}/ai-plan', json={
        "revision": sequence["revision"], "prompt": "Ask about a career in investing", "step_count": 3, **values})
    assert response.status_code == 202, response.text
    return response.json()


def step_input(step, **values):
    return {**{key: step[key] for key in ("id", "draft_id", "title", "purpose", "delay_days", "thread_mode")}, **values}


def test_three_defaults_portable_export_and_safe_import(client):
    templates = client.get("/api/sequence-templates").json()
    assert [item["name"] for item in templates] == ["Networking", "Recruiting", "Reconnect"]
    portable = client.get("/api/sequence-templates/default-networking/export").json()
    assert set(portable) == {"schema_version", "name", "description", "steps"}
    portable["name"] = "My custom cadence"
    portable["steps"][0]["body_html"] = '<p>Hello <a href="javascript:alert(1)">link</a><img src=x onerror=alert(1)></p>'
    imported = client.post("/api/sequence-templates", json=portable)
    assert imported.status_code == 201, imported.text
    template = imported.json()
    assert not template["is_default"]
    assert "javascript" not in template["steps"][0]["body_html"] and "onerror" not in template["steps"][0]["body_html"]
    assert client.get(f'/api/sequence-templates/{template["id"]}/export').json()["name"] == "My custom cadence"
    assert client.get("/api/sequence-templates/schema").json()["properties"]["schema_version"]["const"] == 1
    assert client.delete("/api/sequence-templates/default-networking").status_code == 422
    assert client.delete(f'/api/sequence-templates/{template["id"]}').status_code == 200
    assert client.get(f'/api/sequence-templates/{template["id"]}').status_code == 404


@pytest.mark.parametrize("change", [
    {"schema_version": 2}, {"schema_version": True}, {"workspace_id": "other"}, {"steps": []},
    {"steps": [{"title": "Reply", "thread_mode": "reply", "delay_days": 0}]},
    {"steps": [{"title": "First", "delay_days": 2}]},
    {"steps": [{"title": "First", "delay_days": -1}]},
    {"steps": [{"title": "First", "delay_days": True}]},
    {"steps": [{"title": "First", "delay_days": 0, "unknown": "value"}]},
])
def test_invalid_template_contract_rejected(client, change):
    value = {"schema_version": 1, "name": "Invalid", "steps": [{"title": "First", "delay_days": 0}], **change}
    assert client.post("/api/sequence-templates", json=value).status_code == 422


def test_imported_drafts_are_independent_and_plan_crud_preserves_originals(client):
    contact = client.post("/api/contacts", json={"name": "Jordan"}).json()
    first = draft(client, contact_id=contact["id"], subject="Original first")
    second = draft(client, contact_id=contact["id"], subject="Original second")
    sequence = create(client, draft_ids=[first["id"], second["id"]])
    assert sequence["contact_id"] == contact["id"]
    assert [s["draft"]["subject"] for s in sequence["steps"]] == ["Original first", "Original second"]
    assert sequence["steps"][0]["draft_id"] != first["id"]
    copy = sequence["steps"][0]["draft"]
    assert client.put('/api/drafts/' + copy["id"], json={**copy, "subject": "Sequence-only edit"}).status_code == 200
    assert client.get('/api/drafts/' + first["id"]).json()["subject"] == "Original first"
    ordered = [step_input(sequence["steps"][1], delay_days=0, thread_mode="new_thread"),
               step_input(sequence["steps"][0], delay_days=6, thread_mode="reply")]
    response = client.put('/api/sequences/' + sequence["id"], json={"revision": 1, "steps": ordered})
    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["revision"] == 2 and changed["steps"][0]["id"] == sequence["steps"][1]["id"]
    assert client.put('/api/sequences/' + sequence["id"], json={"revision": 1, "name": "Stale"}).status_code == 409
    assert client.get('/api/sequences/' + sequence["id"]).json()["name"] != "Stale"
    saved = client.post(f'/api/sequences/{sequence["id"]}/save-template', json={"name": "Reusable version"}).json()
    reused = create(client, template_id=saved["id"])
    assert reused["steps"][0]["draft_id"] != changed["steps"][0]["draft_id"]
    removed_step = client.put('/api/sequences/' + sequence["id"], json={"revision": 2, "steps": ordered[:1]})
    assert removed_step.status_code == 200 and len(removed_step.json()["steps"]) == 1
    assert client.delete(f'/api/sequences/{sequence["id"]}?revision=2').status_code == 409
    assert client.delete(f'/api/sequences/{sequence["id"]}?revision=3').json()["drafts_preserved"]
    assert client.get('/api/drafts/' + copy["id"]).status_code == 200
    assert client.get('/api/sequences/' + sequence["id"]).status_code == 404


def test_empty_plan_step_addition_and_structural_validation(client):
    sequence = create(client)
    base = '/api/sequences/' + sequence["id"]
    assert not client.get(base + '/preview').json()["can_mark_ready"]
    assert client.put(base, json={"revision": 1, "status": "ready"}).status_code == 422
    assert client.post(base + '/steps', json={"revision": 1, "thread_mode": "reply"}).status_code == 422
    response = client.post(base + '/steps', json={"revision": 1, "title": "First"})
    assert response.status_code == 200, response.text
    sequence = response.json()
    assert sequence["steps"][0]["thread_mode"] == "new_thread" and sequence["steps"][0]["delay_days"] == 0
    valid = step_input(sequence["steps"][0])
    assert client.put(base, json={"revision": 2, "steps": [valid, valid]}).status_code == 422
    assert client.put(base, json={"revision": 2, "steps": [{**valid, "id": "other-step"}]}).status_code == 422
    assert client.put(base, json={"revision": 2, "steps": [{**valid, "thread_mode": "reply"}]}).status_code == 422
    assert client.put(base, json={"revision": 2, "status": "active"}).status_code == 422
    assert client.put(base, json={"revision": 2, "name": None}).status_code == 422
    assert client.get(base).json()["revision"] == 2


def test_step_purpose_preserves_imported_brief_then_syncs_explicit_edits(client):
    source = draft(client, purpose="Original writer brief")
    sequence = create(client, draft_ids=[source["id"]])
    step = sequence["steps"][0]
    assert step["purpose"] == step["draft"]["purpose"] == "Original writer brief"
    updated = client.put('/api/sequences/' + sequence["id"], json={"revision": 1,
        "steps": [step_input(step, purpose="Ask for a 15-minute career conversation")]})
    assert updated.status_code == 200, updated.text
    saved = updated.json()["steps"][0]
    assert saved["draft"]["purpose"] == saved["purpose"] == "Ask for a 15-minute career conversation"
    assert saved["draft"]["revision"] == 2
    assert client.get('/api/drafts/' + source["id"]).json()["purpose"] == "Original writer brief"
    renamed = client.put('/api/sequences/' + sequence["id"], json={"revision": 2,
        "steps": [step_input(saved, title="Renamed step")]})
    assert renamed.status_code == 200 and renamed.json()["steps"][0]["draft"]["revision"] == 2


def test_cumulative_preview_reply_subject_ready_and_review_staleness(client):
    contact = client.post("/api/contacts", json={"name": "Jordan", "company": "Example"}).json()
    persona = client.post("/api/personas", json={"label": "Sender", "data": {"name": "Alex"}}).json()
    sequence = create(client, template_id="default-networking", contact_id=contact["id"], persona_id=persona["id"])
    base = '/api/sequences/' + sequence["id"]
    review = client.get(base + '/preview').json()
    assert review["can_mark_ready"]
    assert [step["cumulative_day"] for step in review["steps"]] == [0, 4, 11]
    assert review["steps"][1]["effective_subject"] == "Re: A brief introduction"
    assert review["steps"][1]["preview"]["subject"] == "Re: A brief introduction"
    assert "{{" not in review["steps"][1]["preview"]["body_html"]
    marked = client.put(base, json={"revision": 1, "status": "ready"})
    assert marked.status_code == 200 and marked.json()["status"] == "ready"
    copied = sequence["steps"][1]["draft"]
    assert client.put('/api/drafts/' + copied["id"], json={**copied, "body_html": "<p>A later content edit.</p>"}).status_code == 200
    stale = client.get(base).json()
    assert stale["review_stale"] and stale["status"] == "draft"
    assert client.put(base, json={"revision": 2, "status": "ready"}).json()["status"] == "ready"
    client.put('/api/contacts/' + contact["id"], json={"name": "Jordan", "company": "Changed"})
    assert client.get(base).json()["review_stale"]


def test_context_changes_apply_to_every_owned_draft_and_missing_variables_block_ready(client):
    sequence = create(client, template_id="default-networking")
    base = '/api/sequences/' + sequence["id"]
    review = client.get(base + '/preview').json()
    assert not review["can_mark_ready"] and "name" in review["steps"][0]["preview"]["missing_variables"]
    contact = client.post('/api/contacts', json={"name": "Jordan", "company": "Example"}).json()
    persona = client.post('/api/personas', json={"label": "Sender", "data": {"name": "Alex"}}).json()
    response = client.put(base, json={"revision": 1, "contact_id": contact["id"], "persona_id": persona["id"], "language": "zh"})
    assert response.status_code == 200, response.text
    assert all(step["draft"]["contact_id"] == contact["id"] and step["draft"]["persona_id"] == persona["id"]
               and step["draft"]["language"] == "zh" and step["draft"]["revision"] == 2 for step in response.json()["steps"])
    assert client.get(base + '/preview').json()["can_mark_ready"]
    copied = response.json()["steps"][1]["draft"]
    client.put('/api/drafts/' + copied["id"], json={**copied, "body_html": "<p>Hello {{unknown}} {{broken</p>"})
    review = client.get(base + '/preview').json()
    assert not review["can_mark_ready"]
    assert set(review["steps"][1]["preview"]["missing_variables"]) == {"unknown", "malformed_variable"}


def test_workspace_boundaries_cover_sequences_drafts_templates_and_context(client):
    with Session() as db:
        db.add(Workspace(id="other-space", name="Other"))
        db.flush()
        other_contact = Contact(workspace_id="other-space", name="Other")
        other_draft = Draft(workspace_id="other-space", subject="Private", body_html="<p>Private</p>")
        other_sequence = Sequence(workspace_id="other-space", name="Private")
        other_template = SequenceTemplate(workspace_id="other-space", name="Private", steps=[])
        db.add_all([other_contact, other_draft, other_sequence, other_template])
        db.commit()
        contact_id, draft_id, sequence_id, template_id = other_contact.id, other_draft.id, other_sequence.id, other_template.id
    for path in (f'/api/sequences/{sequence_id}', f'/api/sequence-templates/{template_id}'):
        assert client.get(path).status_code == 404
    for values in ({"draft_ids": [draft_id]}, {"template_id": template_id}, {"contact_id": contact_id}):
        assert client.post('/api/sequences', json={"name": "Attempt", **values}).status_code == 404
    assert client.get('/api/sequences').json() == []
    local = create(client)
    assert client.put('/api/sequences/' + local["id"], json={"revision": 1, "contact_id": contact_id}).status_code == 404
    assert client.post(f'/api/sequences/{local["id"]}/steps', json={"revision": 1, "draft_id": draft_id}).status_code == 404
    assert client.get('/api/sequences/' + local["id"]).json()["revision"] == 1


def test_durable_mock_job_idempotency_persistence_and_no_sending(paused_client):
    c = paused_client
    sequence = create(c, template_id="default-reconnect")
    job = queue(c, sequence)
    assert queue(c, sequence)["id"] == job["id"]
    assert job["mode"] == "mock" and job["completed_steps"] == 0 and "snapshot" not in job
    assert process_sequence_job(job["id"])
    assert not process_sequence_job(job["id"])
    saved = c.get('/api/sequences/' + sequence["id"]).json()
    assert saved["revision"] == 2 and saved["status"] == "draft" and len(saved["steps"]) == 3
    assert saved["generation"]["status"] == "succeeded"
    assert saved["generation"]["completed_steps"] == 3
    assert all(step["draft"]["generation_provider"] == "mock" for step in saved["steps"])
    assert c.get(f'/api/sequences/{sequence["id"]}/jobs/{job["id"]}').json()["result_steps"][0]["body_html"]
    other = create(c)
    assert c.get(f'/api/sequences/{other["id"]}/jobs/{job["id"]}').status_code == 404


@pytest.mark.parametrize("edit", ["sequence", "draft", "contact"])
def test_incremental_progress_does_not_overwrite_edits_during_generation(paused_client, monkeypatch, edit):
    c = paused_client
    contact = c.post('/api/contacts', json={"name": "Jordan"}).json()
    sequence = create(c, template_id="default-networking", contact_id=contact["id"])
    job = queue(c, sequence)
    started, release = Event(), Event()
    original = MockAI.complete

    def delayed(self, task, data):
        if data["step_index"] == 1:
            started.set()
            assert release.wait(5)
        return original(self, task, data)

    monkeypatch.setattr(MockAI, "complete", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(process_sequence_job, job["id"])
        assert started.wait(3)
        try:
            progress = c.get(f'/api/sequences/{sequence["id"]}/jobs/{job["id"]}').json()
            assert progress["status"] == "running" and progress["completed_steps"] == 1
            assert len(progress["result_steps"]) == 1
            if edit == "sequence":
                changed = c.put('/api/sequences/' + sequence["id"], json={"revision": 1, "name": "My newer plan"})
            elif edit == "draft":
                copied = sequence["steps"][0]["draft"]
                changed = c.put('/api/drafts/' + copied["id"], json={**copied, "subject": "My newer email"})
            else:
                changed = c.put('/api/contacts/' + contact["id"], json={"name": "Changed recipient"})
            assert changed.status_code == 200, changed.text
        finally:
            release.set()
        assert future.result(timeout=5)
    saved = c.get('/api/sequences/' + sequence["id"]).json()
    assert saved["generation"]["status"] == "failed"
    assert [step["id"] for step in saved["steps"]] == [step["id"] for step in sequence["steps"]]
    if edit == "sequence":
        assert saved["name"] == "My newer plan"
    elif edit == "draft":
        assert saved["steps"][0]["draft"]["subject"] == "My newer email"


@pytest.mark.parametrize("bad_step", [0, 1])
def test_invalid_ai_result_fails_without_fallback_and_can_retry(paused_client, monkeypatch, bad_step):
    c = paused_client
    sequence = create(c, template_id="default-reconnect")
    original = MockAI.complete
    monkeypatch.setattr(MockAI, 'complete', lambda self, task, data:
        {"title": "bad", "delay_days": -4} if data["step_index"] == bad_step else original(self, task, data))
    job = queue(c, sequence)
    process_sequence_job(job["id"])
    saved = c.get('/api/sequences/' + sequence["id"]).json()
    assert saved["generation"]["status"] == "failed" and saved["revision"] == 1
    assert saved["generation"]["completed_steps"] == bad_step
    assert saved["steps"] == sequence["steps"]
    monkeypatch.setattr(MockAI, 'complete', original)
    retry = queue(c, saved)
    assert retry["id"] != job["id"]
    process_sequence_job(retry["id"])
    assert c.get('/api/sequences/' + sequence["id"]).json()["generation"]["status"] == "succeeded"


def test_recovery_never_replays_interrupted_provider_requests(paused_client):
    sequence = create(paused_client)
    job = queue(paused_client, sequence)
    with Session() as db:
        saved = db.get(SequenceJob, job["id"])
        saved.status = "running"
        saved.completed_steps = 1
        saved.result_steps = [{"title": "Partial result"}]
        db.commit()
    recover_sequence_jobs()
    recovered = paused_client.get(f'/api/sequences/{sequence["id"]}/jobs/{job["id"]}').json()
    assert recovered["status"] == "failed" and recovered["completed_steps"] == 1
    assert "may have completed" in recovered["error"]
    assert not process_sequence_job(job["id"])


def test_live_plan_uses_configured_provider_and_never_mock_fallback(paused_client, monkeypatch):
    c = paused_client
    monkeypatch.setattr(settings, "ai_mode", "live")
    monkeypatch.setattr(settings, "ai_api_key", "test-only-key")
    calls = []
    original = MockAI.complete

    def compatible(self, task, data):
        calls.append((task, data["_model"], data["step_index"]))
        return original(self, task, data)

    monkeypatch.setattr(CompatibleAI, "complete", compatible)
    monkeypatch.setattr(MockAI, "complete", lambda *args: pytest.fail("Live mode used mock fallback"))
    sequence = create(c)
    job = queue(c, sequence, step_count=2)
    process_sequence_job(job["id"])
    saved = c.get('/api/sequences/' + sequence["id"]).json()
    assert saved["generation"]["status"] == "succeeded", saved["generation"]
    assert calls == [("sequence_step", job["model"], 0), ("sequence_step", job["model"], 1)]
    assert all(step["draft"]["generation_provider"] == "live" for step in saved["steps"])


def test_live_plan_missing_key_fails_before_any_job_or_provider_call(paused_client, monkeypatch):
    c = paused_client
    monkeypatch.setattr(settings, "ai_mode", "live")
    monkeypatch.setattr(settings, "ai_api_key", "")
    monkeypatch.setattr(CompatibleAI, "complete", lambda *args: pytest.fail("Called unconfigured provider"))
    sequence = create(c)
    response = c.post(f'/api/sequences/{sequence["id"]}/ai-plan', json={
        "revision": 1, "prompt": "Create a brief sequence", "step_count": 2})
    assert response.status_code == 503
    saved = c.get('/api/sequences/' + sequence["id"]).json()
    assert saved["revision"] == 1 and saved["generation"] is None
