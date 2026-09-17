"""Allow an invitation to admit a bounded number of accounts."""

from alembic import op
import sqlalchemy as sa

revision = "ae46c9811006"
down_revision = "fd98a3471005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invitations", sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("invitations", sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE invitations SET use_count = 1 WHERE used_at IS NOT NULL")


def downgrade():
    # Never reopen a partially used shared invitation as a single-use invitation.
    op.execute("UPDATE invitations SET used_at = CURRENT_TIMESTAMP WHERE use_count > 0 AND used_at IS NULL")
    op.drop_column("invitations", "use_count")
    op.drop_column("invitations", "max_uses")
