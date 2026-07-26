"""Read-only access to approved manuscript files."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from novel_application.errors import ManuscriptReadError, RevisionConflictError


class FilesystemManuscriptStore:
    """Read approved Markdown bytes without permitting project-root escape."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.manuscript_root = (self.root / "manuscript").resolve()

    def read_document(self, relative_path: str) -> bytes:
        path = self._resolve(relative_path)
        if not path.is_file():
            raise ManuscriptReadError(f"manuscript document does not exist: {relative_path}")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise ManuscriptReadError(f"cannot read manuscript document: {relative_path}") from exc

    def install_document(self, relative_path: str, content: bytes) -> None:
        path = self._resolve(relative_path)
        if path.exists():
            try:
                if path.is_file() and path.read_bytes() == content:
                    return
            except OSError as exc:
                raise ManuscriptReadError(
                    f"cannot inspect manuscript document: {relative_path}"
                ) from exc
            raise RevisionConflictError(
                f"refusing to replace different manuscript bytes: {relative_path}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            raise ManuscriptReadError(
                f"cannot install manuscript document: {relative_path}"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)

    def _resolve(self, relative_path: str) -> Path:
        lexical = Path(relative_path)
        if (
            lexical.is_absolute()
            or "\\" in relative_path
            or any(part in {"", ".", ".."} for part in lexical.parts)
            or not relative_path.startswith("manuscript/")
            or lexical.suffix.lower() != ".md"
        ):
            raise ManuscriptReadError(
                f"manuscript path must be a normalized project-relative .md path: {relative_path}"
            )

        path = (self.root / lexical).resolve()
        if not path.is_relative_to(self.manuscript_root):
            raise ManuscriptReadError(f"manuscript path escapes the project: {relative_path}")
        return path
