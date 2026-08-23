import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Pin the test environment BEFORE app.core.config is imported, because it calls
# load_dotenv() at module scope. Without this, a developer's local .env leaks
# into the suite and tests pass or fail depending on a file that is not in the
# repository -- which is exactly what happened: a local PAYMENT_PROVIDER=disabled
# turned four payment tests red on one machine and green in CI.
#
# setdefault, not assignment: an explicit variable on the command line still wins.
_TEST_ENV = {
    "APP_ENV": "test",
    "APP_DEBUG": "false",
    "DATABASE_URL": "sqlite:///./test.db",
    "DATABASE_SCHEMA": "public",
    "SECRET_KEY": "ci-test-secret-key-012345678901234567890123",
    "AI_PROVIDER": "mock",
    "PAYMENT_PROVIDER": "midtrans",
    "RATE_LIMIT_STORAGE_URI": "memory://",
    "CORS_ORIGINS": "http://localhost:3000",
    "EMBEDDING_MODEL": "text-embedding-3-small",
    "EMBEDDING_DIMENSIONS": "1536",
    "REQUIRE_EMAIL_VERIFICATION": "false",
    "SMTP_HOST": "",
    "METRICS_TOKEN": "",
}
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.rate_limit import limiter
from app.main import app
from app.models.user import User

TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def reset_test_state():
    """Keep API tests isolated from database and rate-limit state."""
    limiter.reset()
    settings.midtrans_server_key = "ci-test-midtrans-server-key"
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    limiter.reset()


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user(db):
    """Provide a real FK parent for tests that exercise user-scoped records."""
    value = User(
        email="fixture-user@example.com",
        hashed_password="test",
        role="free",
    )
    db.add(value)
    db.commit()
    db.refresh(value)
    return value


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)
