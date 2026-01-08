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
    """
    Creates a new project.
    Only accessible in Admin mode.
    """
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
    is_active: Optional[bool] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Updates an existing project.
    Only Admins can update. Enforces inactive project read-only logic.
    """
    if user.role != "ADMIN":
        raise HTTPException(403, "Only admins can update projects")
        
    project = db.query(Project).filter(Project.id == id).first()
    if not project:
        raise HTTPException(404, "Project not found")
        
    # Check for Inactive Lock
    if not project.is_active:
        # If project is inactive, the ONLY allowed change is to Activate it (is_active=True)
        # If is_active is True in request, allow it.
        # If is_active is None or False, and we are trying to change other things, Block it.
        if is_active is True:
            # Re-activating. Allow other changes too? Maybe. But strictly, let's allow it.
            pass
        else:
            # Not re-activating.
            raise HTTPException(403, "Project is inactive. You must activate it to make changes.")

    if name is not None:
        project.name = name
    if project_prefix is not None:
        project.project_prefix = project_prefix.upper()
    if is_active is not None:
        project.is_active = is_active
        
    db.commit()
    db.refresh(project)
    return project

@router.delete("/{id}")
def delete_project(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Deletes a project and all its associated stories.
    Only Admins can delete.
    """
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

@router.get("/inactive")
def get_inactive_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Retrieves inactive projects based on user role and permissions.
    """
    if user.is_master_admin:
        # Master Admin sees all inactive projects
        projects = db.query(Project).filter(Project.is_active == False).all()
    elif user.view_mode == "ADMIN":
        # ADMIN mode: Shows inactive projects you own
        projects = db.query(Project).filter(
            Project.owner_id == user.id,
            Project.is_active == False
        ).all()
    else:
        # DEVELOPER mode: Shows inactive projects where you're a member/assignee
        assigned_project_ids = [pid[0] for pid in db.query(UserStory.project_id)
            .filter(or_(
                UserStory.assignee_id == user.id,
                UserStory.assignee == user.username,
                UserStory.assignee == user.email
            ))
            .distinct()
            .all()]
        
        team_project_ids = [t.project_id for t in user.teams]
        led_project_ids = [t.project_id for t in user.led_teams]
            
        all_ids = list(set(assigned_project_ids + led_project_ids + team_project_ids))
        
        projects = db.query(Project).filter(
            Project.id.in_(all_ids),
            Project.owner_id != user.id,
            Project.is_active == False
        ).all()
        
    return [
        {
            "id": p.id,
            "name": p.name,
            "project_prefix": p.project_prefix,
            "owner_id": p.owner_id,
            "is_active": p.is_active
        }
        for p in projects
    ]

@router.get("")
def get_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Retrieves active projects viewable by the user.
    Admins see their owned projects.
    Developers see projects they are assigned to or members of.
    """
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
            "owner_id": p.owner_id,
            "is_active": p.is_active
        }
        for p in projects
    ]
