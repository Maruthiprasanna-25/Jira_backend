from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database.base import Base

class ModeSwitchRequest(Base):
    __tablename__ = "mode_switch_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    requested_mode = Column(String(20), nullable=False)  # ADMIN or DEVELOPER
    reason = Column(Text, nullable=False)
    status = Column(String(20), default="PENDING")  # PENDING, APPROVED, REJECTED
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="mode_switch_requests")
