from email.message import EmailMessage
from email.policy import SMTP
import re
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from ..db import get_repo
from ..models import Draft
from ..services.drafts import preview

router = APIRouter()


@router.get("/drafts/{id}/export.eml")
def export_email(id: str, repo=Depends(get_repo)):
    draft = repo.get(Draft, id)
    result = preview(repo, draft)
    if not result["can_mark_ready"] or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", result["recipient_email"]):
        raise HTTPException(422, "Complete the recipient, subject, message and template variables before exporting.")
    message = EmailMessage(policy=SMTP)
    message["To"] = result["recipient_email"]
    message["Subject"] = " ".join(result["subject"].splitlines())
    message["X-Unsent"] = "1"
    message.set_content(result["body_text"])
    message.add_alternative(result["body_html"], subtype="html")
    return Response(message.as_bytes(), media_type="message/rfc822",
                    headers={"Content-Disposition": f'attachment; filename="connact-{id}.eml"'})
