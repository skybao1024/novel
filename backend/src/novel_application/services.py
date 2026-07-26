"""Project initialization, append, and projection rebuild workflows."""

from __future__ import annotations

from novel_application.errors import (
    LedgerConflictError,
    LedgerReadError,
    NavigationMemoryReadError,
    ProjectionOutOfDateError,
    ProjectNotFoundError,
    WorkflowStateError,
)
from novel_application.models import ProjectHealth, ProjectionStatus
from novel_application.ports import (
    CanonLedgerStore,
    CreationRunStateStore,
    ProjectionStore,
    ProjectStore,
    ProjectWriteLock,
)
from novel_core import CanonLedgerEntry, LedgerReplayError, ProjectManifest, replay_ledger


class ProjectService:
    """Coordinate Canon-first writes without knowing filesystem or SQLite details."""

    def __init__(
        self,
        *,
        projects: ProjectStore,
        ledger: CanonLedgerStore,
        projection: ProjectionStore,
        write_lock: ProjectWriteLock,
        runs: CreationRunStateStore | None = None,
    ) -> None:
        self._projects = projects
        self._ledger = ledger
        self._projection = projection
        self._write_lock = write_lock
        self._runs = runs

    def initialize(self, manifest: ProjectManifest) -> ProjectionStatus:
        self._projects.initialize(manifest)
        snapshot = replay_ledger(())
        return self._projection.replace(manifest, snapshot)

    def inspect_health(self) -> ProjectHealth:
        issues: list[str] = []
        snapshot = None
        try:
            snapshot = replay_ledger(self._ledger.read_entries())
            ledger_readable = True
        except (LedgerReadError, LedgerReplayError, ProjectNotFoundError) as exc:
            ledger_readable = False
            issues.append(str(exc))

        try:
            current = self._projection.status()
        except (NavigationMemoryReadError, OSError) as exc:
            current = None
            issues.append(str(exc))

        projection_current = (
            snapshot is not None
            and current is not None
            and current.canon_revision == snapshot.revision
            and current.last_ledger_sequence == snapshot.last_sequence
        )
        if not projection_current and not any(
            issue.startswith("SQLite projection") for issue in issues
        ):
            issues.append("SQLite projection is missing, invalid, or out of date")
        if self._runs is not None:
            try:
                issues.extend(self._runs.health_issues())
            except (NavigationMemoryReadError, WorkflowStateError, OSError) as exc:
                issues.append(str(exc))
        return ProjectHealth(
            ledger_readable=ledger_readable,
            projection_current=projection_current,
            storage_healthy=ledger_readable and projection_current and not issues,
            issues=tuple(issues),
        )

    def append(self, entry: CanonLedgerEntry) -> ProjectionStatus:
        with self._write_lock.acquire():
            manifest = self._projects.load_manifest()
            entries = self._ledger.read_entries()

            for existing in entries:
                if existing.ledger_entry_id != entry.ledger_entry_id:
                    continue
                if existing != entry:
                    raise LedgerConflictError(
                        f"ledger_entry_id {entry.ledger_entry_id} already has other content"
                    )
                snapshot = replay_ledger(entries)
                status = self._projection.status()
                if status is None or status.canon_revision != snapshot.revision:
                    return self._projection.replace(manifest, snapshot)
                return status

            snapshot = replay_ledger((*entries, entry))
            self._ledger.append_entry(entry)
            try:
                return self._projection.replace(manifest, snapshot)
            except Exception as exc:
                raise ProjectionOutOfDateError(snapshot.revision) from exc

    def rebuild_projection(self) -> ProjectionStatus:
        with self._write_lock.acquire():
            manifest = self._projects.load_manifest()
            snapshot = replay_ledger(self._ledger.read_entries())
            return self._projection.replace(manifest, snapshot)

    def ensure_projection_current(self) -> ProjectionStatus:
        manifest = self._projects.load_manifest()
        snapshot = replay_ledger(self._ledger.read_entries())
        current = self._projection.status()
        if (
            current is not None
            and current.canon_revision == snapshot.revision
            and current.last_ledger_sequence == snapshot.last_sequence
        ):
            return current

        with self._write_lock.acquire():
            snapshot = replay_ledger(self._ledger.read_entries())
            current = self._projection.status()
            if (
                current is not None
                and current.canon_revision == snapshot.revision
                and current.last_ledger_sequence == snapshot.last_sequence
            ):
                return current
            return self._projection.replace(manifest, snapshot)
