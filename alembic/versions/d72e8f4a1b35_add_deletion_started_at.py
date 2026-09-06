"""add deletion_started_at to documents

Revision ID: d72e8f4a1b35
Revises: c61f4a8b2d93
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa


revision = "d72e8f4a1b35"
down_revision = "c61f4a8b2d93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "deletion_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_documents_deletion_started_at",
        "documents",
        ["deletion_started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_documents_deletion_started_at",
        table_name="documents",
    )

    op.drop_column(
        "documents",
        "deletion_started_at",
    )
