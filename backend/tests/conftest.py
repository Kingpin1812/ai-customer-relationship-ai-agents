"""Test fixtures. Everything runs against a real PostgreSQL.

Set TEST_DATABASE_URL to use your own server; otherwise an embedded one is started.
Approvals in tests always go through the real decision endpoint: nothing bypasses the gate.
"""

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_storage_dir = tempfile.mkdtemp(prefix="workflow-test-artifacts-")
_pg_server = None


def _database_url() -> str:
    global _pg_server
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    import pixeltable_pgserver

    data_dir = Path(__file__).resolve().parents[1] / ".pgdata-test"
    _pg_server = pixeltable_pgserver.get_server(str(data_dir), cleanup_mode="stop")
    return _pg_server.get_uri().replace("postgresql://", "postgresql+psycopg://", 1)


os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": _database_url(),
        "AUTH_MODE": "dev",
        "JWT_SECRET": "test-only-secret-with-enough-length-for-hs256",
        "TASK_EXECUTOR": "inline",
        "STORAGE_BACKEND": "local",
        "STORAGE_LOCAL_PATH": _storage_dir,
        "PLANNER_MODE": "rules",
        "ENABLE_FAULT_INJECTION": "true",
        "RETRY_BASE_DELAY_SECONDS": "0.001",
        "RETRY_MAX_DELAY_SECONDS": "0.002",
        "RATE_LIMIT_PER_MINUTE": "100000",
    }
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.seed import seed_demo  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(), "head")
    yield
    engine.dispose()
    shutil.rmtree(_storage_dir, ignore_errors=True)
    if _pg_server is not None:
        _pg_server.cleanup()


@pytest.fixture(autouse=True)
def _clean_db(_schema: None) -> Iterator[None]:
    with engine.begin() as conn:
        tables = conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename <> 'alembic_version' AND tablename NOT LIKE 'checkpoint%'"
            )
        ).scalars()
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"))
    with SessionLocal() as db:
        seed_demo(db)
        db.commit()
    yield


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        yield c


class Api:
    """Thin signed-in client so tests read as user actions."""

    def __init__(self, client: TestClient, email: str):
        self.client = client
        response = client.post("/api/v1/auth/dev-login", json={"email": email})
        assert response.status_code == 200, response.text
        self.token = response.json()["access_token"]

    def _headers(self, headers: dict | None) -> dict:
        return {"Authorization": f"Bearer {self.token}", **(headers or {})}

    def get(self, path: str, **kw):
        return self.client.get(
            f"/api/v1{path}", headers=self._headers(kw.pop("headers", None)), **kw
        )

    def post(self, path: str, **kw):
        return self.client.post(
            f"/api/v1{path}", headers=self._headers(kw.pop("headers", None)), **kw
        )

    def patch(self, path: str, **kw):
        return self.client.patch(
            f"/api/v1{path}", headers=self._headers(kw.pop("headers", None)), **kw
        )


@pytest.fixture
def login(client):
    return lambda email: Api(client, email)


@pytest.fixture
def admin(login):
    return login("admin@demo.test")


@pytest.fixture
def manager(login):
    return login("manager@demo.test")


@pytest.fixture
def operator(login):
    return login("operator@demo.test")


@pytest.fixture
def viewer(login):
    return login("viewer@demo.test")


@pytest.fixture
def other_admin(login):
    return login("admin@other.test")


DEMO_REQUEST = (
    "Prepare an invoice for Acme Ltd for 10 hours of approved consulting at ₹2,500 per hour, "
    "update the CRM note, generate this month's sales summary, and prepare an email."
)


@pytest.fixture
def demo_request() -> str:
    return DEMO_REQUEST


_key_counter = {"n": 0}


@pytest.fixture
def submit():
    def _submit(api: Api, request: str = DEMO_REQUEST, context: dict | None = None, key=None):
        _key_counter["n"] += 1
        body = {"request": request, "idempotency_key": key or f"test-key-{_key_counter['n']}"}
        if context:
            body["context"] = context
        return api.post("/workflows", json=body)

    return _submit
