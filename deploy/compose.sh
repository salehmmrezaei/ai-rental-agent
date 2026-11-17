#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec docker compose --project-name "${CASA_PROJECT_NAME:-casa}" --env-file "${CASA_ENV_FILE:-.env.production}" -f docker-compose.prod.yml "$@"
