from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentCreate(BaseModel):
    filename: str = Field(
        min_length=1,
        max_length=255,
    )
    storage_path: str = Field(
        min_length=1,
        max_length=1024,
    )
    department_ids: list[int] = Field(
        min_length=1,
    )


class DocumentDepartmentUpdate(BaseModel):
    department_ids: list[int] = Field(
        min_length=1,
    )

    model_config = ConfigDict(
        extra="forbid"
    )


class DocumentResponse(BaseModel):
    id: int
    filename: str
    storage_path: str
    uploaded_by: int
    status: str
    created_at: datetime
    department_ids: list[int]

    model_config = ConfigDict(
        from_attributes=True
    )


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int

    model_config = ConfigDict(
        extra="forbid"
    )