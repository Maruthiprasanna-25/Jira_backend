from app.models import ActivityLog
from sqlalchemy.orm import Session

def log_activity(
    db: Session,
    issue_id: int,
    user_id: int,
    action_type: str,
    field_changed: str = None,
    old_value: str = None,
    new_value: str = None
):
    log = ActivityLog(
        issue_id=issue_id,
        user_id=user_id,
        action_type=action_type,
        field_changed=field_changed,
        old_value=str(old_value) if old_value else None,
        new_value=str(new_value) if new_value else None,
    )

    db.add(log)
    db.commit()
    db.refresh(log)

    return log
