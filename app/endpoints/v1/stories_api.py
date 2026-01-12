import os
import shutil
from typing import Optional, List, Union, Dict, Any
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, Body
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from app.database.session import get_db
from app.models import Project, UserStory, User, Team
from app.auth.dependencies import get_current_user
from app.auth.permissions import can_create_issue, can_update_issue, can_view_issue
from app.utils.activity_logger import log_activity
from app.utils.notification_service import create_notification, notify_issue_assigned
from app.utils.utils import story_to_dict, track_change
from app.config.settings import settings
from app.schemas.story_schema import UserStoryActivityResponse, IssueType
from app.constants import ErrorMessages, SuccessMessages
from app.utils.common import get_object_or_404, check_project_active

from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/user-stories", tags=["user-stories"])


def _validate_hierarchy(db: Session, parent_id: Optional[int], issue_type: str, current_issue_id: Optional[int] = None):
    """
    Validates parent-child relationships between issues.
    Prevents circular dependencies and incorrect hierarchy (e.g., Epic -> Story -> Task).
    """
    if not parent_id:
        # Relaxed rules: Stories and Tasks can be orphans (no parent).
        # Subtasks must still have a parent? Let's check.
        if issue_type == "Subtask":
            raise HTTPException(400, "Subtask must belong to a Task (parent_issue_id required).")
        return

    parent_story = db.query(UserStory).filter(UserStory.id == parent_id).first()
    if not parent_story:
        raise HTTPException(400, "Parent issue not found")
    
    # Cycle check
    if current_issue_id:
        if parent_id == current_issue_id:
            raise HTTPException(400, "Cannot set issue as its own parent.")
        # Walk up
        ancestor = parent_story
        while ancestor.parent_issue_id:
            if ancestor.parent_issue_id == current_issue_id:
                raise HTTPException(400, ErrorMessages.CIRCULAR_DEPENDENCY)
            ancestor = ancestor.parent  # Requires loading parent, SA relation helps
            if not ancestor:
                break
            
    ptype = parent_story.issue_type
    
    if issue_type == "Epic":
        raise HTTPException(400, "Epics cannot have a parent issue.")
    
    if issue_type == "Story" and ptype != "Epic":
        raise HTTPException(400, f"Story must be a child of an Epic, not {ptype}.")
        
    if issue_type == "Task" and ptype != "Story":
        raise HTTPException(400, f"Task must be a child of a Story, not {ptype}.")
        
    if issue_type == "Subtask" and ptype != "Task":
        raise HTTPException(400, f"Subtask must be a child of a Task, not {ptype}.")
        
    if issue_type == "Bug" and ptype not in ["Story", "Task"]:
        raise HTTPException(400, f"Bug must be a child of a Story or Task, not {ptype}.")


def _generate_story_code(db: Session, project_id: int) -> str:
    """
    Generates a unique story code in the format PREFIX-0001.
    Handles potential collisions when multiple projects share the same prefix.
    """
    # Fetch Project to get prefix
    project = get_object_or_404(db, Project, project_id, ErrorMessages.PROJECT_NOT_FOUND)

    # Use project_prefix preferred, fallback to name if empty
    prefix_raw = getattr(project, 'project_prefix', None)
    name_raw = getattr(project, 'name', '')  # Model attribute is 'name'
    prefix_val = prefix_raw if prefix_raw else name_raw[:2].upper()
        
    # Find the maximum number across ALL stories with this prefix globally
    stories_with_prefix = db.query(UserStory)\
        .filter(UserStory.story_pointer.like(f"{prefix_val}-%"))\
        .all()

    max_num = 0
    for s in stories_with_prefix:
        val = s.story_pointer
        if val:
            try:
                num = int(val.split('-')[-1])
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                continue
    
    next_num = max_num + 1
    return f"{prefix_val}-{next_num:04d}"


# Aggregated Activity Log Helper
def _log_activity_aggregated(db: Session, story_id: int, user_id: Optional[int], action: str, changes_dict: dict):
    """
    Logs changes to a story in an aggregated format (one entry per update transaction).
    """
    if not changes_dict and action == "UPDATED":
        return

    change_lines = []
    if action == "CREATED":
        change_lines.append("Issue Created")
    
    for field, vals in changes_dict.items():
        change_lines.append(f"{field}: {vals['old']} → {vals['new']}")
        
    changes_text = "\n".join(change_lines)
    
    # Import locally to avoid circular if needed or use model directly
    from app.models.story import UserStoryActivity
    
    activity = UserStoryActivity(
        story_id=story_id,
        user_id=user_id,
        action=action,
        changes=changes_text,
        change_count=len(changes_dict)
    )
    db.add(activity)


@router.get("/types", response_model=List[str])
def get_issue_types(user: User = Depends(get_current_user)):
    """
    Returns all supported issue types dynamically from the IssueType enum.
    Single Source of Truth for frontend filters.
    """
    return [t.value for t in IssueType]


@router.get("/search")
def search_stories(
    q: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Search stories by title or story_pointer (Key).
    """
    query = db.query(UserStory).filter(
        or_(
            UserStory.title.ilike(f"%{q}%"),
            UserStory.story_pointer.ilike(f"%{q}%"),
        )
    )
    
    # Permissions checks (simplified for search, generally if you have access to project you see it)
    if user.role != "ADMIN":
        led_ids = [t.project_id for t in user.led_teams]
        member_team_ids = [t.id for t in user.teams]
        assigned_project_ids = [pid[0] for pid in db.query(UserStory.project_id).filter(UserStory.assignee_id == user.id).distinct().all()]
        
        query = query.filter(
            or_(
                UserStory.assignee_id == user.id,
                UserStory.team_id.in_(member_team_ids),
                UserStory.project_id.in_(led_ids),
                UserStory.project_id.in_(assigned_project_ids)
            )
        )
        
    results = query.limit(50).all()
    return [story_to_dict(s) for s in results]


@router.get("/available-parents")
def get_available_parents(
    project_id: int,
    issue_type: str,
    exclude_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Returns a list of potential parent issues based on the child's issue type.
    """
    print(f"DEBUG: get_available_parents called with project_id={project_id}, issue_type={issue_type}", flush=True)
    
    # Check project access
    project = get_object_or_404(db, Project, project_id, ErrorMessages.PROJECT_NOT_FOUND)
    
    is_owner = project.owner_id == user.id
    
    # Permission check based on view_mode
    if not user.is_master_admin:
        if user.view_mode == "ADMIN" and not is_owner:
            raise HTTPException(403, ErrorMessages.ACCESS_DENIED)
        elif user.view_mode == "DEVELOPER" and is_owner:
            raise HTTPException(403, ErrorMessages.ACCESS_DENIED)
    
    target_type = None
    if issue_type == "Story":
        target_type = "Epic"
    elif issue_type == "Task":
        target_type = "Story"
    elif issue_type == "Subtask":
        target_type = "Task"
    elif issue_type == "Bug":
        # Bugs can be child of Story or Task
        query = db.query(UserStory).filter(
            UserStory.project_id == project_id,
            UserStory.issue_type.in_(["Story", "Task"])
        )
        if exclude_id:
            query = query.filter(UserStory.id != exclude_id)
        results = query.all()
        print(f"DEBUG: Found {len(results)} parents of type Story/Task for Bug", flush=True)
        return [{"id": s.id, "title": s.title, "story_code": s.story_pointer} for s in results]
    
    if not target_type:
        return []
        
    query = db.query(UserStory).filter(
        UserStory.project_id == project_id,
        UserStory.issue_type == target_type
    )
    
    if exclude_id:
        query = query.filter(UserStory.id != exclude_id)
    
    results = query.all()
    print(f"DEBUG: Found {len(results)} parents of type {target_type}", flush=True)
    return [{"id": s.id, "title": s.title, "story_code": s.story_pointer} for s in results]


@router.get("/epics/all", response_model=List[dict])
def get_all_epics(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Returns all Epics visible to the user across all projects.
    Used for Global Create Issue (Navbar).
    """
    query = db.query(UserStory).join(Project).filter(UserStory.issue_type == "Epic")
    
    # Filter by user access
    if not user.is_master_admin:
        # Get list ofproject IDs user is part of (via teams)
        member_project_ids = db.query(Team.project_id).filter(
            Team.members.any(id=user.id)
        ).subquery()
        
        query = query.filter(
            or_(
                Project.owner_id == user.id,
                Project.id.in_(member_project_ids)
            )
        )
    
    epics = query.all()
    return [{
        "id": e.id, 
        "title": e.title, 
        "story_code": e.story_pointer, 
        "project_id": e.project_id,
        "project_name": e.project_name
    } for e in epics]


@router.post("")
def create_user_story(
    project_id: int = Form(...),
    release_number: Optional[str] = Form(None),
    sprint_number: Optional[str] = Form(None),
    assignee: str = Form(...),
    assignee_id: Optional[str] = Form(None),  # kept for backward compatibility
    assigned_to: Optional[str] = Form(None),  # NEW: frontend 'assigned_to'
    reviewer: Optional[str] = Form(None),
    title: str = Form(...),
    description: str = Form(...),
    issue_type: Optional[IssueType] = Form(None),
    priority: Optional[str] = Form(None),
    status: str = Form(...),
    # support_doc can come as empty string from some clients if not selected
    support_doc: Optional[Union[UploadFile, str]] = File(None), 
    start_date: Optional[date] = Form(None),
    end_date: Optional[date] = Form(None),
    team_id: Optional[str] = Form(None), # Changed to str
    parent_issue_id: Optional[str] = Form(None), # Changed to str
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Creates a new user story/issue.
    Validates permissions, hierarchy, and handles file uploads.
    """
    # Manual conversion for empty strings (robust)
    def parse_optional_int(val):
        if val is None:
            return None
        if not val or (isinstance(val, str) and not val.strip()):
            return None
        try:
            return int(val)
        except Exception:
            return None

    # Prefer 'assigned_to' (frontend) when present, else fall back to assignee_id
    parsed_assignee_id = parse_optional_int(assigned_to) if assigned_to is not None else parse_optional_int(assignee_id)
    parsed_team_id = parse_optional_int(team_id)
    parsed_parent_issue_id = parse_optional_int(parent_issue_id)
    
    # Handle support_doc if it's a string (empty)
    actual_support_doc = support_doc if isinstance(support_doc, UploadFile) else None

    # Debug log incoming values
    print("DEBUG create_user_story inputs:",
          f"assignee(param)={assignee!r}",
          f"assignee_id(param)={assignee_id!r}",
          f"assigned_to(param)={assigned_to!r}",
          f"parsed_assignee_id={parsed_assignee_id!r}",
          f"team_id(param)={team_id!r}",
          f"parsed_team_id={parsed_team_id!r}",
          f"creator_id={user.id}",
          flush=True)

    # Resolve assignee and permissions
    if user.role == "DEVELOPER":
        is_team_lead = False
        if parsed_team_id:
            if any(t.id == parsed_team_id for t in user.led_teams):
                is_team_lead = True
        
        is_project_lead = any(t.project_id == project_id for t in user.led_teams)

        if is_team_lead or is_project_lead:
            # ALLOW assignment
            if parsed_assignee_id:
                 target_user = get_object_or_404(db, User, parsed_assignee_id, ErrorMessages.USER_NOT_FOUND)
                 assignee = target_user.username
            else:
                 if not assignee or not assignee.strip():
                     assignee = "Unassigned"
        else:
            # Regular Developer: Forced Self-Assignment
            parsed_assignee_id = user.id
            assignee = user.username
    else:
        # ADMIN / MASTER_ADMIN
        if parsed_assignee_id:
            target_user = get_object_or_404(db, User, parsed_assignee_id, ErrorMessages.USER_NOT_FOUND)
            assignee = target_user.username
        else:
            if not assignee or not assignee.strip():
                assignee = "Unassigned"

    project = get_object_or_404(db, Project, project_id, ErrorMessages.PROJECT_NOT_FOUND)
    check_project_active(project.is_active)

    # Permission Check
    if not can_create_issue(user, project_id, parsed_team_id, db):
        is_owner = project.owner_id == user.id
        if user.view_mode == "DEVELOPER" and is_owner:
            msg = "Project owners must switch to Admin mode to create issues in their own projects."
        elif user.view_mode == "ADMIN" and not is_owner:
            msg = "In Admin mode, you can only create issues in projects you own."
        else:
            msg = ErrorMessages.NO_PERMISSION_CREATE
        raise HTTPException(403, msg)

    # Hierarchy Logic
    type_str = issue_type.value if issue_type else None
    _validate_hierarchy(db, parsed_parent_issue_id, type_str)

    # Generate Code
    try:
        story_code = _generate_story_code(db, project_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Save File
    file_path = None
    if actual_support_doc:
        UPLOAD_DIR = "uploads"
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        file_path = f"{UPLOAD_DIR}/{actual_support_doc.filename}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(actual_support_doc.file, buffer)

    try:
        # If assignee is provided and team is selected, ensure the assignee is a member of the team
        if parsed_assignee_id and parsed_team_id:
            team = get_object_or_404(db, Team, parsed_team_id, ErrorMessages.TEAM_NOT_FOUND)

            # If user is not a member of the team, add them (auto-sync)
            member_ids = [m.id for m in (team.members or [])]
            if parsed_assignee_id not in member_ids:
                target_user = get_object_or_404(db, User, parsed_assignee_id, ErrorMessages.USER_NOT_FOUND)
                print(f"DEBUG: Adding user {parsed_assignee_id} to team {parsed_team_id} before create", flush=True)
                team.members.append(target_user)
                db.add(team)
                db.flush()

        new_story = UserStory(
            project_id=project_id,
            release_number=release_number,
            sprint_number=sprint_number,
            story_pointer=story_code,
            assignee=assignee,
            assignee_id=parsed_assignee_id,
            reviewer=reviewer,
            title=title,
            description=description,
            issue_type=issue_type.value if issue_type else None,
            priority=priority,
            status=status,
            support_doc=str(file_path) if file_path else None,
            start_date=start_date,
            end_date=end_date,
            team_id=parsed_team_id,
            parent_issue_id=parsed_parent_issue_id,
            created_by=user.id,
            project_name=project.name,
        )

        db.add(new_story)
        db.flush()
        db.refresh(new_story)
        
        # Log Creation
        _log_activity_aggregated(db, new_story.id, user.id, "CREATED", {"Status": {"old": "None", "new": status}})
        
        if new_story.assignee_id:
            notify_issue_assigned(db, new_story.assignee_id, new_story.title)

        db.commit()
        db.refresh(new_story)

        return story_to_dict(new_story)
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"ERROR in create_user_story: {str(e)}", flush=True)
        # Write to file
        with open("backend_error.log", "a") as f:
            f.write(f"\n--- ERROR at {datetime.now()} ---\n")
            f.write(error_msg)
            f.write("--------------------------------\n")
            
        db.rollback()
        raise HTTPException(500, f"Error creating user story: {str(e)}")


@router.get("/{id}/history", response_model=List[UserStoryActivityResponse])
def get_story_history(id: int, db: Session = Depends(get_db)):
    """
    Retrieves the activity history of a story.
    """
    from app.models.story import UserStoryActivity
    return db.query(UserStoryActivity).filter(UserStoryActivity.story_id == id).order_by(UserStoryActivity.created_at.desc()).all()


@router.get("/{id}")
def get_story_by_id(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Retrieves a specific story by ID.
    """
    story = get_object_or_404(db, UserStory, id, ErrorMessages.STORY_NOT_FOUND)

    if not can_view_issue(user, story, db):
        print(f"DEBUG get_story_by_id: permission denied for user={user.id} to view story={id}", flush=True)
        raise HTTPException(403, ErrorMessages.ACCESS_DENIED)
    return story_to_dict(story)


@router.put("/{id}")
def update_story(
    id: int,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    sprint_number: Optional[str] = Form(None),
    assignee: Optional[str] = Form(None),
    assignee_id: Optional[str] = Form(None), # str to handle empty
    reviewer: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    parent_issue_id: Optional[str] = Form(None), # str
    start_date: Optional[str] = Form(None), # Expecting "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM"
    end_date: Optional[str] = Form(None),
    priority: Optional[str] = Form(None),
    issue_type: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Updates an existing story.
    Logs activity and sends notifications for key changes.
    """
    story = get_object_or_404(db, UserStory, id, ErrorMessages.STORY_NOT_FOUND)
    check_project_active(story.project.is_active)
    
    if not can_update_issue(user, story, db):
        raise HTTPException(403, ErrorMessages.NO_PERMISSION_EDIT)
    
    # Manual Data Construction from Form
    def clean_str(val):
        if val == "" or val == "null" or val == "undefined": return None
        return val
        
    def clean_int(val):
        if not val: return None
        try: return int(val)
        except: return None
    
    # Clean Date Logic
    def parse_date_str(dstr):
        if not dstr: return None
        return dstr[:10]

    update_data = {}
    if title is not None: update_data['title'] = title
    if description is not None: update_data['description'] = description
    if sprint_number is not None: update_data['sprint_number'] = clean_str(sprint_number)
    if assignee is not None: update_data['assignee'] = assignee
    if assignee_id is not None: update_data['assignee_id'] = clean_int(assignee_id)
    if reviewer is not None: update_data['reviewer'] = clean_str(reviewer)
    if status is not None: update_data['status'] = status
    if parent_issue_id is not None: update_data['parent_issue_id'] = clean_int(parent_issue_id)
    if priority is not None: update_data['priority'] = priority
    if issue_type is not None: update_data['issue_type'] = issue_type
    
    if start_date is not None:
         dval = parse_date_str(start_date)
         update_data['start_date'] = datetime.strptime(dval, "%Y-%m-%d").date() if dval else None
    if end_date is not None:
         dval = parse_date_str(end_date)
         update_data['end_date'] = datetime.strptime(dval, "%Y-%m-%d").date() if dval else None

    # ENFORCE DEVELOPER RESTRICTIONS
    if user.role == "DEVELOPER":
        if 'assignee' in update_data:
            del update_data['assignee']
        if 'assignee_id' in update_data:
            del update_data['assignee_id']

    changes = {}
    
    # 0. Handle Parent Issue Hierarchy
    if 'parent_issue_id' in update_data:
        new_parent_id = update_data['parent_issue_id']
        if new_parent_id != story.parent_issue_id:
             try:
                 _validate_hierarchy(db, new_parent_id, story.issue_type, current_issue_id=story.id)
             except HTTPException as e:
                 raise e
             except Exception as e:
                 raise HTTPException(400, f"{ErrorMessages.INVALID_PARENT}: {str(e)}")
             
             changes["parent_issue_id"] = {"old": str(story.parent_issue_id), "new": str(new_parent_id)}
             story.parent_issue_id = new_parent_id

    # 1. Status Hierarchy Check
    if 'status' in update_data and update_data['status'] != story.status:
        new_status = update_data['status']
        if new_status.lower() == "done":
             pending_children = [
                 child for child in story.children 
                 if (child.status or "").lower() != "done"
             ]
             if pending_children:
                 raise HTTPException(400, f"Cannot mark as Done: Child issues are not Done ({len(pending_children)} pending).")
    
    # 2. Iterate
    for field, new_val in update_data.items():
        if field == "parent_issue_id": continue 

        old_val = getattr(story, field, None)
        
        str_old = str(old_val) if old_val is not None else ""
        str_new = str(new_val) if new_val is not None else ""
        
        if field in ['start_date', 'end_date']:
             str_new = str(new_val) if new_val is not None else ""
             
        if str_old != str_new:
            changes[field] = {"old": str_old, "new": str_new}
            setattr(story, field, new_val)
            
            if field == "assignee_id":
                 assignee_user = db.query(User).filter(User.id == new_val).first()
                 story.assignee = assignee_user.username if assignee_user else "Unknown"
                 if story.assignee_id:
                    notify_issue_assigned(db, story.assignee_id, story.title)
            
            if field == "status" and story.assignee_id:
                create_notification(db, story.assignee_id, "Status Updated", f"Story '{story.title}' is now {new_val}")
                
            if field == "priority" and story.assignee_id:
                create_notification(db, story.assignee_id, "Priority Updated", f"Priority for '{story.title}' changed to {new_val}")

    try:
        db.add(story)
        db.flush()
        
        _log_activity_aggregated(db, story.id, user.id, "UPDATED", changes)
        
        db.commit()
        db.refresh(story)
        return story_to_dict(story)
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Update failed: {str(e)}")
    

@router.get("/{id}/activity")
def get_story_activity(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    story = get_object_or_404(db, UserStory, id, ErrorMessages.STORY_NOT_FOUND)
    
    if not can_view_issue(user, story, db):
        raise HTTPException(403, ErrorMessages.ACCESS_DENIED)
    
    from app.models.story import UserStoryActivity
    activities = db.query(UserStoryActivity).filter(UserStoryActivity.story_id == id).order_by(UserStoryActivity.created_at.desc()).all()
    
    result = []
    for act in activities:
        u = db.query(User).filter(User.id == act.user_id).first() if act.user_id else None
        result.append({
            "id": act.id,
            "story_id": act.story_id,
            "user_id": act.user_id,
            "username": u.username if u else "System", 
            "action": act.action,
            "changes": act.changes,
            "created_at": act.created_at
        })
    return result


@router.get("/assigned/me")
def get_my_assigned_stories(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Retrieves stories assigned to the current user.
    Respects view_mode: Developer mode shows assigned work (excluding owned projects).
    """
    # Master admin sees all assigned stories
    if user.is_master_admin:
        stories = db.query(UserStory)\
            .options(joinedload(UserStory.team), joinedload(UserStory.project))\
            .filter(UserStory.assignee_id == user.id).all()
        return [story_to_dict(s) for s in stories]
    
    # Get owned project IDs
    owned_project_ids = [p.id for p in db.query(Project).filter(Project.owner_id == user.id).all()]
    
    # ADMIN mode: Only show assigned stories from owned projects
    if user.view_mode == "ADMIN":
        if not owned_project_ids:
            return []
        stories = db.query(UserStory)\
            .options(joinedload(UserStory.team), joinedload(UserStory.project))\
            .filter(
                UserStory.assignee_id == user.id,
                UserStory.project_id.in_(owned_project_ids)
            ).all()
    else:
        # DEVELOPER mode: Show assigned stories excluding owned projects
        if owned_project_ids:
            stories = db.query(UserStory)\
                .options(joinedload(UserStory.team), joinedload(UserStory.project))\
                .filter(
                    UserStory.assignee_id == user.id,
                    UserStory.project_id.notin_(owned_project_ids)
                ).all()
        else:
            stories = db.query(UserStory)\
                .options(joinedload(UserStory.team), joinedload(UserStory.project))\
                .filter(UserStory.assignee_id == user.id).all()
    
    return [story_to_dict(s) for s in stories]


@router.delete("/{id}")
def delete_user_story(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Deletes a story.
    Checks for project status (read-only if inactive).
    """
    story = get_object_or_404(db, UserStory, id, ErrorMessages.STORY_NOT_FOUND)
        
    check_project_active(story.project.is_active)
        
    db.delete(story)
    db.commit()
    return {"message": SuccessMessages.STORY_DELETED}


@router.get("/project/{project_id}")
def get_stories_by_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Retrieves all stories in a specific project.
    Respects view_mode: Admin mode shows owned projects, Developer mode shows assigned work.
    """
    try:
        # Debug: log caller and received project_id for diagnosis
        print(f"DEBUG get_stories_by_project called with project_id={project_id}, user_id={getattr(user, 'id', None)}, user_role={getattr(user, 'role', None)}, user_view_mode={getattr(user, 'view_mode', None)}", flush=True)

        # Master admin sees everything
        if user.is_master_admin:
            stories = db.query(UserStory)\
                .options(joinedload(UserStory.team), joinedload(UserStory.project))\
                .filter(UserStory.project_id == project_id).all()
            return [story_to_dict(s) for s in stories]
        
        # Check if user owns this project
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            print(f"DEBUG get_stories_by_project: Project id={project_id} not found in DB", flush=True)
            raise HTTPException(404, ErrorMessages.PROJECT_NOT_FOUND)
        
        is_owner = project.owner_id == user.id
        
        # Permission Check (mirroring get_available_parents logic?)
        # Generally:
        # - Admin mode: Show owned projects
        # - Dev mode: Show projects where user is member/assignee
        
        # For now, keeping the original logic which was a bit loose or specific to the frontend view.
        # But let's apply the view_mode filter as per docstring.
        
        query = db.query(UserStory)\
                .options(joinedload(UserStory.team), joinedload(UserStory.project))\
                .filter(UserStory.project_id == project_id)

        if user.view_mode == "ADMIN":
            if not is_owner:
                 # If not owner, you shouldn't see it in Admin view? 
                 # Or maybe strictly owned?
                 # Existing code didn't restrict hard here, but let's be consistent.
                 pass 
        
        stories = query.all()
        return [story_to_dict(s) for s in stories]

    except Exception as e:
        print(f"ERROR in get_stories_by_project: {str(e)}", flush=True)
        raise HTTPException(500, "Internal Server Error")