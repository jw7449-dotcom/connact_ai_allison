"""Workspace Gmail mailboxes, filtered inbox and reviewed delivery commands.

Revision ID: f429db531011
Revises: e318ca421010
"""
from alembic import op
import sqlalchemy as sa

revision = "f429db531011"
down_revision = "e318ca421010"
branch_labels = None
depends_on = None


def scoped():
    return [sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.create_table("mailboxes", *scoped(),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("access_token_encrypted", sa.Text),
        sa.Column("refresh_token_encrypted", sa.Text),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("scopes", sa.JSON, nullable=False),
        sa.Column("sync_enabled", sa.Boolean, nullable=False),
        sa.Column("signature_html", sa.Text, nullable=False),
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column("send_window_start", sa.Integer, nullable=False),
        sa.Column("send_window_end", sa.Integer, nullable=False),
        sa.Column("history_id", sa.String(100)),
        sa.Column("contacts_fingerprint", sa.String(64), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_error", sa.Text),
        sa.Column("sync_status", sa.String(30), nullable=False),
        sa.Column("sync_started_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workspace_id", "email"))
    op.create_table("gmail_oauth_states", *scoped(),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("code_verifier", sa.String(128), nullable=False),
        sa.Column("session_hash", sa.String(64)),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("mail_messages", *scoped(),
        sa.Column("mailbox_id", sa.String(36), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gmail_message_id", sa.String(150), nullable=False),
        sa.Column("gmail_thread_id", sa.String(150), nullable=False),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("contact_email", sa.String(254), nullable=False),
        sa.Column("from_email", sa.String(254), nullable=False),
        sa.Column("to_emails", sa.JSON, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("snippet", sa.Text, nullable=False),
        sa.Column("body_text", sa.Text, nullable=False),
        sa.Column("body_html", sa.Text, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(15), nullable=False),
        sa.Column("is_unread", sa.Boolean, nullable=False),
        sa.Column("is_archived", sa.Boolean, nullable=False),
        sa.Column("labels", sa.JSON, nullable=False),
        sa.Column("rfc_message_id", sa.String(998), nullable=False),
        sa.Column("in_reply_to", sa.Text, nullable=False),
        sa.Column("references", sa.Text, nullable=False),
        sa.Column("reply_to", sa.String(254), nullable=False),
        sa.Column("attachments", sa.JSON, nullable=False),
        sa.Column("is_automated", sa.Boolean, nullable=False),
        sa.UniqueConstraint("mailbox_id", "gmail_message_id"))
    op.create_table("mail_thread_states", *scoped(),
        sa.Column("mailbox_id", sa.String(36), sa.ForeignKey("mailboxes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gmail_thread_id", sa.String(150), nullable=False),
        sa.Column("notes", sa.Text, nullable=False),
        sa.Column("intent", sa.String(30), nullable=False),
        sa.UniqueConstraint("workspace_id", "mailbox_id", "gmail_thread_id"))
    op.create_table("mail_sends", *scoped(),
        sa.Column("mailbox_id", sa.String(36), sa.ForeignKey("mailboxes.id"), nullable=False),
        sa.Column("draft_id", sa.String(36), nullable=False),
        sa.Column("draft_revision", sa.Integer, nullable=False),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("recipient_email", sa.String(254), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(15), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("gmail_message_id", sa.String(150)),
        sa.Column("gmail_thread_id", sa.String(150)),
        sa.Column("rfc_message_id", sa.String(998), nullable=False),
        sa.Column("error", sa.Text),
        sa.UniqueConstraint("workspace_id", "idempotency_key"))
    op.create_table("mail_tasks", *scoped(),
        sa.Column("contact_id", sa.String(36), nullable=False),
        sa.Column("mailbox_id", sa.String(36), sa.ForeignKey("mailboxes.id")),
        sa.Column("thread_id", sa.String(150)),
        sa.Column("title", sa.String(250), nullable=False),
        sa.Column("notes", sa.Text, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.create_table("mail_suppressions", *scoped(),
        sa.Column("contact_id", sa.String(36)),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text, nullable=False),
        sa.UniqueConstraint("workspace_id", "email"))
    for table in ("mailboxes", "gmail_oauth_states", "mail_messages", "mail_thread_states", "mail_sends", "mail_tasks", "mail_suppressions"):
        op.create_index("ix_" + table + "_workspace_id", table, ["workspace_id"])
    for table, columns in {"mail_messages": ["mailbox_id", "contact_id"], "mail_sends": ["mailbox_id", "draft_id", "contact_id", "status", "scheduled_at"], "mail_tasks": ["contact_id", "due_at"]}.items():
        for column in columns:
            op.create_index("ix_" + table + "_" + column, table, [column])
    op.create_index("ix_mail_messages_thread", "mail_messages", ["workspace_id", "mailbox_id", "gmail_thread_id"])


def downgrade():
    for table in ("mail_suppressions", "mail_tasks", "mail_sends", "mail_thread_states", "mail_messages", "gmail_oauth_states", "mailboxes"):
        op.drop_table(table)
