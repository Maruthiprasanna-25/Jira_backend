import logging
from datetime import datetime, timedelta
import re

from fastapi import HTTPException
from jose import jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError

from app.config.settings import settings

# Reduce passlib noise
logging.getLogger("passlib").setLevel(logging.ERROR)

# ✅ Support BOTH hash formats safely
pwd_context = CryptContext(
    schemes=["bcrypt", "bcrypt_sha256"],
    deprecated="auto"
)

# ---------------- PASSWORD VALIDATION ---------------- #

def validate_password(password: str):
    """
    Validates password strength requirements.
    
    Args:
        password: The password string to validate
        
    Raises:
        HTTPException: If password doesn't meet requirements
    """
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
    """
    Validates that the email is in lowercase.
    
    Args:
        email: The email string to check
        
    Raises:
        HTTPException: If email contains uppercase characters
    """
    if email != email.lower():
        raise HTTPException(
            status_code=400,
            detail="Email must be in lowercase"
        )

# ---------------- PASSWORD HASHING ---------------- #

def hash_password(password: str) -> str:
    """
    Hashes a password using the configured context.
    
    Args:
        password: The plain text password
        
    Returns:
        str: The hashed password
    """
    return pwd_context.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifies a plain password against a hash.
    
    Args:
        password: The plain text password
        hashed_password: The stored hash
        
    Returns:
        bool: True if password matches, False otherwise
        
    Raises:
        HTTPException: If hash in database is invalid/unknown
    """
    try:
        return pwd_context.verify(password, hashed_password)
    except UnknownHashError:
        # Database contains invalid hash
        raise HTTPException(
            status_code=500,
            detail="Invalid password hash stored in database"
        )

# ---------------- JWT TOKEN ---------------- #

def create_access_token(data: dict):
    """
    Creates a JWT access token with expiration.
    
    Args:
        data: Payload data to include in the token
        
    Returns:
        str: Encoded JWT token
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
