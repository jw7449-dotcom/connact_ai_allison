"""Persist resumable document parsing and cache successful extractions."""

from alembic import op
import sqlalchemy as sa

revision = "fd98a3471005"
down_revision = "ee84b1251004"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("parsed_data", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("parse_mode", sa.String(15), nullable=False, server_default="legacy"),
        sa.Column("parse_provider", sa.String(30), nullable=False, server_default=""),
        sa.Column("parse_model", sa.String(150), nullable=False, server_default=""),
        sa.Column(
            "parse_prompt_version", sa.String(60), nullable=False, server_default=""
        ),
        sa.Column("parse_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parse_completed_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("uploaded_documents", column)
    op.create_index(
        "uq_documents_cached_parse",
        "uploaded_documents",
        [
            "workspace_id",
            "content_hash",
            "parse_mode",
            "parse_provider",
            "parse_model",
            "parse_prompt_version",
        ],
        unique=True,
        sqlite_where=sa.text(
            "content_hash IS NOT NULL AND status IN ('queued', 'processing', 'parsed')"
        ),
        postgresql_where=sa.text(
            "content_hash IS NOT NULL AND status IN ('queued', 'processing', 'parsed')"
        ),
    )
    # Old parsed rows did not retain the AI result; never pretend their result exists.
    op.execute(
        "UPDATE uploaded_documents SET status = 'failed', error = 'This older upload has no saved parse result. Retry parsing or use the existing saved persona.' WHERE status = 'parsed' AND parsed_data IS NULL"
    )


def downgrade():
    op.drop_index("uq_documents_cached_parse", table_name="uploaded_documents")
    for field in (
        "parse_completed_at",
        "parse_started_at",
        "parse_prompt_version",
        "parse_model",
        "parse_provider",
        "parse_mode",
        "content_hash",
        "parsed_data",
    ):
        op.drop_column("uploaded_documents", field)
