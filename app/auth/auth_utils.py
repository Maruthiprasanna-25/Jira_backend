import logging
# Fix for passlib/bcrypt incompatibility
logging.getLogger('passlib').setLevel(logging.ERROR)
from datetime import datetime, timedelta
from jose import jwt
from passlib.context import CryptContext
import re
from fastapi import HTTPException

from app.config.settings import settings

pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")


def validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long"
        )

    if not re.search(r"[A-Z]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one uppercase letter (A-Z)"
        )

    if not re.search(r"[a-z]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one lowercase letter (a-z)"
        )

    if not re.search(r"[0-9]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one number (0-9)"
        )

    if not re.search(r"[!@#$%^&*]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one special character (!@#$%^&*)"
        )

def validate_lowercase_email(email: str):
    if email != email.lower():
        raise HTTPException(400, "Email must be in lowercase")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)



def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)



def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
