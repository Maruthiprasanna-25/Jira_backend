# from app.routes.notifications import Notification
from app.models import Notification
def notify_issue_assigned(db, user_id: int, issue_title: str):

    notification = Notification(
        user_id=user_id,
        title="Issue Assigned",
        message=f"You have been assigned to: {issue_title}"
    )

    db.add(notification)
    db.commit()
    db.refresh(notification)

    return notification
from app.models import Notification

def create_notification(db, user_id: int, title: str, message: str):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification

def notify_issue_assigned(db, user_id: int, issue_title: str):
    return create_notification(
        db, 
        user_id, 
        "Issue Assigned", 
        f"You have been assigned to: {issue_title}"
    )