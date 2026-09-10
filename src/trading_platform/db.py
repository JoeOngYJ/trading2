from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from psycopg import Connection
from psycopg.rows import dict_row


@contextmanager
def connect(database_url: str) -> Iterator[Connection]:
    with Connection.connect(database_url, row_factory=dict_row) as connection:
        yield connection


def migrate(database_url: str, migrations_dir: Path = Path("/app/migrations")) -> None:
    scripts = sorted(migrations_dir.glob("*.sql"))
    if not scripts:
        raise RuntimeError(f"no migrations found in {migrations_dir}")
    with connect(database_url) as connection:
        connection.execute("SELECT pg_advisory_lock(728104219)")
        try:
            for script in scripts:
                connection.execute(script.read_text(encoding="utf-8"))
            connection.commit()
        finally:
            connection.execute("SELECT pg_advisory_unlock(728104219)")


def json_text(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)
