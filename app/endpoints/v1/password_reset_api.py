import secrets
import hashlib
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database.session import get_db
from app.models import User, PasswordResetToken
from app.auth.auth_utils import hash_password, validate_password
from app.utils.email_service import send_reset_email

router = APIRouter(prefix="/auth", tags=["Password Reset"])

RESET_TOKEN_EXPIRY_MINUTES = 30

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

@router.post("/forgot-password")
def request_password_reset(
    email: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Initiates password reset process.
    Sends an email with a reset link if the account exists.
    """
    user = db.query(User).filter(User.email == email.lower()).first()
    if not user:
        return {"message": "If account exists, a reset link was sent"}

    db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id).delete()

    raw_token = secrets.token_urlsafe(32)
    hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

    reset_record = PasswordResetToken(
        user_id=user.id,
        hashed_token=hashed_token,
        expires_at=datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)
    )

    db.add(reset_record)
    db.commit()

    reset_link = f"http://localhost:5173/reset-password?token={raw_token}"

    print("\n" + "="*50)
    print("RESET PASSWORD LINK:", reset_link)
    print("="*50 + "\n")

    background_tasks.add_task(
        send_reset_email,
        email_to=user.email,
        reset_link=reset_link
    )

    print("📨 Reset email queued to send")
    return {"message": "Password reset link sent if account exists"}

@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """
    Resets the user's password using a valid token.
    """
    validate_password(data.new_password)
    hashed_token = hashlib.sha256(data.token.encode()).hexdigest()

    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.hashed_token == hashed_token,
        PasswordResetToken.used == False
    ).first()

    if not reset_token:
        raise HTTPException(400, "Invalid or expired reset link")

    if reset_token.expires_at < datetime.utcnow():
        raise HTTPException(400, "Reset link expired")

    user = db.query(User).filter(User.id == reset_token.user_id).first()
    user.hashed_password = hash_password(data.new_password)
    reset_token.used = True

    db.commit()
    return {"message": "Password reset successful"}
