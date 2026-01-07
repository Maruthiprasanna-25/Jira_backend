import os
from sqlalchemy.orm import Session
from app.database.session import SessionLocal
from app.models import User
from app.auth.auth_utils import hash_password
from app.config.settings import settings

def create_default_admin():
    db: Session = SessionLocal()
    try:
        admin = db.query(User).filter(User.role == "ADMIN").first()
        if not admin:
            print("⚙️ Creating default ADMIN account...")
            admin_user = User(
                username=settings.ADMIN_USERNAME,
                email=settings.ADMIN_EMAIL,
                hashed_password=hash_password(settings.ADMIN_PASSWORD[:72]),
                role="ADMIN"
            )
            db.add(admin_user)
            db.commit()
            print("✅ Default ADMIN user created")
        else:
            print("ℹ️ ADMIN user already exists")
    finally:
        db.close()
