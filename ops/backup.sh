#!/usr/bin/env bash
set -euo pipefail

backup_root="${PLATFORM_BACKUP_DIR:-/data/Trading/backups}"
repository="${RESTIC_REPOSITORY:?RESTIC_REPOSITORY must point to off-host storage}"
: "${RESTIC_PASSWORD:?RESTIC_PASSWORD must be set}"

mkdir -p "${backup_root}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump_path="${backup_root}/platform-${stamp}.dump"

docker compose exec -T postgres pg_dump -U platform -d platform --format=custom --file=/tmp/platform.dump
docker compose cp postgres:/tmp/platform.dump "${dump_path}"
restic backup "${dump_path}" compose.yaml config migrations user_data/config.json
restic forget --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --prune

echo "Off-host backup completed: ${stamp}"

