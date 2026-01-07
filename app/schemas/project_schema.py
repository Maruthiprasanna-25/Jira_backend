from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from app.schemas.user_schema import UserResponse

class ProjectResponse(BaseModel):
    id: int
    name: str
    project_prefix: str

    class Config:
        from_attributes = True
        orm_mode = True

class TeamSimple(BaseModel):
    id: int
    name: str
    class Config:
        from_attributes = True
        orm_mode = True

class TeamBase(BaseModel):
    name: str
    project_id: int
    lead_id: Optional[int] = None

class TeamCreate(TeamBase):
    member_ids: List[int] = []

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    lead_id: Optional[int] = None
    member_ids: Optional[List[int]] = None

class TeamResponse(TeamBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    members: List[UserResponse] = []
    lead: Optional[UserResponse] = None 
    
    class Config:
        from_attributes = True
        orm_mode = True
