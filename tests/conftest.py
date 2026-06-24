"""Shared test harness: a real Postgres-backed schema, an ASGI client, and a
factory for creating authenticated users per role.

Design notes
------------
* The schema is built ONCE per session by running the real Alembic migration
  chain (``alembic upgrade head``) against a *test* database — not
  ``Base.metadata.create_all`` (which emits some indexes twice and can't build
  the FTS columns added in migrations). This also means tests exercise the same
  schema production runs.
* Tests share the one schema and commit real data (no per-test rollback). The
  suite is small and self-contained — fixtures use random emails / department
  names, and assertions check specific ids rather than exact row counts — so it
  is order-independent. CI runs against a fresh disposable DB each time.
* ``DATABASE_URL`` must point at a disposable database (defaults to a local
  ``arkon_test``; CI overrides it). It is set before importing ``app`` so the
  module-level engine binds to the test DB.
* Auth is exercised end-to-end: users are real ``Employee`` rows and tokens are
  minted with the production ``create_access_token``.

Run (with deps installed + a reachable Postgres)::

    pytest tests/test_chess_api.py -q
"""

import os
import subprocess
import uuid

# Must run before any `app.*` import so settings/engine bind to the test DB.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://arkon:arkon_secret@localhost:5432/arkon_test",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("MCP_TOKEN_PEPPER", "test-pepper")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import async_session_factory, engine
from app.database.models import Department, Employee, EmployeeDepartment
from app.main import app
from app.services.auth_service import audience_for, create_access_token, hash_password


@pytest.fixture(scope="session")
def _schema():
    """Build the schema once via the real migration chain."""
    # Same command the CI `migrations` job runs; alembic reads DATABASE_URL.
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    yield


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine():
    """pytest-asyncio runs each test in its own event loop. The module-level
    async engine pools connections bound to whichever loop created them, so
    reusing the pool in a later test raises "attached to a different loop".
    Dispose after each test (on that test's loop) so the next test gets fresh
    connections."""
    yield
    await engine.dispose()


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
