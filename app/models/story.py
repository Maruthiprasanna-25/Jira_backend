from sqlalchemy import Column, Integer, String, Text, ForeignKey, TIMESTAMP, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.base import Base

class UserStory(Base):
    __tablename__ = "user_story"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id = Column(
        Integer,
        ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    project_name = Column(String(100), nullable=False)
    story_pointer = Column(String(20), unique=True, nullable=False)

    release_number = Column(String(50), nullable=True)
    sprint_number = Column(String(50), nullable=True)

    assignee_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
        index=True
    )

    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)

    assignee = Column(String(100), nullable=False)
    reviewer = Column(String(100), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    issue_type = Column(String(50), nullable=True)
    priority = Column(String(50), nullable=True, default="Medium")
    status = Column(String(50), nullable=True)

    support_doc = Column(String(255), nullable=True)

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    project = relationship("Project", back_populates="stories")
    assignee_user = relationship("User", foreign_keys=[assignee_id])
    team = relationship("Team", back_populates="stories")

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)

    issue_id = Column(Integer, ForeignKey("user_story.id", ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    action_type = Column(String(50), nullable=False)
    field_changed = Column(String(100))
    old_value = Column(Text)
    new_value = Column(Text)

    created_at = Column(TIMESTAMP, server_default=func.now())
