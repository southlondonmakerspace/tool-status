#!/bin/sh
set -e

# Apply any pending migrations before starting the server.
python manage.py migrate --noinput

exec "$@"
