from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(
        min_length=8,
        max_length=128,
    )
    role: str = Field(
        min_length=1,
        max_length=20,
    )
    department_id: int | None = None

    model_config = ConfigDict(
        extra="forbid"
    )


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: str
    department_id: int | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    limit: int
    offset: int

    model_config = ConfigDict(
        extra="forbid"
    )