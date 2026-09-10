"""Canonical value primitives for the frozen E1-v14 accounting kernel.

This module deliberately depends only on the Python standard library.  It does
not know where an authority lives and contains no engine-construction hook.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
import re
from typing import Any, TypeVar


class CanonicalError(ValueError):
    """A value cannot be represented under the frozen canonical contract."""


_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_UTC_RE = re.compile(
    r"^(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})T"
    r"(?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})\.(?P<micro>[0-9]{6})Z$"
)
_K = TypeVar("_K", bound=str)
_V = TypeVar("_V")


class FrozenDict(Mapping[_K, _V]):
    """A small, recursively usable immutable mapping.

    The backing dictionary is copied on construction and is never returned.
    Keys are kept in insertion order for schema-order iteration; canonical JSON
    sorting is handled separately.
    """

    __slots__ = ("__data", "__hash")

    def __init__(self, values: Mapping[_K, _V] | Iterable[tuple[_K, _V]] = ()) -> None:
        data = dict(values)
        object.__setattr__(self, "_FrozenDict__data", data)
        object.__setattr__(self, "_FrozenDict__hash", None)

    def __getitem__(self, key: _K) -> _V:
        return self.__data[key]

    def __iter__(self) -> Iterator[_K]:
        return iter(self.__data)

    def __len__(self) -> int:
        return len(self.__data)

    def __repr__(self) -> str:
        return f"FrozenDict({self.__data!r})"

    def __hash__(self) -> int:
        cached = self.__hash
        if cached is None:
            cached = hash(tuple((key, _hashable(value)) for key, value in self.__data.items()))
            object.__setattr__(self, "_FrozenDict__hash", cached)
        return cached

    def __reduce__(self) -> tuple[type["FrozenDict"], tuple[dict[_K, _V]]]:
        return type(self), (dict(self.__data),)


def _hashable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple((key, _hashable(item)) for key, item in value.items())
    if isinstance(value, tuple):
        return tuple(_hashable(item) for item in value)
    return value


def freeze(value: Any) -> Any:
    """Recursively copy JSON-like data into immutable value containers."""

    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalError("mapping keys must be strings")
            if key in result:
                raise CanonicalError(f"duplicate or colliding mapping key: {key!r}")
            result[key] = freeze(item)
        return FrozenDict(result)
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    if isinstance(value, (str, int, bool, Decimal, datetime)) or value is None:
        if isinstance(value, Decimal) and not value.is_finite():
            raise CanonicalError("non-finite Decimal is forbidden")
        return value
    if isinstance(value, float):
        raise CanonicalError("binary float is forbidden")
    raise CanonicalError(f"unsupported canonical value type: {type(value).__name__}")


def thaw(value: Any) -> Any:
    """Return a detached mutable JSON-like copy of a frozen value."""

    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


def as_decimal(value: Decimal | str | int, field: str = "value") -> Decimal:
    """Parse an exact finite base-10 value; floats and exponents fail closed."""

    if isinstance(value, bool) or isinstance(value, float):
        raise CanonicalError(f"{field} must be an exact Decimal or plain decimal string")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, str) and _DECIMAL_RE.fullmatch(value):
        number = Decimal(value)
    else:
        raise CanonicalError(f"{field} is not a plain base-10 decimal")
    if not number.is_finite():
        raise CanonicalError(f"{field} must be finite")
    return number


def canonical_decimal(value: Decimal | str | int) -> str:
    """Encode a Decimal in the exact E0 plain canonical form."""

    number = as_decimal(value)
    if number.is_zero():
        return "0"
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def parse_utc(value: str, field: str = "timestamp") -> datetime:
    """Parse the required timezone-aware UTC timestamp representation."""

    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        raise CanonicalError(f"{field} must be YYYY-MM-DDTHH:MM:SS.ffffffZ")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise CanonicalError(f"{field} is not a valid UTC timestamp") from exc
    return parsed.replace(tzinfo=timezone.utc)


def format_utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise CanonicalError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            # Converting arbitrary keys to strings is forbidden: {1: ..., "1":
            # ...} must never silently collide.
            if not isinstance(key, str):
                raise CanonicalError("canonical JSON object keys must be strings")
            if key in output:
                raise CanonicalError(f"duplicate or colliding JSON key: {key!r}")
            output[key] = _json_value(item)
        return output
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, datetime):
        return format_utc(value)
    if isinstance(value, float):
        raise CanonicalError("binary float is forbidden in canonical JSON")
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise CanonicalError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Canonical UTF-8 JSON text (without the JSON-lines newline)."""

    try:
        return json.dumps(
            _json_value(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalError("value is not canonical JSON") from exc


def canonical_json_bytes(value: Any, *, newline: bool = False) -> bytes:
    suffix = "\n" if newline else ""
    return (canonical_json(value) + suffix).encode("utf-8")


def canonical_sha256(value: Any, *, newline: bool = False) -> str:
    return hashlib.sha256(canonical_json_bytes(value, newline=newline)).hexdigest()


def canonical_digest(value: Any) -> str:
    """Compatibility spelling for the frozen canonical SHA-256 operation."""

    return canonical_sha256(value)


def digest(value: Any) -> str:
    return canonical_sha256(value)


def sha256_digest(value: Any) -> str:
    return canonical_sha256(value)


def _reject_constant(value: str) -> None:
    raise CanonicalError(f"non-finite JSON number is forbidden: {value}")


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise CanonicalError(f"duplicate JSON object key: {key!r}")
        output[key] = value
    return output


def parse_json_bytes(raw: bytes, *, label: str = "JSON authority") -> Any:
    """Strictly parse UTF-8 JSON, rejecting BOMs, duplicates and non-finite values."""

    if not isinstance(raw, bytes):
        raise CanonicalError(f"{label} must be exact bytes")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise CanonicalError(f"{label} contains a forbidden UTF-8 BOM")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_object_no_duplicates,
            parse_float=Decimal,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalError(f"{label} is not strict UTF-8 JSON") from exc
    return freeze(value)


def quantize_step(
    value: Decimal | str | int,
    step: Decimal | str | int,
    *,
    restore_sign: bool = True,
) -> Decimal:
    """Round absolute quantity down to a rule step, then restore its sign."""

    number = as_decimal(value)
    quantum = as_decimal(step, "step")
    if quantum <= 0:
        raise CanonicalError("step must be positive")
    sign = Decimal(-1) if number < 0 and restore_sign else Decimal(1)
    units = (abs(number) / quantum).to_integral_value(rounding=ROUND_DOWN)
    return sign * units * quantum


def validate_instrument_order(
    *,
    quantity: Decimal | str | int,
    price: Decimal | str | int,
    rule: Mapping[str, Any],
) -> Decimal:
    """Quantize and validate one quantity against the frozen effective rule."""

    requested = as_decimal(quantity, "quantity")
    accounting_price = as_decimal(price, "price")
    if accounting_price <= 0:
        raise CanonicalError("price must be positive")
    tick = as_decimal(rule["tick"], "tick")
    if accounting_price != quantize_step(accounting_price, tick, restore_sign=False):
        raise CanonicalError("price is not aligned to tick")
    rounded = quantize_step(requested, rule["step"])
    absolute = abs(rounded)
    if absolute == 0:
        raise CanonicalError("quantity quantizes to zero")
    maximum = as_decimal(rule["maximum_quantity"], "maximum_quantity")
    if absolute > maximum:
        raise CanonicalError("quantity exceeds maximum_quantity")
    minimum_notional = as_decimal(rule["minimum_notional"], "minimum_notional")
    if absolute * accounting_price < minimum_notional:
        raise CanonicalError("quantity fails minimum_notional")
    return rounded


def solve_base_fee_sale(
    *,
    inventory: Decimal | str | int,
    fee_rate: Decimal | str | int,
    step: Decimal | str | int,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return the largest rule-stepped gross sale, its base fee, and exact dust."""

    available = as_decimal(inventory, "inventory")
    rate = as_decimal(fee_rate, "fee_rate")
    quantum = as_decimal(step, "step")
    if available < 0 or rate < 0 or quantum <= 0:
        raise CanonicalError("inventory/rate/step is outside its bound")
    # The exact continuous upper bound is inventory/(1+rate); stepping it down
    # yields the largest valid gross order without iterative rounding choices.
    gross = quantize_step(available / (Decimal(1) + rate), quantum, restore_sign=False)
    fee = gross * rate
    dust = available - gross - fee
    if dust < 0:
        raise CanonicalError("base-fee solver exceeded inventory")
    return gross, fee, dust


__all__ = [
    "CanonicalError",
    "FrozenDict",
    "as_decimal",
    "canonical_decimal",
    "canonical_digest",
    "canonical_json",
    "canonical_json_bytes",
    "canonical_sha256",
    "digest",
    "format_utc",
    "freeze",
    "parse_json_bytes",
    "parse_utc",
    "quantize_step",
    "solve_base_fee_sale",
    "sha256_digest",
    "thaw",
    "validate_instrument_order",
]
