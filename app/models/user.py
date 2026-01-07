from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.database.base import Base
from app.models.common import team_members

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    profile_pic = Column(String(255), nullable=True)
    role = Column(String(20), default="DEVELOPER")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user")
    
    # Relationships for Teams
    teams = relationship("Team", secondary=team_members, back_populates="members")
    led_teams = relationship("Team", back_populates="lead")

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    hashed_token = Column(String(255), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="reset_tokens")

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)

    is_read = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="notifications")
