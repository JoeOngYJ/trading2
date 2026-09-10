from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from .tradingagents_capture import TradingAgentsCaptureAdapter, audit_pinned_upstream


def main() -> None:
    audit_pinned_upstream()
    adapter = TradingAgentsCaptureAdapter("postgresql://audit-only", Path("/tmp"), uuid4())
    adapter.install()
    adapter.assert_complete_installation()
    print("TradingAgents v0.3.1 capture and lifecycle surfaces verified")


if __name__ == "__main__":
    main()
