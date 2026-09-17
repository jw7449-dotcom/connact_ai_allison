"""Invite accounts and revocable sessions.

Revision ID: da72c13f1003
Revises: c216770d1002
"""
from alembic import op
import sqlalchemy as sa

revision = "da72c13f1003"
down_revision = "c216770d1002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("email", sa.String(250), nullable=False),
        sa.Column("password_hash", sa.String(300), nullable=False),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True),
        sa.UniqueConstraint("email"), sa.UniqueConstraint("workspace_id"))
    op.create_table("login_sessions",
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(36), primary_key=True))
    op.create_index("ix_login_sessions_user_id", "login_sessions", ["user_id"])
    op.create_table("invitations",
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(250), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), primary_key=True))


def downgrade():
    op.drop_table("invitations")
    op.drop_index("ix_login_sessions_user_id", "login_sessions")
    op.drop_table("login_sessions")
    op.drop_table("users")
