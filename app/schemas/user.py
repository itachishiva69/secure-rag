from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: str
    department_id: int | None
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )