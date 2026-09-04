from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    filename: str
    storage_path: str
    department_ids: list[int]


class DocumentResponse(BaseModel):
    id: int
    filename: str
    storage_path: str
    uploaded_by: int
    status: str
    created_at: datetime
    department_ids: list[int]

    model_config = ConfigDict(from_attributes=True)