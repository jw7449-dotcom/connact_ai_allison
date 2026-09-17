"""Workspace-owned Gmail connections, filtered messages and reviewed send commands."""
from datetime import datetime
from sqlalchemy import String, Text, JSON, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import Scoped


class Mailbox(Scoped, Base):
    __tablename__ = "mailboxes"
    __table_args__ = (UniqueConstraint("workspace_id", "email"),)
    provider: Mapped[str] = mapped_column(String(20), default="gmail")
    email: Mapped[str] = mapped_column(String(254))
    display_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(30), default="connected")
    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    signature_html: Mapped[str] = mapped_column(Text, default="")
    timezone: Mapped[str] = mapped_column(String(100), default="UTC")
    send_window_start: Mapped[int] = mapped_column(Integer, default=0)
    send_window_end: Mapped[int] = mapped_column(Integer, default=24)
    history_id: Mapped[str | None] = mapped_column(String(100))
    contacts_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    sync_status: Mapped[str] = mapped_column(String(30), default="idle")
    sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GmailOAuthState(Scoped, Base):
    __tablename__ = "gmail_oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    nonce_hash: Mapped[str] = mapped_column(String(64))
    code_verifier: Mapped[str] = mapped_column(String(128))
    session_hash: Mapped[str | None] = mapped_column(String(64))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    mode: Mapped[str] = mapped_column(String(30))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MailMessage(Scoped, Base):
    __tablename__ = "mail_messages"
    __table_args__ = (UniqueConstraint("mailbox_id", "gmail_message_id"), Index("ix_mail_messages_thread", "workspace_id", "mailbox_id", "gmail_thread_id"))
    mailbox_id: Mapped[str] = mapped_column(ForeignKey("mailboxes.id", ondelete="CASCADE"), index=True)
    gmail_message_id: Mapped[str] = mapped_column(String(150))
    gmail_thread_id: Mapped[str] = mapped_column(String(150))
    # Historical identity is deliberately not a FK: deleting a contact must be possible.
    # Every read rechecks saved=True, ID and exact normalized address in the workspace.
    contact_id: Mapped[str] = mapped_column(String(36), index=True)
    contact_email: Mapped[str] = mapped_column(String(254))
    from_email: Mapped[str] = mapped_column(String(254))
    to_emails: Mapped[list] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    body_text: Mapped[str] = mapped_column(Text, default="")
    body_html: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    direction: Mapped[str] = mapped_column(String(15))
    is_unread: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    labels: Mapped[list] = mapped_column(JSON, default=list)
    rfc_message_id: Mapped[str] = mapped_column(String(998), default="")
    in_reply_to: Mapped[str] = mapped_column(Text, default="")
    references: Mapped[str] = mapped_column(Text, default="")
    reply_to: Mapped[str] = mapped_column(String(254), default="")
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    is_automated: Mapped[bool] = mapped_column(Boolean, default=False)
    content_synced: Mapped[bool] = mapped_column(Boolean, default=True)


class MailThreadState(Scoped, Base):
    __tablename__ = "mail_thread_states"
    __table_args__ = (UniqueConstraint("workspace_id", "mailbox_id", "gmail_thread_id"),)
    mailbox_id: Mapped[str] = mapped_column(ForeignKey("mailboxes.id", ondelete="CASCADE"))
    gmail_thread_id: Mapped[str] = mapped_column(String(150))
    notes: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(String(30), default="none")


class MailSend(Scoped, Base):
    __tablename__ = "mail_sends"
    __table_args__ = (UniqueConstraint("workspace_id", "idempotency_key"),)
    mailbox_id: Mapped[str] = mapped_column(ForeignKey("mailboxes.id"), index=True)
    draft_id: Mapped[str] = mapped_column(String(36), index=True)
    draft_revision: Mapped[int] = mapped_column(Integer)
    contact_id: Mapped[str] = mapped_column(String(36), index=True)
    recipient_email: Mapped[str] = mapped_column(String(254))
    idempotency_key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(15))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    subject: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gmail_message_id: Mapped[str | None] = mapped_column(String(150))
    gmail_thread_id: Mapped[str | None] = mapped_column(String(150))
    rfc_message_id: Mapped[str] = mapped_column(String(998))
    error: Mapped[str | None] = mapped_column(Text)


class MailTask(Scoped, Base):
    __tablename__ = "mail_tasks"
    contact_id: Mapped[str] = mapped_column(String(36), index=True)
    mailbox_id: Mapped[str | None] = mapped_column(ForeignKey("mailboxes.id"))
    thread_id: Mapped[str | None] = mapped_column(String(150))
    title: Mapped[str] = mapped_column(String(250))
    notes: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MailSuppression(Scoped, Base):
    __tablename__ = "mail_suppressions"
    __table_args__ = (UniqueConstraint("workspace_id", "email"),)
    contact_id: Mapped[str | None] = mapped_column(String(36))
    email: Mapped[str] = mapped_column(String(254))
    reason: Mapped[str] = mapped_column(String(30))
    notes: Mapped[str] = mapped_column(Text, default="")
