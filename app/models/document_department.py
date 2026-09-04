from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class DocumentDepartment(Base):
    __tablename__ = "document_departments"

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )

    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"),
        primary_key=True,
    )