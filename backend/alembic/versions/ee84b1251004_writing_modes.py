"""Persist assisted, prompt and template writing modes."""

from alembic import op
import sqlalchemy as sa

revision = "ee84b1251004"
down_revision = "da72c13f1003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "drafts",
        sa.Column(
            "writing_mode", sa.String(15), nullable=False, server_default="assisted"
        ),
    )
    op.create_index(
        "uq_writing_jobs_pending",
        "writing_jobs",
        ["workspace_id", "draft_id", "draft_revision", "action"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued', 'running')"),
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade():
    op.drop_index("uq_writing_jobs_pending", table_name="writing_jobs")
    op.drop_column("drafts", "writing_mode")
