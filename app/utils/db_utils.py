import logging
import os
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models import User
from app.auth.auth_utils import hash_password
from app.config.settings import settings

logger = logging.getLogger(__name__)

def create_default_admin():
    """
    Checks for existing ADMIN user and creates a default one if missing.
    Uses credentials from settings.
    """
    db: Session = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == "ADMIN").first()
        if not admin:
            logger.info("⚙️ Creating default ADMIN account...")
            admin_user = User(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                hashed_password=hash_password(settings.ADMIN_PASSWORD[:72]),
                role="ADMIN"
            )
            db.add(admin_user)
            db.commit()
            logger.info("✅ Default ADMIN user created")
        else:
            logger.info("ℹ️ ADMIN user already exists")
    finally:
        db.close()
