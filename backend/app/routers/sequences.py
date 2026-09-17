from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from ..db import get_repo
from ..sequence_models import Sequence, SequenceStep, SequenceTemplate, SequenceJob
from ..sequence_schemas import (
    SequenceCreate, SequenceUpdate, StepCreate, StepInput,
    TemplateInput, SaveTemplateInput, AIPlanInput,
)
from ..models import Draft
from ..services.sequences import (
    DEFAULT_TEMPLATES, steps_for, get_template, template_json, create_template,
    locked, bump_revision, create_sequence, update_sequence, sequence_json,
    sequence_preview, replace_steps, create_plan_job, job_json, wake_sequence_worker,
)

router = APIRouter()


@router.get("/sequence-templates")
def templates(repo=Depends(get_repo)):
    return DEFAULT_TEMPLATES + [template_json(template) for template in
        sorted(repo.all(SequenceTemplate), key=lambda item: item.updated_at, reverse=True)]


@router.post("/sequence-templates", status_code=201)
def upload_template(body: TemplateInput, repo=Depends(get_repo)):
    """Import portable JSON: schema_version, name, description, ordered steps."""
    return create_template(repo, body)


@router.get("/sequence-templates/schema")
def template_schema(repo=Depends(get_repo)):
    return TemplateInput.model_json_schema()


@router.get("/sequence-templates/{template_id}/export")
def export_template(template_id: str, repo=Depends(get_repo)):
    template = get_template(repo, template_id)
    portable = {key: template[key] for key in ("schema_version", "name", "description", "steps")}
    return JSONResponse(portable, headers={"Content-Disposition": 'attachment; filename="sequence-template.json"'})


@router.get("/sequence-templates/{template_id}")
def template(template_id: str, repo=Depends(get_repo)):
    return get_template(repo, template_id)


@router.delete("/sequence-templates/{template_id}")
def delete_template(template_id: str, repo=Depends(get_repo)):
    if any(item["id"] == template_id for item in DEFAULT_TEMPLATES):
        raise HTTPException(422, "Default templates cannot be deleted. Save a personal copy to customize one.")
    repo.session.delete(repo.get(SequenceTemplate, template_id))
    return {"deleted": True}


@router.get("/sequences")
def sequences(repo=Depends(get_repo)):
    return [sequence_json(repo, sequence, detail=False) for sequence in
        sorted(repo.all(Sequence), key=lambda item: item.updated_at, reverse=True)]


@router.post("/sequences", status_code=201)
def create(body: SequenceCreate, repo=Depends(get_repo)):
    return sequence_json(repo, create_sequence(repo, body))


@router.get("/sequences/{sequence_id}")
def get(sequence_id: str, repo=Depends(get_repo)):
    return sequence_json(repo, repo.get(Sequence, sequence_id))


@router.put("/sequences/{sequence_id}")
def update(sequence_id: str, body: SequenceUpdate, repo=Depends(get_repo)):
    sequence = update_sequence(repo, sequence_id, body)
    repo.session.flush()
    return sequence_json(repo, sequence)


@router.delete("/sequences/{sequence_id}")
def remove(sequence_id: str, revision: int = Query(ge=1), repo=Depends(get_repo)):
    sequence = locked(repo, sequence_id, revision)
    bump_revision(repo, sequence, revision)
    repo.session.execute(delete(SequenceStep).where(SequenceStep.sequence_id == sequence_id,
                                                   SequenceStep.workspace_id == repo.workspace_id))
    repo.session.execute(delete(SequenceJob).where(SequenceJob.sequence_id == sequence_id,
                                                  SequenceJob.workspace_id == repo.workspace_id))
    repo.session.delete(sequence)
    return {"deleted": True, "drafts_preserved": True}


@router.post("/sequences/{sequence_id}/steps")
def add_step(sequence_id: str, body: StepCreate, repo=Depends(get_repo)):
    sequence = locked(repo, sequence_id, body.revision)
    existing = steps_for(repo, sequence.id)
    if len(existing) >= 20:
        raise HTTPException(422, "A sequence may contain at most 20 email steps.")
    data = body.model_dump(exclude={"revision"})
    if not existing:
        # Omitted follow-up defaults become a valid initial step; explicit invalid values are rejected.
        if "thread_mode" in body.model_fields_set and body.thread_mode != "new_thread":
            raise HTTPException(422, "The first step must start a new thread.")
        if "delay_days" in body.model_fields_set and body.delay_days != 0:
            raise HTTPException(422, "The first step must be on day 0.")
        data.update(delay_days=0, thread_mode="new_thread")
    supplied = [StepInput(**{key: getattr(step, key) for key in
        ("id", "draft_id", "title", "purpose", "delay_days", "thread_mode")}) for step in existing]
    supplied.append(StepInput(**data))
    bump_revision(repo, sequence, body.revision)
    replace_steps(repo, sequence, supplied)
    return sequence_json(repo, sequence)


@router.get("/sequences/{sequence_id}/preview")
def get_preview(sequence_id: str, repo=Depends(get_repo)):
    return sequence_preview(repo, repo.get(Sequence, sequence_id))


@router.post("/sequences/{sequence_id}/save-template", status_code=201)
def save_template(sequence_id: str, body: SaveTemplateInput, repo=Depends(get_repo)):
    sequence = repo.get(Sequence, sequence_id)
    steps = []
    for step in steps_for(repo, sequence.id):
        draft = repo.get(Draft, step.draft_id)
        steps.append({**{key: getattr(step, key) for key in ("title", "purpose", "delay_days", "thread_mode")},
            "subject": draft.subject, "body_html": draft.body_html})
    if not steps:
        raise HTTPException(422, "Add at least one step before saving a reusable template.")
    return create_template(repo, TemplateInput(name=body.name, description=body.description, steps=steps))


@router.post("/sequences/{sequence_id}/ai-plan", status_code=202)
def ai_plan(sequence_id: str, body: AIPlanInput, repo=Depends(get_repo)):
    sequence = locked(repo, sequence_id, body.revision)
    job = create_plan_job(repo, sequence, body)
    result = job_json(job)
    repo.session.commit()
    wake_sequence_worker()
    return result


@router.get("/sequences/{sequence_id}/jobs/{job_id}")
def get_job(sequence_id: str, job_id: str, repo=Depends(get_repo)):
    repo.get(Sequence, sequence_id)
    job = repo.get(SequenceJob, job_id)
    if job.sequence_id != sequence_id:
        raise HTTPException(404, "Sequence generation not found.")
    return job_json(job)
