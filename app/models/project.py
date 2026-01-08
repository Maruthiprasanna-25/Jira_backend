from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.base import Base
from app.models.common import team_members

class Project(Base):
    __tablename__ = "project"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    project_prefix = Column(String(5), nullable=False)
    current_story_number = Column(Integer, default=1)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Temporarily nullable for migration

    stories = relationship(
        "UserStory",
        back_populates="project",
        cascade="all, delete-orphan"
    )

    owner = relationship("User")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    teams = relationship("Team", back_populates="project", cascade="all, delete-orphan")

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    project_id = Column(Integer, ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    lead_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="teams")
    lead = relationship("User", back_populates="led_teams")
    members = relationship("User", secondary=team_members, back_populates="teams")
    stories = relationship("UserStory", back_populates="team")
