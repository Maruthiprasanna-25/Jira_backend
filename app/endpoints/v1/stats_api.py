from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import List

from app.database.session import get_db
from app.models import User, Project, ModeSwitchRequest
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/stats", tags=["Statistics"])

@router.get("/master-admin/summary")
def get_master_admin_summary(
    month: int = None,
    year: int = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not user.is_master_admin:
        raise HTTPException(status_code=403, detail="Only Master Admin can access dashboard statistics")

    # 1. Total Projects
    total_projects = db.query(Project).count()

    # 2. Breakdown by Admin
    admin_breakdown = db.query(
        User.username,
        User.email,
        func.count(Project.id).label("project_count")
    ).join(Project, User.id == Project.owner_id)\
     .group_by(User.id).all()

    admins = [
        {"username": row[0], "email": row[1], "count": row[2]}
        for row in admin_breakdown
    ]

    # 3. Weekly Statistics
    now = datetime.now()
    target_month = month if month is not None else now.month
    target_year = year if year is not None else now.year
    
    # Calculate start of the month
    start_of_month = datetime(target_year, target_month, 1)
    # Calculate end of the month (approximate or precise)
    if target_month == 12:
        end_of_month = datetime(target_year + 1, 1, 1)
    else:
        end_of_month = datetime(target_year, target_month + 1, 1)

    weekly_stats = []
    # Divide month into 4 weeks
    current_start = start_of_month
    for i in range(4):
        # Last week takes the remainder of the month
        if i == 3:
            next_start = end_of_month
        else:
            next_start = current_start + timedelta(days=7)
            
        count = db.query(Project).filter(
            Project.created_at >= current_start,
            Project.created_at < next_start
        ).count()
        
        weekly_stats.append({
            "week": f"Week {i+1}",
            "projects": count,
            "range": f"{current_start.strftime('%b %d')} - {next_start.strftime('%b %d')}"
        })
        current_start = next_start

    return {
        "total_projects": total_projects,
        "admin_breakdown": admins,
        "weekly_stats": weekly_stats,
        "selected_month": target_month,
        "selected_year": target_year
    }

@router.get("/master-admin/mode-switch-history")
def get_mode_switch_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if not user.is_master_admin:
        raise HTTPException(status_code=403, detail="Only Master Admin can access history")

    requests = db.query(ModeSwitchRequest).order_by(ModeSwitchRequest.created_at.desc()).all()
    
    result = []
    for r in requests:
        result.append({
            "id": r.id,
            "username": r.user.username,
            "email": r.user.email,
            "requested_mode": r.requested_mode,
            "status": r.status,
            "created_at": r.created_at,
            "reason": r.reason
        })
    return result
