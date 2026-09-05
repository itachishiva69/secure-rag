from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DepartmentCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=100,
    )

    model_config = ConfigDict(
        extra="forbid"
    )


class DepartmentResponse(BaseModel):
    id: int
    name: str
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )