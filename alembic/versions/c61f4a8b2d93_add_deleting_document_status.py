"""add deleting document status

Revision ID: c61f4a8b2d93
Revises: b47d2f8a6c31
Create Date: 2026-09-05
"""

from alembic import op


revision = "c61f4a8b2d93"
down_revision = "b47d2f8a6c31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE document_status "
        "ADD VALUE IF NOT EXISTS 'deleting'"
    )


def downgrade() -> None:
    # PostgreSQL does not support removing a single
    # enum value safely with a simple ALTER TYPE.
    #
    # The migration is intentionally irreversible.
    pass