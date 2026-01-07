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
    if user.role != "ADMIN":
        raise HTTPException(403, "Only admins can create projects")
    project = Project(
        name=name,
        project_prefix=project_prefix.upper()
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
    if user.role == "ADMIN":
        projects = db.query(Project).all()
    else:
        # Projects where user is assigned stories
        assigned_project_ids = [pid[0] for pid in db.query(UserStory.project_id)
            .filter(or_(
                UserStory.assignee_id == user.id,
                UserStory.assignee == user.username,
                UserStory.assignee == user.email
            ))
            .distinct()
            .all()]
        
        # Projects where user is a Team Lead
        led_project_ids = [pid[0] for pid in db.query(Team.project_id)
            .filter(Team.lead_id == user.id)
            .distinct()
            .all()]
            
        # Combine unique project IDs
        all_ids = list(set(assigned_project_ids + led_project_ids))
        
        projects = db.query(Project).filter(Project.id.in_(all_ids)).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "project_prefix": p.project_prefix
        }
        for p in projects
    ]
