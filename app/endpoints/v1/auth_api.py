import os
import shutil
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models import User
from app.auth.auth_utils import (
    hash_password,
    verify_password,
    create_access_token,
    validate_password,
    validate_lowercase_email
)
from app.auth.dependencies import get_current_user
from app.config.settings import settings
from app.schemas.user_schema import LoginRequest, SignupRequest

router = APIRouter(prefix="/auth", tags=["Auth"])

ALLOWED_ROLES = ["ADMIN", "DEVELOPER", "TESTER"]

@router.post("/signup")
def signup(
    request: SignupRequest,
    db: Session = Depends(get_db)
):
    """
    Registers a new user with the specified role.
    Checks if email already exists and enforces validation.
    """
    allowed_roles = ["DEVELOPER", "TESTER"]
    
    if request.role not in allowed_roles:
        if request.role == "ADMIN":
            raise HTTPException(status_code=403, detail="ADMIN role cannot be chosen during signup")
        request.role = "DEVELOPER"
    
    if db.query(User).filter(User.email == request.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    validate_password(request.password)
    validate_lowercase_email(request.email)
    
    user = User(
        username=request.username,
        email=request.email,
        hashed_password=hash_password(request.password),
        role=request.role
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return {"message": "User registered successfully"}

@router.get("/users")
def get_all_users(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Retrieve all users to populate assignee lists"""
    return db.query(User).all()

def perform_login(email: str, password: str, db: Session):
    """
    Validates credentials and generates an access token.
    Handles view mode logic for promoted admins.
    """
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Default view_mode based on role on fresh login
    if not user.is_master_admin:
        # If user is an ADMIN (promoted), default to ADMIN mode. Otherwise DEVELOPER.
        user.view_mode = "ADMIN" if user.role == "ADMIN" else "DEVELOPER"
        db.commit()
    
    token = create_access_token({
        "user_id": user.id,
        "role": user.role
    })
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "role": user.role,
        "view_mode": user.view_mode,
        "is_master_admin": user.is_master_admin
    }

@router.post("/login")
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    Authenticates a user and returns a JWT token.
    """
    return perform_login(request.email, request.password, db)

@router.post("/token")
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """OAuth2 compatible token login, for Swagger UI"""
    return perform_login(form_data.username, form_data.password, db)

@router.get("/me")
def my_profile(user: User = Depends(get_current_user)):
    """
    Retrieves the current authenticated user's profile.
    """
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "view_mode": user.view_mode,
        "is_master_admin": user.is_master_admin,
        "profile_pic": user.profile_pic,
        "created_at": user.created_at
    }

@router.post("/switch-mode")
def switch_mode(
    mode: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Switches the current user's view mode (Admin/Developer).
    Master Admin cannot switch modes.
    """
    if user.is_master_admin:
        raise HTTPException(400, "Master Admin cannot switch modes")
    
    if mode not in ["ADMIN", "DEVELOPER"]:
        raise HTTPException(400, "Invalid mode")
        
    user.view_mode = mode
    db.commit()
    return {"message": f"Switched to {mode} mode", "view_mode": user.view_mode}

@router.post("/verify-password")
def verify_current_password(
    password: str = Form(...),
    user: User = Depends(get_current_user)
):
    """
    Verifies the current user's password (e.g., before sensitive actions).
    """
    if not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"valid": True}

@router.put("/me")
def update_profile(
    username: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    current_password: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates the calling user's profile (Username, Password).
    Requires current password to change password.
    """
    if username:
        user.username = username
    
    if password:
        if not current_password:
            raise HTTPException(400, "Current password is required to set a new password")
        if not verify_password(current_password, user.hashed_password):
            raise HTTPException(401, "Invalid current password")
            
        validate_password(password)
        user.hashed_password = hash_password(password)
    
    db.commit()
    db.refresh(user)
    return user

@router.post("/me/avatar")
def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Uploads a profile picture for the current user.
    """
    UPLOAD_DIR = os.path.join(settings.UPLOAD_DIR, "avatars")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    file_ext = file.filename.split(".")[-1]
    filename = f"user_{user.id}_{int(datetime.utcnow().timestamp())}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    user.profile_pic = f"/uploads/avatars/{filename}"
    db.commit()
    return {"profile_pic": user.profile_pic}

@router.delete("/me/profile-pic")
def delete_profile_pic(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Removes the current user's profile picture.
    """
    user.profile_pic = None
    db.commit()
    return {"message": "Profile picture removed"}

@router.post("/logout")
def logout():
    return {"message": "Logout successful"}
