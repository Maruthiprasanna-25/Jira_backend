from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from app.models import Team, User, Project
from app.schemas import TeamCreate, TeamUpdate

def team_to_dict(t):
    """
    Converts a Team model instance to a dictionary.
    Includes eager-loaded relationships if available.
    """
    if not t: return None
    return {
        "id": t.id,
        "name": t.name,
        "project_id": t.project_id,
        "lead_id": t.lead_id,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "members": [
            {
                "id": m.id,
                "username": m.username,
                "email": m.email,
                "role": m.role,
                "profile_pic": m.profile_pic,
                "created_at": m.created_at.isoformat() if m.created_at else None
            } for m in t.members
        ],
        "lead": {
            "id": t.lead.id,
            "username": t.lead.username,
            "email": t.lead.email,
            "role": t.lead.role,
            "profile_pic": t.lead.profile_pic,
            "created_at": t.lead.created_at.isoformat() if t.lead.created_at else None
        } if t.lead else None
    }

def create_team(db: Session, team_data: TeamCreate):
    """
    Creates a new team.
    
    Args:
        db: Database session
        team_data: Team creation data (name, project_id, etc.)
        
    Returns:
        dict: The created team
        
    Raises:
        HTTPException: If project/lead not found or member validation fails
    """
    # Verify project exists
    project = db.query(Project).filter(Project.id == team_data.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Verify lead exists if provided
    if team_data.lead_id:
        lead = db.query(User).filter(User.id == team_data.lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Team Lead not found")
    
    team = Team(
        name=team_data.name,
        project_id=team_data.project_id,
        lead_id=team_data.lead_id
    )
    
    db.add(team)
    db.flush() 
    
    if team_data.member_ids:
        members = db.query(User).filter(User.id.in_(team_data.member_ids)).all()
        if len(members) != len(team_data.member_ids):
             raise HTTPException(status_code=400, detail="Some member IDs are invalid")
        # Use assignment for many-to-many to be more robust
        team.members = members
    
    db.commit()
    
    # Return with eager loading to ensure serialization success
    result = db.query(Team).options(
        joinedload(Team.members), 
        joinedload(Team.lead)
    ).filter(Team.id == team.id).first()
    return team_to_dict(result)

def get_team(db: Session, team_id: int):
    """
    Retrieves a team by ID.
    
    Args:
        db: Database session
        team_id: Team ID
        
    Returns:
        dict: The team data
        
    Raises:
        HTTPException: If team not found
    """
    team = db.query(Team).options(joinedload(Team.members), joinedload(Team.lead)).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team_to_dict(team)

def get_teams_by_project(db: Session, project_id: int):
    """
    Retrieves all teams associated with a project.
    
    Args:
        db: Database session
        project_id: Project ID
        
    Returns:
        list: List of team dictionaries
    """
    teams = db.query(Team).options(joinedload(Team.members), joinedload(Team.lead)).filter(Team.project_id == project_id).all()
    return [team_to_dict(t) for t in teams]

def update_team(db: Session, team_id: int, team_update: TeamUpdate):
    """
    Updates an existing team.
    
    Args:
        db: Database session
        team_id: Team ID
        team_update: Data to update
        
    Returns:
        dict: Updated team data
        
    Raises:
        HTTPException: If team not found
    """
    # Fetch the Team model directly (not the dict from get_team)
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    if team_update.name:
        team.name = team_update.name
    
    if team_update.lead_id is not None:
        lead = db.query(User).filter(User.id == team_update.lead_id).first()
        if not lead:
             raise HTTPException(status_code=404, detail="New Team Lead not found")
        team.lead_id = team_update.lead_id

    if team_update.member_ids is not None:
        members = db.query(User).filter(User.id.in_(team_update.member_ids)).all()
        team.members = members

    db.commit()
    db.refresh(team)
    
    # Return with eager loading to ensure complete data
    updated_team = db.query(Team).options(
        joinedload(Team.members),
        joinedload(Team.lead)
    ).filter(Team.id == team_id).first()
    
    return team_to_dict(updated_team)

def delete_team(db: Session, team_id: int):
    """
    Deletes a team.
    
    Args:
        db: Database session
        team_id: Team ID
        
    Returns:
        bool: True if deleted
        
    Raises:
        HTTPException: If team not found
    """
    team = db.query(Team).filter(Team.id == team_id).first()

    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    db.delete(team)        # ✅ ORM instance
    db.commit()

    return True


def get_all_teams(db: Session):
    """
    Retrieves all teams in the system.
    """
    teams = db.query(Team).options(joinedload(Team.members), joinedload(Team.lead)).all()
    return [team_to_dict(t) for t in teams]
