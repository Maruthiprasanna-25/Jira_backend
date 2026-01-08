from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models import User, UserStory, Team, Project

def check_issue_permission(user: User, resource, action: str, db: Session = None):
    """
    Centralized permission check logic for issues.
    
    Args:
        user: The user requesting access
        resource: instance of UserStory (or None for creation checks)
        action: "create", "read", "update", "delete"
        db: Optional database session
        
    Returns:
        bool: True if permitted, otherwise raises HTTPException
        
    Raises:
        HTTPException: If permission denied
    """
    if user.role == "ADMIN":
        return True # Admin has all permissions (except maybe super specific ones, but here All)

    # Context Mapping
    # Resource is usually a UserStory or Project. 
    
    if isinstance(resource, UserStory):
        return check_issue_permission(user, resource, action, db)
    
    # Check for Creation (resource might be a dict/object with target context)
    if action == "create_issue":
        # We need project_id and team_id from the request to validate
        # This is harder to genericize without context.
        # We will handle create logic in the route or specific helper.
        pass

    raise HTTPException(status_code=403, detail="Permission denied")

def can_create_issue(user: User, project_id: int, team_id: int, db: Session):
    """
    Checks if a user can create an issue in a project/team.
    
    Args:
        user: The user
        project_id: Target project ID
        team_id: Target team ID
        db: Database session
        
    Returns:
        bool: True if allowed
    """
    if user.role == "ADMIN":
        # Even Admins shouldn't create issues in inactive projects? 
        # Requirement: "no options to make any changes". Implies strict lock.
        # But Admin might need to override? Usually Inactive = Locked for everyone until active.
        # Let's check project status for everyone.
        pass

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not project.is_active:
        return False

    if user.role == "ADMIN":
        return True
    
    # Team Lead Check
    if not team_id:
        return False 
    
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        return False
        
    if team.lead_id == user.id:
        if team.project_id != project_id:
             return False 
        return True
        
    return False

def can_update_issue(user: User, story: UserStory, db: Session):
    """
    Checks if a user can update a specific issue.
    
    Args:
        user: The user
        story: The user story to update
        db: Database session
        
    Returns:
        bool: True if allowed
    """
    if not story.project.is_active:
        return False

    if user.role == "ADMIN":
        return True
    
    # Team Lead
    if story.team_id:
        team = db.query(Team).filter(Team.id == story.team_id).first()
        if team and team.lead_id == user.id:
            return True
        
    # Team Member (or Lead acting as Member)
    if story.assignee_id == user.id:
        return True
        
    return False

def can_delete_issue(user: User, story: UserStory, db: Session):
    """
    Checks if a user can delete a specific issue.
    
    Args:
        user: The user
        story: The user story to delete
        db: Database session
        
    Returns:
        bool: True if allowed
    """
    if not story.project.is_active:
        return False

    if user.role == "ADMIN":
        return True
    
    # Team Lead
    if story.team_id:
        team = db.query(Team).filter(Team.id == story.team_id).first()
        if team and team.lead_id == user.id:
            return True
            
    return False

def can_view_issue(user: User, story: UserStory, db: Session):
    """
    Checks if a user can view a specific issue.
    
    Args:
        user: The user
        story: The user story to view
        db: Database session
        
    Returns:
        bool: True if allowed
    """
    if user.role == "ADMIN":
        return True
        
    # Team Lead (Project Scoped permission?)
    # "view all issues within the project"
    # So we need to check if User is a Team Lead in the Project of the story.
    
    # Check if user leads ANY team in this project
    is_team_lead_in_project = (
        db.query(Team)
        .filter(Team.project_id == story.project_id, Team.lead_id == user.id)
        .count() > 0
    )
    if is_team_lead_in_project:
        return True
        
    # Team Member
    # "view issues assigned to their team"
    if story.team_id:
        # Check if user is member of story.team
        # We need to query membership
        team = db.query(Team).filter(Team.id == story.team_id).first()
        if team and user in team.members:
            return True
    
    # Fallback: If assigned to them directly
    if story.assignee_id == user.id:
        return True

    # 4. Assigned to ANY issue in the project
    # "if i am assigned to any user story in any project i need to get see all user stories in that project"
    is_assigned_in_project = (
        db.query(UserStory)
        .filter(UserStory.project_id == story.project_id, UserStory.assignee_id == user.id)
        .count() > 0
    )
    if is_assigned_in_project:
        return True
        
    return False
def is_admin(user: User):
    """
    Simple check if user is an ADMIN.
    """
    return user.role == "ADMIN"

def is_project_lead(user: User, project_id: int, db: Session):
    """
    Checks if user is a lead in a specific project.
    """
    if is_admin(user):
        return True
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if project and project.owner_id == user.id:
        return True
        
    # A Project Lead is defined as anyone who leads at least ONE team in that project
    return db.query(Team).filter(Team.project_id == project_id, Team.lead_id == user.id).count() > 0

def can_manage_team_members(user: User, team: Team, db: Session):
    """
    Checks if user can manage members of a team.
    """
    if is_admin(user):
        return True
    # Can manage if they are the lead of this specific team OR a lead of any team in this project
    return is_project_lead(user, team.project_id, db)
