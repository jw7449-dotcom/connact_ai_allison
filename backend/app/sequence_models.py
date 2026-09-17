"""Workspace-owned sequence plans. No sending or scheduling is performed."""

from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import Scoped
from datetime import datetime


class Sequence(Scoped, Base):
    __tablename__ = "sequences"
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(10), default="en")
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    persona_id: Mapped[str | None] = mapped_column(ForeignKey("personas.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    review_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)


class SequenceStep(Scoped, Base):
    __tablename__ = "sequence_steps"
    sequence_id: Mapped[str] = mapped_column(ForeignKey("sequences.id", ondelete="CASCADE"), index=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("drafts.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(Text, default="")
    delay_days: Mapped[int] = mapped_column(Integer, default=0)
    thread_mode: Mapped[str] = mapped_column(String(20), default="new_thread")


class SequenceTemplate(Scoped, Base):
    __tablename__ = "sequence_templates"
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    steps: Mapped[list] = mapped_column(JSON)


class SequenceJob(Scoped, Base):
    __tablename__ = "sequence_jobs"
    __table_args__ = (Index(
        "uq_sequence_jobs_pending", "workspace_id", "sequence_id",
        unique=True,
        sqlite_where=text("status IN ('queued', 'running')"),
        postgresql_where=text("status IN ('queued', 'running')"),
    ),)
    sequence_id: Mapped[str] = mapped_column(ForeignKey("sequences.id", ondelete="CASCADE"), index=True)
    sequence_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    mode: Mapped[str] = mapped_column(String(15))
    provider: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(150))
    snapshot: Mapped[dict] = mapped_column(JSON)
    total_steps: Mapped[int] = mapped_column(Integer)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0)
    result_steps: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
