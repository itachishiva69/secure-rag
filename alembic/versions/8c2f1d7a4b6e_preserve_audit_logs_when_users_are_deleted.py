"""preserve audit logs when users are deleted

Revision ID: 8c2f1d7a4b6e
Revises: 4e7b9c2d1a6f
Create Date: 2026-09-08 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c2f1d7a4b6e"
down_revision: Union[str, None] = "4e7b9c2d1a6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_audit_logs_user_id_users"


def _find_user_foreign_key_name() -> str | None:
    bind = op.get_bind()

    result = bind.execute(
        sa.text(
            """
            SELECT
                con.conname
            FROM pg_constraint AS con
            JOIN pg_class AS tbl
                ON tbl.oid = con.conrelid
            JOIN pg_namespace AS nsp
                ON nsp.oid = tbl.relnamespace
            JOIN pg_attribute AS col
                ON col.attrelid = tbl.oid
                AND col.attnum = ANY(con.conkey)
            WHERE nsp.nspname = current_schema()
              AND tbl.relname = 'audit_logs'
              AND con.contype = 'f'
              AND col.attname = 'user_id'
            """
        )
    ).first()

    if result is None:
        return None

    return str(result[0])


def upgrade() -> None:
    op.alter_column(
        "audit_logs",
        "user_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    existing_constraint = _find_user_foreign_key_name()

    if existing_constraint is not None:
        op.drop_constraint(
            existing_constraint,
            "audit_logs",
            type_="foreignkey",
        )

    op.create_foreign_key(
        FK_NAME,
        "audit_logs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        FK_NAME,
        "audit_logs",
        type_="foreignkey",
    )

    op.create_foreign_key(
        "audit_logs_user_id_fkey",
        "audit_logs",
        "users",
        ["user_id"],
        ["id"],
    )

    op.alter_column(
        "audit_logs",
        "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
