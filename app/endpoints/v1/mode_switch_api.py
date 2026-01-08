from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.database.session import get_db
from app.models import User, ModeSwitchRequest, Notification
from app.auth.dependencies import get_current_user
from app.schemas.user_schema import UserResponse, ModeSwitchRequestSchema

router = APIRouter(prefix="/mode-switch", tags=["Mode Switch"])

@router.post("/request")
def create_switch_request(
    request_data: ModeSwitchRequestSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submits a request to switch view mode (Admin <-> Developer).
    Notifies Master Admin.
    """
    requested_mode = request_data.requested_mode
    reason = request_data.reason
    if user.is_master_admin:
        raise HTTPException(400, "Master Admin does not need to request mode switches")
    
    if requested_mode not in ["ADMIN", "DEVELOPER"]:
        raise HTTPException(400, "Invalid mode requested")
    
    # Check if there's already a pending request
    existing = db.query(ModeSwitchRequest).filter(
        ModeSwitchRequest.user_id == user.id,
        ModeSwitchRequest.status == "PENDING"
    ).first()
    
    if existing:
        raise HTTPException(400, "You already have a pending switch request")

    request = ModeSwitchRequest(
        user_id=user.id,
        requested_mode=requested_mode,
        reason=reason,
        status="PENDING"
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    # Notify Master Admin
    master_admin = db.query(User).filter(User.email == "admin@jira.local").first()
    if master_admin:
        notification = Notification(
            user_id=master_admin.id,
            title="New Mode Switch Request",
            message=f"User {user.username} has requested to switch to {requested_mode} mode."
        )
        db.add(notification)
        db.commit()

    return {"message": "Request submitted successfully", "request_id": request.id}

@router.get("/requests")
def get_all_requests(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Retrieves all pending mode switch requests.
    Only accessible by Master Admin.
    """
    if not user.is_master_admin:
        raise HTTPException(403, "Only Master Admin can view requests")
    
    requests = db.query(ModeSwitchRequest).filter(ModeSwitchRequest.status == "PENDING").all()
    
    # Enrich with user info manually or use a schema
    result = []
    for r in requests:
        result.append({
            "id": r.id,
            "user_id": r.user_id,
            "username": r.user.username,
            "email": r.user.email,
            "role": r.user.role,
            "requested_mode": r.requested_mode,
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at
        })
    return result

@router.post("/approve/{request_id}")
def approve_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Approves a mode switch request and updates user role/view mode.
    Only accessible by Master Admin.
    """
    if not user.is_master_admin:
        raise HTTPException(403, "Only Master Admin can approve requests")
    
    request = db.query(ModeSwitchRequest).filter(ModeSwitchRequest.id == request_id).first()
    if not request:
        raise HTTPException(404, "Request not found")
    
    if request.status != "PENDING":
        raise HTTPException(400, f"Request is already {request.status}")

    # Update User Mode and Role
    target_user = request.user
    target_user.role = request.requested_mode
    target_user.view_mode = request.requested_mode
    request.status = "APPROVED"
    
    # Create Notification
    notification = Notification(
        user_id=target_user.id,
        title="Mode Switch Approved",
        message=f"Your request to switch to {request.requested_mode} mode has been approved by the Master Admin."
    )
    db.add(notification)
    
    db.commit()
    return {"message": "Request approved and user mode updated"}

@router.post("/reject/{request_id}")
def reject_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Rejects a mode switch request.
    Only accessible by Master Admin.
    """
    if not user.is_master_admin:
        raise HTTPException(403, "Only Master Admin can reject requests")
    
    request = db.query(ModeSwitchRequest).filter(ModeSwitchRequest.id == request_id).first()
    if not request:
        raise HTTPException(404, "Request not found")
    
    if request.status != "PENDING":
        raise HTTPException(400, f"Request is already {request.status}")

    request.status = "REJECTED"
    
    # Create Notification
    notification = Notification(
        user_id=request.user_id,
        title="Mode Switch Rejected",
        message=f"Your request to switch to {request.requested_mode} mode was rejected."
    )
    db.add(notification)
    
    db.commit()
    return {"message": "Request rejected"}
