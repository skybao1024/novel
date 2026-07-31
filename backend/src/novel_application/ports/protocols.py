"""Small protocols at the application/adapters boundary."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol
from uuid import UUID

from novel_application.models import (
    AssertionHistoryItem,
    EntityOccurrenceItem,
    EventOrder,
    ProjectionStatus,
    SummarySearchHit,
)
from novel_core import (
    AssertionScope,
    BootstrapRun,
    CanonLedgerEntry,
    CanonLedgerSnapshot,
    Chapter,
    ChapterSummary,
    ChapterTrace,
    ChapterTraceBackfill,
    Document,
    DraftRevision,
    Entity,
    Event,
    EventEdge,
    IntentContent,
    IntentRevision,
    ProjectCatalog,
    ProjectManifest,
    Proposition,
    Publication,
    RetrievedSource,
    Review,
    SourceRef,
    Volume,
    VolumeSummary,
    WritingSession,
)


class ProjectStore(Protocol):
    def initialize(self, manifest: ProjectManifest) -> None: ...

    def load_manifest(self) -> ProjectManifest: ...

    def replace_manifest(self, manifest: ProjectManifest) -> None: ...


class ProjectCatalogStore(Protocol):
    def load(self) -> ProjectCatalog: ...

    def replace(self, catalog: ProjectCatalog) -> None: ...


class ProjectCatalogWriteLock(Protocol):
    def acquire(self) -> AbstractContextManager[None]: ...


class ProjectWorkspace(Protocol):
    def normalize_path(self, project_path: str) -> str: ...

    def discover_path(self, start_path: str) -> str | None: ...

    def path_exists(self, project_path: str) -> bool: ...

    def manifest_exists(self, project_path: str) -> bool: ...

    def load_manifest(self, project_path: str) -> ProjectManifest: ...


class CanonLedgerStore(Protocol):
    def read_entries(self) -> tuple[CanonLedgerEntry, ...]: ...

    def append_entry(self, entry: CanonLedgerEntry) -> None: ...


class ProjectWriteLock(Protocol):
    def acquire(self) -> AbstractContextManager[None]: ...


class ManuscriptStore(Protocol):
    def read_document(self, relative_path: str) -> bytes: ...


class ManuscriptPublicationStore(ManuscriptStore, Protocol):
    def install_document(self, relative_path: str, content: bytes) -> None: ...

    def replace_document(
        self,
        relative_path: str,
        *,
        expected_revision: str,
        content: bytes,
    ) -> None: ...


class IntentStore(Protocol):
    def load(self) -> IntentContent | None: ...

    def replace(self, content: IntentContent) -> None: ...


class BootstrapRunStore(Protocol):
    def create(self, run: BootstrapRun) -> None: ...

    def load(self, bootstrap_id: UUID) -> BootstrapRun: ...

    def replace(self, run: BootstrapRun) -> None: ...


class IntentRevisionStore(Protocol):
    def create(self, revision: IntentRevision) -> None: ...

    def load(self, intent_revision_id: UUID) -> IntentRevision: ...

    def replace(self, revision: IntentRevision) -> None: ...


class WritingRunStore(Protocol):
    def create_session(self, session: WritingSession) -> None: ...

    def load_session(self, writing_session_id: UUID) -> WritingSession: ...

    def replace_session(self, session: WritingSession) -> None: ...

    def save_draft(self, draft: DraftRevision, content: bytes) -> None: ...

    def load_draft(
        self, writing_session_id: UUID, draft_revision: str
    ) -> tuple[DraftRevision, bytes]: ...

    def list_drafts(self, writing_session_id: UUID) -> tuple[DraftRevision, ...]: ...

    def save_review(self, review: Review) -> None: ...

    def load_review(self, writing_session_id: UUID, review_id: UUID) -> Review: ...

    def list_reviews(self, writing_session_id: UUID) -> tuple[Review, ...]: ...

    def save_retrieved_source(self, source: RetrievedSource) -> None: ...

    def list_retrieved_sources(
        self,
        writing_session_id: UUID,
    ) -> tuple[RetrievedSource, ...]: ...


class PublicationStore(Protocol):
    def create(self, publication: Publication) -> None: ...

    def load(self, publication_id: UUID) -> Publication: ...

    def replace(self, publication: Publication) -> None: ...


class ChapterTraceBackfillStore(Protocol):
    def create(self, backfill: ChapterTraceBackfill) -> None: ...

    def load(self, backfill_id: UUID) -> ChapterTraceBackfill: ...

    def replace(self, backfill: ChapterTraceBackfill) -> None: ...


class CreationRunStateStore(Protocol):
    def health_issues(self) -> tuple[str, ...]: ...


class NavigationSourceStore(Protocol):
    def save_volume(self, volume: Volume) -> None: ...

    def save_chapter_summary(self, summary: ChapterSummary) -> None: ...

    def save_volume_summary(self, summary: VolumeSummary) -> None: ...

    def save_chapter_trace(self, trace: ChapterTrace) -> None: ...


class ProjectionStore(Protocol):
    def replace(
        self,
        manifest: ProjectManifest,
        snapshot: CanonLedgerSnapshot,
    ) -> ProjectionStatus: ...

    def status(self) -> ProjectionStatus | None: ...


class ProjectionQueryPort(Protocol):
    def list_entities(self) -> tuple[Entity, ...]: ...

    def get_entity(self, entity_id: UUID) -> Entity | None: ...

    def find_entities_by_alias(self, alias_text: str) -> tuple[Entity, ...]: ...

    def get_document(self, document_id: UUID) -> Document | None: ...

    def get_chapter(self, chapter_id: UUID) -> Chapter | None: ...

    def get_event(self, event_id: UUID) -> Event | None: ...

    def get_source_ref(self, source_ref_id: UUID) -> SourceRef | None: ...

    def get_proposition(self, proposition_id: UUID) -> Proposition | None: ...

    def assertion_history(
        self,
        *,
        proposition_id: UUID | None = None,
        subject_entity_id: UUID | None = None,
        predicate: str | None = None,
        scope: AssertionScope | None = None,
        holder_entity_id: UUID | None = None,
    ) -> tuple[AssertionHistoryItem, ...]: ...

    def list_events(
        self,
        *,
        participant_entity_id: UUID | None = None,
        location_entity_id: UUID | None = None,
        source_chapter_id: UUID | None = None,
        order: EventOrder = EventOrder.NARRATIVE,
    ) -> tuple[Event, ...]: ...

    def event_edges(
        self,
        event_id: UUID,
        *,
        direction: str,
    ) -> tuple[EventEdge, ...]: ...

    def source_refs_for_event(self, event_id: UUID) -> tuple[SourceRef, ...]: ...

    def source_refs_for_chapter(self, chapter_id: UUID) -> tuple[SourceRef, ...]: ...


class NavigationQueryPort(Protocol):
    def list_volumes(self) -> tuple[Volume, ...]: ...

    def get_volume(self, volume_id: UUID) -> Volume | None: ...

    def volume_chapters(self, volume_id: UUID) -> tuple[tuple[Chapter, int], ...]: ...

    def get_volume_summary(
        self,
        volume_id: UUID,
    ) -> tuple[VolumeSummary, bool] | None: ...

    def get_chapter_summary(
        self,
        chapter_id: UUID,
    ) -> tuple[ChapterSummary, bool] | None: ...

    def get_chapter_trace(
        self,
        chapter_id: UUID,
    ) -> tuple[ChapterTrace, bool] | None: ...

    def entity_occurrences(
        self,
        entity_id: UUID,
        *,
        before_narrative_order: int,
    ) -> tuple[EntityOccurrenceItem, ...]: ...

    def search_summaries(
        self,
        query: str | None,
        *,
        entity_id: UUID | None,
        before_narrative_order: int,
        limit: int,
    ) -> tuple[SummarySearchHit, ...]: ...
