"""Administrator roles and database-backed original uploads."""

from alembic import op
import sqlalchemy as sa

revision = "b071cc521007"
down_revision = "ae46c9811006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table("document_files",
        sa.Column("document_id", sa.String(36), sa.ForeignKey("uploaded_documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False))


def downgrade():
    op.drop_table("document_files")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "is_admin")
