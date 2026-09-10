#!/usr/bin/env bash
set -euo pipefail

action="${1:-}"
scope="${2:-global}"
reason="${3:-operator action}"

case "${action}" in
  enable) enabled=true ;;
  disable) enabled=false ;;
  *) echo "usage: $0 enable|disable [global|bot:<id>] [reason]" >&2; exit 2 ;;
esac

docker compose exec -T postgres psql -U platform -d platform -v ON_ERROR_STOP=1 \
  --set=scope="${scope}" --set=enabled="${enabled}" --set=reason="${reason}" <<'SQL'
INSERT INTO kill_switches(scope,enabled,reason,updated_at)
VALUES (:'scope', :'enabled'::boolean, :'reason', now())
ON CONFLICT (scope) DO UPDATE
SET enabled=excluded.enabled,reason=excluded.reason,updated_at=excluded.updated_at;
SQL

echo "Kill switch ${scope}: ${action}"
