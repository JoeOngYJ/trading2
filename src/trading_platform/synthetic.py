from __future__ import annotations

from .db import migrate
from .market_collector import collect_once
from .scheduler import schedule_once
from .settings import Settings


def main() -> None:
    settings = Settings()
    migrate(settings.database_url)
    snapshots = collect_once(settings)
    inserted = schedule_once(settings)
    print(f"collected {snapshots} snapshots; scheduled {inserted} synthetic analysis jobs")


if __name__ == "__main__":
    main()
