"""create outbox events

Revision ID: b47d2f8a6c31
Revises: 9c6e1a4b7d2f
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "b47d2f8a6c31"
down_revision = "9c6e1a4b7d2f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),
        sa.Column(
            "event_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey(
                "documents.id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "dispatched_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_outbox_events_event_type",
        "outbox_events",
        ["event_type"],
        unique=False,
    )

    op.create_index(
        "ix_outbox_events_document_id",
        "outbox_events",
        ["document_id"],
        unique=False,
    )

    op.create_index(
        "ix_outbox_events_status",
        "outbox_events",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_outbox_events_available_at",
        "outbox_events",
        ["available_at"],
        unique=False,
    )

    op.create_index(
        "ix_outbox_events_created_at",
        "outbox_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outbox_events_created_at",
        table_name="outbox_events",
    )

    op.drop_index(
        "ix_outbox_events_available_at",
        table_name="outbox_events",
    )

    op.drop_index(
        "ix_outbox_events_status",
        table_name="outbox_events",
    )

    op.drop_index(
        "ix_outbox_events_document_id",
        table_name="outbox_events",
    )

    op.drop_index(
        "ix_outbox_events_event_type",
        table_name="outbox_events",
    )

    op.drop_table(
        "outbox_events"
    )