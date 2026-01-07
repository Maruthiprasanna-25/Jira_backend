from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.endpoints.router import api_router
from app.database.session import engine
from app.database.base import Base
from app.config.settings import settings
from app.utils.db_utils import create_default_admin

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Uploads directory
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Include API Router
app.include_router(api_router)

@app.on_event("startup")
def startup_event():
    create_default_admin()

@app.get("/")
def root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"}