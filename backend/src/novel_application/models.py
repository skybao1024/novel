"""Typed results shared by application queries and storage adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from novel_core import (
    Assertion,
    ChangeSetOperation,
    Chapter,
    ChapterSummary,
    Document,
    ProjectCatalogEntry,
    ProjectManifest,
    Scene,
    SceneSummary,
    SourceRef,
)


class EventOrder(StrEnum):
    NARRATIVE = "narrative"
    STORY_ORDINAL = "story_ordinal"


@dataclass(frozen=True, slots=True)
class ProjectionStatus:
    canon_revision: str
    last_ledger_sequence: int


@dataclass(frozen=True, slots=True)
class ProjectHealth:
    ledger_readable: bool
    projection_current: bool
    storage_healthy: bool
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectResolution:
    manifest: ProjectManifest
    project_path: str
    catalog_entry: ProjectCatalogEntry | None
    catalog_path_matches: bool


@dataclass(frozen=True, slots=True)
class ProjectListItem:
    entry: ProjectCatalogEntry
    path_exists: bool


@dataclass(frozen=True, slots=True)
class ProjectCreationResult:
    entry: ProjectCatalogEntry
    manifest: ProjectManifest
    projection: ProjectionStatus


@dataclass(frozen=True, slots=True)
class ProjectRegistrationResult:
    entry: ProjectCatalogEntry
    path_updated: bool


@dataclass(frozen=True, slots=True)
class ProjectDetails:
    resolution: ProjectResolution
    health: ProjectHealth


@dataclass(frozen=True, slots=True)
class AssertionHistoryItem:
    assertion: Assertion
    introduced_sequence: int
    invalidating_operation: ChangeSetOperation | None = None
    invalidated_sequence: int | None = None


class SummaryRetrievalMethod(StrEnum):
    FTS5_TRIGRAM = "fts5_trigram"
    LITERAL = "literal"
    ENTITY_FILTER = "entity_filter"


@dataclass(frozen=True, slots=True)
class ChapterSummaryItem:
    chapter: Chapter
    summary: ChapterSummary | None
    stale: bool | None


@dataclass(frozen=True, slots=True)
class ChapterSceneItem:
    scene: Scene
    scene_number_in_chapter: int
    summary: SceneSummary | None
    stale: bool | None


@dataclass(frozen=True, slots=True)
class SummarySearchHit:
    summary: ChapterSummary | SceneSummary
    stale: bool
    retrieval_method: SummaryRetrievalMethod
    match_reason: str


@dataclass(frozen=True, slots=True)
class ExactSceneText:
    chapter: Chapter
    scene: Scene
    scene_number_in_chapter: int
    document: Document
    text: str
    source_refs: tuple[SourceRef, ...]

    @property
    def chapter_id(self) -> UUID:
        return self.chapter.chapter_id
