"""Persistent sequence plans, progressive AI jobs, and reusable writing templates."""

from alembic import op
import sqlalchemy as sa

revision = "c183df901008"
down_revision = "b071cc521007"
branch_labels = None
depends_on = None


def scoped():
    return [sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.create_table("sequences", *scoped(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("language", sa.String(10), nullable=False, server_default="en"),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id"), nullable=True),
        sa.Column("persona_id", sa.String(36), sa.ForeignKey("personas.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("review_snapshot", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table("sequence_steps", *scoped(),
        sa.Column("sequence_id", sa.String(36), sa.ForeignKey("sequences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("draft_id", sa.String(36), sa.ForeignKey("drafts.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False, server_default=""),
        sa.Column("delay_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("thread_mode", sa.String(20), nullable=False, server_default="new_thread"))
    op.create_table("sequence_templates", *scoped(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("steps", sa.JSON(), nullable=False))
    op.create_table("sequence_jobs", *scoped(),
        sa.Column("sequence_id", sa.String(36), sa.ForeignKey("sequences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("mode", sa.String(15), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("model", sa.String(150), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("total_steps", sa.Integer(), nullable=False),
        sa.Column("completed_steps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_steps", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table("writing_templates", *scoped(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(60), nullable=False, server_default="Custom"),
        sa.Column("subject", sa.String(1000), nullable=False, server_default=""),
        sa.Column("body_html", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    for table in ("sequences", "sequence_steps", "sequence_templates", "sequence_jobs", "writing_templates"):
        op.create_index("ix_" + table + "_workspace_id", table, ["workspace_id"])
    for table, column in (("sequence_steps", "sequence_id"), ("sequence_steps", "draft_id"),
                          ("sequence_jobs", "sequence_id"), ("sequence_jobs", "status")):
        op.create_index("ix_" + table + "_" + column, table, [column])
    op.create_index("uq_sequence_jobs_pending", "sequence_jobs", ["workspace_id", "sequence_id"],
        unique=True, sqlite_where=sa.text("status IN ('queued', 'running')"),
        postgresql_where=sa.text("status IN ('queued', 'running')"))


def downgrade():
    for table in ("writing_templates", "sequence_jobs", "sequence_templates", "sequence_steps", "sequences"):
        op.drop_table(table)
