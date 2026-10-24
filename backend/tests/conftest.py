"""Test fixtures.

These run against a real MariaDB database (pam_rate_board_test by default),
not SQLite. The behaviour under test depends on SQL semantics that differ
between engines - DECIMAL handling, row locking, guarded UPDATE rowcounts and
unique-constraint races - so testing on SQLite would prove the wrong thing.

Set TEST_DATABASE_URL to point somewhere else. The schema is created from the
Alembic migration so the migration itself is exercised on every run.
"""

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Must be set before app.core.config is first imported.
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "mysql+pymysql://root:@127.0.0.1:3306/pam_rate_board_test?charset=utf8mb4",
)
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["SECRET_KEY"] = "test-secret-key-not-used-anywhere-else"
os.environ["ENVIRONMENT"] = "test"
os.environ["BCRYPT_ROUNDS"] = "4"  # keep the suite fast; production uses 12
os.environ.setdefault("STORAGE_DIR", str(BACKEND_DIR.parent / "storage" / "test"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, Branch, User, UserBranch, UserRole  # noqa: E402

def _existing_tables(conn):
    """Every table actually present, so teardown cannot miss one.

    A hardcoded list silently rots when a model is added; enumerating keeps
    the suite honest.
    """
    rows = conn.execute(
        text(
            "SELECT TABLE_NAME FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'"
        )
    )
    return [row[0] for row in rows]


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Build the schema once for the whole session."""
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in _existing_tables(conn):
            conn.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))

    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Each test starts from an empty database."""
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in _existing_tables(conn):
            if table == "alembic_version":
                continue
            conn.execute(text(f"DELETE FROM `{table}`"))
            conn.execute(text(f"ALTER TABLE `{table}` AUTO_INCREMENT = 1"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Clear the login and pairing limiters between tests.

    They are per-process and keyed by client IP. Every test here shares the
    single TestClient IP, so without this one test's attempts would exhaust
    the budget for the next. The limiters themselves are exercised directly
    in test_rate_limiting.
    """
    from app.api.routes import auth as auth_routes
    from app.api.routes import device_api

    for limiter in (auth_routes._login_limiter, device_api._pairing_limiter):
        with limiter._lock:
            limiter._hits.clear()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def branches(db):
    kuta = Branch(name="Kuta", timezone="Asia/Makassar", is_active=True)
    ubud = Branch(name="Ubud", timezone="Asia/Makassar", is_active=True)
    db.add_all([kuta, ubud])
    db.commit()
    return {"kuta": kuta.id, "ubud": ubud.id}


@pytest.fixture
def admin_user(db):
    user = User(
        username="admin",
        full_name="Administrator",
        password_hash=hash_password("AdminPass123"),
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def staff_user(db, branches):
    user = User(
        username="staff",
        full_name="Staff Ubud",
        password_hash=hash_password("StaffPass123"),
        role=UserRole.STAFF.value,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(UserBranch(user_id=user.id, branch_id=branches["ubud"]))
    db.commit()
    return user


def _login(client, username, password):
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
def admin_token(client, admin_user):
    return _login(client, "admin", "AdminPass123")


@pytest.fixture
def staff_token(client, staff_user):
    return _login(client, "staff", "StaffPass123")


@pytest.fixture
def auth(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def staff_auth(staff_token):
    return {"Authorization": f"Bearer {staff_token}"}
