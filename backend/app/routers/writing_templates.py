"""Workspace-owned reusable emails. Using one never sends an email."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update as sql_update
from ..db import get_repo
from ..models import now
from ..writing_template_models import WritingTemplate
from ..writing_template_schemas import WritingTemplateInput
from ..services.contacts import row
from ..services.drafts import plain_text, sanitize

router = APIRouter()

DEFAULT_TEMPLATES = [
    {
        "id": "default-networking",
        "name": "A thoughtful introduction",
        "description": "Start a professional conversation with a clear, low-pressure ask.",
        "category": "Networking",
        "subject": "A quick introduction, {{name}}",
        "body_html": "<p>Hi {{name}},</p><p>I am reaching out to learn more about your work at {{company}}. Your perspective as {{title}} would be valuable as I explore this area.</p><p>Would you be open to a brief conversation next week?</p><p>Best,<br>{{sender_name}}</p>",
    },
    {
        "id": "default-interview",
        "name": "Informational interview",
        "description": "Ask someone about their experience and career path.",
        "category": "Informational Interview",
        "subject": "Learning about your experience at {{company}}",
        "body_html": "<p>Hi {{name}},</p><p>I would appreciate the chance to hear about your experience as {{title}} at {{company}} and what you have learned along the way.</p><p>Would you have 15 minutes for a conversation? I am happy to work around your schedule.</p><p>Thank you,<br>{{sender_name}}</p>",
    },
    {
        "id": "default-followup",
        "name": "A considerate follow-up",
        "description": "Follow up after an earlier email without adding pressure.",
        "category": "Follow-up",
        "subject": "Following up on my note",
        "body_html": "<p>Hi {{name}},</p><p>I wanted to follow up on my earlier note about connecting. I would still welcome the opportunity to hear your perspective on working at {{company}}.</p><p>If now is not a good time, I completely understand. Thank you for considering it.</p><p>Best,<br>{{sender_name}}</p>",
    },
]


def response(template):
    return {**row(template), "is_default": False}


def values(body):
    result = body.model_dump(exclude={"revision"})
    result["body_html"] = sanitize(result["body_html"])
    if not plain_text(result["body_html"]):
        raise HTTPException(422, "Add email body text before saving a template.")
    return result


@router.get("/writing-templates")
def templates(repo=Depends(get_repo)):
    custom = sorted(repo.all(WritingTemplate), key=lambda x: x.updated_at, reverse=True)
    return [{**item, "revision": 1, "is_default": True} for item in DEFAULT_TEMPLATES] + [response(item) for item in custom]


@router.post("/writing-templates", status_code=201)
def create(body: WritingTemplateInput, repo=Depends(get_repo)):
    return response(repo.add(WritingTemplate, **values(body)))


@router.put("/writing-templates/{id}")
def update(id: str, body: WritingTemplateInput, repo=Depends(get_repo)):
    template = repo.get(WritingTemplate, id)
    if body.revision is None or body.revision != template.revision:
        raise HTTPException(409, "This template changed. Reload the library before updating it.")
    changed = repo.session.execute(sql_update(WritingTemplate).where(
        WritingTemplate.id == id,
        WritingTemplate.workspace_id == repo.workspace_id,
        WritingTemplate.revision == body.revision,
    ).values(**values(body), revision=body.revision + 1, updated_at=now()).execution_options(synchronize_session=False))
    if not changed.rowcount:
        raise HTTPException(409, "This template changed. Reload the library before updating it.")
    repo.session.expire(template)
    repo.session.refresh(template)
    return response(template)


@router.delete("/writing-templates/{id}", status_code=204)
def delete(id: str, repo=Depends(get_repo)):
    repo.session.delete(repo.get(WritingTemplate, id))
