"""add processing_started_at to documents

Revision ID: 9c6e1a4b7d2f
Revises: 8f7a3c9d1e2b
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "9c6e1a4b7d2f"
down_revision = "8f7a3c9d1e2b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "processing_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_documents_processing_started_at",
        "documents",
        ["processing_started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_documents_processing_started_at",
        table_name="documents",
    )

    op.drop_column(
        "documents",
        "processing_started_at",
    )