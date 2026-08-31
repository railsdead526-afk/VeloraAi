from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from app.core.config import settings


def _database_url_with_schema() -> str:
    if not settings.database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        return settings.database_url

    url = make_url(settings.database_url)
    query = dict(url.query)
    query["options"] = f"-csearch_path={settings.database_schema},public"
    return url.set(query=query).render_as_string(hide_password=False)


connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

database_url = _database_url_with_schema()

engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)

_IS_PG = settings.database_url.startswith(("postgresql://", "postgresql+psycopg2://"))

def _apply_search_path(dbapi_connection, connection_record, *args):
    # Ensure search_path is set for each connection (covers both new connections
    # and pooled connections that may have lost the setting). Accepts extra args
    # because the `checkout` pool event passes a third `connectable` argument.
    cursor = dbapi_connection.cursor()
    cursor.execute(f'SET search_path TO "{settings.database_schema}", public')
    cursor.close()

if _IS_PG:
    # Set search_path on new connections
    event.listen(engine, "connect", _apply_search_path)
    # Also set on each checkout from the pool to handle pooled providers that
    # may reset session state.
    event.listen(engine, "checkout", _apply_search_path)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
