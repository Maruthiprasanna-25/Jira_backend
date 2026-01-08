from app.models import Notification

def create_notification(db, user_id: int, title: str, message: str):
    """
    Creates a new notification for a user.
    
    Args:
        db: Database session
        user_id: Target user ID
        title: Notification title
        message: Notification message body
        
    Returns:
        Notification: The created notification entry
    """
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
    """
    Helper to send an 'Issue Assigned' notification.
    
    Args:
        db: Database session
        user_id: Target user ID
        issue_title: Title of the assigned issue
    """
    return create_notification(
        db, 
        user_id, 
        "Issue Assigned", 
        f"You have been assigned to: {issue_title}"
    )