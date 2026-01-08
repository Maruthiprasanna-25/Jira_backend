import os
import shutil
from typing import Optional, List, Union, Dict, Any
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, Body
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database.session import get_db
from app.models import Project, UserStory, User
from app.auth.dependencies import get_current_user
from app.auth.permissions import can_create_issue, can_update_issue, can_view_issue
from app.utils.activity_logger import log_activity
from app.utils.notification_service import create_notification, notify_issue_assigned
from app.utils.utils import story_to_dict, track_change
from app.config.settings import settings
from app.schemas.story_schema import UserStoryActivityResponse, IssueType

from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/user-stories", tags=["user-stories"])

def _validate_hierarchy(db: Session, parent_id: Optional[int], issue_type: str, current_issue_id: Optional[int] = None):
    if not parent_id:
        if issue_type == "Story":
             raise HTTPException(400, "Story must belong to an Epic (parent_issue_id required).")
        if issue_type == "Task":
             raise HTTPException(400, "Task must belong to a Story (parent_issue_id required).")
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
                raise HTTPException(400, "Circular dependency detected.")
            ancestor = ancestor.parent # Requires loading parent, SA relation helps
            # If relation isn't eager loaded this might trigger queries, which is fine for depth < 10
            # Safety break for deep trees? Jira limit? Assume OK.
            if not ancestor: break
            
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
    # Fetch Project to get prefix
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")
        
    # Find the last created story to determine the next number
    last_story = db.query(UserStory)\
        .filter(UserStory.project_id == project_id)\
        .order_by(UserStory.id.desc())\
        .first()

    if last_story:
        # Get the actual Python string value, not the Column object
        val = getattr(last_story, 'story_pointer', None)
        if val:
            try:
                # Assumes format "PREFIX-0001"
                last_num = int(val.split('-')[-1])
                next_num = last_num + 1
            except (ValueError, IndexError):
                # Fallback if code format is weird
                count = db.query(UserStory).filter(UserStory.project_id == project_id).count()
                next_num = count + 1
        else:
            next_num = 1
    else:
        next_num = 1
    
    # Use project_prefix preferred, fallback to name if empty
    # Extract actual values to avoid Column type issues
    prefix_raw = getattr(project, 'project_prefix', None)
    name_raw = getattr(project, 'project_name', '')
    prefix_val = prefix_raw if prefix_raw else name_raw[:2].upper()
    
    return f"{prefix_val}-{next_num:04d}"

# Aggregated Activity Log Helper
def _log_activity_aggregated(db: Session, story_id: int, user_id: Optional[int], action: str, changes_dict: dict):
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
            # UserStory.description.ilike(f"%{q}%") # Optional, maybe too heavy
        )
    )
    
    # Permissions checks (simplified for search, generally if you have access to project you see it)
    # Re-using logic from get_all_stories might be better but let's stick to basic search for now.
    # Ideally should filter by projects user has access to.
    if user.role != "ADMIN":
        led_ids = [t.project_id for t in user.led_teams]
        member_team_ids = [t.id for t in user.teams]
        # This is getting complex to replicate 1:1.
        # Let's filter post-query or add constraints.
        
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
        print(f"DEBUG: Found {len(results)} parents of type {target_type}", flush=True)
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


@router.post("")
def create_user_story(
    project_id: int = Form(...),
    release_number: Optional[str] = Form(None),
    sprint_number: Optional[str] = Form(None),
    assignee: str = Form(...),
    assignee_id: Optional[str] = Form(None), # Changed to str to handle ""
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
    # Manual conversion for empty strings
    def parse_optional_int(val):
        if not val or (isinstance(val, str) and not val.strip()):
            return None
        return int(val)

    parsed_assignee_id = parse_optional_int(assignee_id)
    parsed_team_id = parse_optional_int(team_id)
    parsed_parent_issue_id = parse_optional_int(parent_issue_id)
    
    # Handle support_doc if it's a string (empty)
    actual_support_doc = support_doc if isinstance(support_doc, UploadFile) else None

    if user.role == "OTHER":
        raise HTTPException(403, "Read-only access for this role")
    
    if not can_create_issue(user, project_id, parsed_team_id, db):
        raise HTTPException(403, "Insufficient permissions to create issue in this context. Team Leads must specify their team.")

    # Hierarchy Logic
    type_str = issue_type.value if issue_type else None
    _validate_hierarchy(db, parsed_parent_issue_id, type_str)
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # Generate Code
    try:
        story_code = _generate_story_code(db, project_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Save File
    file_path = None
    if actual_support_doc:
         # ... existing file save logic ...
         UPLOAD_DIR = "uploads"
         os.makedirs(UPLOAD_DIR, exist_ok=True)
         file_path = f"{UPLOAD_DIR}/{actual_support_doc.filename}"
         with open(file_path, "wb") as buffer:
            shutil.copyfileobj(actual_support_doc.file, buffer)

    new_story = UserStory(
        project_id=project_id,
        release_number=release_number,
        sprint_number=sprint_number,
        story_pointer=story_code, # Auto-generated, mapped to story_pointer
        assignee=assignee,
        assignee_id=parsed_assignee_id,
        reviewer=reviewer,
        title=title,
        description=description,
        issue_type=issue_type.value if issue_type else None,
        priority=priority,
        status=status,
        support_doc=str(file_path) if file_path else None,
        start_date=start_date, # Now directly date or None
        end_date=end_date,     # Now directly date or None
        team_id=parsed_team_id,
        parent_issue_id=parsed_parent_issue_id,
        created_by=user.id, # New field
        project_name=project.name, # Denormalized field requirements?
    )

    db.add(new_story)
    db.flush() # Get ID
    db.refresh(new_story)
    
    # Log Creation
    _log_activity_aggregated(db, new_story.id, user.id, "CREATED", {"Status": {"old": "None", "new": status}})
    
    if new_story.assignee_id:
        notify_issue_assigned(db, new_story.assignee_id, new_story.title)

    db.commit()
    db.refresh(new_story)

    return story_to_dict(new_story)

@router.get("/{id}/history", response_model=List[UserStoryActivityResponse])
def get_story_history(id: int, db: Session = Depends(get_db)):
    from app.models.story import UserStoryActivity
    return db.query(UserStoryActivity).filter(UserStoryActivity.story_id == id).order_by(UserStoryActivity.created_at.desc()).all()

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
    story = db.query(UserStory).filter(UserStory.id == id).first()
    if not story:
        raise HTTPException(404, "Story not found")
    
    if not can_update_issue(user, story, db):
        raise HTTPException(403, "No permission to edit this issue.")
    
    # Manual Data Construction from Form
    def clean_str(val):
        if val == "" or val == "null" or val == "undefined": return None
        return val
        
    def clean_int(val):
        if not val: return None
        try: return int(val)
        except: return None

    # Construct update dict, only including fields that were present in Form
    # BUT FastAPI Form defaults to None, so we can't distinguish "not sent" from "sent as None".
    # However, 'update' usually sends typical fields.
    # We will assume if it's None, it wasn't updated? 
    # NO: What if user clears a field?
    # Frontend sends ALL fields in the payload usually (see IssueDetailModal spread).
    # So we can safely look at the args.
    
    # Clean Date Logic
    def parse_date_str(dstr):
        if not dstr: return None
        # Handle "YYYY-MM-DDTHH:MM" or "YYYY-MM-DD"
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
    
    # Dates: we must handle string inputs and convert to date objects (or strings if model allows)
    # Model has Date columns, we can assign Date objects.
    if start_date is not None:
         dval = parse_date_str(start_date)
         update_data['start_date'] = datetime.strptime(dval, "%Y-%m-%d").date() if dval else None
    if end_date is not None:
         dval = parse_date_str(end_date)
         update_data['end_date'] = datetime.strptime(dval, "%Y-%m-%d").date() if dval else None

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
                 raise HTTPException(400, f"Invalid parent assignment: {str(e)}")
             
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
        
        # Date string compare (already converted to date obj or None)
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
    story = db.query(UserStory).filter(UserStory.id == id).first()
    if not story:
        raise HTTPException(404, "Story not found")
    if not can_view_issue(user, story, db):
        raise HTTPException(403, "Access denied")
    
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
    db.delete(story)
    db.commit()
    return {"message": "Story deleted successfully"}




@router.get("/project/{project_id}/board")
def get_project_board(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
         raise HTTPException(404, "Project not found")
    
    stories = db.query(UserStory).filter(UserStory.project_id == project_id).all()
    
    # Build Map
    stories_map = {s.id: s for s in stories}
    children_map = {s.id: [] for s in stories}
    
    for s in stories:
        if s.parent_issue_id and s.parent_issue_id in children_map:
            children_map[s.parent_issue_id].append(s)
            
    # Recursive helper to build tree
    def build_tree(story_id):
        s = stories_map[story_id]
        node = story_to_dict(s)
        # Check loops?? assuming safe
        if s.id in children_map:
             node['children'] = [build_tree(c.id) for c in children_map[s.id]]
        else:
             node['children'] = []
        return node
    
    epics = [s for s in stories if (s.issue_type or "").lower() == IssueType.epic.value.lower()]
    
    # REQUIRED: Return orphan groups? user said NO "Issues without Epic" section.
    # So we only return Epics.
    
    result = []
    
    for epic in epics:
        epic_node = story_to_dict(epic)
        # For the board, the Frontend expects 'children' to be the direct issues under this epic?
        # Board.jsx iterates over 'group.children'.
        # Our build_tree returns children recursively.
        # But 'children_map[epic.id]' contains correct direct children.
        # We need to format them through build_tree to get nested structure if frontend uses it (it seems flat list columns in Board.jsx though).
        # Board.jsx uses 'group.children.filter(...)' so it seems to expect a list of direct children.
        # If there are subtasks, they are children of Tasks.
        # Board.jsx likely puts Tasks in columns. What about subtasks?
        # Board.jsx doesn't seem to recurse for subtasks in the column view.
        # It just lists children.
        
        result.append({
            "epic": epic_node,
            "children": [build_tree(c.id) for c in children_map[epic.id]]
        })
        
    return result