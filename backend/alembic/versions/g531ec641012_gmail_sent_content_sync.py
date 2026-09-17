"""Refresh provisional sent-message content and Gmail attachment IDs once."""
from alembic import op
import sqlalchemy as sa

revision = "g531ec641012"
down_revision = "f429db531011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mail_messages", sa.Column("content_synced", sa.Boolean(), nullable=False, server_default=sa.true()))
    # Existing app sends may predate this field and lack Gmail attachment IDs.
    op.execute("UPDATE mail_messages SET content_synced = false WHERE direction = 'outgoing'")


def downgrade():
    op.drop_column("mail_messages", "content_synced")
