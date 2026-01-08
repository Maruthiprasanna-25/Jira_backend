from app.models.story import UserStoryActivity
from sqlalchemy.orm import Session
from typing import Optional

def log_activity(
    db: Session,
    issue_id: int,
    user_id: int,
    action_type: str,
    field_changed: str = None,
    old_value: str = None,
    new_value: str = None
):
    """
    Logs an activity/change for a user story.
    
    Args:
        db: Database session
        issue_id: ID of the user story
        user_id: ID of the user performing the action
        action_type: Type of action (e.g. 'updated', 'commented')
        field_changed: Optional field name that changed
        old_value: Previous value of the field
        new_value: New value of the field
        
    Returns:
        UserStoryActivity: The created activity log entry
    """
    changes = []
    if field_changed:
        changes.append(f"{field_changed}: {old_value} -> {new_value}")
    
    changes_text = "\n".join(changes) if changes else action_type

    log = UserStoryActivity(
        story_id=issue_id,
        user_id=user_id,
        action=action_type,
        changes=changes_text,
        change_count=1 if field_changed else 0
    )

    db.add(log)
    db.commit()
    db.refresh(log)

    return log
