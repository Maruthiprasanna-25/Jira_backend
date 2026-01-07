from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional
from app.schemas.project_schema import TeamSimple

class UserStoryResponse(BaseModel):
    id: int
    project_id: int
    project_name: str
    story_pointer: str
    team: Optional[TeamSimple] = None

    release_number: Optional[str]
    sprint_number: Optional[str]

    assignee_id: Optional[int]
    team_id: Optional[int] = None

    assignee: str
    reviewer: Optional[str]

    title: str
    description: str
    issue_type: Optional[str]
    priority: Optional[str]
    status: str

    support_doc: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        orm_mode = True
