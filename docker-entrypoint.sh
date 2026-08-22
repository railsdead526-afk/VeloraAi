#!/bin/sh
# Apply migrations before serving. A failed migration must abort the release
# rather than start a process against an out-of-date schema.
set -eu

echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

exec "$@"
