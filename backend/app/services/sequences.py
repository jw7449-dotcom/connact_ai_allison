"""Persistent, ordered email planning with explicit local review and no sending."""

from copy import deepcopy
from threading import Event, Lock, Thread
from types import SimpleNamespace
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError
from ..config import settings
from ..db import Session, WorkspaceRepository
from ..models import Contact, Draft, Persona, now
from ..sequence_models import Sequence, SequenceStep, SequenceTemplate, SequenceJob
from ..sequence_schemas import StepInput, TemplateInput, TemplateStep
from ..providers.ai import CompatibleAI, MockAI
from ..providers.model_registry import resolve_route
from .contacts import row
from .drafts import sanitize, plain_text, preview, validate_email


DEFAULT_TEMPLATES = [
    {"id": "default-networking", "schema_version": 1, "name": "Networking", "description": "Introduce yourself, follow up, and close the loop respectfully.", "is_default": True, "steps": [
        {"title": "Introduction", "purpose": "Introduce yourself and ask for a short conversation.", "delay_days": 0, "thread_mode": "new_thread", "subject": "A brief introduction", "body_html": "<p>Hi {{name}},</p><p>I would appreciate the opportunity to learn about your work at {{company}}. Would you be open to a brief conversation?</p><p>Best,<br>{{sender_name}}</p>"},
        {"title": "Gentle follow-up", "purpose": "Follow up once with a specific, low-pressure request.", "delay_days": 4, "thread_mode": "reply", "subject": "", "body_html": "<p>Hi {{name}},</p><p>I wanted to follow up on my note. If you have time, I would appreciate a brief conversation about your experience. I understand if your schedule is full.</p><p>Best,<br>{{sender_name}}</p>"},
        {"title": "Close the loop", "purpose": "Thank the recipient and end the outreach politely.", "delay_days": 7, "thread_mode": "reply", "subject": "", "body_html": "<p>Hi {{name}},</p><p>Thank you for considering my request. I will leave it here, and would be glad to connect if a better time comes up.</p><p>Best,<br>{{sender_name}}</p>"},
    ]},
    {"id": "default-recruiting", "schema_version": 1, "name": "Recruiting", "description": "Express interest, ask about the right process, then make a final follow-up.", "is_default": True, "steps": [
        {"title": "Express interest", "purpose": "Introduce your career interests without assuming there is an open role.", "delay_days": 0, "thread_mode": "new_thread", "subject": "Learning about {{company}}", "body_html": "<p>Hi {{name}},</p><p>I am interested in learning more about your team at {{company}}. Could you point me toward the appropriate place to learn about opportunities and the application process?</p><p>Best,<br>{{sender_name}}</p>"},
        {"title": "Ask about the process", "purpose": "Ask for guidance on the appropriate application channel.", "delay_days": 5, "thread_mode": "reply", "subject": "", "body_html": "<p>Hi {{name}},</p><p>I wanted to follow up on my interest in {{company}}. If someone else is better placed to advise on the application process, I would appreciate being pointed in the right direction.</p><p>Best,<br>{{sender_name}}</p>"},
        {"title": "Final follow-up", "purpose": "Close the outreach without pressure or an assumed hiring opportunity.", "delay_days": 7, "thread_mode": "reply", "subject": "", "body_html": "<p>Hi {{name}},</p><p>Thank you for your time. I will continue following the published opportunities at {{company}}, and appreciate your consideration.</p><p>Best,<br>{{sender_name}}</p>"},
    ]},
    {"id": "default-reconnect", "schema_version": 1, "name": "Reconnect", "description": "Open a conversation without inventing a prior relationship, then follow up once.", "is_default": True, "steps": [
        {"title": "Open a conversation", "purpose": "Reach out warmly; add genuine prior context only if supplied.", "delay_days": 0, "thread_mode": "new_thread", "subject": "An opportunity to connect", "body_html": "<p>Hi {{name}},</p><p>I hope you are doing well. I would welcome the opportunity to connect and hear about your current work. Would a brief conversation be possible?</p><p>Best,<br>{{sender_name}}</p>"},
        {"title": "Keep the door open", "purpose": "Follow up respectfully and leave the timing to the recipient.", "delay_days": 7, "thread_mode": "reply", "subject": "", "body_html": "<p>Hi {{name}},</p><p>I wanted to follow up on my note. There is no rush; if a conversation would be useful, I would be happy to find a time that works for you.</p><p>Best,<br>{{sender_name}}</p>"},
    ]},
]


def steps_for(repo, sequence_id):
    return repo.session.scalars(repo.query(SequenceStep).where(
        SequenceStep.sequence_id == sequence_id).order_by(SequenceStep.position, SequenceStep.id)).all()


def template_json(template):
    return {**row(template), "is_default": False}


def get_template(repo, template_id):
    for template in DEFAULT_TEMPLATES:
        if template["id"] == template_id:
            return deepcopy(template)
    return template_json(repo.get(SequenceTemplate, template_id))


def create_template(repo, body):
    steps = [step.model_dump() for step in body.steps]
    for step in steps:
        step["body_html"] = sanitize(step["body_html"])
    template = repo.add(SequenceTemplate, name=body.name, description=body.description,
                        schema_version=1, steps=steps)
    return template_json(template)


def locked(repo, sequence_id, revision):
    sequence = repo.session.scalar(repo.query(Sequence).where(
        Sequence.id == sequence_id).with_for_update())
    if not sequence:
        raise HTTPException(404, "Sequence not found in this workspace.")
    if sequence.revision != revision:
        raise HTTPException(409, "This sequence changed. Reopen the latest version before saving.")
    return sequence


def bump_revision(repo, sequence, revision):
    with repo.session.no_autoflush:
        changed = repo.session.execute(update(Sequence).where(
            Sequence.id == sequence.id, Sequence.workspace_id == repo.workspace_id,
            Sequence.revision == revision).values(revision=revision + 1, updated_at=now(),
                status="draft", review_snapshot={}).execution_options(synchronize_session=False))
    if not changed.rowcount:
        raise HTTPException(409, "This sequence changed. Reopen the latest version before saving.")
    repo.session.expire(sequence)
    repo.session.refresh(sequence)


def validate_context(repo, contact_id, persona_id):
    if contact_id:
        repo.get(Contact, contact_id)
    return repo.get(Persona, persona_id) if persona_id else None


def make_draft(repo, sequence, source_id=None, content=None):
    values = {}
    if source_id:
        source = repo.get(Draft, source_id)
        values = {c.name: deepcopy(getattr(source, c.name)) for c in Draft.__table__.columns
                  if c.name not in {"id", "workspace_id", "created_at", "updated_at", "revision", "status"}}
    persona = validate_context(repo, sequence.contact_id, sequence.persona_id)
    # A sequence has one preview recipient and sender. Source emails are independent copies.
    if values.get("contact_id") != sequence.contact_id:
        values["evidence_ids"] = []
    values.update(contact_id=sequence.contact_id, persona_id=sequence.persona_id,
                  persona_version=persona.version if persona else None, language=sequence.language,
                  status="draft", revision=1)
    if content:
        values.update(subject=content.get("subject", ""), body_html=sanitize(content.get("body_html", "<p></p>")),
                      purpose=content.get("purpose", ""))
    return repo.add(Draft, **values)


def replace_steps(repo, sequence, supplied):
    old = {step.id: step for step in steps_for(repo, sequence.id)}
    seen = set()
    for position, value in enumerate(supplied):
        data = value.model_dump() if hasattr(value, "model_dump") else value
        purpose_supplied = "purpose" in (value.model_fields_set if hasattr(value, "model_fields_set") else value)
        step_id, draft_id = data.get("id"), data.get("draft_id")
        previous_purpose = None
        if step_id:
            if step_id not in old:
                raise HTTPException(422, "A step does not belong to this sequence.")
            if step_id in seen:
                raise HTTPException(422, "A sequence cannot contain the same step twice.")
            step = old[step_id]
            previous_purpose = step.purpose
            seen.add(step_id)
            if draft_id and draft_id != step.draft_id:
                step.draft_id = make_draft(repo, sequence, draft_id).id
        else:
            draft = make_draft(repo, sequence, draft_id, data if not draft_id else None)
            step = repo.add(SequenceStep, sequence_id=sequence.id, draft_id=draft.id,
                            position=position, title=data["title"])
        draft = repo.get(Draft, step.draft_id)
        if not purpose_supplied:
            data["purpose"] = previous_purpose if previous_purpose is not None else draft.purpose
        elif data["purpose"] != previous_purpose and data["purpose"] != draft.purpose:
            changed = repo.session.execute(update(Draft).where(Draft.id == draft.id,
                Draft.workspace_id == repo.workspace_id, Draft.revision == draft.revision)
                .values(purpose=data["purpose"], status="draft", revision=draft.revision + 1, updated_at=now())
                .execution_options(synchronize_session=False))
            if not changed.rowcount:
                raise HTTPException(409, "A sequence email changed. Reload before changing its brief.")
            repo.session.expire(draft)
        for key in ("title", "purpose", "delay_days", "thread_mode"):
            setattr(step, key, data[key])
        step.position = position
    for step_id, step in old.items():
        if step_id not in seen:
            repo.session.delete(step)
    repo.session.flush()


def create_sequence(repo, body):
    contact_id, persona_id = body.contact_id, body.persona_id
    if body.draft_ids:
        first = repo.get(Draft, body.draft_ids[0])
        contact_id = contact_id or first.contact_id
        persona_id = persona_id or first.persona_id
    validate_context(repo, contact_id, persona_id)
    sequence = repo.add(Sequence, name=body.name, description=body.description,
                        language=body.language, contact_id=contact_id, persona_id=persona_id)
    if body.template_id:
        template = get_template(repo, body.template_id)
        replace_steps(repo, sequence, template["steps"])
    elif body.draft_ids:
        replace_steps(repo, sequence, [StepInput(draft_id=id, title=f"Email {index + 1}",
            delay_days=0 if index == 0 else 3, thread_mode="new_thread" if index == 0 else "reply")
            for index, id in enumerate(body.draft_ids)])
    return sequence


def context_snapshot(repo, sequence):
    contact = repo.get(Contact, sequence.contact_id) if sequence.contact_id else None
    persona = repo.get(Persona, sequence.persona_id) if sequence.persona_id else None
    return {
        "contact_id": sequence.contact_id, "persona_id": sequence.persona_id,
        "recipient_email": contact.email if contact else "",
        "contact": {key: getattr(contact, key) for key in ("name", "title", "company", "school", "location")} if contact else {},
        "contact_provenance": contact.provider if contact else None,
        "persona": deepcopy(persona.data) if persona else {},
        "persona_version": persona.version if persona else None,
        "draft_revisions": [{"step_id": step.id, "draft_id": step.draft_id,
            "revision": repo.get(Draft, step.draft_id).revision} for step in steps_for(repo, sequence.id)],
    }


def sequence_preview(repo, sequence):
    results, sequence_issues = [], []
    day, thread_subject = 0, ""
    for index, step in enumerate(steps_for(repo, sequence.id)):
        draft = repo.get(Draft, step.draft_id)
        day += step.delay_days
        issues = []
        if index == 0 and (step.delay_days != 0 or step.thread_mode != "new_thread"):
            issues.append("The first email must start a new thread on day 0.")
        if step.thread_mode == "new_thread":
            thread_subject = draft.subject
        effective_subject = thread_subject if step.thread_mode == "new_thread" else (
            thread_subject if thread_subject.lower().startswith("re:") else "Re: " + thread_subject)
        shadow = SimpleNamespace(**{**row(draft), "subject": effective_subject if thread_subject.strip() else ""})
        rendered = preview(repo, shadow)
        if not draft.contact_id:
            issues.append("Choose a recipient.")
        if not thread_subject.strip():
            issues.append("Add a subject to the first email in this thread.")
        if not plain_text(draft.body_html):
            issues.append("Add email content.")
        if rendered["missing_variables"]:
            issues.append("Resolve variables: " + ", ".join(rendered["missing_variables"]) + ".")
        if rendered["persona_changed"]:
            issues.append("The sender profile changed. Review and save this email again.")
        results.append({"step_id": step.id, "draft_id": draft.id, "position": index,
                        "title": step.title, "cumulative_day": day,
                        "effective_subject": rendered["subject"], "issues": issues, "preview": rendered})
    if not results:
        sequence_issues.append("Add at least one email step.")
    return {"can_mark_ready": bool(results) and not sequence_issues and all(not r["issues"] for r in results),
            "steps": results, "issues": sequence_issues,
            "note": "This is a local sequence plan. No email is sent or scheduled."}


def job_json(job):
    return {k: v for k, v in row(job).items() if k != "snapshot"}


def sequence_json(repo, sequence, detail=True):
    data = row(sequence)
    snapshot = data.pop("review_snapshot", {})
    data["review_stale"] = sequence.status == "ready" and snapshot != context_snapshot(repo, sequence)
    if data["review_stale"]:
        data["status"] = "draft"
    steps = steps_for(repo, sequence.id)
    data.update(step_count=len(steps), total_days=sum(step.delay_days for step in steps))
    latest = repo.session.scalar(repo.query(SequenceJob).where(SequenceJob.sequence_id == sequence.id)
                                  .order_by(SequenceJob.created_at.desc()).limit(1))
    data["generation"] = job_json(latest) if latest else None
    if detail:
        data["steps"] = [{**row(step), "draft": row(repo.get(Draft, step.draft_id))} for step in steps]
    return data


def update_sequence(repo, sequence_id, body):
    sequence = locked(repo, sequence_id, body.revision)
    values = body.model_dump(exclude_unset=True, exclude={"revision", "steps", "status"})
    validate_context(repo, values.get("contact_id", sequence.contact_id), values.get("persona_id", sequence.persona_id))
    bump_revision(repo, sequence, body.revision)
    for key, value in values.items():
        setattr(sequence, key, value)
    if "steps" in body.model_fields_set:
        replace_steps(repo, sequence, body.steps)
    if set(values) & {"contact_id", "persona_id", "language"}:
        persona = repo.get(Persona, sequence.persona_id) if sequence.persona_id else None
        for step in steps_for(repo, sequence.id):
            draft = repo.get(Draft, step.draft_id)
            changes = {"revision": draft.revision + 1, "status": "draft", "updated_at": now()}
            if "contact_id" in values:
                changes.update(contact_id=sequence.contact_id)
                if draft.contact_id != sequence.contact_id:
                    changes["evidence_ids"] = []
            if "persona_id" in values:
                changes.update(persona_id=sequence.persona_id, persona_version=persona.version if persona else None)
            if "language" in values:
                changes["language"] = sequence.language
            changed = repo.session.execute(update(Draft).where(Draft.id == draft.id,
                Draft.workspace_id == repo.workspace_id, Draft.revision == draft.revision).values(**changes)
                .execution_options(synchronize_session=False))
            if not changed.rowcount:
                raise HTTPException(409, "A sequence email changed. Reload before applying these settings.")
            repo.session.expire(draft)
    repo.session.flush()
    if body.status == "ready":
        if not sequence_preview(repo, sequence)["can_mark_ready"]:
            raise HTTPException(422, "Review every step: complete the recipient, subject, content and variables first.")
        sequence.status = "ready"
        sequence.review_snapshot = context_snapshot(repo, sequence)
    return sequence


def create_plan_job(repo, sequence, body):
    route = resolve_route(body.model)
    if settings.ai_mode == "live" and not route.configured:
        raise HTTPException(503, f"{route.provider_label}: configure an API key or choose another model.")
    pending = repo.all(SequenceJob, SequenceJob.sequence_id == sequence.id, SequenceJob.status.in_(["queued", "running"]))
    if pending:
        return pending[0]
    if len(repo.all(SequenceJob, SequenceJob.status.in_(["queued", "running"]))) >= 5:
        raise HTTPException(429, "Five sequence plans are pending. Wait for one to finish.")
    snapshot = context_snapshot(repo, sequence)
    snapshot.update(prompt=body.prompt, language=body.language or sequence.language,
                    sequence_name=sequence.name, description=sequence.description,
                    prompt_version="sequence-steps-v1")
    try:
        with repo.session.begin_nested():
            return repo.add(SequenceJob, sequence_id=sequence.id, sequence_revision=sequence.revision,
                status="queued", mode=settings.ai_mode, provider=route.provider, model=route.id,
                snapshot=snapshot, total_steps=body.step_count)
    except IntegrityError:
        pending = repo.all(SequenceJob, SequenceJob.sequence_id == sequence.id, SequenceJob.status.in_(["queued", "running"]))
        if pending:
            return pending[0]
        raise


def validate_ai_step(result, index):
    try:
        step = TemplateStep.model_validate(result)
    except (ValidationError, TypeError):
        raise HTTPException(502, f"AI returned an invalid step {index + 1}. The saved sequence is unchanged.")
    if index == 0 and (step.thread_mode != "new_thread" or step.delay_days != 0):
        raise HTTPException(502, "AI returned an invalid first step. It must start a new thread on day 0.")
    if not plain_text(step.body_html) or (step.thread_mode == "new_thread" and not step.subject.strip()):
        raise HTTPException(502, f"AI returned an empty email at step {index + 1}. The saved sequence is unchanged.")
    email = validate_email({"subject": step.subject or "Reply", "body_html": step.body_html})
    return {**step.model_dump(), "subject": email["subject"] if step.subject else "", "body_html": email["body_html"]}


def process_sequence_job(job_id):
    with Session() as db:
        claimed = db.execute(update(SequenceJob).where(SequenceJob.id == job_id, SequenceJob.status == "queued")
            .values(status="running", started_at=now(), error=None))
        if not claimed.rowcount:
            db.rollback()
            return False
        job = db.get(SequenceJob, job_id)
        data, mode, model, provider_name = deepcopy(job.snapshot), job.mode, job.model, job.provider
        total, workspace_id, sequence_id, revision = job.total_steps, job.workspace_id, job.sequence_id, job.sequence_revision
        db.commit()
    try:
        route = resolve_route(model)
        if mode != settings.ai_mode or provider_name != route.provider or data.get("prompt_version") != "sequence-steps-v1":
            raise HTTPException(409, "AI configuration changed. Create a fresh sequence plan.")
        provider = MockAI() if mode == "mock" else CompatibleAI()
        provider_data = {key: data[key] for key in ("prompt", "language", "sequence_name", "description",
            "contact", "contact_provenance", "persona")}
        generated = []
        for index in range(total):
            # Each provider response is persisted before the next request. This is step progress,
            # not simulated token streaming, and no DB lock is held during network I/O.
            result = provider.complete("sequence_step", {**provider_data, "_model": model,
                "step_index": index, "step_count": total, "previous_steps": generated})
            generated.append(validate_ai_step(result, index))
            with Session() as db:
                changed = db.execute(update(SequenceJob).where(SequenceJob.id == job_id, SequenceJob.status == "running")
                    .values(completed_steps=len(generated), result_steps=deepcopy(generated)))
                db.commit()
                if not changed.rowcount:
                    return True
        with Session() as db:
            repo = WorkspaceRepository(db, workspace_id)
            sequence = locked(repo, sequence_id, revision)
            # Claim the sequence write and every previously linked email before validating
            # the snapshot. This closes the final read/write race on both SQLite and PostgreSQL.
            bump_revision(repo, sequence, revision)
            for expected in data["draft_revisions"]:
                changed = db.execute(update(Draft).where(Draft.id == expected["draft_id"],
                    Draft.workspace_id == workspace_id, Draft.revision == expected["revision"])
                    .values(revision=Draft.revision, updated_at=Draft.updated_at)
                    .execution_options(synchronize_session=False))
                if not changed.rowcount:
                    raise HTTPException(409, "A sequence email changed during generation. Your edits are preserved; generate a fresh plan.")
            for model_cls, record_id in ((Contact, sequence.contact_id), (Persona, sequence.persona_id)):
                if record_id:
                    db.execute(update(model_cls).where(model_cls.id == record_id,
                        model_cls.workspace_id == workspace_id).values(updated_at=model_cls.updated_at)
                        .execution_options(synchronize_session=False))
            frozen = {key: data[key] for key in context_snapshot(repo, sequence)}
            if context_snapshot(repo, sequence) != frozen:
                raise HTTPException(409, "A sequence email, recipient or sender changed during generation. Your edits are preserved; generate a fresh plan.")
            sequence.language = data["language"]
            replace_steps(repo, sequence, generated)
            for step in steps_for(repo, sequence.id):
                draft = repo.get(Draft, step.draft_id)
                draft.model, draft.generation_provider = model, mode
            changed = db.execute(update(SequenceJob).where(SequenceJob.id == job_id, SequenceJob.status == "running")
                .values(status="succeeded", completed_at=now(), error=None))
            if not changed.rowcount:
                db.rollback()
                return True
            db.commit()
    except Exception as exc:
        error = str(exc.detail) if isinstance(exc, HTTPException) else "Sequence generation failed unexpectedly. Your saved sequence is unchanged. Try generating again."
        # Provider messages are already sanitized, and redact configured credentials defensively.
        try:
            key = resolve_route(model).api_key
            if key:
                error = error.replace(key, "[redacted]")
        except Exception:
            pass
        with Session() as db:
            db.execute(update(SequenceJob).where(SequenceJob.id == job_id, SequenceJob.status == "running")
                .values(status="failed", error=error, completed_at=now()))
            db.commit()
    return True


def recover_sequence_jobs():
    with Session() as db:
        db.execute(update(SequenceJob).where(SequenceJob.status == "running").values(status="failed",
            completed_at=now(), error="The server restarted during generation. Your sequence is unchanged. Generate again to retry; prior provider requests may have completed."))
        db.commit()


_worker = None
_guard, _wake, _stop = Lock(), Event(), Event()


def wake_sequence_worker():
    _wake.set()


def _sequence_loop():
    while not _stop.is_set():
        try:
            with Session() as db:
                job_id = db.scalar(select(SequenceJob.id).where(SequenceJob.status == "queued")
                    .order_by(SequenceJob.created_at).limit(1))
            if job_id:
                process_sequence_job(job_id)
                continue
        except Exception:
            pass
        _wake.wait(1)
        _wake.clear()


def start_sequence_worker():
    global _worker
    with _guard:
        if _worker and _worker.is_alive():
            return
        recover_sequence_jobs()
        _stop.clear()
        _wake.clear()
        _worker = Thread(target=_sequence_loop, name="sequence-jobs", daemon=True)
        _worker.start()


def stop_sequence_worker():
    _stop.set()
    _wake.set()
    if _worker:
        _worker.join(timeout=5)
