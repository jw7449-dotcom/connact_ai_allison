"""Persist discovery and independent profile/email enrichment jobs."""

from alembic import op
import sqlalchemy as sa

revision = "c216770d1002"
down_revision = "9c3b2f1a7001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "people_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id")),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("upstream", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("next_poll_at", sa.DateTime(timezone=True)),
    )
    for field in ("workspace_id", "contact_id", "status", "fingerprint"):
        op.create_index("ix_people_jobs_" + field, "people_jobs", [field])


def downgrade():
    op.drop_table("people_jobs")
