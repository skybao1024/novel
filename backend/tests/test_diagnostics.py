from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from novel_adapters.filesystem import (
    DiagnosticOutcome,
    DiagnosticRecord,
    FilesystemDiagnosticLog,
)


def _record(
    suffix: int,
    *,
    completed_at: datetime,
    project_id: UUID | None = None,
    outcome: DiagnosticOutcome = DiagnosticOutcome.SUCCESS,
) -> DiagnosticRecord:
    return DiagnosticRecord(
        diagnostic_id=UUID(f"90000000-0000-4000-8000-{suffix:012d}"),
        protocol_version="1.0",
        command="session context",
        phase="completed",
        outcome=outcome,
        exit_code=0 if outcome is DiagnosticOutcome.SUCCESS else 6,
        started_at=completed_at,
        completed_at=completed_at,
        duration_ms=12,
        project_id=project_id,
        operation_ids={"session_id": ("80000000-0000-4000-8000-000000000001",)},
        error_code=None if outcome is DiagnosticOutcome.SUCCESS else "storage_error",
        error_type=None if outcome is DiagnosticOutcome.SUCCESS else "OSError",
    )


def test_diagnostic_log_appends_filters_and_reads_exact_records(tmp_path: Path) -> None:
    project_id = UUID("70000000-0000-4000-8000-000000000001")
    log = FilesystemDiagnosticLog(tmp_path)
    success = _record(
        1,
        completed_at=datetime(2026, 7, 28, 1, tzinfo=UTC),
        project_id=project_id,
    )
    failure = _record(
        2,
        completed_at=datetime(2026, 7, 28, 2, tzinfo=UTC),
        project_id=project_id,
        outcome=DiagnosticOutcome.ERROR,
    )

    log.append(success)
    log.append(failure)

    selected, warnings = log.list(
        project_id=project_id,
        outcome=DiagnosticOutcome.ERROR,
    )
    assert warnings == ()
    assert selected == (failure,)
    loaded, warnings = log.show(success.diagnostic_id)
    assert warnings == ()
    assert loaded == success


def test_diagnostic_log_retention_removes_only_expired_partitions(tmp_path: Path) -> None:
    log = FilesystemDiagnosticLog(tmp_path, retention_days=2)
    expired = _record(1, completed_at=datetime(2026, 7, 26, 1, tzinfo=UTC))
    current = _record(2, completed_at=datetime(2026, 7, 28, 1, tzinfo=UTC))

    log.append(expired)
    log.append(current)

    paths = sorted((tmp_path / "diagnostics").glob("*.jsonl"))
    assert [path.name for path in paths] == ["cli-2026-07-28.jsonl"]
    records, warnings = log.list()
    assert warnings == ()
    assert records == (current,)


def test_invalid_diagnostic_line_is_reported_without_hiding_valid_records(
    tmp_path: Path,
) -> None:
    log = FilesystemDiagnosticLog(tmp_path)
    record = _record(1, completed_at=datetime(2026, 7, 28, 1, tzinfo=UTC))
    log.append(record)
    path = next((tmp_path / "diagnostics").glob("*.jsonl"))
    with path.open("a", encoding="utf-8") as stream:
        stream.write("{not-json}\n")

    records, warnings = log.list()

    assert records == (record,)
    assert warnings == (f"invalid diagnostic record: {path.name}:2",)
