"""Persistent writing briefs and reviewable asynchronous suggestions."""

from alembic import op
import sqlalchemy as sa

revision = "9c3b2f1a7001"
down_revision = "5aba178b468a"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("model", sa.String(150), nullable=False, server_default=""),
        sa.Column("length", sa.String(15), nullable=False, server_default="medium"),
        sa.Column("cta", sa.Text(), nullable=False, server_default=""),
        sa.Column("custom_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
    ):
        op.add_column("drafts", column)
    op.create_table(
        "writing_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "draft_id", sa.String(36), sa.ForeignKey("drafts.id"), nullable=False
        ),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("mode", sa.String(15), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(150), nullable=False),
        sa.Column("prompt_version", sa.String(60), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for field in ("workspace_id", "draft_id", "status"):
        op.create_index("ix_writing_jobs_" + field, "writing_jobs", [field])


def downgrade():
    op.drop_table("writing_jobs")
    for field in ("evidence_ids", "custom_instructions", "cta", "length", "model"):
        op.drop_column("drafts", field)
