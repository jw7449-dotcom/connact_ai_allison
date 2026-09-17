"""Workspace accounts, Google identities, and opaque, revocable sessions."""
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, Integer, Boolean, false
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from .models import Identity, now


class User(Identity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(250), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginSession(Identity, Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Invitation(Identity, Base):
    __tablename__ = "invitations"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(250))
    max_uses: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    use_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GoogleIdentity(Identity, Base):
    __tablename__ = "google_identities"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    subject: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class GoogleOAuthState(Identity, Base):
    __tablename__ = "google_oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    nonce_hash: Mapped[str] = mapped_column(String(64))
    code_verifier: Mapped[str] = mapped_column(String(128))
    next_path: Mapped[str] = mapped_column(String(2000))
    invitation_hash: Mapped[str | None] = mapped_column(String(64))
    linking_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    purpose: Mapped[str] = mapped_column(String(30), default="signin", server_default="signin")
    linking_email_hash: Mapped[str | None] = mapped_column(String(64))
    linking_session_hash: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
