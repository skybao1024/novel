"""AI-first Volume/Chapter navigation and exact historical prose reads."""

from __future__ import annotations

from uuid import UUID

from novel_application.errors import (
    ChapterHistoryAccessError,
    ChapterNotFoundError,
    ManuscriptReadError,
    VolumeNotFoundError,
)
from novel_application.models import (
    EntityLine,
    ExactChapterText,
    ProjectionStatus,
    SummarySearchHit,
    VolumeChapterItem,
    VolumeSummaryItem,
)
from novel_application.ports import (
    CanonLedgerStore,
    ManuscriptStore,
    NavigationQueryPort,
    NavigationSourceStore,
    ProjectionStore,
    ProjectStore,
    ProjectWriteLock,
)
from novel_application.queries import CanonQueryService
from novel_core import (
    Chapter,
    ChapterStatus,
    ChapterSummary,
    ChapterTrace,
    DocumentKind,
    Volume,
    VolumeSummary,
    chapter_summary_is_stale,
    chapter_trace_is_stale,
    manuscript_revision,
    replay_ledger,
    validate_volume_bindings,
    volume_summary_is_stale,
)


class NavigationMemoryService:
    """Expose navigation memory as hints and approved prose as authority."""

    def __init__(
        self,
        *,
        navigation: NavigationQueryPort,
        canon: CanonQueryService,
        manuscripts: ManuscriptStore,
    ) -> None:
        self._navigation = navigation
        self._canon = canon
        self._manuscripts = manuscripts

    def volumes(self) -> tuple[VolumeSummaryItem, ...]:
        items: list[VolumeSummaryItem] = []
        for volume in self._navigation.list_volumes():
            projected = self._navigation.get_volume_summary(volume.volume_id)
            items.append(
                VolumeSummaryItem(
                    volume=volume,
                    summary=projected[0] if projected is not None else None,
                    stale=projected[1] if projected is not None else None,
                )
            )
        return tuple(items)

    def chapters(self, volume_id: UUID) -> tuple[VolumeChapterItem, ...]:
        self._require_volume(volume_id)
        items: list[VolumeChapterItem] = []
        for chapter, chapter_number in self._navigation.volume_chapters(volume_id):
            projected = self._navigation.get_chapter_summary(chapter.chapter_id)
            items.append(
                VolumeChapterItem(
                    chapter=chapter,
                    chapter_number_in_volume=chapter_number,
                    summary=projected[0] if projected is not None else None,
                    stale=projected[1] if projected is not None else None,
                )
            )
        return tuple(items)

    def search_summaries(
        self,
        *,
        query: str | None,
        entity_id: UUID | None,
        before_chapter_id: UUID,
        limit: int = 20,
    ) -> tuple[SummarySearchHit, ...]:
        normalized = query.strip() if query is not None else None
        if normalized == "":
            normalized = None
        if not normalized and entity_id is None:
            raise ValueError("summary search requires --query, --entity, or both")
        if not 1 <= limit <= 100:
            raise ValueError("summary search limit must be between 1 and 100")
        if entity_id is not None and self._canon.get_entity(entity_id) is None:
            raise ValueError(f"entity does not exist: {entity_id}")
        target = self._canon.get_chapter(before_chapter_id)
        if target is None:
            raise ChapterNotFoundError(f"target Chapter does not exist: {before_chapter_id}")
        return self.search_summaries_before_order(
            query=normalized,
            entity_id=entity_id,
            before_narrative_order=target.narrative_order,
            limit=limit,
        )

    def search_summaries_before_order(
        self,
        *,
        query: str | None,
        entity_id: UUID | None,
        before_narrative_order: int,
        limit: int = 20,
    ) -> tuple[SummarySearchHit, ...]:
        normalized = query.strip() if query is not None else None
        if normalized == "":
            normalized = None
        if not normalized and entity_id is None:
            raise ValueError("summary search requires --query, --entity, or both")
        if not 1 <= limit <= 100:
            raise ValueError("summary search limit must be between 1 and 100")
        if entity_id is not None and self._canon.get_entity(entity_id) is None:
            raise ValueError(f"entity does not exist: {entity_id}")
        return self._navigation.search_summaries(
            normalized,
            entity_id=entity_id,
            before_narrative_order=before_narrative_order,
            limit=limit,
        )

    def read_chapter(
        self,
        *,
        volume_id: UUID,
        chapter_id: UUID,
        before_chapter_id: UUID,
    ) -> ExactChapterText:
        target = self._canon.get_chapter(before_chapter_id)
        if target is None:
            raise ChapterNotFoundError(f"target Chapter does not exist: {before_chapter_id}")
        return self.read_chapter_before_order(
            volume_id=volume_id,
            chapter_id=chapter_id,
            before_narrative_order=target.narrative_order,
        )

    def read_chapter_before_order(
        self,
        *,
        volume_id: UUID,
        chapter_id: UUID,
        before_narrative_order: int,
    ) -> ExactChapterText:
        result = self.read_approved_chapter(volume_id=volume_id, chapter_id=chapter_id)
        if result.chapter.narrative_order >= before_narrative_order:
            raise ChapterHistoryAccessError(
                "historical Chapter must be before the target Chapter in Narrative Order"
            )
        return result

    def read_approved_chapter(
        self,
        *,
        volume_id: UUID,
        chapter_id: UUID,
    ) -> ExactChapterText:
        volume = self._require_volume(volume_id)
        volume_chapter = next(
            (
                (chapter, number)
                for chapter, number in self._navigation.volume_chapters(volume_id)
                if chapter.chapter_id == chapter_id
            ),
            None,
        )
        if volume_chapter is None:
            if self._canon.get_chapter(chapter_id) is None:
                raise ChapterNotFoundError(f"Chapter does not exist: {chapter_id}")
            raise ChapterHistoryAccessError(
                f"Chapter {chapter_id} does not belong to Volume {volume_id}"
            )
        chapter, chapter_number = volume_chapter
        if chapter.status is not ChapterStatus.APPROVED:
            raise ChapterHistoryAccessError("only approved Chapters can be read as history")

        document = self._canon.get_document(chapter.source_document_id)
        if document is None:
            raise ChapterHistoryAccessError(
                f"Chapter source Document does not exist: {chapter.source_document_id}"
            )
        if document.document_kind is not DocumentKind.MANUSCRIPT:
            raise ChapterHistoryAccessError("Chapter source is not an approved manuscript Document")
        if chapter.revision != document.revision:
            raise ChapterHistoryAccessError(
                "Chapter revision does not match its approved manuscript Document"
            )

        content = self._manuscripts.read_document(document.relative_path)
        actual_revision = manuscript_revision(content)
        if actual_revision != document.revision:
            raise ManuscriptReadError(
                f"manuscript revision mismatch for {document.relative_path}: "
                f"approved={document.revision}, actual={actual_revision}"
            )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ManuscriptReadError(
                f"approved manuscript is not UTF-8: {document.relative_path}"
            ) from exc

        source_refs = tuple(
            source_ref
            for source_ref in self._canon.source_refs_for_chapter(chapter.chapter_id)
            if source_ref.document_id == document.document_id
            and source_ref.document_revision == document.revision
        )
        return ExactChapterText(
            volume=volume,
            chapter=chapter,
            chapter_number_in_volume=chapter_number,
            document=document,
            text=text,
            source_refs=source_refs,
        )

    def entity_line_before_order(
        self,
        *,
        entity_id: UUID,
        before_narrative_order: int,
    ) -> EntityLine:
        entity = self._canon.get_entity(entity_id)
        if entity is None:
            raise ValueError(f"entity does not exist: {entity_id}")
        return EntityLine(
            entity=entity,
            occurrences=self._navigation.entity_occurrences(
                entity_id,
                before_narrative_order=before_narrative_order,
            ),
        )

    def _require_volume(self, volume_id: UUID):
        volume = self._navigation.get_volume(volume_id)
        if volume is None:
            raise VolumeNotFoundError(f"Volume does not exist: {volume_id}")
        return volume


class NavigationMemoryWriter:
    """Validate and atomically replace non-Canon navigation source files."""

    def __init__(
        self,
        *,
        sources: NavigationSourceStore,
        navigation: NavigationQueryPort,
        canon: CanonQueryService,
        projects: ProjectStore,
        ledger: CanonLedgerStore,
        projection: ProjectionStore,
        write_lock: ProjectWriteLock,
    ) -> None:
        self._sources = sources
        self._navigation = navigation
        self._canon = canon
        self._projects = projects
        self._ledger = ledger
        self._projection = projection
        self._write_lock = write_lock

    def save_volume(self, volume: Volume) -> ProjectionStatus:
        with self._write_lock.acquire():
            volumes = {existing.volume_id: existing for existing in self._navigation.list_volumes()}
            volumes[volume.volume_id] = volume
            chapter_ids = {
                chapter_id for existing in volumes.values() for chapter_id in existing.chapter_ids
            }
            chapters: list[Chapter] = []
            for chapter_id in chapter_ids:
                chapter = self._canon.get_chapter(chapter_id)
                if chapter is None:
                    raise ChapterNotFoundError(
                        f"Volume references an unknown Chapter: {chapter_id}"
                    )
                chapters.append(chapter)
            validate_volume_bindings(tuple(volumes.values()), tuple(chapters))
            self._sources.save_volume(volume)
            return self._rebuild_projection()

    def save_chapter_summary(self, summary: ChapterSummary) -> ProjectionStatus:
        with self._write_lock.acquire():
            volume = self._navigation.get_volume(summary.volume_id)
            if volume is None:
                raise VolumeNotFoundError(
                    f"Chapter Summary Volume does not exist: {summary.volume_id}"
                )
            chapter = self._canon.get_chapter(summary.chapter_id)
            if chapter is None:
                raise ChapterNotFoundError(
                    f"Chapter Summary Chapter does not exist: {summary.chapter_id}"
                )
            document = self._canon.get_document(summary.source_document_id)
            if document is None:
                raise ChapterHistoryAccessError(
                    f"Chapter Summary source Document does not exist: {summary.source_document_id}"
                )
            if chapter_summary_is_stale(
                summary,
                volume=volume,
                chapter=chapter,
                document=document,
            ):
                raise ChapterHistoryAccessError(
                    "new Chapter Summary must bind the current approved Chapter revision"
                )
            self._sources.save_chapter_summary(summary)
            return self._rebuild_projection()

    def save_volume_summary(self, summary: VolumeSummary) -> ProjectionStatus:
        with self._write_lock.acquire():
            volume = self._navigation.get_volume(summary.volume_id)
            if volume is None:
                raise VolumeNotFoundError(
                    f"Volume Summary Volume does not exist: {summary.volume_id}"
                )
            chapter_summaries: dict[UUID, ChapterSummary] = {}
            for chapter_id in volume.chapter_ids:
                projected = self._navigation.get_chapter_summary(chapter_id)
                if projected is None:
                    raise ChapterHistoryAccessError(
                        f"Volume Summary requires Chapter Summary: {chapter_id}"
                    )
                chapter_summary, stale = projected
                if stale:
                    raise ChapterHistoryAccessError(
                        f"Volume Summary cannot consume stale Chapter Summary: {chapter_id}"
                    )
                chapter_summaries[chapter_id] = chapter_summary
            if volume_summary_is_stale(
                summary,
                volume=volume,
                chapter_summaries=chapter_summaries,
                stale_chapter_ids=set(),
            ):
                raise ChapterHistoryAccessError(
                    "new Volume Summary dependencies do not match current Chapter Summaries"
                )
            self._sources.save_volume_summary(summary)
            return self._rebuild_projection()

    def save_chapter_trace(self, trace: ChapterTrace) -> ProjectionStatus:
        with self._write_lock.acquire():
            volume = self._navigation.get_volume(trace.volume_id)
            if volume is None:
                raise VolumeNotFoundError(f"Chapter Trace Volume does not exist: {trace.volume_id}")
            chapter = self._canon.get_chapter(trace.chapter_id)
            if chapter is None:
                raise ChapterNotFoundError(
                    f"Chapter Trace Chapter does not exist: {trace.chapter_id}"
                )
            document = self._canon.get_document(trace.source_document_id)
            if document is None:
                raise ChapterHistoryAccessError(
                    f"Chapter Trace source Document does not exist: {trace.source_document_id}"
                )
            if chapter_trace_is_stale(
                trace,
                volume=volume,
                chapter=chapter,
                document=document,
            ):
                raise ChapterHistoryAccessError(
                    "new Chapter Trace must bind the current approved Chapter revision"
                )
            unknown_entities = tuple(
                occurrence.entity_id
                for occurrence in trace.entity_occurrences
                if self._canon.get_entity(occurrence.entity_id) is None
            )
            if unknown_entities:
                raise ChapterHistoryAccessError(
                    "Chapter Trace references unknown Entity IDs: "
                    + ", ".join(str(entity_id) for entity_id in unknown_entities)
                )
            self._sources.save_chapter_trace(trace)
            return self._rebuild_projection()

    def _rebuild_projection(self) -> ProjectionStatus:
        manifest = self._projects.load_manifest()
        snapshot = replay_ledger(self._ledger.read_entries())
        return self._projection.replace(manifest, snapshot)
