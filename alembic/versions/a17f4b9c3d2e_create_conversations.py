"""create conversations and conversation messages

Revision ID: a17f4b9c3d2e
Revises: 8c2f1d7a4b6e
Create Date: 2026-09-08
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a17f4b9c3d2e"
down_revision: str | Sequence[str] | None = "8c2f1d7a4b6e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The migration may be retried after a partial DDL failure. PostgreSQL
    # supports transactional DDL, but keeping the enum creation explicitly
    # idempotent also makes this migration safe when the enum already exists.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'conversation_message_role'
                  AND typnamespace = (
                      SELECT oid
                      FROM pg_namespace
                      WHERE nspname = current_schema()
                  )
            ) THEN
                CREATE TYPE conversation_message_role
                AS ENUM ('user', 'assistant');
            END IF;
        END
        $$;
        """
    )

    conversation_message_role = postgresql.ENUM(
        "user",
        "assistant",
        name="conversation_message_role",
        create_type=False,
    )

    op.create_table(
        "conversations",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.String(length=200),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_conversations_user_id",
        "conversations",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversations_created_at",
        "conversations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_conversations_updated_at",
        "conversations",
        ["updated_at"],
        unique=False,
    )

    op.create_table(
        "conversation_messages",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "role",
            conversation_message_role,
            nullable=False,
        ),
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_conversation_messages_conversation_id",
        "conversation_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversation_messages_created_at",
        "conversation_messages",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_messages_created_at",
        table_name="conversation_messages",
    )
    op.drop_index(
        "ix_conversation_messages_conversation_id",
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")

    op.drop_index(
        "ix_conversations_updated_at",
        table_name="conversations",
    )
    op.drop_index(
        "ix_conversations_created_at",
        table_name="conversations",
    )
    op.drop_index(
        "ix_conversations_user_id",
        table_name="conversations",
    )
    op.drop_table("conversations")

    op.execute(
        "DROP TYPE IF EXISTS conversation_message_role"
    )
