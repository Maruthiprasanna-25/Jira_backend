from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional
from app.schemas.project_schema import TeamSimple
from enum import Enum

class IssueType(str, Enum):
    epic = "Epic"
    story = "Story"
    task = "Task"
    bug = "Bug"
    subtask = "Subtask"

class UserStoryResponse(BaseModel):
    id: int
    project_id: int
    project_name: str
    story_pointer: Optional[str] = None # Support existing
    story_code: Optional[str] = None # New standard

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
    parent_issue_id: Optional[int] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        orm_mode = True

class UserStoryActivityResponse(BaseModel):
    """
    Aggregated activity log response.
    Represents ONE save action with multiple field changes.
    """
    id: int
    story_id: int
    user_id: Optional[int]
    action: str  # UPDATED, CREATED, STATUS_CHANGED
    changes: str  # Human-readable text
    change_count: int  # Number of fields changed
    created_at: datetime

    class Config:
        from_attributes = True
        orm_mode = True

class UserStoryUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    sprint_number: Optional[str] = None
    assignee: Optional[str] = None
    assignee_id: Optional[int] = None # Added for consistency
    reviewer: Optional[str] = None
    status: Optional[str] = None
    parent_issue_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    priority: Optional[str] = None
    issue_type: Optional[str] = None
