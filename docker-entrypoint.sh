#!/bin/sh
# Apply migrations before serving. A failed migration must abort the release
# rather than start a process against an out-of-date schema.
#
# Set RUN_MIGRATIONS=false on services that must not migrate — notably the
# maintenance cron, which would otherwise race the web service during a deploy.
set -eu

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "Running database migrations..."
    alembic upgrade head
    echo "Migrations complete."
else
    echo "RUN_MIGRATIONS=false; skipping migrations."
fi

exec "$@"
