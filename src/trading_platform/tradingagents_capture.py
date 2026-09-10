from __future__ import annotations

import base64
import contextvars
import functools
import hashlib
import importlib
import importlib.metadata
import inspect
import json
import threading
import types
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from .artifacts import ArtifactStore
from .capture import (
    canonical_digest,
    classify_error,
    complete_semantic_invocation,
    persist_source_call,
    persist_vendor_attempt,
    sanitize,
    start_semantic_invocation,
)
from .contracts import (
    SemanticInvocationRecord,
    SourceCallOutcome,
    SourceCallRecord,
    SourceObservation,
    VendorAttemptRecord,
)
from .source_metadata import build_source_temporal_metadata
from .source_allowlist import (
    CryptoCaptureScope,
    IngressPolicyError,
    KNOWN_ROUTED_METHODS,
    validate_completed_fallbacks,
    validate_crypto_scope,
    validate_semantic_ingress,
    validate_vendor_attempt,
)


PINNED_VERSION = "0.3.1"
PINNED_COMMIT = "01477f9afb7a47b849ed4c9259d3a9a4738d9fda"
EXPECTED_SOURCE_HASHES = {
    "tradingagents.dataflows.interface": "c931d4977e0c5df7aebfe7fb565f364ee2e52ac162c135f66a60e48837a2e9cd",
    "tradingagents.agents.analysts.sentiment_analyst": "15731278f6f4d68b397597fe8c8bbaa788675c275bd2db81fe05d0a61e3c669c",
    "tradingagents.agents.utils.agent_utils": "997a8bec6a7a65fff644b130ad235738c007fd97fe9dc1cfdadac8d3def6dc0a",
    "tradingagents.agents.utils.market_data_validation_tools": "1b3bd5da283ea9ae2a5d189ac60f4f952c95dc63bd8e78eb6fb0f7090af1a7c2",
    "tradingagents.graph.trading_graph": "2febfe879d119fcc1b866783e2754ca09b1eacfc9b0d430d214e8ebec6fa853d",
    "tradingagents.agents.utils.memory": "8401dacff141fd53f14e13d002f57f57f01943ab3a97ced8d14efb4b9fdbbbcd",
    "tradingagents.dataflows.y_finance": "967f675cf5acdf1781fa5c5e0a25c1c43d6ec1dc82ae82d19f6a619c236a791c",
    "tradingagents.dataflows.yfinance_news": "4cfcf333d5b017ce9a14a182b8e775ea7f326a401827c5b9a69bc27648516a10",
    "tradingagents.dataflows.reddit": "b30c4ee6964bf981be766bc3a98cd58c507cbff66d682a812f4287a33e8e16f4",
    "tradingagents.dataflows.stocktwits": "47396ba6ea42dcd204af938591a70ad71e4be1f8e6c90d77337fa049f3d1cb8c",
    "tradingagents.dataflows.market_data_validator": "6f32e7905afa2216b5d7a7db208636f4a1c1f8223246685f84c8a6803b62ade7",
    "tradingagents.dataflows.symbol_utils": "c2a46c1152bd6991b9ba59b61618b2ae58d3b8e88b40c96c1cb85e01ca32b7b4",
    "tradingagents.dataflows.alpha_vantage_stock": "e72a43304017b535c098fc67e65f0c80ba22dbf2b0f9818ea10afd1d5d5ba5a4",
    "tradingagents.dataflows.alpha_vantage_indicator": "d6d100027991490bdaed7cb2420e9700e77a7525202eae3499cc1ecfbc9f9576",
    "tradingagents.dataflows.alpha_vantage_news": "75aefe37c02cbeb3195d9174d7fb8c4af6516d5ff433f309ed0a1afa55001cd0",
    "tradingagents.dataflows.alpha_vantage_common": "935d2d7129f3b81ed691c0be65a1a6399b01fde790f6a593d665f748a9d66a7b",
}
ROUTED_CATEGORY = {
    "core_stock_apis": "research_market",
    "technical_indicators": "research_market",
    "fundamental_data": "fundamental",
    "news_data": "news",
    "macro_data": "macro",
    "prediction_markets": "prediction",
}
_ADAPTER_INSTALL_LOCK = threading.RLock()
_ACTIVE_CAPTURE_ADAPTER: "TradingAgentsCaptureAdapter | None" = None

ROUTE_BINDING_MODULES = (
    "tradingagents.agents.utils.core_stock_tools",
    "tradingagents.agents.utils.technical_indicators_tools",
    "tradingagents.agents.utils.fundamental_data_tools",
    "tradingagents.agents.utils.news_data_tools",
    "tradingagents.agents.utils.macro_data_tools",
    "tradingagents.agents.utils.prediction_markets_tools",
)

CONSUMER_BY_METHOD = {
    "get_stock_data": "market_analyst",
    "get_indicators": "market_analyst",
    "get_verified_market_snapshot": "market_analyst",
    "resolve_instrument_identity": "graph_preflight",
    "get_news": "news_analyst",
    "get_global_news": "news_analyst",
    "get_macro_indicators": "news_analyst",
    "get_prediction_markets": "news_analyst",
    "fetch_stocktwits_messages": "social_analyst",
    "fetch_reddit_posts": "social_analyst",
    "get_fundamentals": "fundamentals_analyst",
    "get_balance_sheet": "fundamentals_analyst",
    "get_cashflow": "fundamentals_analyst",
    "get_income_statement": "fundamentals_analyst",
    "get_insider_transactions": "fundamentals_analyst",
}


@dataclass
class _InvocationContext:
    invocation_id: UUID
    ordinal: int
    method: str
    category: str
    consumer: str
    arguments: dict[str, Any]
    arguments_hash: str
    started_at: datetime
    next_fallback_ordinal: int = 0
    last_vendor: str | None = None
    last_artifact_digest: str | None = None
    last_observation_id: UUID | None = None
    last_first_seen_at: datetime | None = None
    hook_data: dict[str, Any] = field(default_factory=dict)
    expected_vendor_chain: tuple[str, ...] = ()
    attempts: list[tuple[str, str]] = field(default_factory=list)


_INVOCATION_CONTEXT: contextvars.ContextVar[_InvocationContext | None] = contextvars.ContextVar(
    "tradingagents_capture_invocation", default=None
)


class InvalidCapturedResponse(RuntimeError):
    """A pinned vendor returned an error-shaped value instead of raising."""


class InvalidTemporalMetadata(RuntimeError):
    """A captured result could not produce required typed source chronology."""


class UpstreamDriftError(RuntimeError):
    pass


class CapturePersistenceError(RuntimeError):
    pass


ISOLATED_ANALYSTS = ("market", "social", "news")
LIFECYCLE_ISOLATION_VERSION = "1.0.0"


def isolated_tradingagents_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    """Return a fresh-run configuration with mutable upstream memory disabled."""
    isolated = configuration.copy()
    isolated["checkpoint_enabled"] = False
    isolated["memory_log_path"] = None
    isolated["platform_lifecycle_isolation"] = LIFECYCLE_ISOLATION_VERSION
    return isolated


class _IsolatedMemoryLog:
    """Explicitly empty, side-effect-free replacement for upstream file memory."""

    __trading_platform_isolated__ = True

    def get_pending_entries(self) -> list[dict[str, Any]]:
        return []

    def get_past_context(self, ticker: str, n_same: int = 5, n_cross: int = 3) -> str:
        return ""

    def store_decision(self, ticker: str, trade_date: str, final_trade_decision: str) -> None:
        return None

    def batch_update_with_outcomes(self, updates: list[dict[str, Any]]) -> None:
        raise RuntimeError("TradingAgents reflection memory is disabled")


def _skip_pending_reflection(graph: Any, ticker: str) -> None:
    return None


def _skip_state_log(graph: Any, trade_date: str, final_state: dict[str, Any]) -> None:
    return None


setattr(_skip_pending_reflection, "__trading_platform_isolated__", True)
setattr(_skip_state_log, "__trading_platform_isolated__", True)


class TradingAgentsLifecycleIsolation:
    """Disable upstream state that is not part of the immutable capture contract."""

    def __init__(self) -> None:
        self._installed_graph_id: int | None = None

    def install(self, graph: Any) -> None:
        audit_pinned_upstream()
        if tuple(graph.selected_analysts) != ISOLATED_ANALYSTS:
            raise UpstreamDriftError(
                "unsafe TradingAgents analyst set; expected " + ",".join(ISOLATED_ANALYSTS)
            )
        if graph.config.get("checkpoint_enabled") is not False:
            raise UpstreamDriftError("TradingAgents checkpointing must be explicitly disabled")
        if graph.config.get("memory_log_path") is not None:
            raise UpstreamDriftError("TradingAgents memory path must be disabled before construction")
        graph.memory_log = _IsolatedMemoryLog()
        graph._resolve_pending_entries = types.MethodType(_skip_pending_reflection, graph)
        graph._log_state = types.MethodType(_skip_state_log, graph)
        self._installed_graph_id = id(graph)

    def assert_installed(self, graph: Any) -> None:
        if self._installed_graph_id != id(graph):
            raise RuntimeError("lifecycle isolation is not installed on this graph")
        checks = (
            getattr(graph.memory_log, "__trading_platform_isolated__", False),
            getattr(graph._resolve_pending_entries, "__trading_platform_isolated__", False),
            getattr(graph._log_state, "__trading_platform_isolated__", False),
            graph.config.get("checkpoint_enabled") is False,
            graph.config.get("memory_log_path") is None,
            tuple(graph.selected_analysts) == ISOLATED_ANALYSTS,
        )
        if not all(checks):
            raise UpstreamDriftError("TradingAgents lifecycle isolation was modified after install")


def encode_normalized(value: Any) -> bytes:
    if isinstance(value, bytes):
        document = {"type": "bytes", "value": base64.b64encode(value).decode("ascii")}
    elif isinstance(value, str):
        document = {"type": "str", "value": value}
    elif value is None or isinstance(value, (bool, int, float, list, dict)):
        document = {"type": "json", "value": value}
    else:
        raise TypeError(f"unsupported captured return type: {type(value).__name__}")
    try:
        return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    except (TypeError, ValueError) as exc:
        raise TypeError("captured return value is not JSON-safe") from exc


def decode_normalized(content: bytes) -> Any:
    document = json.loads(content)
    if set(document) != {"type", "value"}:
        raise ValueError("invalid normalized artifact envelope")
    if document["type"] == "bytes":
        return base64.b64decode(document["value"], validate=True)
    if document["type"] in ("str", "json"):
        return document["value"]
    raise ValueError("unknown normalized artifact type")


def classify_captured_result(
    value: Any, method: str | None = None
) -> tuple[SourceCallOutcome, str | None]:
    """Classify only pinned, explicit sentinels; never infer availability from prose."""
    if method == "resolve_instrument_identity" and value == {}:
        return SourceCallOutcome.NO_DATA, "instrument_identity_unavailable"
    if isinstance(value, dict):
        if any(key in value for key in ("Error Message", "Information", "Note")):
            return SourceCallOutcome.INVALID_RESPONSE, "vendor_error_shaped_response"
        if method in ("get_news", "get_global_news") and value.get("feed") == []:
            return SourceCallOutcome.NO_DATA, "vendor_no_data"
    if not isinstance(value, str):
        return SourceCallOutcome.AVAILABLE, None
    stripped = value.lstrip()
    if stripped.startswith("NO_DATA_AVAILABLE:"):
        return SourceCallOutcome.NO_DATA, "vendor_no_data"
    if stripped.startswith("DATA_UNAVAILABLE:"):
        return SourceCallOutcome.UNAVAILABLE, "vendor_unavailable"
    if method in ("get_news", "get_global_news") and stripped.startswith(
        ("No news found", "No global news found")
    ):
        return SourceCallOutcome.NO_DATA, "vendor_no_data"
    if method == "fetch_stocktwits_messages":
        if stripped.startswith("<stocktwits unavailable:"):
            return SourceCallOutcome.UNAVAILABLE, "vendor_unavailable"
        if stripped.startswith("<no StockTwits messages found"):
            return SourceCallOutcome.NO_DATA, "vendor_no_data"
    if method == "fetch_reddit_posts" and stripped.startswith("<no Reddit posts found"):
        return SourceCallOutcome.NO_DATA, "vendor_no_data"
    lowered = stripped.lower()
    if lowered.startswith((
        "error fetching", "error retrieving", "error:", "failed to fetch", "request failed"
    )):
        return SourceCallOutcome.INVALID_RESPONSE, "vendor_error_shaped_response"
    return SourceCallOutcome.AVAILABLE, None


def audit_pinned_upstream() -> None:
    try:
        installed = importlib.metadata.version("tradingagents")
    except importlib.metadata.PackageNotFoundError as exc:
        raise UpstreamDriftError("TradingAgents is not installed") from exc
    if installed != PINNED_VERSION:
        raise UpstreamDriftError(f"TradingAgents version drift: expected {PINNED_VERSION}, got {installed}")
    for module_name, expected in EXPECTED_SOURCE_HASHES.items():
        module = importlib.import_module(module_name)
        source_path = inspect.getsourcefile(module)
        if not source_path:
            raise UpstreamDriftError(f"cannot locate source for {module_name}")
        actual = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
        if actual != expected:
            raise UpstreamDriftError(f"TradingAgents source drift in {module_name}")
    interface = importlib.import_module("tradingagents.dataflows.interface")
    actual_methods = set(interface.VENDOR_METHODS)
    expected_methods = {method for info in interface.TOOLS_CATEGORIES.values() for method in info["tools"]}
    if actual_methods != expected_methods:
        raise UpstreamDriftError("TradingAgents vendor method inventory drift")
    if actual_methods != set(KNOWN_ROUTED_METHODS):
        raise UpstreamDriftError("TradingAgents routed ingress allowlist drift")
    trading_graph = importlib.import_module("tradingagents.graph.trading_graph")
    for method in ("_resolve_pending_entries", "_fetch_returns", "_run_graph", "_log_state"):
        if not inspect.isfunction(getattr(trading_graph.TradingAgentsGraph, method, None)):
            raise UpstreamDriftError(f"TradingAgents lifecycle method drift: {method}")
    memory = importlib.import_module("tradingagents.agents.utils.memory")
    for method in (
        "get_pending_entries", "get_past_context", "store_decision", "batch_update_with_outcomes"
    ):
        if not inspect.isfunction(getattr(memory.TradingMemoryLog, method, None)):
            raise UpstreamDriftError(f"TradingAgents memory method drift: {method}")


class TradingAgentsCaptureAdapter:
    """Capture exact semantic values before TradingAgents receives them."""

    def __init__(self, database_url: str, artifact_dir: Path, session_id: UUID):
        self.database_url = database_url
        self.store = ArtifactStore(artifact_dir)
        self.session_id = session_id
        self._installed = False
        self._lock = threading.Lock()
        self._restore_actions: list[Callable[[], None]] = []
        self._scope: CryptoCaptureScope | None = None

    def _load_scope(self) -> CryptoCaptureScope:
        """Load and validate the immutable instrument and vendor boundary once."""
        from .db import connect

        if self._scope is not None:
            return self._scope
        with connect(self.database_url) as connection:
            row = connection.execute(
                """
                SELECT session.instrument_id,instrument.research_symbol,
                       instrument.execution_exchange,instrument.execution_pair,
                       instrument.market_type,instrument.enabled,
                       manifest.configured_vendors
                FROM capture_sessions AS session
                JOIN instruments AS instrument
                  ON instrument.instrument_id=session.instrument_id
                JOIN evidence_manifests AS manifest
                  ON manifest.manifest_id=session.manifest_id
                 AND manifest.capture_session_id=session.session_id
                WHERE session.session_id=%s AND session.status='collecting'
                  AND session.mode='live_capture' AND session.deadline_at>now()
                  AND session.job_id IS NOT NULL
                  AND session.job_attempt IS NOT NULL
                  AND session.fencing_token IS NOT NULL
                """,
                (self.session_id,),
            ).fetchone()
        if row is None:
            raise IngressPolicyError("ingress.capture_scope_invalid")
        scope = CryptoCaptureScope(
            instrument_id=row["instrument_id"],
            research_symbol=row["research_symbol"],
            execution_exchange=row["execution_exchange"],
            execution_pair=row["execution_pair"],
            market_type=row["market_type"],
            enabled=bool(row["enabled"]),
            vendor_plan=row["configured_vendors"],
        )
        validate_crypto_scope(scope)
        self._scope = scope
        return scope

    def _allocate_ordinal(self) -> int:
        from .db import connect

        with connect(self.database_url) as connection:
            row = connection.execute(
                """
                UPDATE capture_sessions SET next_call_ordinal=next_call_ordinal+1
                WHERE session_id=%s AND status='collecting' AND deadline_at>now()
                RETURNING next_call_ordinal-1 AS ordinal
                """,
                (self.session_id,),
            ).fetchone()
            connection.commit()
        if row is None:
            raise CapturePersistenceError("capture session is closed, missing, or past deadline")
        return int(row["ordinal"])

    @staticmethod
    def _replay_safety(category: str) -> tuple[bool, str | None]:
        if category == "social":
            return False, "live social feed; safe only from this captured artifact"
        if category == "prediction":
            return False, "live-at-fetch prediction market snapshot"
        if category == "macro":
            return False, "macro response has no verified point-in-time vintage"
        return True, None

    @staticmethod
    def _classify_vendor_error(error: BaseException) -> tuple[SourceCallOutcome, str]:
        if isinstance(error, IngressPolicyError):
            return SourceCallOutcome.POLICY_REJECTED, error.code
        name = error.__class__.__name__.lower()
        if name == "nomarketdataerror":
            return SourceCallOutcome.NO_DATA, "vendor_no_data"
        if name == "vendornotconfigurederror":
            return SourceCallOutcome.UNAVAILABLE, "vendor_not_configured"
        if name == "vendorratelimiterror":
            return SourceCallOutcome.RATE_LIMITED, "vendor_rate_limited"
        if isinstance(error, InvalidCapturedResponse):
            return SourceCallOutcome.INVALID_RESPONSE, "vendor_error_shaped_response"
        if isinstance(error, InvalidTemporalMetadata):
            return SourceCallOutcome.INVALID_RESPONSE, "temporal_metadata_invalid"
        return classify_error(error)

    def _start_context(
        self,
        *,
        method: str,
        category: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        consumer: str | None = None,
    ) -> _InvocationContext:
        from .db import connect

        invocation_id = uuid4()
        started_at = datetime.now(timezone.utc)
        arguments = sanitize({"args": list(args), "kwargs": kwargs})
        arguments_hash = canonical_digest(arguments)
        resolved_consumer = consumer or CONSUMER_BY_METHOD.get(method, "unassigned")
        expected_vendor_chain = validate_semantic_ingress(
            self._load_scope(), method=method, category=category,
            consumer=resolved_consumer, arguments=arguments,
        )
        with connect(self.database_url) as connection:
            ordinal = start_semantic_invocation(
                connection,
                invocation_id=invocation_id,
                session_id=self.session_id,
                method=method,
                category=category,
                policy_subject=method,
                consumer=resolved_consumer,
                sanitized_arguments=arguments,
                arguments_hash=arguments_hash,
                started_at=started_at,
            )
            connection.commit()
        return _InvocationContext(
            invocation_id=invocation_id,
            ordinal=ordinal,
            method=method,
            category=category,
            consumer=resolved_consumer,
            arguments=arguments,
            arguments_hash=arguments_hash,
            started_at=started_at,
            expected_vendor_chain=expected_vendor_chain,
        )

    def _complete_context(self, context: _InvocationContext, result: Any) -> None:
        from .db import connect
        from .evidence import persist_observation

        first_seen_at = context.last_first_seen_at or datetime.now(timezone.utc)
        outcome, error_code = classify_captured_result(result, context.method)
        validate_completed_fallbacks(
            context.expected_vendor_chain, context.attempts, outcome.value
        )
        content = encode_normalized(result)
        artifact = self.store.put(content, "application/vnd.tradingagents.normalized+json")
        replay_safe, unsafe_reason = self._replay_safety(context.category)
        try:
            metadata = build_source_temporal_metadata(
                method=context.method,
                arguments=context.arguments,
                result=result,
                outcome=outcome,
                first_seen_at=first_seen_at,
                hook_data=context.hook_data,
            )
        except (TypeError, ValueError) as exc:
            raise InvalidTemporalMetadata("source chronology could not be validated") from exc
        observation_id = context.last_observation_id
        if context.last_artifact_digest != artifact.digest or observation_id is None:
            observation = SourceObservation(
                category=context.category,
                vendor=context.last_vendor or "tradingagents_router",
                symbol_or_query=str(context.arguments.get("args", [context.method])[0]),
                event_at=(
                    metadata.latest_bar_at
                    if context.category == "research_market"
                    else metadata.latest_item_at
                ),
                published_at=(metadata.latest_item_at if context.category == "news" else None),
                first_seen_at=first_seen_at,
                retrieved_at=first_seen_at,
                artifact=artifact,
                request_parameters=context.arguments,
                status="available" if outcome == SourceCallOutcome.AVAILABLE else "unavailable",
                error_code=error_code,
                quality_flags=([error_code] if error_code else []) + metadata.quality_flags,
                replay_safe=replay_safe,
                replay_unsafe_reason=unsafe_reason,
            )
            observation_id = observation.observation_id
        else:
            observation = None
        completed_at = datetime.now(timezone.utc)
        invocation = SemanticInvocationRecord(
            invocation_id=context.invocation_id,
            session_id=self.session_id,
            ordinal=context.ordinal,
            method=context.method,
            category=context.category,
            policy_subject=context.method,
            consumer=context.consumer,
            sanitized_arguments=context.arguments,
            arguments_hash=context.arguments_hash,
            started_at=context.started_at,
            first_seen_at=first_seen_at,
            completed_at=completed_at,
            information_cutoff_at=metadata.information_cutoff_at, outcome=outcome,
            error_code=error_code,
            normalized_artifact_digest=artifact.digest,
            observation_id=observation_id,
            typed_metadata=metadata,
            replay_safe=replay_safe,
            replay_unsafe_reason=unsafe_reason,
        )
        with connect(self.database_url) as connection:
            with connection.transaction():
                if observation is not None:
                    persist_observation(connection, observation)
                complete_semantic_invocation(connection, invocation)

    def _fail_context(self, context: _InvocationContext, error: BaseException) -> None:
        from .db import connect

        completed_at = datetime.now(timezone.utc)
        outcome, error_code = self._classify_vendor_error(error)
        if outcome in (SourceCallOutcome.NO_DATA, SourceCallOutcome.UNAVAILABLE):
            # An exception delivered no value to the graph. Reserve no_data/unavailable
            # semantic outcomes for exact persisted sentinels that were actually returned.
            outcome = SourceCallOutcome.VENDOR_ERROR
        replay_safe, unsafe_reason = self._replay_safety(context.category)
        metadata = build_source_temporal_metadata(
            method=context.method, arguments=context.arguments, result=None,
            outcome=outcome, first_seen_at=completed_at, hook_data=context.hook_data,
        )
        invocation = SemanticInvocationRecord(
            invocation_id=context.invocation_id,
            session_id=self.session_id,
            ordinal=context.ordinal,
            method=context.method,
            category=context.category,
            policy_subject=context.method,
            consumer=context.consumer,
            sanitized_arguments=context.arguments,
            arguments_hash=context.arguments_hash,
            started_at=context.started_at,
            first_seen_at=completed_at,
            completed_at=completed_at,
            outcome=outcome,
            error_code=error_code,
            typed_metadata=metadata,
            replay_safe=replay_safe,
            replay_unsafe_reason=unsafe_reason,
        )
        with connect(self.database_url) as connection:
            complete_semantic_invocation(connection, invocation)
            connection.commit()

    def _persist_failure(
        self, *, ordinal: int, method: str, category: str, vendor: str,
        arguments: dict[str, Any], started_at: datetime, error: BaseException,
        context: _InvocationContext, fallback_ordinal: int,
    ) -> SourceCallOutcome:
        from .db import connect

        completed_at = datetime.now(timezone.utc)
        outcome, error_code = self._classify_vendor_error(error)
        call = SourceCallRecord(
            session_id=self.session_id, ordinal=ordinal, method=method, category=category,
            vendor=vendor, fallback_ordinal=fallback_ordinal,
            sanitized_arguments=arguments, arguments_hash=canonical_digest(arguments),
            started_at=started_at, first_seen_at=completed_at, completed_at=completed_at,
            outcome=outcome, error_code=error_code,
        )
        attempt = VendorAttemptRecord(
            invocation_id=context.invocation_id, session_id=self.session_id,
            fallback_ordinal=fallback_ordinal, vendor=vendor, started_at=started_at,
            first_seen_at=completed_at, completed_at=completed_at, outcome=outcome,
            error_code=error_code,
        )
        with connect(self.database_url) as connection:
            with connection.transaction():
                persist_source_call(connection, call)
                persist_vendor_attempt(connection, attempt)
        return outcome

    def capture_call(
        self, method: str, category: str, vendor: str, function: Callable[..., Any],
        args: tuple[Any, ...], kwargs: dict[str, Any], consumer: str | None = None,
    ) -> Any:
        from .db import connect
        from .evidence import persist_observation

        context = _INVOCATION_CONTEXT.get()
        if context is None:
            raise CapturePersistenceError("vendor call occurred outside a semantic invocation")
        if method != context.method:
            raise IngressPolicyError("ingress.vendor_method_mismatch")
        if category != context.category:
            raise IngressPolicyError("ingress.vendor_category_mismatch")
        fallback_ordinal = context.next_fallback_ordinal
        validate_vendor_attempt(context.expected_vendor_chain, vendor, fallback_ordinal)
        ordinal = self._allocate_ordinal()
        context.next_fallback_ordinal += 1
        started_at = datetime.now(timezone.utc)
        arguments = sanitize({"args": list(args), "kwargs": kwargs})
        try:
            result = function(*args, **kwargs)
        except BaseException as exc:
            try:
                failure_outcome = self._persist_failure(
                    ordinal=ordinal, method=method, category=category, vendor=vendor,
                    arguments=arguments, started_at=started_at, error=exc,
                    context=context, fallback_ordinal=fallback_ordinal,
                )
                context.attempts.append((vendor, failure_outcome.value))
            except BaseException as persistence_error:
                raise CapturePersistenceError("failed to persist vendor failure") from persistence_error
            raise
        outcome, error_code = classify_captured_result(result, method)
        if outcome == SourceCallOutcome.INVALID_RESPONSE:
            invalid = InvalidCapturedResponse("vendor returned an error-shaped response")
            try:
                failure_outcome = self._persist_failure(
                    ordinal=ordinal, method=method, category=category, vendor=vendor,
                    arguments=arguments, started_at=started_at, error=invalid,
                    context=context, fallback_ordinal=fallback_ordinal,
                )
                context.attempts.append((vendor, failure_outcome.value))
            except BaseException as persistence_error:
                raise CapturePersistenceError(
                    "failed to persist invalid vendor response"
                ) from persistence_error
            raise invalid
        first_seen_at = datetime.now(timezone.utc)
        try:
            metadata = build_source_temporal_metadata(
                method=method, arguments=context.arguments, result=result,
                outcome=outcome, first_seen_at=first_seen_at,
                hook_data=context.hook_data,
            )
        except (TypeError, ValueError) as exc:
            invalid = InvalidTemporalMetadata("source chronology could not be validated")
            try:
                failure_outcome = self._persist_failure(
                    ordinal=ordinal, method=method, category=category, vendor=vendor,
                    arguments=arguments, started_at=started_at, error=invalid,
                    context=context, fallback_ordinal=fallback_ordinal,
                )
                context.attempts.append((vendor, failure_outcome.value))
            except BaseException as persistence_error:
                raise CapturePersistenceError(
                    "failed to persist invalid temporal metadata"
                ) from persistence_error
            raise invalid from exc
        content = encode_normalized(result)
        artifact = self.store.put(content, "application/vnd.tradingagents.normalized+json")
        replay_safe, unsafe_reason = self._replay_safety(category)
        observation = SourceObservation(
            category=category,
            vendor=vendor,
            symbol_or_query=str(args[0]) if args else method,
            event_at=(
                metadata.latest_bar_at
                if category == "research_market"
                else metadata.latest_item_at
            ),
            published_at=(metadata.latest_item_at if category == "news" else None),
            first_seen_at=first_seen_at,
            retrieved_at=first_seen_at,
            artifact=artifact,
            request_parameters=arguments,
            status="available" if outcome == SourceCallOutcome.AVAILABLE else "unavailable",
            error_code=error_code,
            quality_flags=([error_code] if error_code else []) + metadata.quality_flags,
            replay_safe=replay_safe,
            replay_unsafe_reason=unsafe_reason,
        )
        completed_at = datetime.now(timezone.utc)
        call = SourceCallRecord(
            session_id=self.session_id, ordinal=ordinal, method=method, category=category,
            vendor=vendor, fallback_ordinal=fallback_ordinal,
            consumer=consumer or context.consumer, sanitized_arguments=arguments,
            arguments_hash=canonical_digest(arguments), started_at=started_at,
            first_seen_at=first_seen_at, completed_at=completed_at,
            outcome=outcome,
            error_code=error_code,
            normalized_artifact_digest=artifact.digest, observation_id=observation.observation_id,
        )
        attempt = VendorAttemptRecord(
            invocation_id=context.invocation_id, session_id=self.session_id,
            fallback_ordinal=fallback_ordinal, vendor=vendor, started_at=started_at,
            first_seen_at=first_seen_at, completed_at=completed_at, outcome=outcome,
            error_code=error_code, normalized_artifact_digest=artifact.digest,
            observation_id=observation.observation_id,
        )
        try:
            with connect(self.database_url) as connection:
                with connection.transaction():
                    persist_observation(connection, observation)
                    persist_source_call(connection, call)
                    persist_vendor_attempt(connection, attempt)
        except BaseException as exc:
            raise CapturePersistenceError("failed to persist captured vendor result") from exc
        context.last_vendor = vendor
        context.last_artifact_digest = artifact.digest
        context.last_observation_id = observation.observation_id
        context.last_first_seen_at = first_seen_at
        context.attempts.append((vendor, outcome.value))
        return result

    def _wrapper(self, method: str, category: str, vendor: str, function: Callable[..., Any]):
        @functools.wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            return self.capture_call(method, category, vendor, function, args, kwargs)
        setattr(wrapped, "__trading_platform_captured__", True)
        return wrapped

    @staticmethod
    def _news_extract_wrapper(function: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(function)
        def wrapped(article: dict[str, Any]) -> dict[str, Any]:
            data = function(article)
            context = _INVOCATION_CONTEXT.get()
            if context is not None and context.method in ("get_news", "get_global_news"):
                published_at = data.get("pub_date")
                if isinstance(published_at, datetime):
                    if published_at.tzinfo is None or published_at.utcoffset() is None:
                        published_at = published_at.replace(tzinfo=timezone.utc)
                    else:
                        published_at = published_at.astimezone(timezone.utc)
                else:
                    published_at = None
                context.hook_data["pending_news_time"] = published_at
                context.hook_data["news_hook_observed"] = True
            return data

        setattr(wrapped, "__trading_platform_metadata_hook__", True)
        return wrapped

    @staticmethod
    def _news_window_wrapper(function: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(function)
        def wrapped(pub_date: Any, start_dt: datetime, end_dt: datetime) -> bool:
            kept = function(pub_date, start_dt, end_dt)
            context = _INVOCATION_CONTEXT.get()
            if context is not None and context.method in ("get_news", "get_global_news"):
                published_at = context.hook_data.pop("pending_news_time", None)
                if kept:
                    context.hook_data["kept_news_count"] = (
                        int(context.hook_data.get("kept_news_count", 0)) + 1
                    )
                    if published_at is not None:
                        context.hook_data.setdefault("kept_news_times", []).append(published_at)
            return kept

        setattr(wrapped, "__trading_platform_metadata_hook__", True)
        return wrapped

    @staticmethod
    def _reddit_fetch_wrapper(function: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            posts = function(*args, **kwargs)
            context = _INVOCATION_CONTEXT.get()
            if context is not None and context.method == "fetch_reddit_posts":
                context.hook_data["reddit_hook_observed"] = True
                context.hook_data["reddit_item_count"] = (
                    int(context.hook_data.get("reddit_item_count", 0)) + len(posts)
                )
                captured = context.hook_data.setdefault("reddit_created_times", [])
                for post in posts:
                    timestamp = post.get("created_utc")
                    try:
                        captured.append(datetime.fromtimestamp(float(timestamp), timezone.utc))
                    except (TypeError, ValueError, OSError):
                        captured.append(None)
            return posts

        setattr(wrapped, "__trading_platform_metadata_hook__", True)
        return wrapped

    def _semantic_wrapper(
        self, method: str, category: str, function: Callable[..., Any], *, direct_vendor: str | None = None
    ) -> Callable[..., Any]:
        @functools.wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            context = self._start_context(method=method, category=category, args=args, kwargs=kwargs)
            token = _INVOCATION_CONTEXT.set(context)
            try:
                if direct_vendor is None:
                    result = function(method, *args, **kwargs)
                else:
                    result = self.capture_call(
                        method, category, direct_vendor, function, args, kwargs,
                        consumer=context.consumer,
                    )
                self._complete_context(context, result)
                return result
            except BaseException as exc:
                try:
                    self._fail_context(context, exc)
                except ValueError as completion_error:
                    if "already complete" not in str(completion_error):
                        raise CapturePersistenceError(
                            "failed to persist semantic invocation failure"
                        ) from completion_error
                raise
            finally:
                _INVOCATION_CONTEXT.reset(token)

        setattr(wrapped, "__trading_platform_semantic_captured__", True)
        return wrapped

    def _route_wrapper(self, function: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(function)
        def wrapped(method: str, *args: Any, **kwargs: Any) -> Any:
            interface = importlib.import_module("tradingagents.dataflows.interface")
            upstream_category = interface.get_category_for_method(method)
            category = ROUTED_CATEGORY[upstream_category]
            context = self._start_context(
                method=method, category=category, args=args, kwargs=kwargs
            )
            token = _INVOCATION_CONTEXT.set(context)
            try:
                vendor_config = interface.get_vendor(upstream_category, method)
                configured = tuple(
                    vendor.strip() for vendor in vendor_config.split(",")
                    if vendor.strip() and vendor.strip() != "default"
                )
                actual_chain = configured or tuple(interface.VENDOR_METHODS[method])
                if actual_chain != context.expected_vendor_chain:
                    raise IngressPolicyError(
                        "ingress.configured_vendor_chain_mismatch"
                    )
                result = function(method, *args, **kwargs)
                self._complete_context(context, result)
                return result
            except BaseException as exc:
                try:
                    self._fail_context(context, exc)
                except ValueError as completion_error:
                    if "already complete" not in str(completion_error):
                        raise CapturePersistenceError(
                            "failed to persist semantic invocation failure"
                        ) from completion_error
                raise
            finally:
                _INVOCATION_CONTEXT.reset(token)

        setattr(wrapped, "__trading_platform_semantic_captured__", True)
        return wrapped

    def install(self) -> None:
        global _ACTIVE_CAPTURE_ADAPTER
        with self._lock:
            if self._installed:
                return
            with _ADAPTER_INSTALL_LOCK:
                if _ACTIVE_CAPTURE_ADAPTER is not None:
                    raise RuntimeError("another TradingAgents capture session is already installed")
                audit_pinned_upstream()
                try:
                    interface = importlib.import_module("tradingagents.dataflows.interface")
                    original_route = interface.route_to_vendor
                    semantic_route = self._route_wrapper(original_route)
                    self._restore_actions.append(
                        functools.partial(setattr, interface, "route_to_vendor", original_route)
                    )
                    interface.route_to_vendor = semantic_route
                    for module_name in ROUTE_BINDING_MODULES:
                        route_module = importlib.import_module(module_name)
                        imported_route = getattr(route_module, "route_to_vendor", None)
                        if imported_route is not original_route:
                            raise UpstreamDriftError(
                                f"TradingAgents route binding drift in {module_name}"
                            )
                        self._restore_actions.append(
                            functools.partial(
                                setattr, route_module, "route_to_vendor", imported_route
                            )
                        )
                        route_module.route_to_vendor = semantic_route
                    news_module = importlib.import_module(
                        "tradingagents.dataflows.yfinance_news"
                    )
                    for hook_name, wrapper_factory in (
                        ("_extract_article_data", self._news_extract_wrapper),
                        ("_in_news_window", self._news_window_wrapper),
                    ):
                        original_hook = getattr(news_module, hook_name)
                        self._restore_actions.append(
                            functools.partial(setattr, news_module, hook_name, original_hook)
                        )
                        setattr(news_module, hook_name, wrapper_factory(original_hook))
                    reddit_module = importlib.import_module("tradingagents.dataflows.reddit")
                    original_reddit_fetch = reddit_module._fetch_subreddit
                    self._restore_actions.append(
                        functools.partial(
                            setattr, reddit_module, "_fetch_subreddit", original_reddit_fetch
                        )
                    )
                    reddit_module._fetch_subreddit = self._reddit_fetch_wrapper(
                        original_reddit_fetch
                    )
                    for upstream_category, info in interface.TOOLS_CATEGORIES.items():
                        category = ROUTED_CATEGORY[upstream_category]
                        for method in info["tools"]:
                            vendors = interface.VENDOR_METHODS[method]
                            for vendor, function in list(vendors.items()):
                                if isinstance(function, list):
                                    raise UpstreamDriftError(
                                        "list-valued vendor implementation is unsupported"
                                    )
                                self._restore_actions.append(
                                    functools.partial(vendors.__setitem__, vendor, function)
                                )
                                vendors[vendor] = self._wrapper(method, category, vendor, function)
                    sentiment = importlib.import_module(
                        "tradingagents.agents.analysts.sentiment_analyst"
                    )
                    for name, method, vendor in (
                        ("fetch_stocktwits_messages", "fetch_stocktwits_messages", "stocktwits"),
                        ("fetch_reddit_posts", "fetch_reddit_posts", "reddit"),
                    ):
                        original = getattr(sentiment, name)
                        self._restore_actions.append(functools.partial(setattr, sentiment, name, original))
                        setattr(
                            sentiment,
                            name,
                            self._semantic_wrapper(
                                method, "social", original, direct_vendor=vendor
                            ),
                        )
                    validation_tools = importlib.import_module(
                        "tradingagents.agents.utils.market_data_validation_tools"
                    )
                    original_snapshot = validation_tools.build_verified_market_snapshot
                    self._restore_actions.append(
                        functools.partial(
                            setattr,
                            validation_tools,
                            "build_verified_market_snapshot",
                            original_snapshot,
                        )
                    )
                    validation_tools.build_verified_market_snapshot = self._semantic_wrapper(
                        "get_verified_market_snapshot",
                        "research_market",
                        original_snapshot,
                        direct_vendor="yfinance",
                    )
                    agent_utils = importlib.import_module("tradingagents.agents.utils.agent_utils")
                    original_identity = agent_utils.resolve_instrument_identity
                    identity_wrapper = self._semantic_wrapper(
                        "resolve_instrument_identity",
                        "research_market",
                        original_identity,
                        direct_vendor="yfinance_identity",
                    )
                    self._restore_actions.append(
                        functools.partial(
                            setattr, agent_utils, "resolve_instrument_identity", original_identity
                        )
                    )
                    agent_utils.resolve_instrument_identity = identity_wrapper
                    trading_graph = importlib.import_module("tradingagents.graph.trading_graph")
                    original_graph_identity = trading_graph.resolve_instrument_identity
                    self._restore_actions.append(
                        functools.partial(
                            setattr,
                            trading_graph,
                            "resolve_instrument_identity",
                            original_graph_identity,
                        )
                    )
                    trading_graph.resolve_instrument_identity = identity_wrapper
                    self._installed = True
                    _ACTIVE_CAPTURE_ADAPTER = self
                except BaseException:
                    for restore in reversed(self._restore_actions):
                        restore()
                    self._restore_actions.clear()
                    raise

    def uninstall(self) -> None:
        global _ACTIVE_CAPTURE_ADAPTER
        with self._lock:
            with _ADAPTER_INSTALL_LOCK:
                if not self._installed:
                    return
                if _ACTIVE_CAPTURE_ADAPTER is not self:
                    raise RuntimeError("capture adapter ownership changed unexpectedly")
                for restore in reversed(self._restore_actions):
                    restore()
                self._restore_actions.clear()
                self._installed = False
                _ACTIVE_CAPTURE_ADAPTER = None

    def assert_complete_installation(self) -> None:
        if not self._installed:
            raise RuntimeError("capture adapter is not installed")
        interface = importlib.import_module("tradingagents.dataflows.interface")
        if not getattr(
            interface.route_to_vendor, "__trading_platform_semantic_captured__", False
        ):
            raise UpstreamDriftError("uncaptured TradingAgents semantic router")
        uncaptured = [
            f"{method}:{vendor}"
            for method, vendors in interface.VENDOR_METHODS.items()
            for vendor, function in vendors.items()
            if not getattr(function, "__trading_platform_captured__", False)
        ]
        news_module = importlib.import_module("tradingagents.dataflows.yfinance_news")
        for hook_name in ("_extract_article_data", "_in_news_window"):
            if not getattr(
                getattr(news_module, hook_name), "__trading_platform_metadata_hook__", False
            ):
                uncaptured.append(f"yfinance_news.{hook_name}")
        reddit_module = importlib.import_module("tradingagents.dataflows.reddit")
        if not getattr(
            reddit_module._fetch_subreddit, "__trading_platform_metadata_hook__", False
        ):
            uncaptured.append("reddit._fetch_subreddit")
        sentiment = importlib.import_module("tradingagents.agents.analysts.sentiment_analyst")
        for name in ("fetch_stocktwits_messages", "fetch_reddit_posts"):
            if not getattr(
                getattr(sentiment, name), "__trading_platform_semantic_captured__", False
            ):
                uncaptured.append(name)
        validation_tools = importlib.import_module(
            "tradingagents.agents.utils.market_data_validation_tools"
        )
        if not getattr(
            validation_tools.build_verified_market_snapshot,
            "__trading_platform_semantic_captured__", False,
        ):
            uncaptured.append("get_verified_market_snapshot")
        agent_utils = importlib.import_module("tradingagents.agents.utils.agent_utils")
        if not getattr(
            agent_utils.resolve_instrument_identity,
            "__trading_platform_semantic_captured__", False
        ):
            uncaptured.append("resolve_instrument_identity")
        for module_name in ROUTE_BINDING_MODULES:
            route_module = importlib.import_module(module_name)
            if route_module.route_to_vendor is not interface.route_to_vendor:
                uncaptured.append(f"{module_name}.route_to_vendor")
        if uncaptured:
            raise UpstreamDriftError("uncaptured TradingAgents ingress: " + ", ".join(uncaptured))
