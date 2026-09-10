from __future__ import annotations

import json
from pathlib import Path


class PairMap:
    def __init__(self, mapping: dict[str, str]):
        if not mapping:
            raise ValueError("pair map cannot be empty")
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("TradingAgents symbols must map one-to-one to Freqtrade pairs")
        self._to_pair = mapping
        self._to_symbol = {pair: symbol for symbol, pair in mapping.items()}

    @classmethod
    def load(cls, path: Path) -> "PairMap":
        with path.open(encoding="utf-8") as handle:
            return cls(json.load(handle))

    def pair_for(self, symbol: str) -> str:
        try:
            return self._to_pair[symbol]
        except KeyError as exc:
            raise ValueError(f"unmapped TradingAgents symbol: {symbol}") from exc

    def symbol_for(self, pair: str) -> str:
        try:
            return self._to_symbol[pair]
        except KeyError as exc:
            raise ValueError(f"unmapped Freqtrade pair: {pair}") from exc

    @property
    def symbols(self) -> list[str]:
        return sorted(self._to_pair)

