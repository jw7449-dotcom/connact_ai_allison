from time import monotonic, sleep
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update as sql_update
from ..db import get_repo
from ..models import Draft, Contact, Persona, SourceEvidence, WritingJob, now
from ..schemas import DraftInput, GenerateInput, AcceptGenerationInput
from ..services.contacts import row
from ..services.drafts import (
    sanitize,
    preview,
    writing_snapshot,
    create_writing_job,
    process_writing_job,
    wake_writing_worker,
)
from ..providers.ai import model_catalog, resolve_model
from ..config import settings

router = APIRouter()


def locked(repo, id, revision):
    d = repo.session.scalar(repo.query(Draft).where(Draft.id == id).with_for_update())
    if not d:
        raise HTTPException(404, "Draft not found.")
    if revision != d.revision:
        raise HTTPException(
            409,
            "This draft changed in another tab. Reopen the latest draft before saving.",
        )
    return d


def apply(repo, d, body):
    if body.contact_id:
        repo.get(Contact, body.contact_id)
    p = repo.get(Persona, body.persona_id) if body.persona_id else None
    if body.model:
        resolve_model(body.model)
    for source_id in body.evidence_ids:
        source = repo.get(SourceEvidence, source_id)
        if not body.contact_id or source.contact_id != body.contact_id:
            raise HTTPException(
                422, "Selected evidence must belong to this draft's recipient."
            )
    for k, v in body.model_dump(exclude={"revision"}).items():
        setattr(d, k, v)
    d.evidence_ids = list(dict.fromkeys(d.evidence_ids))
    d.body_html = sanitize(d.body_html)
    d.persona_version = p.version if p else None
    if d.status == "ready" and not preview(repo, d)["can_mark_ready"]:
        raise HTTPException(
            422,
            "Complete the recipient, subject, body and all variables before marking this draft ready.",
        )


def persist_revision(repo, d, revision):
    """CAS also protects SQLite, where SELECT FOR UPDATE is unavailable."""
    values = {
        c.name: getattr(d, c.name)
        for c in d.__table__.columns
        if c.name not in {"id", "workspace_id", "created_at", "updated_at", "revision"}
    }
    values.update(revision=revision + 1, updated_at=now())
    with repo.session.no_autoflush:
        changed = repo.session.execute(
            sql_update(Draft)
            .where(
                Draft.id == d.id,
                Draft.workspace_id == repo.workspace_id,
                Draft.revision == revision,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
    if not changed.rowcount:
        raise HTTPException(
            409,
            "This draft changed in another tab. Reopen the latest draft before saving.",
        )
    repo.session.expire(d)
    repo.session.refresh(d)
    return d


def get_job(repo, draft_id, job_id, lock=False):
    repo.get(Draft, draft_id)
    query = repo.query(WritingJob).where(
        WritingJob.id == job_id, WritingJob.draft_id == draft_id
    )
    if lock:
        query = query.with_for_update()
    job = repo.session.scalar(query)
    if not job:
        raise HTTPException(404, "Writing suggestion not found.")
    return job


def accept_job(repo, draft_id, job_id, revision):
    d = locked(repo, draft_id, revision)
    job = get_job(repo, draft_id, job_id, lock=True)
    if job.status != "succeeded" or not job.result:
        raise HTTPException(
            409, "Only a completed, unreviewed suggestion can be accepted."
        )
    if d.revision != job.draft_revision or writing_snapshot(repo, d) != job.snapshot:
        raise HTTPException(
            409,
            "The draft, sender profile or selected recipient information changed after generation. Your edits are preserved. Generate a fresh suggestion.",
        )
    with repo.session.no_autoflush:
        d.subject = job.result["subject"]
        d.body_html = sanitize(job.result["body_html"])
        d.status = "draft"
        d.persona_version = job.snapshot["persona_version"]
        d.generation_provider = job.mode
        d.model = job.model
        persist_revision(repo, d, revision)
        job.status = "accepted"
    repo.session.flush()
    return row(d)


@router.get("/ai/models")
def models(repo=Depends(get_repo)):
    return model_catalog()


@router.get("/drafts")
def drafts(repo=Depends(get_repo)):
    return [
        row(d)
        for d in sorted(repo.all(Draft), key=lambda x: x.updated_at, reverse=True)
    ]


@router.post("/drafts")
def create(body: DraftInput, repo=Depends(get_repo)):
    d = repo.add(Draft)
    apply(repo, d, body)
    repo.session.flush()
    return row(d)


@router.get("/drafts/{id}")
def get(id: str, repo=Depends(get_repo)):
    d = repo.get(Draft, id)
    result = row(d)
    result["preview"] = preview(repo, d)
    return result


@router.put("/drafts/{id}")
def update(id: str, body: DraftInput, repo=Depends(get_repo)):
    d = locked(repo, id, body.revision)
    with repo.session.no_autoflush:
        apply(repo, d, body)
        persist_revision(repo, d, body.revision)
    return row(d)


@router.get("/drafts/{id}/preview")
def get_preview(id: str, repo=Depends(get_repo)):
    return preview(repo, repo.get(Draft, id))


@router.post("/drafts/{id}/generations", status_code=202)
def queue_generation(id: str, body: GenerateInput, repo=Depends(get_repo)):
    d = locked(repo, id, body.revision)
    job = create_writing_job(repo, d, body.action)
    result = row(job)
    # Commit before notifying the worker; it uses its own session.
    repo.session.commit()
    wake_writing_worker()
    return result


@router.get("/drafts/{id}/generations")
def list_generations(id: str, repo=Depends(get_repo)):
    repo.get(Draft, id)
    return [
        row(j)
        for j in repo.session.scalars(
            repo.query(WritingJob)
            .where(WritingJob.draft_id == id)
            .order_by(WritingJob.created_at.desc())
            .limit(50)
        ).all()
    ]


@router.get("/drafts/{id}/generations/{job_id}")
def generation(id: str, job_id: str, repo=Depends(get_repo)):
    return row(get_job(repo, id, job_id))


@router.post("/drafts/{id}/generations/{job_id}/accept")
def accept(id: str, job_id: str, body: AcceptGenerationInput, repo=Depends(get_repo)):
    return accept_job(repo, id, job_id, body.revision)


@router.post("/drafts/{id}/generations/{job_id}/discard")
def discard(id: str, job_id: str, repo=Depends(get_repo)):
    job = get_job(repo, id, job_id, lock=True)
    if job.status == "accepted":
        raise HTTPException(409, "This suggestion was already accepted into the draft.")
    job.status = "discarded"
    repo.session.flush()
    return row(job)


@router.post("/drafts/{id}/generate", deprecated=True)
def generate(id: str, body: GenerateInput, repo=Depends(get_repo)):
    """Legacy synchronous API; release locks during I/O and keep the same stale guard."""
    d = locked(repo, id, body.revision)
    job = create_writing_job(repo, d, body.action)
    job_id = job.id
    repo.session.commit()
    process_writing_job(job_id)
    repo.session.expire_all()
    job = get_job(repo, id, job_id)
    # The persistent consumer may have won the atomic claim. Preserve the legacy
    # synchronous contract while releasing every database read transaction.
    deadline = monotonic() + getattr(settings, "ai_timeout_seconds", 60) + 5
    while job.status in ("queued", "running") and monotonic() < deadline:
        repo.session.commit()
        sleep(0.05)
        repo.session.expire_all()
        job = get_job(repo, id, job_id)
    if job.status == "failed":
        raise HTTPException(502, job.error)
    if job.status in ("queued", "running"):
        raise HTTPException(
            409,
            "Generation is running. Retrieve this draft's writing suggestions to review it.",
        )
    return accept_job(repo, id, job_id, body.revision)
