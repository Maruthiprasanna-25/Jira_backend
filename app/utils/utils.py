from typing import Optional
from app.utils.activity_logger import log_activity

def story_to_dict(s):
    if not s: return None
    return {
        "id": s.id,
        "project_id": s.project_id,
        "project_name": s.project_name,
        "story_pointer": s.story_pointer,
        "release_number": s.release_number,
        "sprint_number": s.sprint_number,
        "assignee_id": s.assignee_id,
        "team_id": s.team_id,
        "team": {"id": s.team.id, "name": s.team.name} if s.team else None,
        "assignee": s.assignee,
        "reviewer": s.reviewer,
        "title": s.title,
        "description": s.description,
        "issue_type": s.issue_type,
        "priority": s.priority,
        "status": s.status,
        "support_doc": s.support_doc,
        "start_date": str(s.start_date) if s.start_date else None,
        "end_date": str(s.end_date) if s.end_date else None,
        "parent_issue_id": s.parent_issue_id
    }

def track_change(db, story, user_id, field, old_value, new_value):
    norm_old = "" if old_value is None else str(old_value).strip()
    norm_new = "" if new_value is None else str(new_value).strip()
    if field in ["start_date", "end_date"]:
        try:
            o_date = str(old_value)[:10] if old_value else ""
            n_date = str(new_value)[:10] if new_value else ""
            if o_date == n_date:
                return
        except:
            pass
    if norm_old == norm_new:
        return
    log_activity(
        db=db,
        issue_id=story.id,
        user_id=user_id,
        action_type="FIELD_UPDATED",
        field_changed=field,
        old_value=old_value,
        new_value=new_value
    )
