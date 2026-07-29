"""AI-first Chapter/Scene navigation and exact historical prose reads."""

from __future__ import annotations

from uuid import UUID

from novel_application.errors import (
    ChapterNotFoundError,
    ManuscriptReadError,
    SceneHistoryAccessError,
    SceneNotFoundError,
)
from novel_application.models import (
    ChapterSceneItem,
    ChapterSummaryItem,
    EntityLine,
    ExactSceneText,
    ProjectionStatus,
    SummarySearchHit,
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
    ChapterSummary,
    DocumentKind,
    Scene,
    SceneStatus,
    SceneSummary,
    SceneTrace,
    chapter_summary_is_stale,
    manuscript_revision,
    replay_ledger,
    scene_summary_is_stale,
    scene_trace_is_stale,
    validate_chapter_bindings,
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

    def chapters(self) -> tuple[ChapterSummaryItem, ...]:
        items: list[ChapterSummaryItem] = []
        for chapter in self._navigation.list_chapters():
            projected = self._navigation.get_chapter_summary(chapter.chapter_id)
            items.append(
                ChapterSummaryItem(
                    chapter=chapter,
                    summary=projected[0] if projected is not None else None,
                    stale=projected[1] if projected is not None else None,
                )
            )
        return tuple(items)

    def scenes(self, chapter_id: UUID) -> tuple[ChapterSceneItem, ...]:
        self._require_chapter(chapter_id)
        items: list[ChapterSceneItem] = []
        for scene, scene_number in self._navigation.chapter_scenes(chapter_id):
            projected = self._navigation.get_scene_summary(scene.scene_id)
            items.append(
                ChapterSceneItem(
                    scene=scene,
                    scene_number_in_chapter=scene_number,
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
        before_scene_id: UUID,
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
        target = self._canon.get_scene(before_scene_id)
        if target is None:
            raise SceneNotFoundError(f"target Scene does not exist: {before_scene_id}")
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

    def read_scene(
        self,
        *,
        chapter_id: UUID,
        scene_id: UUID,
        before_scene_id: UUID,
    ) -> ExactSceneText:
        target = self._canon.get_scene(before_scene_id)
        if target is None:
            raise SceneNotFoundError(f"target Scene does not exist: {before_scene_id}")
        return self.read_scene_before_order(
            chapter_id=chapter_id,
            scene_id=scene_id,
            before_narrative_order=target.narrative_order,
        )

    def read_scene_before_order(
        self,
        *,
        chapter_id: UUID,
        scene_id: UUID,
        before_narrative_order: int,
    ) -> ExactSceneText:
        chapter = self._require_chapter(chapter_id)
        chapter_scene = next(
            (
                (scene, number)
                for scene, number in self._navigation.chapter_scenes(chapter_id)
                if scene.scene_id == scene_id
            ),
            None,
        )
        if chapter_scene is None:
            if self._canon.get_scene(scene_id) is None:
                raise SceneNotFoundError(f"Scene does not exist: {scene_id}")
            raise SceneHistoryAccessError(
                f"Scene {scene_id} does not belong to Chapter {chapter_id}"
            )
        scene, scene_number = chapter_scene
        if scene.narrative_order >= before_narrative_order:
            raise SceneHistoryAccessError(
                "historical Scene must be before the target Scene in Narrative Order"
            )
        if scene.status is not SceneStatus.APPROVED:
            raise SceneHistoryAccessError("only approved Scenes can be read as history")

        document = self._canon.get_document(scene.source_document_id)
        if document is None:
            raise SceneHistoryAccessError(
                f"Scene source Document does not exist: {scene.source_document_id}"
            )
        if document.document_kind is not DocumentKind.MANUSCRIPT:
            raise SceneHistoryAccessError("Scene source is not an approved manuscript Document")
        if scene.revision != document.revision:
            raise SceneHistoryAccessError(
                "Scene revision does not match its approved manuscript Document"
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
            for source_ref in self._canon.source_refs_for_scene(scene.scene_id)
            if source_ref.document_id == document.document_id
            and source_ref.document_revision == document.revision
        )
        return ExactSceneText(
            chapter=chapter,
            scene=scene,
            scene_number_in_chapter=scene_number,
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

    def _require_chapter(self, chapter_id: UUID):
        chapter = self._navigation.get_chapter(chapter_id)
        if chapter is None:
            raise ChapterNotFoundError(f"Chapter does not exist: {chapter_id}")
        return chapter


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

    def save_chapter(self, chapter: Chapter) -> ProjectionStatus:
        with self._write_lock.acquire():
            chapters = {
                existing.chapter_id: existing for existing in self._navigation.list_chapters()
            }
            chapters[chapter.chapter_id] = chapter
            scene_ids = {
                scene_id for existing in chapters.values() for scene_id in existing.scene_ids
            }
            scenes: list[Scene] = []
            for scene_id in scene_ids:
                scene = self._canon.get_scene(scene_id)
                if scene is None:
                    raise SceneNotFoundError(f"Chapter references an unknown Scene: {scene_id}")
                scenes.append(scene)
            validate_chapter_bindings(tuple(chapters.values()), tuple(scenes))
            self._sources.save_chapter(chapter)
            return self._rebuild_projection()

    def save_scene_summary(self, summary: SceneSummary) -> ProjectionStatus:
        with self._write_lock.acquire():
            chapter = self._navigation.get_chapter(summary.chapter_id)
            if chapter is None:
                raise ChapterNotFoundError(
                    f"Scene Summary Chapter does not exist: {summary.chapter_id}"
                )
            scene = self._canon.get_scene(summary.scene_id)
            if scene is None:
                raise SceneNotFoundError(f"Scene Summary Scene does not exist: {summary.scene_id}")
            document = self._canon.get_document(summary.source_document_id)
            if document is None:
                raise SceneHistoryAccessError(
                    f"Scene Summary source Document does not exist: {summary.source_document_id}"
                )
            if scene_summary_is_stale(
                summary,
                chapter=chapter,
                scene=scene,
                document=document,
            ):
                raise SceneHistoryAccessError(
                    "new Scene Summary must bind the current approved Scene revision"
                )
            self._sources.save_scene_summary(summary)
            return self._rebuild_projection()

    def save_chapter_summary(self, summary: ChapterSummary) -> ProjectionStatus:
        with self._write_lock.acquire():
            chapter = self._navigation.get_chapter(summary.chapter_id)
            if chapter is None:
                raise ChapterNotFoundError(
                    f"Chapter Summary Chapter does not exist: {summary.chapter_id}"
                )
            scene_summaries: dict[UUID, SceneSummary] = {}
            for scene_id in chapter.scene_ids:
                projected = self._navigation.get_scene_summary(scene_id)
                if projected is None:
                    raise SceneHistoryAccessError(
                        f"Chapter Summary requires Scene Summary: {scene_id}"
                    )
                scene_summary, stale = projected
                if stale:
                    raise SceneHistoryAccessError(
                        f"Chapter Summary cannot consume stale Scene Summary: {scene_id}"
                    )
                scene_summaries[scene_id] = scene_summary
            if chapter_summary_is_stale(
                summary,
                chapter=chapter,
                scene_summaries=scene_summaries,
                stale_scene_ids=set(),
            ):
                raise SceneHistoryAccessError(
                    "new Chapter Summary dependencies do not match current Scene Summaries"
                )
            self._sources.save_chapter_summary(summary)
            return self._rebuild_projection()

    def save_scene_trace(self, trace: SceneTrace) -> ProjectionStatus:
        with self._write_lock.acquire():
            chapter = self._navigation.get_chapter(trace.chapter_id)
            if chapter is None:
                raise ChapterNotFoundError(
                    f"Scene Trace Chapter does not exist: {trace.chapter_id}"
                )
            scene = self._canon.get_scene(trace.scene_id)
            if scene is None:
                raise SceneNotFoundError(f"Scene Trace Scene does not exist: {trace.scene_id}")
            document = self._canon.get_document(trace.source_document_id)
            if document is None:
                raise SceneHistoryAccessError(
                    f"Scene Trace source Document does not exist: {trace.source_document_id}"
                )
            if scene_trace_is_stale(
                trace,
                chapter=chapter,
                scene=scene,
                document=document,
            ):
                raise SceneHistoryAccessError(
                    "new Scene Trace must bind the current approved Scene revision"
                )
            unknown_entities = tuple(
                occurrence.entity_id
                for occurrence in trace.entity_occurrences
                if self._canon.get_entity(occurrence.entity_id) is None
            )
            if unknown_entities:
                raise SceneHistoryAccessError(
                    "Scene Trace references unknown Entity IDs: "
                    + ", ".join(str(entity_id) for entity_id in unknown_entities)
                )
            self._sources.save_scene_trace(trace)
            return self._rebuild_projection()

    def _rebuild_projection(self) -> ProjectionStatus:
        manifest = self._projects.load_manifest()
        snapshot = replay_ledger(self._ledger.read_entries())
        return self._projection.replace(manifest, snapshot)
