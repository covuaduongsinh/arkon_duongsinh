"""Shared test harness: a real Postgres-backed schema, an ASGI client, and a
factory for creating authenticated users per role.

Design notes
------------
* The schema is built with ``Base.metadata.create_all`` against a *test* database
  (fresh per test, dropped afterwards) so tests are isolated without depending on
  the Alembic migration chain. Migrations are validated separately in CI
  (``alembic upgrade head`` on an empty DB).
* ``DATABASE_URL`` must point at a disposable database. It defaults to a local
  ``arkon_test`` DB; CI overrides it via the environment. We set it *before*
  importing anything under ``app`` so ``app.config.settings`` and the module-level
  engine bind to the test DB.
* Auth is exercised end-to-end: users are real ``Employee`` rows and tokens are
  minted with the production ``create_access_token`` — no dependency overrides.

Run (inside the api container or any env with deps + a reachable Postgres)::

    pytest tests/test_chess_api.py -q
"""

import os
import uuid

# Must run before any `app.*` import so settings/engine bind to the test DB.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://arkon:arkon_secret@localhost:5432/arkon_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("MCP_TOKEN_PEPPER", "test-pepper")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.database import async_session_factory, engine
from app.database.models import (
    Base,
    Department,
    Employee,
    EmployeeDepartment,
)
from app.main import app
from app.services.auth_service import audience_for, create_access_token, hash_password


@pytest_asyncio.fixture
async def _schema():
    """Create a fresh schema for each test and drop it afterwards."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db(_schema):
    """A session for arranging test fixtures (seed users, departments, …)."""
    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(_schema):
    """ASGI client. Lifespan is intentionally NOT run (no MinIO/seed side effects)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def make_user(db):
    """Factory: create an Employee and return (employee, auth_headers).

    Usage::

        emp, headers = await make_user(role="admin")
        emp, headers = await make_user(global_role="student", departments=[dept])
    """

    async def _factory(
        *,
        role: str = "employee",
        global_role: str = "viewer",
        departments=(),
    ):
        emp = Employee(
            name=f"user-{uuid.uuid4().hex[:8]}",
            email=f"{uuid.uuid4().hex}@test.local",
            role=role,
            global_role=global_role,
            is_active=True,
            password_hash=hash_password("password123"),
        )
        db.add(emp)
        await db.flush()
        for dept in departments:
            db.add(EmployeeDepartment(employee_id=emp.id, department_id=dept.id))
        await db.commit()
        token = create_access_token(
            str(emp.id), emp.role, emp.name, audience=audience_for(emp)
        )
        return emp, {"Authorization": f"Bearer {token}"}

    return _factory


@pytest_asyncio.fixture
async def make_department(db):
    """Factory: create a Department row."""

    async def _factory(name: str | None = None) -> Department:
        dept = Department(name=name or f"dept-{uuid.uuid4().hex[:8]}")
        db.add(dept)
        await db.commit()
        await db.refresh(dept)
        return dept

    return _factory
