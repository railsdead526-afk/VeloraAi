from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def _database_url_with_schema() -> str:
    if not settings.database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
        return settings.database_url

    url = make_url(settings.database_url)
    query = dict(url.query)
    # `extensions` is appended for Supabase, which installs pgvector there
    # rather than in `public`. Postgres silently ignores schemas in a
    # search_path that do not exist, so this is inert everywhere else.
    query["options"] = f"-csearch_path={settings.database_schema},public,extensions"
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

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
