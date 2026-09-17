from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    String,
    Text,
    JSON,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    text,
    LargeBinary,
)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now():
    return datetime.now(timezone.utc)


class Identity:
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )


class Scoped(Identity):
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )


class Workspace(Identity, Base):
    __tablename__ = "workspaces"
    name: Mapped[str] = mapped_column(String(150), default="Personal workspace")


class Persona(Scoped, Base):
    __tablename__ = "personas"
    label: Mapped[str] = mapped_column(String(150))
    domain: Mapped[str] = mapped_column(String(30), default="finance")
    version: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSON)


class PersonaRevision(Scoped, Base):
    __tablename__ = "persona_revisions"
    __table_args__ = (UniqueConstraint("workspace_id", "persona_id", "version"),)
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)


class UploadedDocument(Scoped, Base):
    __tablename__ = "uploaded_documents"
    __table_args__ = (Index(
        "uq_documents_cached_parse", "workspace_id", "content_hash", "parse_mode", "parse_provider", "parse_model", "parse_prompt_version",
        unique=True,
        sqlite_where=text("content_hash IS NOT NULL AND status IN ('queued', 'processing', 'parsed')"),
        postgresql_where=text("content_hash IS NOT NULL AND status IN ('queued', 'processing', 'parsed')"),
    ),)
    original_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    error: Mapped[str | None] = mapped_column(Text)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    persona_id: Mapped[str | None] = mapped_column(ForeignKey("personas.id"))
    parsed_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    parse_mode: Mapped[str] = mapped_column(String(15), default="legacy")
    parse_provider: Mapped[str] = mapped_column(String(30), default="")
    parse_model: Mapped[str] = mapped_column(String(150), default="")
    parse_prompt_version: Mapped[str] = mapped_column(String(60), default="")
    parse_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parse_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentFile(Base):
    __tablename__ = "document_files"
    document_id: Mapped[str] = mapped_column(ForeignKey("uploaded_documents.id", ondelete="CASCADE"), primary_key=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class Contact(Scoped, Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("workspace_id", "provider", "provider_id"),)
    provider: Mapped[str] = mapped_column(String(30), default="manual")
    provider_id: Mapped[str | None] = mapped_column(String(160))
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    name: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(250), default="")
    company: Mapped[str] = mapped_column(String(250), default="")
    location: Mapped[str] = mapped_column(String(250), default="")
    school: Mapped[str] = mapped_column(String(250), default="")
    profile_url: Mapped[str] = mapped_column(Text, default="")
    email: Mapped[str] = mapped_column(String(250), default="")
    email_status: Mapped[str] = mapped_column(String(60), default="not_requested")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")


class ContactDomainProfile(Scoped, Base):
    __tablename__ = "contact_domain_profiles"
    __table_args__ = (UniqueConstraint("workspace_id", "contact_id", "domain"),)
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), index=True)
    domain: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict] = mapped_column(JSON)


class SourceEvidence(Scoped, Base):
    __tablename__ = "source_evidence"
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(500))
    snippet: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40), default="profile")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MatchAssessment(Scoped, Base):
    __tablename__ = "match_assessments"
    contact_id: Mapped[str] = mapped_column(ForeignKey("contacts.id"), index=True)
    persona_id: Mapped[str] = mapped_column(ForeignKey("personas.id"))
    persona_revision_id: Mapped[str] = mapped_column(ForeignKey("persona_revisions.id"))
    persona_version: Mapped[int] = mapped_column(Integer)
    contact_fingerprint: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(10), default="en")
    reason: Mapped[str] = mapped_column(Text)
    source_ids: Mapped[list] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(30))


class Draft(Scoped, Base):
    __tablename__ = "drafts"
    contact_id: Mapped[str | None] = mapped_column(
        ForeignKey("contacts.id"), index=True
    )
    persona_id: Mapped[str | None] = mapped_column(ForeignKey("personas.id"))
    persona_version: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(10), default="en")
    purpose: Mapped[str] = mapped_column(Text, default="")
    starting_point: Mapped[str] = mapped_column(String(60), default="Networking")
    tone: Mapped[str] = mapped_column(String(30), default="professional")
    subject: Mapped[str] = mapped_column(Text, default="")
    body_html: Mapped[str] = mapped_column(Text, default="<p></p>")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    generation_provider: Mapped[str] = mapped_column(String(30), default="manual")
    model: Mapped[str] = mapped_column(String(150), default="")
    writing_mode: Mapped[str] = mapped_column(String(15), default="assisted")
    length: Mapped[str] = mapped_column(String(15), default="medium")
    cta: Mapped[str] = mapped_column(Text, default="")
    custom_instructions: Mapped[str] = mapped_column(Text, default="")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)


class WritingJob(Scoped, Base):
    __tablename__ = "writing_jobs"
    __table_args__ = (Index(
        "uq_writing_jobs_pending", "workspace_id", "draft_id", "draft_revision", "action",
        unique=True,
        sqlite_where=text("status IN ('queued', 'running')"),
        postgresql_where=text("status IN ('queued', 'running')"),
    ),)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"), index=True)
    draft_revision: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    mode: Mapped[str] = mapped_column(String(15))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(150))
    prompt_version: Mapped[str] = mapped_column(String(60))
    snapshot: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PeopleJob(Scoped, Base):
    __tablename__ = "people_jobs"
    kind: Mapped[str] = mapped_column(String(30))
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    input: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    upstream: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    retryable: Mapped[bool] = mapped_column(Boolean, default=True)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
