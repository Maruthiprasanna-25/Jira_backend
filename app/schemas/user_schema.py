from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class LoginRequest(BaseModel):
    email: str
    password: str

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str
    role: Optional[str] = "DEVELOPER"

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    view_mode: str
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

class ModeSwitchRequestSchema(BaseModel):
    requested_mode: str
    reason: str
