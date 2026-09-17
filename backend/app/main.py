from contextlib import asynccontextmanager
from urllib.parse import urlparse
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select, text
from .db import Session, get_repo
from .models import Workspace
from .config import settings
from .routers import personas, contacts, finance, drafts, auth, export, admin, sequences, writing_templates
from .services.drafts import start_writing_worker, stop_writing_worker
from .services.people_jobs import start_people_worker, stop_people_worker
from .services.documents import start_document_worker, stop_document_worker
from .services.file_storage import preserve_legacy_files
from .services.sequences import start_sequence_worker, stop_sequence_worker
from .services.auth_logging import configure_auth_log_redaction
from .routers import gmail, mail, mail_unsubscribe
from .services.mail import start_mail_worker, stop_mail_worker

configure_auth_log_redaction()


@asynccontextmanager
async def lifespan(app):
    if settings.auth_mode == "local" and urlparse(settings.public_origin).hostname not in ("localhost", "127.0.0.1"):
        raise RuntimeError("A public origin requires AUTH_MODE=open or invite.")
    if settings.auth_mode != "local" and urlparse(settings.public_origin).hostname not in ("localhost", "127.0.0.1") and not settings.public_origin.startswith("https://"):
        raise RuntimeError("Customer workspaces require an HTTPS PUBLIC_ORIGIN.")
    with Session() as db:
        if db.get(Workspace, settings.workspace_id) is None:
            db.add(Workspace(id=settings.workspace_id, name="Personal workspace"))
            db.commit()
    preserve_legacy_files()
    start_writing_worker()
    start_people_worker()
    start_document_worker()
    start_sequence_worker()
    start_mail_worker()
    try:
        yield
    finally:
        stop_mail_worker()
        stop_sequence_worker()
        stop_document_worker()
        stop_people_worker()
        stop_writing_worker()


app = FastAPI(title="Connact.ai API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[h.strip() for h in settings.allowed_hosts.split(",") if h.strip()]
    + ([settings.render_external_hostname] if settings.render_external_hostname else []),
)


@app.middleware("http")
async def local_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed = {settings.public_origin.rstrip("/")}
    if settings.auth_mode == "local":
        allowed.update({"http://localhost:3100", "http://127.0.0.1:3100"})
    if origin and origin.rstrip("/") not in allowed:
        return JSONResponse(
            {"detail": "This origin is not allowed to access the workspace."},
            status_code=403,
        )
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.get("/api/health")
def health():
    with Session() as db:
        db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": (
            "postgresql"
            if settings.database_url.startswith("postgresql")
            else "sqlite-test"
        ),
    }


@app.get("/api/config")
def config(request: Request, repo=Depends(get_repo)):
    from .providers.model_registry import model_routes

    return {
        "workspace": "Personal workspace",
        "local_only": settings.auth_mode == "local",
        "auth_mode": settings.auth_mode,
        "is_admin": bool((user := auth.session_user(repo.session, request)) and user.is_admin),
        "workspace_id": repo.workspace_id,
        "people_mode": settings.people_mode,
        "public_search_mode": settings.public_search_mode,
        "ai_mode": settings.ai_mode,
        "providers": {
            "apollo": bool(settings.apollo_api_key),
            "serpapi": bool(settings.serpapi_api_key),
            "ai": any(r.configured for r in model_routes().values()),
            "apify": bool(settings.apify_api_key),
        },
    }


for router in (personas.router, contacts.router, finance.router, drafts.router, auth.router, export.router, admin.router, sequences.router, writing_templates.router):
    app.include_router(router, prefix="/api")

app.include_router(gmail.router, prefix="/api")
app.include_router(mail.router, prefix="/api")
app.include_router(mail_unsubscribe.router, prefix="/api")
