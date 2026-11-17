#!/bin/sh
# Private logical database, upload and certificate backup. No secrets are echoed.
set -eu
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
casa_backup_dir=${1:-"backups/$(date -u +%Y%m%dT%H%M%SZ)"}
mkdir "$casa_backup_dir"
deploy/compose.sh exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner --no-acl' > "$casa_backup_dir/database.dump.partial"
mv "$casa_backup_dir/database.dump.partial" "$casa_backup_dir/database.dump"
deploy/compose.sh run --rm --no-deps -T --entrypoint tar backend -C /app/uploads -czf - . > "$casa_backup_dir/uploads.tar.gz.partial"
mv "$casa_backup_dir/uploads.tar.gz.partial" "$casa_backup_dir/uploads.tar.gz"
deploy/compose.sh run --rm --no-deps -T --entrypoint tar web -C /data -czf - . > "$casa_backup_dir/caddy-data.tar.gz.partial"
mv "$casa_backup_dir/caddy-data.tar.gz.partial" "$casa_backup_dir/caddy-data.tar.gz"
printf 'Backup completed in %s. Store it encrypted off the VPS.\n' "$casa_backup_dir"
