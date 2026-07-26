from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from novel_adapters.filesystem import (
    FilesystemCanonLedgerStore,
    FilesystemProjectStore,
    FilesystemProjectWriteLock,
)
from novel_adapters.sqlite import SQLiteProjectionStore
from novel_application import (
    LedgerReadError,
    ProjectBusyError,
    ProjectionOutOfDateError,
    ProjectService,
)
from novel_core import CanonLedgerEntry, CanonLedgerSnapshot, ProjectManifest


def project_manifest() -> ProjectManifest:
    return ProjectManifest(
        project_id=UUID("b0000000-0000-4000-8000-000000000001"),
        title="银戒身份谜案",
        language="zh-CN",
        minimum_core_version="0.1.0",
    )


def project_service(root: Path) -> ProjectService:
    return ProjectService(
        projects=FilesystemProjectStore(root),
        ledger=FilesystemCanonLedgerStore(root),
        projection=SQLiteProjectionStore(root),
        write_lock=FilesystemProjectWriteLock(root),
    )


def test_initialize_creates_versioned_project_layout(tmp_path: Path) -> None:
    root = tmp_path / "story"
    status = project_service(root).initialize(project_manifest())

    assert status.last_ledger_sequence == 0
    assert (root / "novel.yaml").is_file()
    assert (root / "canon" / "ledger" / "canon.jsonl").read_bytes() == b""
    assert (root / "intent").is_dir()
    assert (root / "structure" / "chapters").is_dir()
    assert (root / "memory" / "chapters").is_dir()
    assert (root / "memory" / "scenes").is_dir()
    assert not (root / "runs").exists()
    assert not (root / ".novel" / "cache").exists()
    assert (root / ".novel" / "project.sqlite").is_file()
    assert (root / ".gitignore").read_text(encoding="utf-8") == ".novel/\n"
    assert FilesystemProjectStore(root).load_manifest() == project_manifest()


def test_project_write_lock_returns_project_busy(tmp_path: Path) -> None:
    root = tmp_path / "story"
    FilesystemProjectStore(root).initialize(project_manifest())
    first = FilesystemProjectWriteLock(root)
    second = FilesystemProjectWriteLock(root)

    with first.acquire():
        with pytest.raises(ProjectBusyError):
            with second.acquire():
                pass
    assert not first.layout.write_lock.exists()


def test_project_write_lock_recovers_only_a_well_formed_dead_owner(tmp_path: Path) -> None:
    root = tmp_path / "story"
    FilesystemProjectStore(root).initialize(project_manifest())
    lock = FilesystemProjectWriteLock(root)
    lock.layout.write_lock.write_text(
        json.dumps({"pid": 999_999_999, "token": "dead-owner"}),
        encoding="utf-8",
    )

    with lock.acquire():
        assert lock.layout.write_lock.is_file()
    assert not lock.layout.write_lock.exists()


def test_ledger_rejects_incomplete_or_blank_jsonl(tmp_path: Path) -> None:
    root = tmp_path / "story"
    FilesystemProjectStore(root).initialize(project_manifest())
    ledger = FilesystemCanonLedgerStore(root)

    ledger.layout.ledger.write_text("{}", encoding="utf-8")
    with pytest.raises(LedgerReadError, match="incomplete"):
        ledger.read_entries()

    ledger.layout.ledger.write_text("\n", encoding="utf-8")
    with pytest.raises(LedgerReadError, match="blank"):
        ledger.read_entries()


def test_append_is_durable_and_idempotent(
    tmp_path: Path,
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    root = tmp_path / "story"
    service = project_service(root)
    service.initialize(project_manifest())

    first = service.append(ledger_entries[0])
    second = service.append(ledger_entries[1])
    repeated = service.append(ledger_entries[1])

    assert first.last_ledger_sequence == 1
    assert second.last_ledger_sequence == 2
    assert repeated == second
    assert FilesystemCanonLedgerStore(root).read_entries() == ledger_entries


def test_failed_projection_update_leaves_recoverable_canon(
    tmp_path: Path,
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    root = tmp_path / "story"
    real_projection = SQLiteProjectionStore(root)
    projection = _FailAfterEmptyProjection(real_projection)
    service = ProjectService(
        projects=FilesystemProjectStore(root),
        ledger=FilesystemCanonLedgerStore(root),
        projection=projection,
        write_lock=FilesystemProjectWriteLock(root),
    )
    service.initialize(project_manifest())

    with pytest.raises(ProjectionOutOfDateError):
        service.append(ledger_entries[0])

    assert FilesystemCanonLedgerStore(root).read_entries() == (ledger_entries[0],)
    recovered = project_service(root).ensure_projection_current()
    assert recovered.last_ledger_sequence == 1


class _FailAfterEmptyProjection:
    def __init__(self, delegate: SQLiteProjectionStore) -> None:
        self.delegate = delegate

    def replace(
        self,
        manifest: ProjectManifest,
        snapshot: CanonLedgerSnapshot,
    ):
        if snapshot.last_sequence:
            raise RuntimeError("simulated projection failure")
        return self.delegate.replace(manifest, snapshot)

    def status(self):
        return self.delegate.status()
