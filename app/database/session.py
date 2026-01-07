import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use env variable if available, else fallback to hardcoded
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:Mysql%4012345@localhost/user_story_db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
