from sqlalchemy import Column, Integer, ForeignKey, Table
from app.database.base import Base

# Association Table for Team Members
team_members = Table(
    "team_members",
    Base.metadata,
    Column("team_id", Integer, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
)
