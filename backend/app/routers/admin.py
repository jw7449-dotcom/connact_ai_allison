"""Read-only account and workspace inspection, guarded on every request."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from ..db import Session
from ..auth_models import User
from ..models import (
    Persona, PersonaRevision, UploadedDocument, DocumentFile, Contact,
    ContactDomainProfile, SourceEvidence, MatchAssessment, Draft, WritingJob, PeopleJob,
)
from .auth import session_user
from ..services.file_storage import file_response, legacy_path

router = APIRouter(prefix="/admin")
SECTIONS = {
    "personas": Persona, "persona_revisions": PersonaRevision,
    "contacts": Contact, "contact_profiles": ContactDomainProfile,
    "sources": SourceEvidence, "assessments": MatchAssessment,
    "drafts": Draft, "documents": UploadedDocument,
    "people_jobs": PeopleJob, "writing_jobs": WritingJob,
}


def admin_db(request: Request):
    with Session() as db:
        user = session_user(db, request)
        if not user:
            raise HTTPException(401, "Please sign in to your workspace.")
        if not user.is_admin:
            raise HTTPException(403, "Administrator access is required.")
        yield db


def account(db, user_id):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Account not found.")
    return user


def account_json(user):
    # Never serialize passwords or session/invitation tokens.
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin,
            "created_at": user.created_at, "last_login_at": user.last_login_at}


def counts_by_workspace(db, workspace_ids):
    counts = {ident: {} for ident in workspace_ids}
    for key, model in SECTIONS.items():
        rows = db.execute(select(model.workspace_id, func.count()).where(
            model.workspace_id.in_(workspace_ids)).group_by(model.workspace_id)).all()
        for ident, count in rows:
            counts[ident][key] = count
    return counts


@router.get("/overview")
def overview(db=Depends(admin_db)):
    return {
        "accounts": db.scalar(select(func.count()).select_from(User)),
        "administrators": db.scalar(select(func.count()).select_from(User).where(User.is_admin.is_(True))),
        "saved_contacts": db.scalar(select(func.count()).select_from(Contact).where(Contact.saved.is_(True))),
        "drafts": db.scalar(select(func.count()).select_from(Draft)),
        "documents": db.scalar(select(func.count()).select_from(UploadedDocument)),
        "stored_bytes": db.scalar(select(func.coalesce(func.sum(DocumentFile.byte_size), 0))),
    }


@router.get("/users")
def users(q: str = Query(default="", max_length=250), offset: int = Query(default=0, ge=0),
          limit: int = Query(default=25, ge=1, le=100), db=Depends(admin_db)):
    query = select(User)
    if q.strip():
        query = query.where(User.email.icontains(q.strip(), autoescape=True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(User.created_at.desc(), User.id).offset(offset).limit(limit)).all()
    counts = counts_by_workspace(db, [user.workspace_id for user in rows])
    return {"items": [{**account_json(user), "counts": counts[user.workspace_id]} for user in rows],
            "total": total, "offset": offset, "limit": limit}


@router.get("/users/{user_id}")
def user_detail(user_id: str, db=Depends(admin_db)):
    user = account(db, user_id)
    counts = counts_by_workspace(db, [user.workspace_id])[user.workspace_id]
    return {**account_json(user), "counts": counts}


@router.get("/users/{user_id}/data/{section}")
def workspace_data(user_id: str, section: str, offset: int = Query(default=0, ge=0),
                   limit: int = Query(default=25, ge=1, le=100), db=Depends(admin_db)):
    user = account(db, user_id)
    model = SECTIONS.get(section)
    if model is None:
        raise HTTPException(404, "Data category not found.")
    query = select(model).where(model.workspace_id == user.workspace_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(model.created_at.desc(), model.id).offset(offset).limit(limit)).all()
    items = []
    for record in rows:
        item = {column.name: getattr(record, column.name) for column in model.__table__.columns
                if column.name not in {"workspace_id", "storage_key"}}
        if section == "documents":
            stored = db.get(DocumentFile, record.id)
            available = bool(stored) or legacy_path(record).is_file()
            item.update(file_available=available, byte_size=stored.byte_size if stored else None,
                        download_url=f"/api/admin/users/{user.id}/documents/{record.id}/download" if available else None)
        items.append(item)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/users/{user_id}/documents/{document_id}/download")
def download(user_id: str, document_id: str, db=Depends(admin_db)):
    user = account(db, user_id)
    document = db.scalar(select(UploadedDocument).where(
        UploadedDocument.id == document_id, UploadedDocument.workspace_id == user.workspace_id))
    if document is None:
        raise HTTPException(404, "Document not found for this account.")
    return file_response(db, document)
