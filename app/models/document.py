from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

from sqlalchemy import Enum as SQLEnum
from app.models.document_status import DocumentStatus

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[DocumentStatus] = mapped_column(
    SQLEnum(
        DocumentStatus,
        name="document_status",
        values_callable=lambda enum: [
            member.value for member in enum
        ],
    ),
    nullable=False,
    default=DocumentStatus.UPLOADED,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    uploader = relationship(
        "User",
        backref="documents",
    )

    departments = relationship(
        "Department",
        secondary="document_departments",
        back_populates="documents",
    )