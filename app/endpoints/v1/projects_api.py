from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database.session import get_db
from app.models import Project, UserStory, User, Team
from app.schemas import ProjectResponse
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("", response_model=ProjectResponse)
def create_project(
    name: str = Form(...),
    project_prefix: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # Check if user is in ADMIN mode
    # Master Admin is always in ADMIN mode as per auth_api update
    if user.view_mode != "ADMIN":
        raise HTTPException(status_code=403, detail="Developers cannot create projects. Please switch to Admin Mode.")

    # Any user in ADMIN mode can create projects
    project = Project(
        name=name,
        project_prefix=project_prefix.upper(),
        owner_id=user.id
    )
    if project.current_story_number is None:
            project.current_story_number = 1
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

@router.put("/{id}")
def update_project(
    id: int,
    name: Optional[str] = Form(None),
    project_prefix: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != "ADMIN":
        raise HTTPException(403, "Only admins can update projects")
        
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(404, "Project not found")
        
    if name is not None:
        project.name = name
    if project_prefix is not None:
        project.project_prefix = project_prefix.upper()
        
    db.commit()
    db.refresh(project)
    return project

@router.delete("/{id}")
def delete_project(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role != "ADMIN":
        raise HTTPException(403, "Only admins can delete projects")
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    # delete all stories of project
    db.query(UserStory).filter(UserStory.project_id == id).delete()
    db.delete(project)
    db.commit()
    return {"message": "Project and all associated data deleted successfully"}

@router.get("")
def get_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.is_master_admin:
        # Master Admin sees everything
        projects = db.query(Project).all()
    elif user.view_mode == "ADMIN":
        # ADMIN mode: Shows projects you own
        projects = db.query(Project).filter(Project.owner_id == user.id).all()
    else:
        # DEVELOPER mode: Shows projects where you're a member/assignee (excluding owned projects)
        
        # Projects where user is assigned stories
        assigned_project_ids = [pid[0] for pid in db.query(UserStory.project_id)
            .filter(or_(
                UserStory.assignee_id == user.id,
                UserStory.assignee == user.username,
                UserStory.assignee == user.email
            ))
            .distinct()
            .all()]
        
        # Projects where user is a Team Lead or Member
        # Get all projects from teams user is in
        team_project_ids = [t.project_id for t in user.teams]
        led_project_ids = [t.project_id for t in user.led_teams]
            
        # Combine unique project IDs
        all_ids = list(set(assigned_project_ids + led_project_ids + team_project_ids))
        
        # Exclude projects user owns as specified
        projects = db.query(Project).filter(
            Project.id.in_(all_ids),
            Project.owner_id != user.id
        ).all()
        
    return [
        {
            "id": p.id,
            "name": p.name,
            "project_prefix": p.project_prefix,
            "owner_id": p.owner_id
        }
        for p in projects
    ]
