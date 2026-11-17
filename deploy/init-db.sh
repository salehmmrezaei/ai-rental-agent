#!/bin/sh
# Runs only when the PostgreSQL volume is empty. Values are psql variables,
# never interpolated into SQL syntax by the shell.
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 \
  --set app_user="$APP_DB_USER" --set app_password="$APP_DB_PASSWORD" \
  --set database_name="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"app_user" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'app_password';
ALTER DATABASE :"database_name" OWNER TO :"app_user";
GRANT ALL ON SCHEMA public TO :"app_user";
CREATE EXTENSION IF NOT EXISTS btree_gist;
SQL
