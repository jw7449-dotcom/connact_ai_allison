import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from fastapi import HTTPException
from app.config import settings
from app.db import Session
from app.models import Contact, Draft, SourceEvidence, Workspace, WritingJob
from app.providers.ai import CompatibleAI, MockAI
from app.services.drafts import (
    process_writing_job,
    recover_writing_jobs,
    start_writing_worker,
    stop_writing_worker,
)


@pytest.fixture
def paused_client(client):
    stop_writing_worker()
    yield client
    stop_writing_worker()


def make_draft(client, **data):
    r = client.post(
        "/api/drafts", json={"purpose": "Learn about a career transition", **data}
    )
    assert r.status_code == 200, r.text
    return r.json()


def queue(client, draft, action="generate"):
    r = client.post(
        f'/api/drafts/{draft["id"]}/generations',
        json={"revision": draft["revision"], "action": action},
    )
    assert r.status_code == 202, r.text
    return r.json()


def test_brief_survives_reload_and_suggestion_requires_review(paused_client):
    c = paused_client
    model = c.get("/api/ai/models").json()["default_model"]
    d = make_draft(
        c,
        model=model,
        length="short",
        cta="Could we arrange 15 minutes?",
        custom_instructions="Use plain language",
    )
    j = queue(c, d)
    assert queue(c, d)["id"] == j["id"]
    assert j["snapshot"]["persona"] == {} and j["snapshot"]["contact"] == {}
    assert j["snapshot"]["source_ids"] == []
    assert process_writing_job(j["id"])
    assert not process_writing_job(j["id"])
    saved = c.get("/api/drafts/" + d["id"]).json()
    assert saved["body_html"] == d["body_html"] and saved["revision"] == 1
    assert (
        saved["cta"] == d["cta"]
        and saved["custom_instructions"] == d["custom_instructions"]
    )
    result = c.get(f'/api/drafts/{d["id"]}/generations/{j["id"]}').json()
    assert result["status"] == "succeeded" and result["result"]["body_html"]
    assert "{{name}}" not in result["result"]["body_html"]
    accepted = c.post(
        f'/api/drafts/{d["id"]}/generations/{j["id"]}/accept', json={"revision": 1}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["revision"] == 2 and accepted.json()["model"] == model
    assert c.get(f'/api/drafts/{d["id"]}/generations').json()[0]["status"] == "accepted"


def test_editing_during_provider_call_is_unlocked_and_cannot_be_overwritten(
    paused_client, monkeypatch
):
    c = paused_client
    started, release = Event(), Event()

    def delayed(self, task, data):
        started.set()
        assert release.wait(5)
        return {"subject": "Suggestion", "body_html": "<p>Generated message</p>"}

    monkeypatch.setattr(MockAI, "complete", delayed)
    d = make_draft(c)
    j = queue(c, d)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(process_writing_job, j["id"])
        assert started.wait(2)
        try:
            changed = c.put(
                "/api/drafts/" + d["id"],
                json={**d, "body_html": "<p>My newer edit</p>"},
            )
            assert changed.status_code == 200, changed.text
        finally:
            release.set()
        assert future.result(timeout=3)
    assert (
        c.post(
            f'/api/drafts/{d["id"]}/generations/{j["id"]}/accept', json={"revision": 2}
        ).status_code
        == 409
    )
    assert c.get("/api/drafts/" + d["id"]).json()["body_html"] == "<p>My newer edit</p>"
    assert (
        c.get(f'/api/drafts/{d["id"]}/generations/{j["id"]}').json()["snapshot"][
            "body_html"
        ]
        == d["body_html"]
    )


def test_selected_evidence_scoped_frozen_and_contact_changes_are_stale(paused_client):
    c = paused_client
    contact = c.post(
        "/api/contacts", json={"name": "Jordan", "company": "Example"}
    ).json()
    other = c.post("/api/contacts", json={"name": "Other"}).json()
    with Session() as db:
        source = SourceEvidence(
            workspace_id=settings.workspace_id,
            contact_id=contact["id"],
            provider="manual",
            title="Career biography",
            snippet="Worked in research",
            kind="manual",
        )
        wrong = SourceEvidence(
            workspace_id=settings.workspace_id,
            contact_id=other["id"],
            provider="manual",
            title="Other",
            snippet="Unrelated",
            kind="manual",
        )
        db.add_all([source, wrong])
        db.commit()
        source_id, wrong_id = source.id, wrong.id
    assert (
        c.post(
            "/api/drafts",
            json={"contact_id": contact["id"], "evidence_ids": [wrong_id]},
        ).status_code
        == 422
    )
    d = make_draft(c, contact_id=contact["id"], evidence_ids=[source_id])
    j = queue(c, d)
    assert j["snapshot"]["evidence"][0]["snippet"] == "Worked in research"
    process_writing_job(j["id"])
    c.put(
        "/api/contacts/" + contact["id"],
        json={"name": "Jordan", "company": "New Example"},
    )
    assert (
        c.post(
            f'/api/drafts/{d["id"]}/generations/{j["id"]}/accept',
            json={"revision": d["revision"]},
        ).status_code
        == 409
    )
    with Session() as db:
        db.add(Workspace(id="other-writing", name="Other"))
        db.flush()
        alien = Draft(workspace_id="other-writing", purpose="private")
        db.add(alien)
        db.commit()
        alien_id = alien.id
    assert c.get(f"/api/drafts/{alien_id}/generations").status_code == 404
    unrelated = make_draft(c)
    assert (
        c.get(f'/api/drafts/{unrelated["id"]}/generations/{j["id"]}').status_code == 404
    )


def test_failed_and_discarded_jobs_preserve_draft_and_sanitize_results(
    paused_client, monkeypatch
):
    c = paused_client
    d = make_draft(c, subject="Saved subject", body_html="<p>Saved body</p>")

    def fail(self, task, data):
        raise HTTPException(502, "Provider temporarily unavailable")

    monkeypatch.setattr(MockAI, "complete", fail)
    j = queue(c, d)
    process_writing_job(j["id"])
    assert (
        c.get(f'/api/drafts/{d["id"]}/generations/{j["id"]}').json()["status"]
        == "failed"
    )
    assert c.get("/api/drafts/" + d["id"]).json()["body_html"] == d["body_html"]
    monkeypatch.setattr(
        MockAI,
        "complete",
        lambda *args: {
            "subject": "Safe",
            "body_html": '<p onclick="alert(1)">Hi</p><script>bad()</script><a href="javascript:alert(1)">link</a>',
        },
    )
    j = queue(c, d)
    process_writing_job(j["id"])
    result = c.get(f'/api/drafts/{d["id"]}/generations/{j["id"]}').json()["result"][
        "body_html"
    ]
    assert (
        "onclick" not in result
        and "<script>" not in result
        and "javascript:" not in result
    )
    assert (
        c.post(f'/api/drafts/{d["id"]}/generations/{j["id"]}/discard').json()["status"]
        == "discarded"
    )
    assert (
        c.post(
            f'/api/drafts/{d["id"]}/generations/{j["id"]}/accept', json={"revision": 1}
        ).status_code
        == 409
    )


def test_restart_recovery_resumes_queued_and_does_not_rebill_interrupted(paused_client):
    c = paused_client
    d = make_draft(c)
    queued = queue(c, d)
    second = make_draft(c)
    running = queue(c, second)
    with Session() as db:
        db.get(WritingJob, running["id"]).status = "running"
        db.commit()
    recover_writing_jobs()
    interrupted = c.get(
        f'/api/drafts/{second["id"]}/generations/{running["id"]}'
    ).json()
    assert (
        interrupted["status"] == "failed"
        and "may have completed" in interrupted["error"]
    )
    start_writing_worker()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = c.get(f'/api/drafts/{d["id"]}/generations/{queued["id"]}').json()
        if result["status"] == "succeeded":
            break
        time.sleep(0.02)
    assert result["status"] == "succeeded"
    assert c.get("/api/drafts/" + d["id"]).json()["revision"] == 1


def test_model_allowlist_and_bailian_payload(paused_client, monkeypatch):
    import importlib

    ai_module = importlib.import_module("app.providers.ai")
    monkeypatch.setattr(settings, "ai_models", "qwen-plus,qwen-turbo")
    monkeypatch.setattr(settings, "ai_model", "qwen-plus")
    monkeypatch.setattr(
        settings, "ai_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    assert (
        paused_client.post(
            "/api/drafts", json={"model": "arbitrary-expensive-model"}
        ).status_code
        == 422
    )
    captured = {}

    def request(*args, **kwargs):
        captured.update(kwargs["json"])
        return {
            "choices": [
                {"message": {"content": '{"subject":"Hello","body_html":"<p>Hi</p>"}'}}
            ]
        }

    monkeypatch.setattr(ai_module, "request_json", request)
    CompatibleAI().complete("generate", {"_model": "qwen-turbo", "purpose": "Connect"})
    assert captured["model"] == "qwen-turbo" and captured["enable_thinking"] is False
    assert "_model" not in captured["messages"][1]["content"]
    assert captured["response_format"] == {"type": "json_object"}


def test_prompt_and_template_modes_are_independent_and_persisted(paused_client):
    c = paused_client
    prompt = make_draft(
        c,
        purpose="",
        writing_mode="prompt",
        custom_instructions="Ask for a short career conversation",
    )
    j = queue(c, prompt)
    assert j["snapshot"]["writing_mode"] == "prompt"
    process_writing_job(j["id"])
    assert (
        c.get(f'/api/drafts/{prompt["id"]}/generations/{j["id"]}').json()["status"]
        == "succeeded"
    )
    template = make_draft(
        c,
        purpose="",
        writing_mode="template",
        subject="A reusable message",
        body_html="<p>I would value your career advice.</p>",
    )
    j = queue(c, template)
    process_writing_job(j["id"])
    result = c.get(f'/api/drafts/{template["id"]}/generations/{j["id"]}').json()[
        "result"
    ]
    assert result["body_html"] == template["body_html"]
    assert c.get("/api/drafts/" + template["id"]).json()["writing_mode"] == "template"
    empty = make_draft(c, purpose="", writing_mode="prompt", custom_instructions="")
    assert (
        c.post(
            f'/api/drafts/{empty["id"]}/generations', json={"revision": 1}
        ).status_code
        == 422
    )


def test_cancel_while_running_does_not_resurrect_result(paused_client, monkeypatch):
    c = paused_client
    started, release = Event(), Event()

    def delayed(self, task, data):
        started.set()
        assert release.wait(5)
        return {"subject": "Suggestion", "body_html": "<p>Ignore after discard</p>"}

    monkeypatch.setattr(MockAI, "complete", delayed)
    d = make_draft(c)
    j = queue(c, d)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(process_writing_job, j["id"])
        assert started.wait(2)
        try:
            assert (
                c.post(f'/api/drafts/{d["id"]}/generations/{j["id"]}/discard').json()[
                    "status"
                ]
                == "discarded"
            )
        finally:
            release.set()
        future.result(timeout=3)
    result = c.get(f'/api/drafts/{d["id"]}/generations/{j["id"]}').json()
    assert result["status"] == "discarded" and result["result"] is None


def test_model_bracket_placeholders_remain_visible_as_missing_variables(
    paused_client, monkeypatch
):
    c = paused_client
    monkeypatch.setattr(
        MockAI,
        "complete",
        lambda *args: {
            "subject": "Hello [Name]",
            "body_html": "<p>Dear [Recipient Name],</p><p>Regards, [Your Name]</p>",
        },
    )
    d = make_draft(c)
    j = queue(c, d)
    process_writing_job(j["id"])
    r = c.post(
        f'/api/drafts/{d["id"]}/generations/{j["id"]}/accept', json={"revision": 1}
    )
    assert r.status_code == 200
    preview = c.get(f'/api/drafts/{d["id"]}/preview').json()
    assert preview["missing_variables"] == ["name", "sender_name"]
    assert not preview["can_mark_ready"]
