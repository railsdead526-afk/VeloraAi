# VeloraAi Production Database

VeloraAi uses PostgreSQL on Supabase as its managed production database.

The existing Supabase project contains legacy public tables that are not part of the current Alembic model. They must not be dropped or renamed during the migration.

## Schema isolation

Production VeloraAi uses the dedicated PostgreSQL schema:

```text
veloraai
```

The application and Alembic migration runner must use:

```text
search_path=veloraai,public
```

This keeps the legacy `public` tables isolated while allowing PostgreSQL extensions and shared objects in `public` to remain accessible.

## Source of truth

Alembic migrations in `alembic/versions/` are the source of truth for the VeloraAi application schema. Do not use `Base.metadata.create_all()` in production and do not manage the same tables with a second migration system.

## Provisioning order

1. Create the `veloraai` schema in Supabase.
2. Configure Railway `DATABASE_URL` for the VeloraAi service.
3. Configure the same schema/search path for the application connection and Alembic.
4. Run `alembic upgrade head`.
5. Verify `/api/v1/ready` and database connectivity.
6. Only then enable production AI/payment configuration.
