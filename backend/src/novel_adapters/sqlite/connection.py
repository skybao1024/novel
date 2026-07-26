"""SQLite connection policy for a local project database."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_database(
    database_path: Path,
    *,
    read_only: bool = False,
    wal: bool = True,
) -> sqlite3.Connection:
    if read_only:
        connection = sqlite3.connect(
            f"file:{database_path}?mode=ro",
            uri=True,
            timeout=5.0,
        )
    else:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database_path, timeout=5.0)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    if wal and not read_only:
        connection.execute("PRAGMA journal_mode = WAL")
    return connection
