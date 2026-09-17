import re
from copy import deepcopy
from threading import Event, Lock, Thread
from html import escape, unescape
import bleach
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from ..models import Contact, Persona, SourceEvidence, WritingJob, now
from ..db import Session
from ..config import settings
from ..providers.ai import CompatibleAI, MockAI, PROMPT_VERSION, resolve_model

TAGS = ["p", "br", "strong", "b", "em", "ul", "ol", "li", "a"]
VARIABLE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def sanitize(body):
    return bleach.clean(
        body,
        tags=TAGS,
        attributes={"a": ["href", "title"]},
        protocols=["http", "https", "mailto"],
        strip=True,
    )


def plain_text(body):
    body = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
    body = re.sub(r"</(p|li)>", "\n\n", body, flags=re.I)
    return unescape(bleach.clean(body, tags=[], strip=True)).strip()


def preview(repo, draft):
    contact = repo.get(Contact, draft.contact_id) if draft.contact_id else None
    persona = repo.get(Persona, draft.persona_id) if draft.persona_id else None
    variables = {
        "name": contact.name if contact else "",
        "company": contact.company if contact else "",
        "title": contact.title if contact else "",
        "school": contact.school if contact else "",
        "sender_name": persona.data.get("name", "") if persona else "",
    }
    missing = set()

    def render(text, html=False):
        def replace(match):
            key = match.group(1).strip()
            value = variables.get(key)
            if not value:
                missing.add(key)
                return f"[MISSING: {escape(key)}]"
            return escape(value) if html else value

        return VARIABLE.sub(replace, text)

    subject = render(draft.subject)
    body = sanitize(render(draft.body_html, True))
    # Catch unfinished or malformed placeholder syntax too.
    if "{{" in subject + body or "}}" in subject + body:
        missing.add("malformed_variable")
    stale = bool(
        persona and draft.persona_version and persona.version != draft.persona_version
    )
    complete = bool(
        subject.strip() and plain_text(body) and contact and not missing and not stale
    )
    return {
        "subject": subject,
        "body_html": body,
        "body_text": plain_text(body),
        "missing_variables": sorted(missing),
        "variables": variables,
        "can_mark_ready": complete,
        "persona_changed": stale,
        "recipient_email": contact.email if contact else "",
        "note": "Ready means content reviewed. Sending requires a connected Gmail mailbox and explicit confirmation.",
    }


def writing_snapshot(repo, draft):
    """Freeze all context the writer can see. Selection is explicit and workspace scoped."""
    from .contacts import contact_json

    persona = repo.get(Persona, draft.persona_id) if draft.persona_id else None
    contact = repo.get(Contact, draft.contact_id) if draft.contact_id else None
    contact_data = contact_json(repo, contact) if contact else {}
    evidence = []
    for source_id in dict.fromkeys(draft.evidence_ids or []):
        source = repo.get(SourceEvidence, source_id)
        if not contact or source.contact_id != contact.id:
            raise HTTPException(
                422, "Selected evidence must belong to this draft's recipient."
            )
        evidence.append(
            {
                k: getattr(source, k)
                for k in ("id", "provider", "url", "title", "snippet", "kind")
            }
        )
    # Include the structured profile only when the user selected its source.
    professional = contact_data.get("professional") or contact_data.get(
        "domains", {}
    ).get("professional", {})
    professional = (
        professional
        if professional.get("source_id") in (draft.evidence_ids or [])
        else {}
    )
    return deepcopy(
        {
            "persona_id": persona.id if persona else None,
            "persona_version": persona.version if persona else None,
            "persona": persona.data if persona else {},
            "contact_id": contact.id if contact else None,
            "contact": (
                {
                    k: getattr(contact, k)
                    for k in (
                        "name",
                        "company",
                        "title",
                        "school",
                        "location",
                        "profile_url",
                    )
                }
                if contact
                else {}
            ),
            "contact_provenance": (
                "discovery"
                if contact and contact.provider == "serpapi"
                else (contact.provider if contact else None)
            ),
            "professional": professional,
            "source_ids": list(dict.fromkeys(draft.evidence_ids or [])),
            "evidence": evidence,
            **{
                k: getattr(draft, k)
                for k in (
                    "purpose",
                    "language",
                    "starting_point",
                    "tone",
                    "length",
                    "cta",
                    "custom_instructions",
                    "subject",
                    "body_html",
                    "writing_mode",
                )
            },
        }
    )


def create_writing_job(repo, draft, action):
    if (
        action == "generate"
        and draft.writing_mode == "assisted"
        and not draft.purpose.strip()
    ):
        raise HTTPException(422, "Enter a writing brief first.")
    if (
        action == "generate"
        and draft.writing_mode == "prompt"
        and not draft.custom_instructions.strip()
    ):
        raise HTTPException(422, "Enter your writing prompt first.")
    if (
        action == "generate"
        and draft.writing_mode == "template"
        and not plain_text(draft.body_html)
    ):
        raise HTTPException(422, "Write or paste an email template first.")
    if action != "generate" and not plain_text(draft.body_html):
        raise HTTPException(422, "Write or generate a message first.")
    model = resolve_model(draft.model)
    if settings.ai_mode == "live":
        from ..providers.model_registry import resolve_route

        route = resolve_route(model)
        if not route.configured:
            raise HTTPException(503, f"{route.provider_label}: API key is missing. Configure it on the server or choose another model.")
    snapshot = writing_snapshot(repo, draft)
    # A double click/retried HTTP request must not create a second billable call.
    pending = repo.all(
        WritingJob,
        WritingJob.draft_id == draft.id,
        WritingJob.draft_revision == draft.revision,
        WritingJob.action == action,
        WritingJob.status.in_(["queued", "running"]),
    )
    if pending:
        return pending[0]
    if len(repo.all(WritingJob, WritingJob.status.in_(["queued", "running"]))) >= 10:
        raise HTTPException(
            429,
            "Ten writing requests are pending. Wait for a result before generating again.",
        )
    try:
        with repo.session.begin_nested():
            return repo.add(
                WritingJob,
                draft_id=draft.id,
                draft_revision=draft.revision,
                action=action,
                status="queued",
                mode=settings.ai_mode,
                provider=getattr(settings, "ai_provider", "compatible"),
                model=model,
                prompt_version=PROMPT_VERSION,
                snapshot=snapshot,
            )
    except IntegrityError:
        pending = repo.all(
            WritingJob,
            WritingJob.draft_id == draft.id,
            WritingJob.draft_revision == draft.revision,
            WritingJob.action == action,
            WritingJob.status.in_(["queued", "running"]),
        )
        if pending:
            return pending[0]
        raise


def validate_email(result):
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("subject"), str)
        or not isinstance(result.get("body_html"), str)
    ):
        raise HTTPException(
            502, "AI returned an invalid email. Your draft is unchanged."
        )
    if not result["subject"].strip() or not plain_text(result["body_html"]):
        raise HTTPException(502, "AI returned an empty email. Your draft is unchanged.")
    if len(result["subject"]) > 1000 or len(result["body_html"]) > 60000:
        raise HTTPException(502, "AI response exceeds draft limits.")
    # Compatible models occasionally emit bracket placeholders despite the prompt.
    # Canonicalize known fields so the preview reliably blocks unresolved variables.
    aliases = {
        "name": "name",
        "first name": "name",
        "recipient name": "name",
        "your name": "sender_name",
        "sender name": "sender_name",
        "company": "company",
        "company name": "company",
        "title": "title",
        "school": "school",
    }

    def canonical(text):
        return re.sub(
            r"\[\s*([^\[\]]{1,30})\s*\]",
            lambda m: (
                "{{" + aliases[m.group(1).strip().lower()] + "}}"
                if m.group(1).strip().lower() in aliases
                else m.group(0)
            ),
            text,
        )

    return {
        "subject": canonical(result["subject"]),
        "body_html": sanitize(canonical(result["body_html"])),
    }


def process_writing_job(job_id):
    """Claim atomically, release the transaction, call the model, persist only a suggestion."""
    with Session() as db:
        claimed = db.execute(
            update(WritingJob)
            .where(WritingJob.id == job_id, WritingJob.status == "queued")
            .values(status="running", started_at=now(), error=None)
        )
        if not claimed.rowcount:
            db.rollback()
            return False
        job = db.get(WritingJob, job_id)
        action, model, mode = job.action, job.model, job.mode
        data = deepcopy(job.snapshot)
        prompt_version = job.prompt_version
        provider_name = job.provider
        db.commit()
    # No open database transaction or draft lock while the paid provider request runs.
    try:
        if prompt_version != PROMPT_VERSION:
            raise HTTPException(
                409,
                "Writing instructions changed after this job was queued. Generate a fresh suggestion.",
            )
        if mode != settings.ai_mode or provider_name != getattr(
            settings, "ai_provider", "compatible"
        ):
            raise HTTPException(
                409,
                "The AI provider configuration changed after this job was queued. Generate a fresh suggestion.",
            )
        data["_model"] = model
        provider = MockAI() if mode == "mock" else CompatibleAI()
        result = validate_email(provider.complete(action, data))
        status, error = "succeeded", None
    except HTTPException as exc:
        result, status, error = None, "failed", str(exc.detail)
    except Exception:
        result, status, error = (
            None,
            "failed",
            "Writing failed unexpectedly. Your saved draft is unchanged. Try a new generation.",
        )
    # Explicit redaction; never persist raw request bodies or provider exceptions.
    if error and settings.ai_api_key:
        error = error.replace(settings.ai_api_key, "[redacted]")
    with Session() as db:
        db.execute(
            update(WritingJob)
            .where(WritingJob.id == job_id, WritingJob.status == "running")
            .values(status=status, result=result, error=error, completed_at=now())
        )
        db.commit()
    return True


def recover_writing_jobs():
    """Single-worker startup: interrupted calls are not automatically billed twice."""
    with Session() as db:
        db.execute(
            update(WritingJob)
            .where(WritingJob.status == "running")
            .values(
                status="failed",
                completed_at=now(),
                error="The server restarted during generation. Your draft is unchanged. Generate again to retry; the previous provider call may have completed.",
            )
        )
        db.commit()


_worker = None
_worker_guard = Lock()
_wake = Event()
_stop = Event()


def wake_writing_worker():
    _wake.set()


def _writing_loop():
    while not _stop.is_set():
        try:
            with Session() as db:
                job_id = db.scalar(
                    select(WritingJob.id)
                    .where(WritingJob.status == "queued")
                    .order_by(WritingJob.created_at)
                    .limit(1)
                )
            if job_id:
                process_writing_job(job_id)
                continue
        except Exception:
            # A transient database outage must not kill the persistent queue consumer.
            pass
        _wake.wait(1)
        _wake.clear()


def start_writing_worker():
    global _worker
    with _worker_guard:
        if _worker and _worker.is_alive():
            return
        recover_writing_jobs()
        _stop.clear()
        _wake.clear()
        _worker = Thread(target=_writing_loop, name="writing-jobs", daemon=True)
        _worker.start()


def stop_writing_worker():
    _stop.set()
    _wake.set()
    if _worker:
        _worker.join(timeout=5)
