from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from trading_platform.contracts import PortfolioRating
from trading_platform.source_policy import PolicyVerdict, RuleOutcome
from trading_platform.worker import process_one


class WorkerConnection:
    def __init__(self):
        self.rollbacks = 0
        self.transaction_depth = 0

    def transaction(self):
        @contextmanager
        def transaction_scope():
            self.transaction_depth += 1
            try:
                yield
            finally:
                self.transaction_depth -= 1
        return transaction_scope()

    def rollback(self):
        self.rollbacks += 1


class ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *args):
        return None


class OwnedLease:
    def __init__(self, *args):
        self.checks = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def ensure_owned(self):
        self.checks += 1


def worker_fixture(tmp_path):
    now = datetime.now(timezone.utc)
    settings = SimpleNamespace(
        database_url="postgresql://test",
        research_mode="tradingagents",
        environment="production",
        bot_id="freqtrade-primary",
        exchange="binance",
        hmac_secret="a-reliable-test-secret-that-is-longer-than-32-bytes",
        producer_version="test",
        code_revision="revision",
        analysis_lease_seconds=900,
        capture_deadline_seconds=600,
        capture_adapter_version="1.0.0",
        tradingagents_commit="01477f9afb7a47b849ed4c9259d3a9a4738d9fda",
        artifact_dir=tmp_path,
        timeframe="5m",
        clock_skew_seconds=30,
        max_clock_offset_ms=2000,
    )
    job = {
        "job_id": uuid4(),
        "correlation_id": uuid4(),
        "instrument_id": "crypto:binance:spot:BTC-USDT",
        "execution_snapshot_id": uuid4(),
        "attempt": 2,
        "fencing_token": 4,
        "lease_expires_at": now + timedelta(minutes=15),
        "symbol": "BTC-USD",
        "pair": "BTC/USDT",
        "timeframe": "5m",
        "candle_close_at": now - timedelta(minutes=5),
    }
    return settings, job


def install_common_mocks(monkeypatch, connection, job):
    monkeypatch.setattr(
        "trading_platform.worker.connect", lambda *_: ConnectionContext(connection)
    )
    monkeypatch.setattr("trading_platform.worker.recover_expired_analysis_jobs", lambda *_: 0)
    monkeypatch.setattr("trading_platform.worker.claim_analysis_job", lambda *_: job)
    monkeypatch.setattr("trading_platform.worker.create_analysis_attempt", lambda *a, **k: None)
    monkeypatch.setattr("trading_platform.worker.LeaseRenewer", OwnedLease)
    monkeypatch.setattr(
        "trading_platform.worker.build_tradingagents_configuration",
        lambda *_: {"llm_provider": "test"},
    )
    monkeypatch.setattr(
        "trading_platform.worker.TradingAgentsCaptureAdapter", lambda *a, **k: object()
    )


def test_research_failure_rejects_open_capture_then_retries_job(monkeypatch, tmp_path):
    connection = WorkerConnection()
    settings, job = worker_fixture(tmp_path)
    install_common_mocks(monkeypatch, connection, job)
    started = []
    rejected = []
    failed = []
    monkeypatch.setattr(
        "trading_platform.worker.start_capture_session",
        lambda *args, **kwargs: started.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "trading_platform.worker.run_tradingagents",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("vendor failed")),
    )
    monkeypatch.setattr(
        "trading_platform.worker.reject_capture_session",
        lambda *args, **kwargs: rejected.append(
            (args, kwargs, connection.transaction_depth)
        ),
    )
    monkeypatch.setattr(
        "trading_platform.worker.fail_analysis_job",
        lambda *args, **kwargs: failed.append(
            (args, kwargs, connection.transaction_depth)
        ) or True,
    )

    assert process_one(settings, "worker-a") is True
    assert len(started) == 1
    assert len(rejected) == 1
    assert rejected[0][0][2] == "worker.analysis_failed"
    assert failed[0][1]["error_code"] == "analysis_failed"
    assert failed[0][1]["revocation_context"]["reason_code"] == "worker.analysis_failed"
    assert rejected[0][2] == failed[0][2] == 1


def test_policy_reject_consumes_job_without_publishing(monkeypatch, tmp_path):
    connection = WorkerConnection()
    settings, job = worker_fixture(tmp_path)
    install_common_mocks(monkeypatch, connection, job)
    terminal = []
    published = []
    monkeypatch.setattr("trading_platform.worker.start_capture_session", lambda *a, **k: None)
    monkeypatch.setattr(
        "trading_platform.worker.run_tradingagents",
        lambda *a, **k: SimpleNamespace(
            decision=SimpleNamespace(rating=PortfolioRating.BUY)
        ),
    )
    monkeypatch.setattr("trading_platform.worker.begin_capture_evaluation", lambda *a, **k: None)
    policy = SimpleNamespace(
        verdict=PolicyVerdict.REJECT,
        result_digest="sha256:" + "a" * 64,
        rules=(SimpleNamespace(
            outcome=RuleOutcome.FAIL, code="execution_snapshot.invalid"
        ),),
    )
    monkeypatch.setattr(
        "trading_platform.worker.evaluate_and_finalize_capture",
        lambda *a, **k: (policy, None),
    )
    monkeypatch.setattr(
        "trading_platform.worker.complete_analysis_without_signal",
        lambda *args, **kwargs: terminal.append(
            (args, kwargs, connection.transaction_depth)
        ),
    )
    monkeypatch.setattr(
        "trading_platform.worker.persist_signal_and_outbox",
        lambda *args, **kwargs: published.append((args, kwargs)),
    )

    assert process_one(settings, "worker-a") is True
    assert terminal[0][1]["outcome_code"] == "execution_snapshot.invalid"
    assert terminal[0][1]["denied_rating"] == PortfolioRating.BUY
    assert terminal[0][1]["revocation_context"]["pair"] == "BTC/USDT"
    assert terminal[0][2] == 1
    assert published == []


def test_policy_seal_and_signal_publication_share_one_outer_transaction(
    monkeypatch, tmp_path
):
    connection = WorkerConnection()
    settings, job = worker_fixture(tmp_path)
    install_common_mocks(monkeypatch, connection, job)
    monkeypatch.setattr("trading_platform.worker.start_capture_session", lambda *a, **k: None)
    result = SimpleNamespace(
        decision=SimpleNamespace(rating=PortfolioRating.BUY)
    )
    monkeypatch.setattr("trading_platform.worker.run_tradingagents", lambda *a, **k: result)
    monkeypatch.setattr("trading_platform.worker.begin_capture_evaluation", lambda *a, **k: None)
    policy = SimpleNamespace(
        verdict=PolicyVerdict.PASS,
        permitted_ratings=(PortfolioRating.BUY.value,),
    )
    monkeypatch.setattr(
        "trading_platform.worker.evaluate_and_finalize_capture",
        lambda *a, **k: (policy, SimpleNamespace(manifest_id=uuid4())),
    )
    publication_depths = []
    monkeypatch.setattr(
        "trading_platform.worker._persist_publishable_result",
        lambda *a, **k: publication_depths.append(connection.transaction_depth),
    )

    assert process_one(settings, "worker-a") is True
    assert publication_depths == [1]
