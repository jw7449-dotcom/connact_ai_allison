"""Original uploads are private database records; legacy disk files remain readable."""

from pathlib import Path
from urllib.parse import quote
from fastapi import HTTPException, Response
from sqlalchemy import select
from ..config import settings
from ..models import DocumentFile, UploadedDocument
from ..db import Session


def legacy_path(document):
    directory = (Path(settings.upload_dir).resolve() / document.workspace_id).resolve()
    path = (directory / document.storage_key).resolve()
    if path.parent != directory:
        raise HTTPException(404, "Stored file is missing.")
    return path


def read_content(db, document):
    stored = db.get(DocumentFile, document.id)
    if stored:
        return stored.content
    path = legacy_path(document)
    if not path.is_file():
        raise HTTPException(404, "Original file is unavailable. Please upload it again.")
    return path.read_bytes()


def file_response(db, document):
    return Response(read_content(db, document), media_type="application/octet-stream", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(document.original_name, safe=""),
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


def preserve_legacy_files():
    # Copy only files still present; an old Render disk lost on redeploy cannot be recovered.
    with Session() as db:
        ids = db.scalars(select(UploadedDocument.id).outerjoin(DocumentFile)
                         .where(DocumentFile.document_id.is_(None))).all()
        for document_id in ids:
            document = db.get(UploadedDocument, document_id)
            path = legacy_path(document)
            if path.is_file():
                content = path.read_bytes()
                db.add(DocumentFile(document_id=document.id, byte_size=len(content), content=content))
                db.commit()
