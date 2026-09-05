"""add document processing status

Revision ID: 5d4ac5502950
Revises: a293bdc4d50d
Create Date: 2026-09-04 07:36:24.721601

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5d4ac5502950"
down_revision: Union[str, Sequence[str], None] = "a293bdc4d50d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


document_status_enum = sa.Enum(
    "uploaded",
    "processing",
    "indexed",
    "failed",
    name="document_status",
)


def upgrade() -> None:
    """Upgrade schema."""

    document_status_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    op.alter_column(
        "documents",
        "status",
        server_default=None,
        existing_type=sa.VARCHAR(length=50),
        existing_nullable=False,
    )

    op.alter_column(
        "documents",
        "status",
        existing_type=sa.VARCHAR(length=50),
        type_=document_status_enum,
        existing_nullable=False,
        postgresql_using="status::document_status",
    )

    op.alter_column(
        "documents",
        "status",
        server_default=sa.text(
            "'uploaded'::document_status"
        ),
        existing_type=document_status_enum,
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.alter_column(
        "documents",
        "status",
        server_default=None,
        existing_type=document_status_enum,
        existing_nullable=False,
    )

    op.alter_column(
        "documents",
        "status",
        existing_type=document_status_enum,
        type_=sa.VARCHAR(length=50),
        existing_nullable=False,
        postgresql_using="status::text",
    )

    op.alter_column(
        "documents",
        "status",
        server_default=sa.text(
            "'uploaded'::character varying"
        ),
        existing_type=sa.VARCHAR(length=50),
        existing_nullable=False,
    )

    document_status_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )