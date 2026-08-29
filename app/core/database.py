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

if _IS_PG:
    def _set_search_path(dbapi_connection, connection_record):
        # Pooled providers (e.g. Supabase Supavisor) may strip the `options`
        # startup parameter, so the search path must be set per connection.
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{settings.database_schema}", public')
        cursor.close()

    event.listen(engine, "connect", _set_search_path)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
