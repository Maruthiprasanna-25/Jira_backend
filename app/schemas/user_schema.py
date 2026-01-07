from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    profile_pic: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
        orm_mode = True

class NotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True
        orm_mode = True

class NotificationCount(BaseModel):
    unread_count: int
