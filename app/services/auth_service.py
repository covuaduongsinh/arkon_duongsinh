"""
Auth Service — JWT-based authentication for Admin Portal and Employee Portal.

Handles:
  - Password hashing (bcrypt)
  - JWT token generation and verification
  - Login / logout (stateless JWT)
  - Role-based access (admin vs employee)
  - Scoped permission checks (v2: resource:action:scope format)
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.database.models import Department, Employee, EmployeeDepartment

# JWT config
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

security = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

# JWT audiences — separate internal staff tokens from external/student tokens
# so a student token can never be used where an internal-only check requires it.
AUD_INTERNAL = "arkon:internal"
AUD_STUDENT = "arkon:student"


def audience_for(employee: Employee) -> str:
    """Pick the token audience for an employee."""
    if getattr(employee, "is_external", False) or getattr(employee, "global_role", "") == "student":
        return AUD_STUDENT
    return AUD_INTERNAL


def create_access_token(employee_id: str, role: str, name: str, audience: str = AUD_INTERNAL) -> str:
    """Create a signed JWT token."""
    payload = {
        "sub": employee_id,
        "role": role,
        "name": name,
        "aud": audience,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None.

    Audience is not enforced here (verify_aud=False) so legacy tokens without an
    `aud` claim keep working; callers that need to restrict by audience read
    `payload["aud"]` themselves (see require_internal).
    """
    try:
        return jwt.decode(
            token, settings.secret_key, algorithms=[JWT_ALGORITHM],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# Email-verification token hashing (HMAC, like MCP tokens)
# ---------------------------------------------------------------------------

def hash_verification_token(token: str) -> str:
    """HMAC-SHA256 the email-verification token for at-rest storage."""
    import hashlib
    import hmac
    return hmac.new(
        settings.secret_key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


# ---------------------------------------------------------------------------
# Login / authenticate
# ---------------------------------------------------------------------------

async def authenticate_employee(
    db: AsyncSession, email: str, password: str
) -> Optional[Employee]:
    """
    Verify email + password. Returns Employee or None.
    """
    stmt = (
        select(Employee)
        .where(Employee.email == email, Employee.is_active.is_(True))
        .options(
            selectinload(Employee.employee_departments).selectinload(
                EmployeeDepartment.department
            ),
        )
    )
    result = await db.execute(stmt)
    employee = result.scalar_one_or_none()

    if not employee or not employee.password_hash:
        return None
    if not verify_password(password, employee.password_hash):
        return None
    return employee


# ---------------------------------------------------------------------------
# Student / external self-signup (Roadmap A)
# ---------------------------------------------------------------------------

async def _get_or_create_student_department(db: AsyncSession) -> Department:
    name = settings.student_department_name
    dept = (await db.execute(
        select(Department).where(Department.name == name)
    )).scalar_one_or_none()
    if dept is None:
        dept = Department(name=name, description="Self-registered students / external users")
        db.add(dept)
        await db.flush()
    return dept


async def register_student(
    db: AsyncSession, *, name: str, email: str, password: str,
) -> tuple[Employee, Optional[str]]:
    """Create a self-signup student account.

    Returns (employee, raw_verification_token). The account is inactive unless
    `student_signup_auto_activate` is set; an admin (or email verification)
    activates it. Raises ValueError on duplicate email / weak input.
    """
    import secrets

    email = email.strip().lower()
    name = name.strip()
    if not name or "@" not in email:
        raise ValueError("A valid name and email are required")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    existing = (await db.execute(
        select(Employee).where(Employee.email == email)
    )).scalar_one_or_none()
    if existing is not None:
        raise ValueError("An account with this email already exists")

    dept = await _get_or_create_student_department(db)

    raw_token = secrets.token_urlsafe(32)
    student = Employee(
        name=name,
        email=email,
        password_hash=hash_password(password),
        role="employee",
        global_role="student",
        is_external=True,
        email_verified=False,
        is_active=bool(settings.student_signup_auto_activate),
        verification_token_hash=hash_verification_token(raw_token),
        verification_sent_at=datetime.now(timezone.utc),
    )
    db.add(student)
    await db.flush()
    db.add(EmployeeDepartment(employee_id=student.id, department_id=dept.id))
    await db.flush()
    return student, raw_token


async def verify_email_token(db: AsyncSession, raw_token: str) -> Optional[Employee]:
    """Mark a student's email verified (and activate them) from a token. None if invalid."""
    token_hash = hash_verification_token(raw_token)
    student = (await db.execute(
        select(Employee).where(Employee.verification_token_hash == token_hash)
    )).scalar_one_or_none()
    if student is None:
        return None
    student.email_verified = True
    student.is_active = True
    student.verification_token_hash = None
    await db.flush()
    return student


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Employee:
    """
    FastAPI dependency — extracts and validates JWT from Authorization header.
    Returns the authenticated Employee.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    result = await db.execute(
        select(Employee)
        .options(
            selectinload(Employee.employee_departments).selectinload(
                EmployeeDepartment.department
            ),
        )
        .where(Employee.id == uuid.UUID(payload["sub"]))
    )
    employee = result.scalar_one_or_none()
    if not employee or not employee.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or deactivated",
        )

    # Ensure default global_role is populated
    if not getattr(employee, "global_role", None):
        employee.global_role = "viewer"

    return employee


async def require_admin(
    current_user: Employee = Depends(get_current_user),
) -> Employee:
    """
    FastAPI dependency — requires admin role.
    Use on admin-only endpoints.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def require_permission(permission: str):
    """
    FastAPI dependency factory — checks a specific permission on the employee's custom role.
    Admins bypass all permission checks.
    
    Supports both new scoped format (doc:read:own_dept) and org permissions (org:settings:read).
    
    For scoped resource permissions (doc/wiki), this only checks that the user
    has SOME variant (own_dept or all). Actual scope filtering (which documents
    they can see) is handled by the permission engine at query time.

    Usage: Depends(require_permission("doc:read"))  — checks for doc:read:own_dept OR doc:read:all
           Depends(require_permission("org:settings:read"))  — exact match
    """
    async def _check(current_user: Employee = Depends(get_current_user)) -> Employee:
        if current_user.role == "admin":
            return current_user

        from app.services.permission_engine import (
            _get_user_permissions,
            has_any_permission,
        )
        effective = _get_user_permissions(current_user)

        # Check exact match first (for org: permissions)
        if permission in effective:
            return current_user

        # Check as resource:action (matches either :own_dept or :all)
        parts = permission.split(":")
        if len(parts) == 2:
            resource, action = parts
            if has_any_permission(list(effective), resource, action):
                return current_user
        elif len(parts) == 3:
            # Exact scoped permission check
            if permission in effective:
                return current_user
            # Also check if user has the :all version when :own_dept is required
            resource, action, scope = parts
            if scope == "own_dept" and f"{resource}:{action}:all" in effective:
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission required: {permission}",
        )
    return Depends(_check)
