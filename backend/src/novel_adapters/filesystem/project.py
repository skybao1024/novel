"""Filesystem implementation of project storage and the JSONL Canon Ledger."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from novel_application.errors import (
    LedgerReadError,
    ProjectAlreadyExistsError,
    ProjectBusyError,
    ProjectManifestInvalidError,
    ProjectNotFoundError,
    ProjectPathInvalidError,
)
from novel_core import CanonLedgerEntry, ProjectManifest


@dataclass(frozen=True, slots=True)
class ProjectLayout:
    root: Path

    @property
    def manifest(self) -> Path:
        return self.root / "novel.yaml"

    @property
    def ledger(self) -> Path:
        return self.root / "canon" / "ledger" / "canon.jsonl"

    @property
    def chapters(self) -> Path:
        return self.root / "structure" / "chapters"

    @property
    def chapter_memory(self) -> Path:
        return self.root / "memory" / "chapters"

    @property
    def scene_memory(self) -> Path:
        return self.root / "memory" / "scenes"

    @property
    def runtime(self) -> Path:
        return self.root / ".novel"

    @property
    def database(self) -> Path:
        return self.runtime / "project.sqlite"

    @property
    def runtime_tmp(self) -> Path:
        return self.runtime / "tmp"

    @property
    def intent(self) -> Path:
        return self.root / "intent"

    @property
    def bootstrap_runs(self) -> Path:
        return self.root / "runs" / "bootstrap"

    @property
    def intent_runs(self) -> Path:
        return self.root / "runs" / "intent"

    @property
    def writing_runs(self) -> Path:
        return self.root / "runs" / "writing"

    @property
    def publication_runs(self) -> Path:
        return self.root / "runs" / "publish"

    @property
    def write_lock(self) -> Path:
        return self.runtime / "locks" / "write.lock"


PROJECT_DIRECTORIES = (
    "intent",
    "canon/ledger",
    "structure/chapters",
    "manuscript",
    "memory/chapters",
    "memory/scenes",
    ".novel/locks",
    ".novel/tmp",
)


class FilesystemProjectStore:
    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    def initialize(self, manifest: ProjectManifest) -> None:
        if self.layout.manifest.exists():
            raise ProjectAlreadyExistsError(
                f"project manifest already exists: {self.layout.manifest}"
            )
        if self.layout.root.exists():
            if not self.layout.root.is_dir():
                raise ProjectPathInvalidError(
                    f"project path is not a directory: {self.layout.root}"
                )
            try:
                if any(self.layout.root.iterdir()):
                    raise ProjectAlreadyExistsError(
                        f"project directory is not empty: {self.layout.root}"
                    )
            except OSError as exc:
                raise ProjectPathInvalidError(
                    f"cannot inspect project directory: {self.layout.root}"
                ) from exc

        try:
            self.layout.root.mkdir(parents=True, exist_ok=True)
            for relative_directory in PROJECT_DIRECTORIES:
                (self.layout.root / relative_directory).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectPathInvalidError(
                f"cannot create project directory: {self.layout.root}"
            ) from exc

        _write_new_text(
            self.layout.manifest,
            json.dumps(
                manifest.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        _write_new_text(self.layout.ledger, "")

        gitignore = self.layout.root / ".gitignore"
        if not gitignore.exists():
            _write_new_text(gitignore, ".novel/\n")

    def load_manifest(self) -> ProjectManifest:
        if not self.layout.manifest.is_file():
            raise ProjectNotFoundError(f"missing project manifest: {self.layout.manifest}")
        try:
            return ProjectManifest.model_validate_json(self.layout.manifest.read_bytes())
        except ValidationError as exc:
            raise ProjectManifestInvalidError(
                f"invalid project manifest: {self.layout.manifest}"
            ) from exc
        except OSError as exc:
            raise ProjectManifestInvalidError(
                f"cannot read project manifest: {self.layout.manifest}"
            ) from exc

    def replace_manifest(self, manifest: ProjectManifest) -> None:
        current = self.load_manifest()
        if current.project_id != manifest.project_id:
            raise ProjectManifestInvalidError("replacement Manifest changes Project ID")
        payload = (
            json.dumps(
                manifest.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        _replace_bytes(self.layout.manifest, payload)


class FilesystemCanonLedgerStore:
    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    def read_entries(self) -> tuple[CanonLedgerEntry, ...]:
        path = self.layout.ledger
        if not path.is_file():
            raise ProjectNotFoundError(f"missing Canon Ledger: {path}")

        try:
            content = path.read_bytes()
        except OSError as exc:
            raise LedgerReadError(f"cannot read Canon Ledger: {path}") from exc

        if not content:
            return ()
        if not content.endswith(b"\n"):
            raise LedgerReadError("Canon Ledger ends with an incomplete JSONL record")

        entries: list[CanonLedgerEntry] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                raise LedgerReadError(f"blank Canon Ledger record at line {line_number}")
            try:
                entries.append(CanonLedgerEntry.model_validate_json(line))
            except ValidationError as exc:
                raise LedgerReadError(f"invalid Canon Ledger record at line {line_number}") from exc
        return tuple(entries)

    def append_entry(self, entry: CanonLedgerEntry) -> None:
        path = self.layout.ledger
        if not path.is_file():
            raise ProjectNotFoundError(f"missing Canon Ledger: {path}")

        payload = f"{entry.to_canonical_json()}\n".encode()
        try:
            file_descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
            try:
                view = memoryview(payload)
                while view:
                    written = os.write(file_descriptor, view)
                    view = view[written:]
                os.fsync(file_descriptor)
            finally:
                os.close(file_descriptor)
        except OSError as exc:
            raise LedgerReadError(f"cannot append Canon Ledger: {path}") from exc


class FilesystemProjectWriteLock:
    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    @contextmanager
    def acquire(self) -> Iterator[None]:
        lock_path = self.layout.write_lock
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        token = str(uuid4())
        payload = json.dumps(
            {"pid": os.getpid(), "token": token},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

        file_descriptor = _acquire_lock_file(lock_path)

        try:
            os.write(file_descriptor, payload)
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)

        try:
            yield
        finally:
            try:
                current = json.loads(lock_path.read_text(encoding="utf-8"))
                if current.get("token") == token:
                    lock_path.unlink()
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                pass


def _write_new_text(path: Path, content: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise ProjectAlreadyExistsError(f"refusing to overwrite: {path}") from exc


def _replace_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _acquire_lock_file(lock_path: Path) -> int:
    try:
        return os.open(
            lock_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as first_error:
        if not _remove_stale_lock(lock_path):
            raise ProjectBusyError(f"project write lock is held: {lock_path}") from first_error
    try:
        return os.open(
            lock_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise ProjectBusyError(f"project write lock is held: {lock_path}") from exc


def _remove_stale_lock(lock_path: Path) -> bool:
    """Remove only a well-formed lock whose recorded process no longer exists."""

    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        pid = payload.get("pid")
        token = payload.get("token")
        if not isinstance(pid, int) or pid <= 0 or not isinstance(token, str) or not token:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            current = json.loads(lock_path.read_text(encoding="utf-8"))
            if current == payload:
                lock_path.unlink()
                return True
        except (PermissionError, OSError):
            return False
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return False
    return False
