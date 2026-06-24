"""
Auth router — login, logout, profile, change password.

Two system roles:
  - admin: Full access (bypasses all permission checks)
  - employee: Access governed by custom_role scoped permissions
"""


from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.database.models import Employee
from app.services.auth_service import (
    audience_for,
    authenticate_employee,
    create_access_token,
    get_current_user,
    hash_password,
    register_student,
    verify_email_token,
    verify_password,
)
from app.services.permission_engine import get_effective_permissions
from app.utils.rate_limit import check_rate_limit

router = APIRouter()


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


# Deprecated WorkspaceMembershipOut DTO


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ProfileResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    department_ids: list[str] = []
    department_names: list[str] = []
    is_active: bool
    has_mcp_token: bool
    permissions: list[str] = []
    workspace_memberships: list[dict] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_workspace_memberships(db, employee_id) -> list:
    """Workspace memberships have been deprecated and removed."""
    return []


def _build_user_dict(employee: Employee, permissions: list[str], workspace_memberships: Optional[list] = None) -> dict:
    """Build user dict for login/me responses."""
    return {
        "id": str(employee.id),
        "name": employee.name,
        "email": employee.email,
        "role": employee.role,
        "department_ids": [str(ed.department_id) for ed in employee.employee_departments],
        "department_names": [
            ed.department.name for ed in employee.employee_departments if ed.department
        ],
        "permissions": permissions,
        "workspace_memberships": workspace_memberships or [],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate with email + password. Returns JWT token.
    Works for both admin and employee roles.
    """
    employee = await authenticate_employee(db, req.email, req.password)
    if not employee:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(
        employee_id=str(employee.id),
        role=employee.role,
        name=employee.name,
        audience=audience_for(employee),
    )

    permissions = get_effective_permissions(employee)

    return LoginResponse(
        access_token=token,
        user=_build_user_dict(employee, permissions, []),
    )


# ---------------------------------------------------------------------------
# Public student self-signup (Roadmap A) — gated by enable_student_signup
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


@router.post("/auth/register")
async def register(
    req: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Self-register a student/external account. Disabled unless
    `enable_student_signup` is set. The account is inactive until an admin
    approves it (or email verification completes) unless auto-activate is on.
    """
    if not settings.enable_student_signup:
        raise HTTPException(403, "Self-signup is currently disabled. Contact an administrator.")

    client_ip = request.client.host if request.client else "unknown"
    allowed = await check_rate_limit(
        f"signup:{client_ip}", settings.signup_rate_limit_per_hour, 3600
    )
    if not allowed:
        raise HTTPException(429, "Too many sign-up attempts. Please try again later.")

    try:
        student, raw_token = await register_student(
            db, name=req.name, email=req.email, password=req.password,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    await db.commit()

    # No SMTP configured by default — log the verification link so an operator
    # can retrieve it. When email is wired, send it here instead.
    base = (settings.portal_base_url or "").rstrip("/")
    verify_link = f"{base}/verify-email?token={raw_token}" if base else f"/verify-email?token={raw_token}"
    logger.info(f"[student-signup] {student.email} verification link: {verify_link}")

    if settings.student_signup_auto_activate:
        return {"status": "active", "message": "Account created. You can now sign in."}
    return {
        "status": "pending",
        "message": "Account created. It will be activated after email verification "
                   "or admin approval.",
    }


class VerifyEmailRequest(BaseModel):
    token: str


@router.post("/auth/verify-email", response_model=LoginResponse)
async def verify_email(req: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """Verify a student's email from the token and sign them in."""
    student = await verify_email_token(db, req.token)
    if not student:
        raise HTTPException(400, "Invalid or expired verification link.")
    await db.commit()
    # Reload with departments eager-loaded for the user payload.
    from sqlalchemy.orm import selectinload

    from app.database.models import EmployeeDepartment
    full = (await db.execute(
        select(Employee)
        .where(Employee.id == student.id)
        .options(selectinload(Employee.employee_departments).selectinload(EmployeeDepartment.department))
    )).scalar_one()
    token = create_access_token(
        employee_id=str(full.id), role=full.role, name=full.name,
        audience=audience_for(full),
    )
    permissions = get_effective_permissions(full)
    return LoginResponse(access_token=token, user=_build_user_dict(full, permissions, []))


@router.get("/auth/me", response_model=ProfileResponse)
async def get_profile(
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user profile. Validates the JWT is still valid."""
    permissions = get_effective_permissions(current_user)
    workspace_memberships = await _get_workspace_memberships(db, current_user.id)

    return ProfileResponse(
        id=str(current_user.id),
        name=current_user.name,
        email=current_user.email,
        role=current_user.role,
        department_ids=[str(ed.department_id) for ed in current_user.employee_departments],
        department_names=[
            ed.department.name for ed in current_user.employee_departments if ed.department
        ],
        is_active=current_user.is_active,
        has_mcp_token=bool(current_user.mcp_token_hash),
        permissions=permissions,
        workspace_memberships=workspace_memberships,
    )


@router.post("/auth/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    if not current_user.password_hash:
        raise HTTPException(400, "No password set. Contact admin.")

    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(401, "Current password is incorrect")

    if len(req.new_password) < 6:
        raise HTTPException(400, "New password must be at least 6 characters")

    current_user.password_hash = hash_password(req.new_password)
    await db.flush()
    return {"message": "Password changed successfully"}


@router.get("/auth/status")
async def auth_status():
    """Check if auth is required (public endpoint for frontend)."""
    return {"auth_required": True}
