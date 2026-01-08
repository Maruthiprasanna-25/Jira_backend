from typing import List
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import User
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/admin", tags=["Admin"])

ALLOWED_ROLES = ["ADMIN", "DEVELOPER", "TESTER", "OTHER"]

@router.get("/users")
def admin_get_all_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves all users for the admin dashboard.
    Only accessible by Master Admin.
    """
    if not current_user.is_master_admin:
        raise HTTPException(status_code=403, detail="Only Master Admin can view all users")
    
    users = db.query(User).all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "profile_pic": user.profile_pic,
            "created_at": user.created_at
        }
        for user in users
    ]

@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    new_role: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Updates a user's role.
    Only Master Admin can perform this action.
    """
    if not current_user.is_master_admin:
        raise HTTPException(status_code=403, detail="Only Master Admin can change user roles")
    
    new_role = new_role.upper()
    if new_role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Allowed roles: {ALLOWED_ROLES}")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.id == current_user.id and new_role != "ADMIN":
        raise HTTPException(status_code=400, detail="Admin cannot remove their own ADMIN role")
    
    user.role = new_role
    db.commit()
    return {
        "message": "User role updated successfully",
        "user_id": user.id,
        "new_role": user.role
    }
