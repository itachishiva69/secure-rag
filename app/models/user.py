from datetime import datetime

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        SQLEnum(
            UserRole,
            name="user_role",
            values_callable=lambda enum: [
                member.value for member in enum
            ],
        ),
        nullable=False,
        default=UserRole.USER,
    )

    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    department = relationship(
        "Department",
        backref="users",
    )