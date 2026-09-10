from __future__ import annotations

import time

import uvicorn
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest

from .db import connect
from .settings import Settings


app = FastAPI(title="Platform operational metrics", docs_url=None, redoc_url=None)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    with connect(Settings().database_url) as connection:
        connection.execute("SELECT 1")
    return {"status": "healthy"}


@app.get("/metrics")
def metrics() -> Response:
    registry = CollectorRegistry()
    outbox_pending = Gauge("platform_outbox_pending", "Unpublished outbox events", registry=registry)
    outbox_age = Gauge("platform_outbox_oldest_seconds", "Age of oldest unpublished event", registry=registry)
    outbox_claims = Gauge(
        "platform_outbox_claims", "Outbox claim leases by state", ["state"], registry=registry
    )
    job_count = Gauge("platform_analysis_jobs", "Analysis jobs by state", ["status"], registry=registry)
    heartbeat_age = Gauge(
        "platform_service_heartbeat_age_seconds", "Age of last service heartbeat", ["service"], registry=registry
    )
    delivery_count = Gauge(
        "platform_delivery_receipts", "Delivery receipts by disposition", ["disposition"], registry=registry
    )
    settings = Settings()
    with connect(settings.database_url) as connection:
        row = connection.execute(
            """
            SELECT count(*) AS count,
                   COALESCE(extract(epoch FROM now() - min(created_at)), 0) AS age
            FROM outbox WHERE published_at IS NULL
            """
        ).fetchone()
        outbox_pending.set(row["count"])
        outbox_age.set(row["age"])
        claim_row = connection.execute(
            """
            SELECT count(*) FILTER (
                       WHERE claim_expires_at > now()
                   ) AS active,
                   count(*) FILTER (
                       WHERE claim_expires_at <= now()
                   ) AS expired
            FROM outbox WHERE published_at IS NULL AND claim_token IS NOT NULL
            """
        ).fetchone()
        outbox_claims.labels("active").set(claim_row["active"])
        outbox_claims.labels("expired").set(claim_row["expired"])
        for row in connection.execute("SELECT status,count(*) AS count FROM analysis_jobs GROUP BY status"):
            job_count.labels(row["status"]).set(row["count"])
        for row in connection.execute(
            "SELECT service_id,extract(epoch FROM now()-observed_at) AS age FROM service_heartbeats"
        ):
            heartbeat_age.labels(row["service_id"]).set(row["age"])
        for row in connection.execute(
            "SELECT disposition,count(*) AS count FROM delivery_receipts GROUP BY disposition"
        ):
            delivery_count.labels(row["disposition"]).set(row["count"])
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


def main() -> None:
    uvicorn.run("trading_platform.monitor:app", host="0.0.0.0", port=9100, access_log=False)


if __name__ == "__main__":
    main()
