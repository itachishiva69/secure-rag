"""use enum for user roles

Revision ID: cc1eb9b21ad6
Revises: 020f08e0843f
Create Date: 2026-09-03

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "cc1eb9b21ad6"
down_revision: Union[str, Sequence[str], None] = "020f08e0843f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


user_role_enum = sa.Enum(
    "admin",
    "user",
    name="user_role",
)


def upgrade() -> None:
    # Create the PostgreSQL enum type first.
    user_role_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    # Convert the existing VARCHAR column to the enum.
    op.alter_column(
        "users",
        "role",
        existing_type=sa.VARCHAR(length=50),
        type_=user_role_enum,
        postgresql_using="role::user_role",
        existing_nullable=False,
    )


def downgrade() -> None:
    # Convert the enum back to VARCHAR.
    op.alter_column(
        "users",
        "role",
        existing_type=user_role_enum,
        type_=sa.VARCHAR(length=50),
        postgresql_using="role::varchar",
        existing_nullable=False,
    )

    # Remove the PostgreSQL enum type.
    user_role_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )