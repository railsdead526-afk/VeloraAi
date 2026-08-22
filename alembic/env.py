from logging.config import fileConfig
import os
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url
from alembic import context

from app.core.database import Base
from app.models import user, conversation, message, ai_usage, embedding_usage

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
database_schema = os.getenv("DATABASE_SCHEMA", "public")

if database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
    url = make_url(database_url)
    query = dict(url.query)
    query["options"] = f"-csearch_path={database_schema},public"
    database_url = url.set(query=query).render_as_string(hide_password=False)

config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=database_schema if database_schema != "public" else None,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=database_schema if database_schema != "public" else None,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
