"""Atomic user-level Project Catalog storage and filesystem project location."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from novel_application.errors import (
    ProjectCatalogBusyError,
    ProjectCatalogReadError,
    ProjectCatalogWriteError,
    ProjectPathInvalidError,
)
from novel_core import ProjectCatalog, ProjectManifest

CATALOG_FILENAME = "projects.json"
CATALOG_LOCK_FILENAME = "projects.lock"
APP_DATA_ENVIRONMENT_VARIABLE = "NOVEL_APP_DATA_DIR"


def default_app_data_directory(
    *,
    environment: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """Return a dependency-free, cross-platform user application data directory."""

    current_environment = os.environ if environment is None else environment
    override = current_environment.get(APP_DATA_ENVIRONMENT_VARIABLE)
    if override:
        return _normalize_path(override)

    current_platform = sys.platform if platform is None else platform
    user_home = Path.home() if home is None else home
    if current_platform == "darwin":
        return (user_home / "Library" / "Application Support" / "Novel").resolve()
    if current_platform == "win32":
        local_app_data = current_environment.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else user_home / "AppData" / "Local"
        return (base / "Novel").resolve()

    xdg_data_home = current_environment.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else user_home / ".local" / "share"
    return (base / "novel").resolve()


class FilesystemProjectCatalogStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.expanduser().resolve()
        self.path = self.directory / CATALOG_FILENAME

    def load(self) -> ProjectCatalog:
        if not self.path.exists():
            return ProjectCatalog()
        if not self.path.is_file():
            raise ProjectCatalogReadError(f"Project Catalog is not a file: {self.path}")
        try:
            catalog = ProjectCatalog.model_validate_json(self.path.read_bytes())
            self._validate_normalized_paths(catalog)
            return catalog
        except (OSError, ValidationError, ProjectPathInvalidError) as exc:
            raise ProjectCatalogReadError(f"invalid Project Catalog: {self.path}") from exc

    def replace(self, catalog: ProjectCatalog) -> None:
        self._validate_normalized_paths(catalog)
        payload = (
            json.dumps(
                catalog.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode()
        temporary_path: Path | None = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=".projects-",
                suffix=".tmp",
                dir=self.directory,
            )
            temporary_path = Path(temporary_name)
            try:
                os.fchmod(file_descriptor, 0o600)
                view = memoryview(payload)
                while view:
                    written = os.write(file_descriptor, view)
                    view = view[written:]
                os.fsync(file_descriptor)
            finally:
                os.close(file_descriptor)
            os.replace(temporary_path, self.path)
            _fsync_directory(self.directory)
        except (OSError, ProjectPathInvalidError) as exc:
            raise ProjectCatalogWriteError(
                f"cannot atomically write Project Catalog: {self.path}"
            ) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _validate_normalized_paths(catalog: ProjectCatalog) -> None:
        for entry in catalog.projects:
            if _normalize_path(entry.project_path) != Path(entry.project_path):
                raise ProjectPathInvalidError(
                    f"Catalog project_path is not normalized and absolute: {entry.project_path}"
                )


class FilesystemProjectCatalogWriteLock:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.expanduser().resolve()
        self.path = self.directory / CATALOG_LOCK_FILENAME

    @contextmanager
    def acquire(self) -> Iterator[None]:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectCatalogWriteError(
                f"cannot create Project Catalog directory: {self.directory}"
            ) from exc

        token = str(uuid4())
        payload = json.dumps(
            {"pid": os.getpid(), "token": token},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        file_descriptor = _acquire_catalog_lock(self.path)
        try:
            os.write(file_descriptor, payload)
            os.fsync(file_descriptor)
        finally:
            os.close(file_descriptor)

        try:
            yield
        finally:
            try:
                current = json.loads(self.path.read_text(encoding="utf-8"))
                if current.get("token") == token:
                    self.path.unlink()
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                pass


class FilesystemProjectWorkspace:
    def normalize_path(self, project_path: str) -> str:
        return str(_normalize_path(project_path))

    def discover_path(self, start_path: str) -> str | None:
        start = _normalize_path(start_path)
        current = start if start.is_dir() else start.parent
        for candidate in (current, *current.parents):
            if (candidate / "novel.yaml").is_file():
                return str(candidate)
        return None

    def path_exists(self, project_path: str) -> bool:
        return _normalize_path(project_path).exists()

    def manifest_exists(self, project_path: str) -> bool:
        return (_normalize_path(project_path) / "novel.yaml").is_file()

    def load_manifest(self, project_path: str) -> ProjectManifest:
        from novel_adapters.filesystem.project import FilesystemProjectStore

        return FilesystemProjectStore(_normalize_path(project_path)).load_manifest()


def _normalize_path(value: str | Path) -> Path:
    try:
        raw = os.fspath(value)
        if not raw or "\x00" in raw:
            raise ValueError
        return Path(raw).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProjectPathInvalidError(f"invalid project path: {value}") from exc


def _acquire_catalog_lock(lock_path: Path) -> int:
    try:
        return os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as first_error:
        if not _remove_stale_lock(lock_path):
            raise ProjectCatalogBusyError(
                f"Project Catalog write lock is held: {lock_path}"
            ) from first_error
    try:
        return os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ProjectCatalogBusyError(f"Project Catalog write lock is held: {lock_path}") from exc


def _remove_stale_lock(lock_path: Path) -> bool:
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


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    file_descriptor = os.open(directory, flags)
    try:
        os.fsync(file_descriptor)
    finally:
        os.close(file_descriptor)
