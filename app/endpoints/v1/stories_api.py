import os
import shutil
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database.session import get_db
from app.models import Project, UserStory, User, ActivityLog
from app.auth.dependencies import get_current_user
from app.auth.permissions import can_create_issue, can_update_issue, can_view_issue
from app.utils.activity_logger import log_activity
from app.utils.notification_service import create_notification, notify_issue_assigned
from app.utils.utils import story_to_dict, track_change
from app.config.settings import settings

router = APIRouter(prefix="/user-stories", tags=["user-stories"])

@router.post("")
def create_user_story(
    project_id: int = Form(...),
    release_number: Optional[str] = Form(None),
    sprint_number: Optional[str] = Form(None),
    assignee: str = Form(...),
    assignee_id: Optional[int] = Form(None),
    reviewer: Optional[str] = Form(None),
    title: str = Form(...),
    description: str = Form(...),
    issue_type: Optional[str] = Form(None),
    priority: Optional[str] = Form(None),
    status: str = Form(...),
    support_doc: Optional[UploadFile] = File(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    team_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role == "OTHER":
        raise HTTPException(403, "Read-only access for this role")
    
    if not can_create_issue(user, project_id, team_id, db):
        raise HTTPException(403, "Insufficient permissions to create issue in this context. Team Leads must specify their team.")
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    
    if project.current_story_number is None:
        project.current_story_number = 1
    
    story_pointer = f"{project.project_prefix}-{project.current_story_number:04d}"
    project.current_story_number += 1
    
    filename = None
    if support_doc:
        base_name = support_doc.filename
        unique_name = f"{story_pointer}_{base_name}"
        file_path = os.path.join(settings.UPLOAD_DIR, unique_name)
        with open(file_path, "wb") as f:
            shutil.copyfileobj(support_doc.file, f)
        filename = unique_name
    
    story = UserStory(
        project_id=project.id,
        project_name=project.name,
        story_pointer=story_pointer,
        release_number=release_number,
        sprint_number=sprint_number,
        assignee=assignee,
        assignee_id=assignee_id,
        reviewer=reviewer,
        title=title,
        description=description,
        issue_type=issue_type,
        priority=priority,
        status=status,
        support_doc=filename,
        start_date=start_date,
        end_date=end_date,
        team_id=team_id
    )
    db.add(story)
    db.commit()
    db.refresh(story)
    
    log_activity(db=db, issue_id=story.id, user_id=user.id, action_type="ISSUE_CREATED")
    
    if story.assignee_id:
        notify_issue_assigned(db, story.assignee_id, story.title)
    
    return story_to_dict(story)

@router.get("")
def get_all_stories(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role == "ADMIN":
        stories = db.query(UserStory).all()
    else:
        led_project_ids = [t.project_id for t in user.led_teams]
        member_team_ids = [t.id for t in user.teams]
        assigned_project_ids = [
            pid[0] for pid in 
            db.query(UserStory.project_id)
            .filter(UserStory.assignee_id == user.id)
            .distinct()
            .all()
        ]
        
        stories = db.query(UserStory).filter(
            or_(
                UserStory.assignee_id == user.id,
                UserStory.team_id.in_(member_team_ids),
                UserStory.project_id.in_(led_project_ids),
                UserStory.project_id.in_(assigned_project_ids)
            )
        ).all()
    
    return [story_to_dict(s) for s in stories]

@router.get("/project/{project_id}")
def get_stories_by_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    query = db.query(UserStory).filter(UserStory.project_id == project_id)
    
    if user.role != "ADMIN":
        is_lead_in_project = any(t.project_id == project_id for t in user.led_teams)
        has_assignment_in_project = (
            db.query(UserStory)
            .filter(UserStory.project_id == project_id, UserStory.assignee_id == user.id)
            .count() > 0
        )
        if not (is_lead_in_project or has_assignment_in_project):
            member_team_ids = [t.id for t in user.teams]
            query = query.filter(
                or_(
                    UserStory.assignee_id == user.id,
                    UserStory.team_id.in_(member_team_ids)
                )
            )
    stories = query.all()
    return [story_to_dict(s) for s in stories]

@router.get("/{id}")
def get_story_by_id(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    story = db.query(UserStory).filter(UserStory.id == id).first()
    if not story:
        raise HTTPException(404, "Story not found")
    if not can_view_issue(user, story, db):
        raise HTTPException(403, "Access denied")
    return story_to_dict(story)

@router.get("/{id}/activity")
def get_story_activity(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    story = db.query(UserStory).filter(UserStory.id == id).first()
    if not story:
        raise HTTPException(404, "Story not found")
    if not can_view_issue(user, story, db):
        raise HTTPException(403, "Access denied")
        
    activities = db.query(ActivityLog).filter(ActivityLog.issue_id == id).order_by(ActivityLog.created_at.desc()).all()
    
    result = []
    for act in activities:
        u = db.query(User).filter(User.id == act.user_id).first()
        result.append({
            "id": act.id,
            "issue_id": act.issue_id,
            "user_id": act.user_id,
            "username": u.username if u else "Unknown",
            "action_type": act.action_type,
            "field_changed": act.field_changed,
            "old_value": act.old_value,
            "new_value": act.new_value,
            "created_at": act.created_at
        })
    return result

@router.put("/{id}")
def update_story(
    id: int,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    issue_type: Optional[str] = Form(None),
    priority: Optional[str] = Form(None),
    assignee: Optional[str] = Form(None),
    assignee_id: Optional[int] = Form(None),
    reviewer: Optional[str] = Form(None),
    sprint_number: Optional[str] = Form(None),
    release_number: Optional[str] = Form(None),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    team_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    story = db.query(UserStory).filter(UserStory.id == id).first()
    if not story:
        raise HTTPException(404, "Story not found")
    
    if not can_update_issue(user, story, db):
        raise HTTPException(403, "No permission to edit this issue.")
    
    if team_id is not None:
        track_change(db, story, user.id, "team_id", story.team_id, team_id)
        story.team_id = team_id
    
    if title is not None:
        track_change(db, story, user.id, "Title", story.title, title)
        story.title = title
    if status is not None and story.status != status:
        track_change(db, story, user.id, "status", story.status, status)
        story.status = status
        if story.assignee_id:
            create_notification(db, story.assignee_id, "Status Updated", f"Story '{story.title}' is now {status}")
    if priority is not None and story.priority != priority:
        track_change(db, story, user.id, "priority", story.priority, priority)
        story.priority = priority
        if story.assignee_id:
            create_notification(db, story.assignee_id, "Priority Updated", f"Priority for '{story.title}' changed to {priority}")
    if assignee_id is not None and story.assignee_id != assignee_id:
        track_change(db, story, user.id, "assignee_id", story.assignee_id, assignee_id)
        story.assignee_id = assignee_id
        if not assignee:
             assignee_user = db.query(User).filter(User.id == assignee_id).first()
             story.assignee = assignee_user.username if assignee_user else "Unknown"
    
    if description is not None:
        track_change(db, story, user.id, "description", story.description, description)
        story.description = description
    if issue_type is not None:
        track_change(db, story, user.id, "issue_type", story.issue_type, issue_type)
        story.issue_type = issue_type
    if reviewer is not None:
        track_change(db, story, user.id, "reviewer", story.reviewer, reviewer)
        story.reviewer = reviewer
    if sprint_number is not None:
        track_change(db, story, user.id, "sprint_number", story.sprint_number, sprint_number)
        story.sprint_number = sprint_number
    if release_number is not None:
        track_change(db, story, user.id, "release_number", story.release_number, release_number)
        story.release_number = release_number
    if start_date is not None:
        track_change(db, story, user.id, "start_date", story.start_date, start_date)
        story.start_date = start_date
    if end_date is not None:
        track_change(db, story, user.id, "end_date", story.end_date, end_date)
        story.end_date = end_date
        
    db.commit()
    db.refresh(story)
    return story_to_dict(story)
@router.get("/assigned/me")
def get_my_assigned_stories(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # This fetches stories specifically assigned to the logged-in user
    stories = db.query(UserStory).filter(UserStory.assignee_id == user.id).all()
    return [story_to_dict(s) for s in stories]

@router.delete("/{id}")
def delete_user_story(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    story = db.query(UserStory).filter(UserStory.id == id).first()
    if not story:
        raise HTTPException(404, "Story not found")
        
    # Only allow owners, leads, or admins to delete (adjust as needed)
    db.delete(story)
    db.commit()
    return {"message": "Story deleted successfully"}