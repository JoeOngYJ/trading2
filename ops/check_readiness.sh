#!/usr/bin/env bash
set -euo pipefail

docker compose config -q
docker compose ps
curl --fail --silent http://127.0.0.1:9100/healthz
curl --fail --silent http://127.0.0.1:8080/api/v1/ping

docker compose exec -T postgres psql -U platform -d platform -v ON_ERROR_STOP=1 -c \
  "SELECT count(*) AS unpublished_outbox FROM outbox WHERE published_at IS NULL;"
docker compose exec -T postgres psql -U platform -d platform -v ON_ERROR_STOP=1 -c \
  "SELECT service_id,status,now()-observed_at AS age FROM service_heartbeats ORDER BY service_id;"

