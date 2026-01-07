import os
import shutil
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
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

router = APIRouter(prefix="/auth", tags=["Auth"])

ALLOWED_ROLES = ["ADMIN", "DEVELOPER", "TESTER", "OTHER"]

@router.post("/signup")
def signup(
    username: str,
    email: str,
    password: str,
    role: Optional[str] = "DEVELOPER",
    db: Session = Depends(get_db)
):
    allowed_roles = ["DEVELOPER", "TESTER", "OTHER"]
    
    if role not in allowed_roles:
        if role == "ADMIN":
            raise HTTPException(status_code=403, detail="ADMIN role cannot be chosen during signup")
        role = "DEVELOPER"
    
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    validate_password(password)
    validate_lowercase_email(email)
    
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        role=role
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

@router.post("/login")
def login(
    email: str,
    password: str,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    token = create_access_token({
        "user_id": user.id,
        "role": user.role
    })
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "role": user.role
    }

@router.get("/me")
def my_profile(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "profile_pic": user.profile_pic,
        "created_at": user.created_at
    }

@router.put("/me")
def update_profile(
    username: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if email:
        validate_lowercase_email(email)
        existing = db.query(User).filter(User.email == email.lower()).first()
        if existing and existing.id != user.id:
            raise HTTPException(400, detail="Email already in use")
        user.email = email.lower()
    
    if username:
        user.username = username
    
    if password:
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
    user.profile_pic = None
    db.commit()
    return {"message": "Profile picture removed"}

@router.post("/logout")
def logout():
    return {"message": "Logout successful"}
