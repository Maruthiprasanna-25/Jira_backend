import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """
    Application configuration settings.
    Loads from environment variables with defaults.
    """
    PROJECT_NAME: str = "Jira-like Backend API"
    PROJECT_VERSION: str = "1.0.0"
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "mysql+pymysql://root:Mysql%4012345@localhost/user_story_db")
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    UPLOAD_DIR: str = "uploads"
    
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@jira.local")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "Admin@123")
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    
    ALLOWED_ORIGINS: list = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

settings = Settings()
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
