#!/bin/sh

set -eu

DATABASE_URL="$(python -m config.compose_database_url)"
export DATABASE_URL

exec "$@"
