from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models import Notification
from app.constants import ErrorMessages
from app.utils.common import get_object_or_404

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("")
def get_notifications(user_id: int, db: Session = Depends(get_db)):
    """
    Retrieves all notifications for a user, ordered by date.
    """
    return db.query(Notification).filter(Notification.user_id == user_id).order_by(Notification.created_at.desc()).all()

@router.put("/{notification_id}/read")
def mark_as_read(notification_id: int, db: Session = Depends(get_db)):
    """
    Marks a notification as read.
    """
    notification = get_object_or_404(db, Notification, notification_id, ErrorMessages.NOTIFICATION_NOT_FOUND)
    notification.is_read = True
    db.commit()
    return {"message": "Marked as read"}