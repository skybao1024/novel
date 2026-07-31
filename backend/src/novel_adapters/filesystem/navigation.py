"""Reviewable Volume and navigation-memory files."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar
from uuid import UUID, uuid4

from pydantic import ValidationError

from novel_adapters.filesystem.project import ProjectLayout
from novel_application.errors import NavigationMemoryReadError
from novel_core import ChapterSummary, ChapterTrace, Volume, VolumeSummary
from novel_core._base import VersionedDomainModel

ModelType = TypeVar("ModelType", bound=VersionedDomainModel)


class _Hasher(Protocol):
    def update(self, content: bytes) -> None: ...

    def hexdigest(self) -> str: ...


@dataclass(frozen=True, slots=True)
class NavigationSourceSnapshot:
    """Validated file sources used to rebuild the SQLite memory projection."""

    volumes: tuple[Volume, ...]
    chapter_summaries: tuple[ChapterSummary, ...]
    volume_summaries: tuple[VolumeSummary, ...]
    chapter_traces: tuple[ChapterTrace, ...]
    revision: str


class FilesystemNavigationStore:
    """Load and atomically replace explicit JSON navigation sources."""

    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    def load_snapshot(self) -> NavigationSourceSnapshot:
        hasher = hashlib.sha256()
        volumes = self._load_models(
            self.layout.volumes,
            Volume,
            "volume_id",
            hasher,
        )
        chapter_summaries = self._load_models(
            self.layout.chapter_memory,
            ChapterSummary,
            "chapter_id",
            hasher,
        )
        volume_summaries = self._load_models(
            self.layout.volume_memory,
            VolumeSummary,
            "volume_id",
            hasher,
        )
        chapter_traces = self._load_models(
            self.layout.chapter_traces,
            ChapterTrace,
            "chapter_id",
            hasher,
        )
        return NavigationSourceSnapshot(
            volumes=volumes,
            chapter_summaries=chapter_summaries,
            volume_summaries=volume_summaries,
            chapter_traces=chapter_traces,
            revision=f"sha256:{hasher.hexdigest()}",
        )

    def save_volume(self, volume: Volume) -> None:
        self._replace_model(self.layout.volumes / f"{volume.volume_id}.json", volume)

    def save_chapter_summary(self, summary: ChapterSummary) -> None:
        self._replace_model(self.layout.chapter_memory / f"{summary.chapter_id}.json", summary)

    def save_volume_summary(self, summary: VolumeSummary) -> None:
        self._replace_model(
            self.layout.volume_memory / f"{summary.volume_id}.json",
            summary,
        )

    def save_chapter_trace(self, trace: ChapterTrace) -> None:
        self._replace_model(self.layout.chapter_traces / f"{trace.chapter_id}.json", trace)

    def _load_models(
        self,
        directory: Path,
        model: type[ModelType],
        id_field: str,
        hasher: _Hasher,
    ) -> tuple[ModelType, ...]:
        if not directory.is_dir():
            return ()
        loaded: list[ModelType] = []
        seen_ids: set[UUID] = set()
        for path in sorted(directory.glob("*.json")):
            try:
                content = path.read_bytes()
                item = model.model_validate_json(content)
            except (OSError, ValidationError) as exc:
                raise NavigationMemoryReadError(f"invalid navigation source file: {path}") from exc
            object_id = getattr(item, id_field)
            if path.stem != str(object_id):
                raise NavigationMemoryReadError(
                    f"navigation filename does not match {id_field}: {path}"
                )
            if object_id in seen_ids:
                raise NavigationMemoryReadError(
                    f"duplicate {id_field} in navigation sources: {object_id}"
                )
            seen_ids.add(object_id)
            relative_path = path.relative_to(self.layout.root).as_posix().encode("utf-8")
            hasher.update(relative_path)
            hasher.update(b"\0")
            hasher.update(content)
            hasher.update(b"\0")
            loaded.append(item)
        return tuple(loaded)

    @staticmethod
    def _replace_model(path: Path, model: VersionedDomainModel) -> None:
        payload = (
            json.dumps(
                model.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            raise NavigationMemoryReadError(
                f"cannot replace navigation source file: {path}"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)
