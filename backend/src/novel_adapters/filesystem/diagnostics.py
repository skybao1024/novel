"""Best-effort, application-local diagnostic records for CLI invocations."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

DIAGNOSTIC_SCHEMA_VERSION = "1.0.0"
DIAGNOSTIC_DIRECTORY = "diagnostics"
DIAGNOSTIC_FILE_PREFIX = "cli-"
DIAGNOSTIC_RETENTION_DAYS = 30


class DiagnosticOutcome(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


class DiagnosticRecord(BaseModel):
    """One sanitized CLI boundary observation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0.0"] = DIAGNOSTIC_SCHEMA_VERSION
    diagnostic_id: UUID
    protocol_version: str
    command: str
    phase: str
    outcome: DiagnosticOutcome
    exit_code: int = Field(ge=0)
    started_at: AwareDatetime
    completed_at: AwareDatetime
    duration_ms: int = Field(ge=0)
    project_id: UUID | None = None
    operation_ids: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    error_code: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    traceback: str | None = None


class DiagnosticRecordNotFoundError(LookupError):
    """Raised when an exact diagnostic ID is not present in retained logs."""


class DiagnosticLogWriteError(OSError):
    """Raised when a diagnostic record cannot be appended."""


class FilesystemDiagnosticLog:
    """Append and query sanitized, date-partitioned JSONL diagnostics."""

    def __init__(
        self,
        application_data_directory: Path,
        *,
        retention_days: int = DIAGNOSTIC_RETENTION_DAYS,
    ) -> None:
        if retention_days < 1:
            raise ValueError("diagnostic retention_days must be positive")
        self.directory = application_data_directory.expanduser().resolve() / DIAGNOSTIC_DIRECTORY
        self.retention_days = retention_days

    def append(self, record: DiagnosticRecord) -> None:
        payload = (
            json.dumps(
                record.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        path = self._path(record.completed_at.date())
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                written = os.write(descriptor, payload)
                if written != len(payload):
                    raise OSError("partial diagnostic record write")
            finally:
                os.close(descriptor)
            self._remove_expired_files(record.completed_at.date())
        except OSError as exc:
            raise DiagnosticLogWriteError(f"cannot append diagnostic log: {path}") from exc

    def list(
        self,
        *,
        limit: int = 50,
        project_id: UUID | None = None,
        outcome: DiagnosticOutcome | None = None,
    ) -> tuple[tuple[DiagnosticRecord, ...], tuple[str, ...]]:
        if not 1 <= limit <= 200:
            raise ValueError("diagnostic limit must be between 1 and 200")
        records, warnings = self._read_all()
        selected = (
            record
            for record in records
            if (project_id is None or record.project_id == project_id)
            and (outcome is None or record.outcome is outcome)
        )
        ordered = sorted(
            selected,
            key=lambda item: (item.completed_at, str(item.diagnostic_id)),
            reverse=True,
        )
        return tuple(ordered[:limit]), warnings

    def show(self, diagnostic_id: UUID) -> tuple[DiagnosticRecord, tuple[str, ...]]:
        records, warnings = self._read_all()
        for record in records:
            if record.diagnostic_id == diagnostic_id:
                return record, warnings
        raise DiagnosticRecordNotFoundError(f"diagnostic record not found: {diagnostic_id}")

    def _read_all(self) -> tuple[tuple[DiagnosticRecord, ...], tuple[str, ...]]:
        if not self.directory.is_dir():
            return (), ()
        records: list[DiagnosticRecord] = []
        warnings: list[str] = []
        for path in sorted(self.directory.glob(f"{DIAGNOSTIC_FILE_PREFIX}*.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                warnings.append(f"unreadable diagnostic log: {path.name}")
                continue
            for line_number, line in enumerate(lines, start=1):
                if not line:
                    continue
                try:
                    records.append(DiagnosticRecord.model_validate_json(line))
                except ValidationError:
                    warnings.append(f"invalid diagnostic record: {path.name}:{line_number}")
        return tuple(records), tuple(warnings)

    def _path(self, value: date) -> Path:
        return self.directory / f"{DIAGNOSTIC_FILE_PREFIX}{value.isoformat()}.jsonl"

    def _remove_expired_files(self, today: date) -> None:
        oldest_retained = today - timedelta(days=self.retention_days - 1)
        for path in self.directory.glob(f"{DIAGNOSTIC_FILE_PREFIX}*.jsonl"):
            value = _diagnostic_file_date(path)
            if value is not None and value < oldest_retained:
                path.unlink(missing_ok=True)


def _diagnostic_file_date(path: Path) -> date | None:
    stem = path.name.removeprefix(DIAGNOSTIC_FILE_PREFIX).removesuffix(".jsonl")
    try:
        return date.fromisoformat(stem)
    except ValueError:
        return None
