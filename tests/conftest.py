import os
import sys

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import app.models  # noqa: F401
from app.main import app
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.rate_limit import limiter
from app.models.user import User
from app.api.v1 import agent_stream, conversations

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


# The canonical /messages/stream route now lives in agent_stream.py. Keep the
# legacy integration tests' monkeypatch target effective while they are
# migrated to patch agent_stream directly. This is test-only compatibility.
def _legacy_stream_patch_bridge(*args, **kwargs):
    return conversations.stream_ai_reply_from_history(*args, **kwargs)


agent_stream.stream_ai_reply_from_history = _legacy_stream_patch_bridge


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
