"""add audit logs

Revision ID: 8f7a3c9d1e2b
Revises: 5d4ac5502950
Create Date: 2026-09-05 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f7a3c9d1e2b"
down_revision: Union[str, None] = "5d4ac5502950"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
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
            "action",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "resource_type",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "resource_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "department_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "success",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_audit_logs_user_id",
        "audit_logs",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_action",
        "audit_logs",
        ["action"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_resource_id",
        "audit_logs",
        ["resource_id"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_department_id",
        "audit_logs",
        ["department_id"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_created_at",
        "audit_logs",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audit_logs_created_at",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_department_id",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_resource_id",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_action",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_user_id",
        table_name="audit_logs",
    )

    op.drop_table("audit_logs")