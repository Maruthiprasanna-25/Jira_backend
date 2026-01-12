from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database.session import get_db
from app.schemas import TeamCreate, TeamUpdate
from app.utils import team_service
from app.auth.dependencies import get_current_user
from app.models import User, Team
from app.auth.permissions import (
    is_admin,
    is_project_lead,
    can_manage_team_members
)
from app.utils.notification_service import create_notification
from app.constants import ErrorMessages, SuccessMessages
from app.utils.common import get_object_or_404

router = APIRouter(prefix="/teams", tags=["Teams"])

@router.post("", status_code=201)
def create_team(
    team_data: TeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Creates a new team.
    Restricted to Admins and Project Leads.
    """
    if not is_project_lead(current_user, team_data.project_id, db):
        raise HTTPException(
            status_code=403,
            detail=ErrorMessages.ONLY_ADMINS_PROJECT_LEADS
        )

    new_team = team_service.create_team(db, team_data)

    lead_id = (
        new_team.get("lead_id")
        if isinstance(new_team, dict)
        else getattr(new_team, "lead_id", None)
    )

    team_name = (
        new_team.get("name")
        if isinstance(new_team, dict)
        else getattr(new_team, "name", "")
    )

    if lead_id:
        create_notification(
            db,
            lead_id,
            "Team Lead Assignment",
            f"You have been assigned as the Team Lead for team '{team_name}'."
        )

    return new_team

@router.get("")
def get_all_teams(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves all teams in the system.
    """
    return team_service.get_all_teams(db)

@router.get("/project/{project_id}")
def get_project_teams(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves all teams for a specific project.
    """
    return team_service.get_teams_by_project(db, project_id)

@router.get("/{team_id}")
def get_team(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves details of a specific team.
    """
    return team_service.get_team(db, team_id)

@router.put("/{team_id}")
def update_team(
    team_id: int,
    team_update: TeamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Updates an existing team.
    Restricted to Admins and Project Leads.
    """
    team_model = get_object_or_404(db, Team, team_id, ErrorMessages.TEAM_NOT_FOUND)

    old_lead_id = team_model.lead_id

    if not can_manage_team_members(current_user, team_model, db):
        raise HTTPException(
            status_code=403,
            detail="Only Admins or Project Leads can manage team members"
        )

    updated_team = team_service.update_team(db, team_id, team_update)

    team_name = (
        updated_team.get("name")
        if isinstance(updated_team, dict)
        else getattr(updated_team, "name", "")
    )

    if team_update.lead_id is not None and team_update.lead_id != old_lead_id:
        create_notification(
            db,
            team_update.lead_id,
            "Team Lead Assignment",
            f"You have been assigned as the Team Lead for team '{team_name}'."
        )
        
        if old_lead_id:
             create_notification(
                db,
                old_lead_id,
                "Team Lead Removal",
                f"You have been removed as the Team Lead for team '{team_name}'."
            )

    return updated_team

@router.delete("/{team_id}")
def delete_team(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Deletes a team.
    Restricted to Admins.
    """
    if not is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only Admins can delete teams"
        )

    team_service.delete_team(db, team_id)
    return {"message": SuccessMessages.TEAM_DELETED}