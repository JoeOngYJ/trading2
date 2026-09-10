from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from trading_platform.outbox import claim_pending, publish_pending


class Result:
    def __init__(self, *, one=None, rows=None):
        self.one = one
        self.rows = rows or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.rows


class ClaimConnection:
    def __init__(self, *, event=None, mark_owned=True):
        self.event = event
        self.mark_owned = mark_owned
        self.calls = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, query, parameters=None):
        compact = " ".join(query.split())
        self.calls.append((compact, parameters))
        if "WITH candidates AS" in compact:
            if self.event is None:
                return Result(rows=[])
            return Result(rows=[{**self.event, "claim_token": parameters[2]}])
        if "SET published_at=now()" in compact:
            return Result(one={"outbox_id": self.event["outbox_id"]} if self.mark_owned else None)
        return Result()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def outbox_settings():
    return SimpleNamespace(
        database_url="postgresql://test", outbox_batch_size=10, outbox_claim_seconds=60,
    )


def event_row():
    return {
        "outbox_id": 7, "event_id": uuid4(), "subject": "signals.v2.test",
        "payload": {"test": True}, "publish_attempts": 0,
    }


def test_claim_uses_skip_locked_and_commits_before_network_io():
    connection = ClaimConnection(event=event_row())
    rows = claim_pending(connection, outbox_settings(), "relay-a")
    query, parameters = connection.calls[0]
    assert "FOR UPDATE SKIP LOCKED" in query
    assert "claim_expires_at IS NULL OR claim_expires_at <= now()" in query
    assert parameters[0] == 10
    assert parameters[1] == "relay-a"
    assert rows[0]["claim_token"] == parameters[2]
    assert connection.commits == 1


@pytest.mark.asyncio
async def test_successful_publish_is_fenced_by_owner_token(monkeypatch):
    connection = ClaimConnection(event=event_row())
    monkeypatch.setattr("trading_platform.outbox.connect", lambda *_: nullcontext(connection))

    class JetStream:
        def __init__(self): self.messages = []
        async def publish(self, *args, **kwargs): self.messages.append((args, kwargs))

    js = JetStream()
    assert await publish_pending(outbox_settings(), js, "relay-a") == 1
    mark_query, mark_parameters = next(
        call for call in connection.calls if "SET published_at=now()" in call[0]
    )
    assert "claim_owner=%s AND claim_token=%s AND claim_expires_at>now()" in mark_query
    assert mark_parameters[1] == "relay-a"
    assert js.messages[0][1]["headers"]["Nats-Msg-Id"] == str(connection.event["event_id"])
    assert connection.commits == 2


@pytest.mark.asyncio
async def test_lost_or_expired_claim_cannot_mark_event_published(monkeypatch):
    connection = ClaimConnection(event=event_row(), mark_owned=False)
    monkeypatch.setattr("trading_platform.outbox.connect", lambda *_: nullcontext(connection))

    class JetStream:
        async def publish(self, *args, **kwargs): return None

    assert await publish_pending(outbox_settings(), JetStream(), "stale-relay") == 0


@pytest.mark.asyncio
async def test_publish_failure_releases_owned_claim_with_backoff(monkeypatch):
    connection = ClaimConnection(event=event_row())
    monkeypatch.setattr("trading_platform.outbox.connect", lambda *_: nullcontext(connection))
    monkeypatch.setattr("trading_platform.outbox.random.random", lambda: 0.0)

    class JetStream:
        async def publish(self, *args, **kwargs): raise RuntimeError("nats unavailable")

    assert await publish_pending(outbox_settings(), JetStream(), "relay-a") == 0
    failure_query, failure_parameters = next(
        call for call in connection.calls if "next_attempt_at=now()" in call[0]
    )
    assert "claim_owner=NULL,claim_token=NULL,claim_expires_at=NULL" in failure_query
    assert failure_parameters[0] == 2
    assert failure_parameters[3] == "relay-a"
    assert connection.rollbacks == 1
