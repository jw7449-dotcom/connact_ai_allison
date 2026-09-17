"""Bind explicit administrator linking to its target email and live session."""
from alembic import op
import sqlalchemy as sa

revision = "e318ca421010"
down_revision = "d247ab731009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("google_oauth_states", sa.Column("purpose", sa.String(30), nullable=False, server_default="signin"))
    op.add_column("google_oauth_states", sa.Column("linking_email_hash", sa.String(64), nullable=True))
    op.add_column("google_oauth_states", sa.Column("linking_session_hash", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("google_oauth_states", "linking_session_hash")
    op.drop_column("google_oauth_states", "linking_email_hash")
    op.drop_column("google_oauth_states", "purpose")
