"""Typed results shared by application queries and storage adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from novel_core import (
    Assertion,
    ChangeSetOperation,
    Chapter,
    ChapterEntityOccurrence,
    ChapterSummary,
    ChapterTrace,
    Document,
    DraftEntityMatchCandidate,
    Entity,
    ProjectCatalogEntry,
    ProjectManifest,
    SourceRef,
    Volume,
    VolumeSummary,
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
class VolumeSummaryItem:
    volume: Volume
    summary: VolumeSummary | None
    stale: bool | None


@dataclass(frozen=True, slots=True)
class VolumeChapterItem:
    chapter: Chapter
    chapter_number_in_volume: int
    summary: ChapterSummary | None
    stale: bool | None


@dataclass(frozen=True, slots=True)
class SummarySearchHit:
    summary: VolumeSummary | ChapterSummary
    stale: bool
    retrieval_method: SummaryRetrievalMethod
    match_reason: str


@dataclass(frozen=True, slots=True)
class ExactChapterText:
    volume: Volume
    chapter: Chapter
    chapter_number_in_volume: int
    document: Document
    text: str
    source_refs: tuple[SourceRef, ...]

    @property
    def volume_id(self) -> UUID:
        return self.volume.volume_id


@dataclass(frozen=True, slots=True)
class EntityOccurrenceItem:
    volume: Volume
    chapter: Chapter
    chapter_trace: ChapterTrace
    occurrence: ChapterEntityOccurrence
    stale: bool


@dataclass(frozen=True, slots=True)
class EntityLine:
    entity: Entity
    occurrences: tuple[EntityOccurrenceItem, ...]


@dataclass(frozen=True, slots=True)
class ChapterTraceBackfillSource:
    project_id: UUID
    base_canon_revision: str
    volume: Volume
    chapter: Chapter
    document: Document
    text: str
    exact_candidates: tuple[DraftEntityMatchCandidate, ...]
    registry_entities: tuple[Entity, ...]
    candidate_entities: tuple[Entity, ...]
    current_trace: ChapterTrace | None
    current_trace_stale: bool | None
    current_trace_digest: str | None

    @property
    def source_revision(self) -> str:
        return self.document.revision
