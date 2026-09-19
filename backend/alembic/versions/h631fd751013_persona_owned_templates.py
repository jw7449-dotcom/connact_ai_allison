"""Writing templates belong to a persona."""

from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = "h631fd751013"
down_revision = "g531ec641012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("writing_templates", sa.Column("persona_id", sa.String(), nullable=True))
    op.create_index("ix_writing_templates_persona_id", "writing_templates", ["persona_id"])
    op.create_foreign_key(
        "fk_writing_templates_persona_id",
        "writing_templates",
        "personas",
        ["persona_id"],
        ["id"],
        ondelete="CASCADE",
    )
    bind = op.get_bind()
    workspaces = bind.execute(
        sa.text("select distinct workspace_id from writing_templates")
    ).scalars().all()
    for workspace_id in workspaces:
        persona_id = bind.execute(
            sa.text(
                "select id from personas where workspace_id = :w"
                " order by created_at asc limit 1"
            ),
            {"w": workspace_id},
        ).scalar()
        if persona_id is None:
            # Templates must not be lost; an empty persona is recoverable.
            persona_id = str(uuid4())
            bind.execute(
                sa.text(
                    "insert into personas (id, workspace_id, label, domain, version,"
                    " data, created_at, updated_at)"
                    " values (:i, :w, 'Persona 1', 'finance', 1, :d, now(), now())"
                ),
                {"i": persona_id, "w": workspace_id, "d": "{}"},
            )
        bind.execute(
            sa.text(
                "update writing_templates set persona_id = :p"
                " where workspace_id = :w and persona_id is null"
            ),
            {"p": persona_id, "w": workspace_id},
        )
    op.alter_column("writing_templates", "persona_id", nullable=False)


def downgrade():
    op.drop_constraint(
        "fk_writing_templates_persona_id", "writing_templates", type_="foreignkey"
    )
    op.drop_index("ix_writing_templates_persona_id", table_name="writing_templates")
    op.drop_column("writing_templates", "persona_id")
