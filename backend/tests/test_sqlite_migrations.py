from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from novel_adapters.sqlite.migrations import (
    DEFAULT_MIGRATIONS,
    MigrationError,
    MigrationRunner,
)


def test_initial_migration_is_repeatable(tmp_path: Path) -> None:
    database = tmp_path / "project.sqlite"
    runner = MigrationRunner(database)

    applied = runner.apply(backup=False)
    repeated = runner.apply(backup=False)

    assert [migration.version for migration in applied] == [1, 2]
    assert repeated == ()
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
            )
        }
        assert {
            "chapters",
            "chapter_scenes",
            "navigation_summaries",
            "navigation_summaries_fts",
            "writing_sessions",
            "draft_revisions",
            "reviews",
            "publications",
        } <= tables
        assert {
            "candidate_changesets",
            "validation_findings",
            "text_chunks",
            "text_chunks_fts",
        }.isdisjoint(tables)
    finally:
        connection.close()


def test_modified_applied_migration_is_rejected(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    shutil.copytree(DEFAULT_MIGRATIONS, migrations)
    database = tmp_path / "project.sqlite"
    MigrationRunner(database, migrations_directory=migrations).apply(backup=False)

    initial = migrations / "0001_initial.sql"
    initial.write_text(
        initial.read_text(encoding="utf-8") + "\n-- modified\n",
        encoding="utf-8",
    )
    with pytest.raises(MigrationError, match="modified"):
        MigrationRunner(database, migrations_directory=migrations).apply(backup=False)


def test_failed_migration_rolls_back_and_upgrade_creates_backup(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    shutil.copytree(DEFAULT_MIGRATIONS, migrations)
    database = tmp_path / "project.sqlite"
    runner = MigrationRunner(database, migrations_directory=migrations)
    runner.apply(backup=False)

    bad = migrations / "0003_bad.sql"
    bad.write_text(
        "CREATE TABLE should_rollback(value TEXT) STRICT;\nINVALID SQL;\n",
        encoding="utf-8",
    )
    with pytest.raises(MigrationError):
        runner.apply()

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 2
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'should_rollback'"
            ).fetchone()
            is None
        )
    finally:
        connection.close()
    assert list(tmp_path.glob("project.sqlite.backup-v2*"))
