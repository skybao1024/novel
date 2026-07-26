"""Numbered, checksummed SQL migrations without an ORM."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import sysconfig
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from novel_adapters.sqlite.connection import connect_database

MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]{4})_(?P<name>[a-z0-9_]+)\.sql$")
SOURCE_MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
INSTALLED_MIGRATIONS = Path(sysconfig.get_path("data")) / "novel" / "migrations"
DEFAULT_MIGRATIONS = SOURCE_MIGRATIONS if SOURCE_MIGRATIONS.is_dir() else INSTALLED_MIGRATIONS


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str
    sql: str


class MigrationError(RuntimeError):
    pass


class MigrationRunner:
    def __init__(
        self,
        database_path: Path,
        *,
        migrations_directory: Path = DEFAULT_MIGRATIONS,
    ) -> None:
        self.database_path = database_path
        self.migrations_directory = migrations_directory

    def discover(self) -> tuple[Migration, ...]:
        migrations: list[Migration] = []
        seen_versions: set[int] = set()
        for path in sorted(self.migrations_directory.glob("*.sql")):
            match = MIGRATION_NAME.fullmatch(path.name)
            if match is None:
                raise MigrationError(f"invalid migration filename: {path.name}")
            version = int(match.group("version"))
            if version in seen_versions:
                raise MigrationError(f"duplicate migration version: {version}")
            sql = path.read_text(encoding="utf-8")
            migrations.append(
                Migration(
                    version=version,
                    name=match.group("name"),
                    path=path,
                    checksum=hashlib.sha256(sql.encode()).hexdigest(),
                    sql=sql,
                )
            )
            seen_versions.add(version)
        return tuple(migrations)

    def pending(self) -> tuple[Migration, ...]:
        migrations = self.discover()
        if not self.database_path.exists() or self.database_path.stat().st_size == 0:
            return migrations
        with connect_database(self.database_path, wal=False) as connection:
            applied = _applied_migrations(connection)
        _validate_applied(applied, migrations)
        return tuple(migration for migration in migrations if migration.version not in applied)

    def apply(self, *, backup: bool = True) -> tuple[Migration, ...]:
        migrations = self.discover()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect_database(self.database_path, wal=False)
        try:
            applied = _applied_migrations(connection)
            _validate_applied(applied, migrations)
            pending = tuple(
                migration for migration in migrations if migration.version not in applied
            )
            if not pending:
                return ()

            if backup and applied:
                self._backup(connection, max(applied))

            for migration in pending:
                self._apply_one(connection, migration)
            return pending
        finally:
            connection.close()

    def _backup(self, source: sqlite3.Connection, current_version: int) -> Path:
        backup_path = self.database_path.with_name(
            f"{self.database_path.name}.backup-v{current_version}"
        )
        if backup_path.exists():
            backup_path = self.database_path.with_name(
                f"{self.database_path.name}.backup-v{current_version}-"
                f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
            )
        destination = sqlite3.connect(backup_path)
        try:
            source.backup(destination)
        finally:
            destination.close()
        return backup_path

    @staticmethod
    def _apply_one(connection: sqlite3.Connection, migration: Migration) -> None:
        applied_at = datetime.now(UTC).isoformat()
        try:
            connection.executescript(f"BEGIN IMMEDIATE;\n{migration.sql}")
            connection.execute(
                """
                INSERT INTO schema_migrations(version, name, checksum, applied_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    applied_at,
                ),
            )
            connection.execute(f"PRAGMA user_version = {migration.version}")
            connection.commit()
        except sqlite3.Error as exc:
            if connection.in_transaction:
                connection.rollback()
            raise MigrationError(f"migration {migration.path.name} failed: {exc}") from exc


def _applied_migrations(connection: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    exists = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'schema_migrations'
        """
    ).fetchone()
    if exists is None:
        return {}
    return {
        row["version"]: (row["name"], row["checksum"])
        for row in connection.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        )
    }


def _validate_applied(
    applied: dict[int, tuple[str, str]],
    available: tuple[Migration, ...],
) -> None:
    available_by_version = {migration.version: migration for migration in available}
    for version, (name, checksum) in applied.items():
        migration = available_by_version.get(version)
        if migration is None:
            raise MigrationError(f"applied migration {version:04d}_{name} is missing")
        if migration.name != name or migration.checksum != checksum:
            raise MigrationError(f"applied migration {version:04d}_{name} was modified")
