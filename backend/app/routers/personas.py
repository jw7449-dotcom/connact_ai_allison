from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from ..db import get_repo
from ..config import settings
from ..models import Persona, PersonaRevision, UploadedDocument, Draft
from ..schemas import PersonaInput
from ..services.contacts import row
from ..services.documents import (
    queue_document,
    document_response,
    retry_document,
    process_document,
    wake_document_worker,
)
from time import monotonic, sleep
from ..services.file_storage import file_response

router = APIRouter()


@router.get("/personas")
def personas(repo=Depends(get_repo)):
    return [row(p) for p in repo.all(Persona)]


@router.post("/personas")
def create(body: PersonaInput, repo=Depends(get_repo)):
    p = repo.add(Persona, label=body.label, data=body.data.model_dump())
    repo.add(PersonaRevision, persona_id=p.id, version=p.version, data=p.data)
    if body.document_id:
        repo.get(UploadedDocument, body.document_id).persona_id = p.id
    return row(p)


@router.put("/personas/{id}")
def update(id: str, body: PersonaInput, repo=Depends(get_repo)):
    p = repo.session.scalar(
        repo.query(Persona).where(Persona.id == id).with_for_update()
    )
    if not p:
        raise HTTPException(404, "Persona not found.")
    if body.version != p.version:
        raise HTTPException(
            409, "This persona changed elsewhere. Reopen it before editing."
        )
    p.label, p.data, p.version = body.label, body.data.model_dump(), p.version + 1
    for draft in repo.all(Draft, Draft.persona_id == p.id):
        draft.status = "draft"
        draft.revision += 1
    repo.add(PersonaRevision, persona_id=p.id, version=p.version, data=p.data)
    if body.document_id:
        repo.get(UploadedDocument, body.document_id).persona_id = p.id
    return row(p)


@router.post("/documents/jobs", status_code=202)
def upload_job(file: UploadFile = File(...), repo=Depends(get_repo)):
    document = queue_document(repo, file)
    response = document_response(document)
    repo.session.commit()
    wake_document_worker()
    return response


@router.get("/documents")
def documents(repo=Depends(get_repo)):
    return [
        document_response(document)
        for document in repo.session.scalars(
            repo.query(UploadedDocument)
            .order_by(UploadedDocument.created_at.desc())
            .limit(50)
        ).all()
    ]


@router.get("/documents/{id}/status")
def document_status(id: str, repo=Depends(get_repo)):
    return document_response(repo.get(UploadedDocument, id))


@router.post("/documents/{id}/retry", status_code=202)
def retry_upload(id: str, repo=Depends(get_repo)):
    document = retry_document(repo, repo.get(UploadedDocument, id))
    response = document_response(document)
    repo.session.commit()
    wake_document_worker()
    return response


@router.post("/documents", deprecated=True)
def upload(file: UploadFile = File(...), repo=Depends(get_repo)):
    """Compatibility endpoint; the result now remains available after navigation."""
    document = queue_document(repo, file)
    document_id = document.id
    repo.session.commit()
    process_document(document_id)
    repo.session.expire_all()
    document = repo.get(UploadedDocument, document_id)
    deadline = monotonic() + getattr(settings, "ai_timeout_seconds", 60) + 5
    while document.status in ("queued", "processing") and monotonic() < deadline:
        repo.session.commit()
        sleep(0.05)
        repo.session.expire_all()
        document = repo.get(UploadedDocument, document_id)
    return document_response(document)


@router.get("/documents/{id}/download")
def download(id: str, repo=Depends(get_repo)):
    d = repo.get(UploadedDocument, id)
    return file_response(repo.session, d)
