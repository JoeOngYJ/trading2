from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status

from .contracts import ExecutionEvent
from .db import connect, migrate
from .repository import record_execution_event
from .settings import Settings


logger = logging.getLogger("audit-api")
app = FastAPI(title="Trading execution audit ingress", docs_url=None, redoc_url=None)


def get_settings() -> Settings:
    return Settings()


def authorize(
    x_audit_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not ((x_audit_token or token) == settings.audit_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid audit token")


@app.on_event("startup")
def startup() -> None:
    settings = Settings()
    migrate(settings.database_url)


@app.get("/healthz")
def healthz(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    with connect(settings.database_url) as connection:
        connection.execute("SELECT 1")
    return {"status": "healthy"}


@app.post("/v1/execution-events", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(authorize)])
async def execution_event(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, str]:
    raw: dict[str, Any] = await request.json()
    raw.setdefault("occurred_at", datetime.now(timezone.utc).isoformat())
    raw.setdefault("bot_id", settings.bot_id)
    raw.setdefault("exchange", settings.exchange)
    raw.setdefault("payload", raw.copy())
    for key in ("signal_id", "run_id"):
        if raw.get(key) in ("", "None", None):
            raw[key] = None
    event = ExecutionEvent.model_validate(raw)
    with connect(settings.database_url) as connection:
        record_execution_event(connection, event, "webhook")
    return {"event_id": str(event.event_id), "status": "accepted"}


def main() -> None:
    uvicorn.run("trading_platform.audit_api:app", host="0.0.0.0", port=8090, access_log=False)


if __name__ == "__main__":
    main()
