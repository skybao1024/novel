"""Approved Bootstrap, Intent, Session, Draft, Review, and Publish use cases."""

from __future__ import annotations

import difflib
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from novel_application.errors import (
    ApprovalMismatchError,
    ChapterNotFoundError,
    ProjectNotBootstrappedError,
    PublicationRecoveryRequiredError,
    RevisionConflictError,
    SceneNotFoundError,
    TraceBackfillRecoveryRequiredError,
    WorkflowStateError,
)
from novel_application.memory import NavigationMemoryService
from novel_application.models import (
    ChapterSceneItem,
    ChapterSummaryItem,
    EntityLine,
    ExactSceneText,
    SceneTraceBackfillSource,
    SummarySearchHit,
)
from novel_application.ports import (
    BootstrapRunStore,
    CanonLedgerStore,
    IntentRevisionStore,
    IntentStore,
    ManuscriptPublicationStore,
    NavigationQueryPort,
    NavigationSourceStore,
    ProjectionStore,
    ProjectStore,
    ProjectWriteLock,
    PublicationStore,
    SceneTraceBackfillStore,
    WritingRunStore,
)
from novel_application.queries import CanonQueryService
from novel_core import (
    Approval,
    BootstrapContent,
    BootstrapDraft,
    BootstrapEntityResolution,
    BootstrapRun,
    BootstrapStatus,
    CanonLedgerEntry,
    Chapter,
    ChapterSummary,
    ContinuitySceneStatus,
    ContinuityStatus,
    CreationContext,
    Document,
    DocumentKind,
    DocumentLedgerRecord,
    DraftEntityCandidates,
    DraftEntityMatchCandidate,
    DraftRevision,
    Entity,
    EntityLedgerRecord,
    EntityMention,
    EntityProminence,
    EntityResolutionStatus,
    IntentContent,
    IntentRevision,
    IntentRevisionStatus,
    ProjectStatus,
    Publication,
    PublicationPlan,
    PublicationStatus,
    RetrievalKind,
    RetrievedSource,
    Review,
    ReviewRecommendation,
    Scene,
    SceneEntityOccurrence,
    SceneLedgerRecord,
    SceneStatus,
    SceneSummary,
    SceneSummaryDependency,
    SceneTrace,
    SceneTraceBackfill,
    SceneTraceBackfillPlan,
    SceneTraceBackfillStatus,
    SceneTraceDraft,
    SourceRefLedgerRecord,
    StoryTime,
    StoryTimeKind,
    WritingSession,
    WritingSessionStatus,
    approval_digest,
    chapter_heading,
    chapter_summary_is_stale,
    intent_revision,
    manuscript_revision,
    replay_ledger,
    scene_summary_digest,
    scene_trace_digest,
)
from novel_core.canon.ledger import LedgerRecord

Clock = Callable[[], datetime]
IdFactory = Callable[[], UUID]
NARRATIVE_ORDER_STEP = 1_000_000


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BootstrapService:
    def __init__(
        self,
        *,
        projects: ProjectStore,
        ledger: CanonLedgerStore,
        projection: ProjectionStore,
        intent: IntentStore,
        runs: BootstrapRunStore,
        write_lock: ProjectWriteLock,
        new_id: IdFactory = uuid4,
        clock: Clock = _utc_now,
    ) -> None:
        self._projects = projects
        self._ledger = ledger
        self._projection = projection
        self._intent = intent
        self._runs = runs
        self._write_lock = write_lock
        self._new_id = new_id
        self._clock = clock

    def start(self) -> BootstrapRun:
        manifest = self._projects.load_manifest()
        if manifest.status is not ProjectStatus.NOT_BOOTSTRAPPED:
            raise WorkflowStateError("project is already bootstrapped")
        snapshot = replay_ledger(self._ledger.read_entries())
        current_intent = self._intent.load()
        if current_intent is not None:
            raise WorkflowStateError("empty project already contains formal Intent Canon")
        run = BootstrapRun(
            bootstrap_id=self._new_id(),
            project_id=manifest.project_id,
            base_canon_revision=snapshot.revision,
            base_intent_revision=intent_revision(None),
            revision=0,
            status=BootstrapStatus.DRAFTING,
            created_at=self._clock(),
        )
        self._runs.create(run)
        return run

    def save(self, bootstrap_id: UUID, draft: BootstrapDraft) -> BootstrapRun:
        run = self._runs.load(bootstrap_id)
        if run.status in {BootstrapStatus.APPROVED, BootstrapStatus.APPLIED}:
            raise WorkflowStateError("approved Bootstrap content is immutable")
        manifest = self._projects.load_manifest()
        if manifest.project_id != run.project_id:
            raise WorkflowStateError("Bootstrap belongs to another Project")
        current = self._intent.load()
        if intent_revision(current) != run.base_intent_revision:
            raise RevisionConflictError("formal Intent changed after Bootstrap started")
        existing_ids = (
            {
                resolution.temporary_name: resolution.entity.entity_id
                for resolution in run.content.entity_resolutions
            }
            if run.content is not None
            else {}
        )
        content = BootstrapContent(
            intent=draft.intent,
            entity_resolutions=tuple(
                BootstrapEntityResolution(
                    temporary_name=entity_draft.temporary_name,
                    entity=Entity(
                        entity_id=(
                            existing_ids[entity_draft.temporary_name]
                            if entity_draft.temporary_name in existing_ids
                            else self._new_id()
                        ),
                        entity_type=entity_draft.entity_type,
                        display_name=entity_draft.display_name,
                        created_revision=run.base_canon_revision,
                    ),
                )
                for entity_draft in draft.entity_drafts
            ),
            initial_goal=draft.initial_goal,
            unresolved_questions=draft.unresolved_questions,
        )
        content_digest = (
            f"sha256:{hashlib.sha256(content.to_canonical_json().encode()).hexdigest()}"
        )
        diff = _intent_diff(current, content.intent)
        protected = {
            "bootstrap_id": str(run.bootstrap_id),
            "project_id": str(run.project_id),
            "base_canon_revision": run.base_canon_revision,
            "base_intent_revision": run.base_intent_revision,
            "content": content.model_dump(mode="json"),
            "content_digest": content_digest,
            "intent_diff": diff,
        }
        saved = BootstrapRun(
            bootstrap_id=run.bootstrap_id,
            project_id=run.project_id,
            base_canon_revision=run.base_canon_revision,
            base_intent_revision=run.base_intent_revision,
            revision=run.revision + 1,
            status=BootstrapStatus.PREPARED,
            content=content,
            content_digest=content_digest,
            intent_diff=diff,
            approval_digest=approval_digest("bootstrap", protected),
            created_at=run.created_at,
        )
        self._runs.replace(saved)
        return saved

    def inspect(self, bootstrap_id: UUID) -> BootstrapRun:
        return self._runs.load(bootstrap_id)

    def approve(self, bootstrap_id: UUID, digest: str) -> BootstrapRun:
        run = self._runs.load(bootstrap_id)
        if run.status is not BootstrapStatus.PREPARED:
            raise WorkflowStateError("only a prepared Bootstrap can be approved")
        if digest != run.approval_digest:
            raise ApprovalMismatchError("Bootstrap approval digest does not match")
        approved = run.model_copy(
            update={
                "status": BootstrapStatus.APPROVED,
                "approval": Approval(
                    operation_id=run.bootstrap_id,
                    approval_digest=digest,
                    approved_at=self._clock(),
                ),
            }
        )
        self._runs.replace(approved)
        return approved

    def apply(self, bootstrap_id: UUID) -> BootstrapRun:
        with self._write_lock.acquire():
            run = self._runs.load(bootstrap_id)
            if run.status is BootstrapStatus.APPLIED:
                return run
            if run.status is not BootstrapStatus.APPROVED or run.content is None:
                raise WorkflowStateError("Bootstrap must be approved before apply")
            manifest = self._projects.load_manifest()
            if manifest.project_id != run.project_id:
                raise WorkflowStateError("Bootstrap belongs to another Project")
            entries = self._ledger.read_entries()
            snapshot = replay_ledger(entries)
            existing = next(
                (entry for entry in entries if entry.ledger_entry_id == run.bootstrap_id),
                None,
            )
            if existing is None and snapshot.revision != run.base_canon_revision:
                raise RevisionConflictError("Canon changed after Bootstrap started")
            current_intent = self._intent.load()
            current_intent_revision = intent_revision(current_intent)
            candidate_revision = intent_revision(run.content.intent)
            if current_intent_revision not in {run.base_intent_revision, candidate_revision}:
                raise RevisionConflictError("Intent changed after Bootstrap started")

            entry = None
            if run.content.entity_resolutions:
                assert run.approval is not None
                entry = CanonLedgerEntry(
                    ledger_sequence=len(entries) + 1,
                    ledger_entry_id=run.bootstrap_id,
                    base_revision=run.base_canon_revision,
                    approved_at=run.approval.approved_at,
                    records=tuple(
                        EntityLedgerRecord(value=resolution.entity)
                        for resolution in run.content.entity_resolutions
                    ),
                )
                if existing is None:
                    snapshot = replay_ledger((*entries, entry))
                elif existing != entry:
                    raise RevisionConflictError("Bootstrap Ledger entry has different content")
                else:
                    snapshot = replay_ledger(entries)

            self._intent.replace(run.content.intent)
            if entry is not None and existing is None:
                self._ledger.append_entry(entry)
            ready_manifest = manifest.model_copy(update={"status": ProjectStatus.READY})
            self._projects.replace_manifest(ready_manifest)
            self._projection.replace(ready_manifest, snapshot)
            applied = run.model_copy(
                update={"status": BootstrapStatus.APPLIED, "applied_at": self._clock()}
            )
            self._runs.replace(applied)
            return applied


class IntentService:
    def __init__(
        self,
        *,
        projects: ProjectStore,
        intent: IntentStore,
        revisions: IntentRevisionStore,
        write_lock: ProjectWriteLock,
        new_id: IdFactory = uuid4,
        clock: Clock = _utc_now,
    ) -> None:
        self._projects = projects
        self._intent = intent
        self._revisions = revisions
        self._write_lock = write_lock
        self._new_id = new_id
        self._clock = clock

    def show(self) -> tuple[IntentContent, str]:
        _require_ready(self._projects.load_manifest())
        content = self._intent.load()
        if content is None:
            raise WorkflowStateError("bootstrapped Project has no Intent Canon")
        return content, intent_revision(content)

    def prepare(self, candidate: IntentContent) -> IntentRevision:
        manifest = self._projects.load_manifest()
        _require_ready(manifest)
        current, base_revision = self.show()
        candidate_revision = intent_revision(candidate)
        if candidate_revision == base_revision:
            raise WorkflowStateError("Intent candidate does not change formal Intent")
        diff = _intent_diff(current, candidate)
        revision_id = self._new_id()
        protected = {
            "intent_revision_id": str(revision_id),
            "project_id": str(manifest.project_id),
            "base_intent_revision": base_revision,
            "candidate": candidate.model_dump(mode="json"),
            "candidate_revision": candidate_revision,
            "intent_diff": diff,
        }
        revision = IntentRevision(
            intent_revision_id=revision_id,
            project_id=manifest.project_id,
            base_intent_revision=base_revision,
            candidate=candidate,
            candidate_revision=candidate_revision,
            intent_diff=diff,
            approval_digest=approval_digest("intent_revision", protected),
            status=IntentRevisionStatus.PREPARED,
            created_at=self._clock(),
        )
        self._revisions.create(revision)
        return revision

    def inspect(self, intent_revision_id: UUID) -> IntentRevision:
        return self._revisions.load(intent_revision_id)

    def approve(self, intent_revision_id: UUID, digest: str) -> IntentRevision:
        revision = self._revisions.load(intent_revision_id)
        if revision.status is not IntentRevisionStatus.PREPARED:
            raise WorkflowStateError("only a prepared Intent Revision can be approved")
        if digest != revision.approval_digest:
            raise ApprovalMismatchError("Intent approval digest does not match")
        approved = revision.model_copy(
            update={
                "status": IntentRevisionStatus.APPROVED,
                "approval": Approval(
                    operation_id=revision.intent_revision_id,
                    approval_digest=digest,
                    approved_at=self._clock(),
                ),
            }
        )
        self._revisions.replace(approved)
        return approved

    def apply(self, intent_revision_id: UUID) -> IntentRevision:
        with self._write_lock.acquire():
            revision = self._revisions.load(intent_revision_id)
            return self._apply_under_lock(revision)

    def apply_approved_under_lock(self, intent_revision_id: UUID) -> IntentRevision:
        return self._apply_under_lock(self._revisions.load(intent_revision_id))

    def _apply_under_lock(self, revision: IntentRevision) -> IntentRevision:
        if revision.status is IntentRevisionStatus.APPLIED:
            return revision
        if revision.status is not IntentRevisionStatus.APPROVED:
            raise WorkflowStateError("Intent Revision must be approved before apply")
        manifest = self._projects.load_manifest()
        if manifest.project_id != revision.project_id:
            raise WorkflowStateError("Intent Revision belongs to another Project")
        current = self._intent.load()
        current_revision = intent_revision(current)
        if current_revision == revision.candidate_revision:
            pass
        elif current_revision == revision.base_intent_revision:
            self._intent.replace(revision.candidate)
        else:
            raise RevisionConflictError("formal Intent no longer matches the revision base")
        applied = revision.model_copy(
            update={"status": IntentRevisionStatus.APPLIED, "applied_at": self._clock()}
        )
        self._revisions.replace(applied)
        return applied


class WritingSessionService:
    def __init__(
        self,
        *,
        projects: ProjectStore,
        ledger: CanonLedgerStore,
        intent: IntentStore,
        navigation: NavigationQueryPort,
        canon: CanonQueryService,
        runs: WritingRunStore,
        new_id: IdFactory = uuid4,
        clock: Clock = _utc_now,
    ) -> None:
        self._projects = projects
        self._ledger = ledger
        self._intent = intent
        self._navigation = navigation
        self._canon = canon
        self._runs = runs
        self._new_id = new_id
        self._clock = clock

    def start(
        self,
        *,
        author_goal: str,
        target_story_time: StoryTime,
        chapter_id: UUID | None,
        new_chapter_number: int | None,
        new_chapter_title: str | None,
        before_scene_id: UUID | None,
        after_scene_id: UUID | None,
        creative_constraints: tuple[str, ...] = (),
        pov_entity_id: UUID | None = None,
        location_entity_id: UUID | None = None,
    ) -> WritingSession:
        manifest = self._projects.load_manifest()
        _require_ready(manifest)
        content = self._intent.load()
        if content is None:
            raise WorkflowStateError("ready Project has no Intent Canon")
        snapshot = replay_ledger(self._ledger.read_entries())
        chapter = self._resolve_target_chapter(
            chapter_id=chapter_id,
            new_chapter_number=new_chapter_number,
            new_chapter_title=new_chapter_title,
        )
        narrative_order = self._target_order(
            before_scene_id=before_scene_id,
            after_scene_id=after_scene_id,
            target_chapter_id=chapter.chapter_id if chapter is not None else chapter_id,
        )
        target_chapter_id = chapter.chapter_id if chapter is not None else self._new_id()
        target_scene_id = self._new_id()
        session = WritingSession(
            writing_session_id=self._new_id(),
            project_id=manifest.project_id,
            target_scene_id=target_scene_id,
            target_document_id=self._new_id(),
            target_document_path=f"manuscript/{target_scene_id}.md",
            target_chapter_id=target_chapter_id,
            target_chapter_number=(
                chapter.chapter_number if chapter is not None else int(new_chapter_number)
            ),
            target_chapter_title=(chapter.title if chapter is not None else str(new_chapter_title)),
            required_chapter_heading=(
                None
                if chapter is not None
                else chapter_heading(
                    language=manifest.language,
                    chapter_number=int(new_chapter_number),
                    title=str(new_chapter_title),
                )
            ),
            target_narrative_order=narrative_order,
            target_story_time=target_story_time,
            pov_entity_id=pov_entity_id,
            location_entity_id=location_entity_id,
            before_scene_id=before_scene_id,
            after_scene_id=after_scene_id,
            base_canon_revision=snapshot.revision,
            base_intent_revision=intent_revision(content),
            author_goal=author_goal,
            creative_constraints=creative_constraints,
            status=WritingSessionStatus.OPEN,
            created_at=self._clock(),
        )
        self._runs.create_session(session)
        return session

    def show(self, writing_session_id: UUID) -> WritingSession:
        return self._runs.load_session(writing_session_id)

    def context(self, writing_session_id: UUID) -> CreationContext:
        session = self._runs.load_session(writing_session_id)
        content = self._intent.load()
        if content is None:
            raise WorkflowStateError("Project has no formal Intent Canon")
        if intent_revision(content) != session.base_intent_revision:
            raise RevisionConflictError("formal Intent changed after Session start")
        chapter = self._navigation.get_chapter(session.target_chapter_id)
        previous_summary = None
        if session.before_scene_id is not None:
            projected = self._navigation.get_scene_summary(session.before_scene_id)
            previous_summary = projected[0] if projected is not None else None
        continuity_scenes = self._continuity_scenes(session)
        return CreationContext(
            project_id=session.project_id,
            writing_session_id=session.writing_session_id,
            author_goal=session.author_goal,
            creative_constraints=session.creative_constraints,
            target_scene_id=session.target_scene_id,
            target_chapter_id=session.target_chapter_id,
            target_narrative_order=session.target_narrative_order,
            required_chapter_heading=session.required_chapter_heading,
            before_scene_id=session.before_scene_id,
            after_scene_id=session.after_scene_id,
            base_canon_revision=session.base_canon_revision,
            base_intent_revision=session.base_intent_revision,
            intent=content,
            chapter=chapter,
            previous_scene_summary=previous_summary,
            previous_scene_text_available=session.before_scene_id is not None,
            continuity_chapter_id=(continuity_scenes[0].chapter_id if continuity_scenes else None),
            continuity_scene_ids=tuple(scene.scene_id for scene in continuity_scenes),
            important_entities=self._canon.list_entities(),
            query_capabilities=(
                "session continuity-status",
                "memory chapters",
                "memory scenes",
                "memory search-summaries",
                "memory read-scene",
                "memory entity-line",
                "draft entity-candidates",
                "resolve entity",
                "query character",
                "query event-chain",
            ),
        )

    def continuity_status(self, writing_session_id: UUID) -> ContinuityStatus:
        session = self._runs.load_session(writing_session_id)
        continuity_scenes = self._continuity_scenes(session)
        retrieved = self._runs.list_retrieved_sources(writing_session_id)
        scene_statuses = tuple(
            ContinuitySceneStatus(
                chapter_id=scene.chapter_id,
                scene_id=scene.scene_id,
                document_id=scene.source_document_id,
                document_revision=scene.revision,
                narrative_order=scene.narrative_order,
                retrieved_source_ids=tuple(
                    source.retrieved_source_id
                    for source in retrieved
                    if source.retrieval_kind is RetrievalKind.EXACT_SCENE
                    and source.chapter_id == scene.chapter_id
                    and source.scene_id == scene.scene_id
                    and source.document_id == scene.source_document_id
                    and source.document_revision == scene.revision
                ),
                satisfied=any(
                    source.retrieval_kind is RetrievalKind.EXACT_SCENE
                    and source.chapter_id == scene.chapter_id
                    and source.scene_id == scene.scene_id
                    and source.document_id == scene.source_document_id
                    and source.document_revision == scene.revision
                    for source in retrieved
                ),
            )
            for scene in continuity_scenes
        )
        missing_scene_ids = tuple(scene.scene_id for scene in scene_statuses if not scene.satisfied)
        return ContinuityStatus(
            writing_session_id=writing_session_id,
            continuity_chapter_id=(continuity_scenes[0].chapter_id if continuity_scenes else None),
            required_scenes=scene_statuses,
            missing_scene_ids=missing_scene_ids,
            satisfied=not missing_scene_ids,
        )

    def require_continuity(self, writing_session_id: UUID) -> ContinuityStatus:
        status = self.continuity_status(writing_session_id)
        if not status.satisfied:
            missing = ", ".join(str(scene_id) for scene_id in status.missing_scene_ids)
            raise WorkflowStateError("Draft requires exact reads for continuity Scenes: " + missing)
        return status

    def require_draft_format(self, writing_session_id: UUID, text: str) -> None:
        session = self._runs.load_session(writing_session_id)
        required = session.required_chapter_heading
        if required is None:
            return
        lines = text.splitlines()
        first_line = lines[0] if lines else ""
        if first_line != required:
            raise WorkflowStateError("new Chapter Draft must begin with exact heading: " + required)

    def close(self, writing_session_id: UUID) -> WritingSession:
        session = self._runs.load_session(writing_session_id)
        return self.close_under_lock(session)

    def close_under_lock(self, session: WritingSession) -> WritingSession:
        if session.status is WritingSessionStatus.CLOSED:
            return session
        closed = session.model_copy(
            update={"status": WritingSessionStatus.CLOSED, "closed_at": self._clock()}
        )
        self._runs.replace_session(closed)
        return closed

    def _continuity_scenes(self, session: WritingSession) -> tuple[Scene, ...]:
        if session.before_scene_id is None:
            return ()
        previous_scene = self._canon.get_scene(session.before_scene_id)
        if previous_scene is None:
            raise SceneNotFoundError(f"before Scene does not exist: {session.before_scene_id}")
        if previous_scene.chapter_id is None:
            raise WorkflowStateError("before Scene is not assigned to a Chapter")
        scenes = tuple(
            sorted(
                (
                    scene
                    for scene, _scene_number in self._navigation.chapter_scenes(
                        previous_scene.chapter_id
                    )
                    if scene.status is SceneStatus.APPROVED
                    and scene.narrative_order < session.target_narrative_order
                ),
                key=lambda scene: scene.narrative_order,
            )
        )
        if previous_scene.scene_id not in {scene.scene_id for scene in scenes}:
            raise WorkflowStateError(
                "before Scene is not an approved Scene before the Session boundary"
            )
        return scenes

    def _resolve_target_chapter(
        self,
        *,
        chapter_id: UUID | None,
        new_chapter_number: int | None,
        new_chapter_title: str | None,
    ) -> Chapter | None:
        new_values = new_chapter_number is not None or new_chapter_title is not None
        if chapter_id is not None and new_values:
            raise ValueError("choose an existing Chapter or a new Chapter, not both")
        if chapter_id is not None:
            chapter = self._navigation.get_chapter(chapter_id)
            if chapter is None:
                raise ChapterNotFoundError(f"Chapter does not exist: {chapter_id}")
            return chapter
        if new_chapter_number is None or new_chapter_title is None:
            raise ValueError("new Chapter requires number and title")
        if any(
            chapter.chapter_number == new_chapter_number
            for chapter in self._navigation.list_chapters()
        ):
            raise RevisionConflictError(f"Chapter number already exists: {new_chapter_number}")
        return None

    def _target_order(
        self,
        *,
        before_scene_id: UUID | None,
        after_scene_id: UUID | None,
        target_chapter_id: UUID | None,
    ) -> int:
        scenes = sorted(
            (
                scene
                for chapter in self._navigation.list_chapters()
                for scene, _number in self._navigation.chapter_scenes(chapter.chapter_id)
            ),
            key=lambda scene: scene.narrative_order,
        )
        by_id = {scene.scene_id: scene for scene in scenes}
        before = by_id.get(before_scene_id) if before_scene_id is not None else None
        after = by_id.get(after_scene_id) if after_scene_id is not None else None
        if before_scene_id is not None and before is None:
            raise SceneNotFoundError(f"before Scene does not exist: {before_scene_id}")
        if after_scene_id is not None and after is None:
            raise SceneNotFoundError(f"after Scene does not exist: {after_scene_id}")
        if before is None and after is None:
            if scenes:
                raise WorkflowStateError("non-empty novel requires an explicit Scene boundary")
            return NARRATIVE_ORDER_STEP
        if before is not None and after is not None:
            if before.narrative_order >= after.narrative_order:
                raise WorkflowStateError("before Scene must precede after Scene")
            between = [
                scene
                for scene in scenes
                if before.narrative_order < scene.narrative_order < after.narrative_order
            ]
            if between:
                raise WorkflowStateError("Session boundaries must be adjacent")
            if target_chapter_id is not None and (
                before.chapter_id != target_chapter_id or after.chapter_id != target_chapter_id
            ):
                raise WorkflowStateError("insertion boundaries must belong to target Chapter")
            gap = after.narrative_order - before.narrative_order
            if gap <= 1:
                raise WorkflowStateError("no stable Narrative Order slot remains between Scenes")
            return before.narrative_order + gap // 2
        if before is not None:
            if scenes[-1].scene_id != before.scene_id:
                raise WorkflowStateError(
                    "an omitted after boundary means append after the last Scene"
                )
            return before.narrative_order + NARRATIVE_ORDER_STEP
        assert after is not None
        if scenes[0].scene_id != after.scene_id:
            raise WorkflowStateError(
                "an omitted before boundary means insert before the first Scene"
            )
        if after.narrative_order <= 1:
            raise WorkflowStateError(
                "no stable Narrative Order slot remains before the first Scene"
            )
        return max(1, after.narrative_order // 2)


class SessionNavigationService:
    """Apply one saved Session boundary and record every returned source."""

    def __init__(
        self,
        *,
        sessions: WritingRunStore,
        memory: NavigationMemoryService,
        canon: CanonQueryService,
        new_id: IdFactory = uuid4,
        clock: Clock = _utc_now,
    ) -> None:
        self._sessions = sessions
        self._memory = memory
        self._canon = canon
        self._new_id = new_id
        self._clock = clock

    def chapters(self, session_id: UUID) -> tuple[ChapterSummaryItem, ...]:
        session = self._open(session_id)
        items = tuple(
            item
            for item in self._memory.chapters()
            if item.summary is None
            or max(
                (
                    scene.narrative_order
                    for scene_item in self._memory.scenes(item.chapter.chapter_id)
                    for scene in (scene_item.scene,)
                ),
                default=0,
            )
            < session.target_narrative_order
        )
        for item in items:
            if item.summary is not None:
                self._record(
                    session,
                    RetrievalKind.CHAPTER_SUMMARY,
                    chapter_id=item.chapter.chapter_id,
                    reason="Session Chapter navigation",
                )
        return items

    def scenes(self, session_id: UUID, chapter_id: UUID) -> tuple[ChapterSceneItem, ...]:
        session = self._open(session_id)
        items = tuple(
            item
            for item in self._memory.scenes(chapter_id)
            if item.scene.narrative_order < session.target_narrative_order
        )
        for item in items:
            if item.summary is not None:
                self._record(
                    session,
                    RetrievalKind.SCENE_SUMMARY,
                    chapter_id=chapter_id,
                    scene_id=item.scene.scene_id,
                    document_id=item.scene.source_document_id,
                    document_revision=item.scene.revision,
                    reason="Session Scene navigation",
                )
        return items

    def search(
        self,
        session_id: UUID,
        *,
        query: str | None,
        entity_id: UUID | None,
        limit: int,
    ) -> tuple[SummarySearchHit, ...]:
        session = self._open(session_id)
        hits = self._memory.search_summaries_before_order(
            query=query,
            entity_id=entity_id,
            before_narrative_order=session.target_narrative_order,
            limit=limit,
        )
        for hit in hits:
            if isinstance(hit.summary, ChapterSummary):
                self._record(
                    session,
                    RetrievalKind.CHAPTER_SUMMARY,
                    chapter_id=hit.summary.chapter_id,
                    reason=hit.match_reason,
                )
            else:
                self._record(
                    session,
                    RetrievalKind.SCENE_SUMMARY,
                    chapter_id=hit.summary.chapter_id,
                    scene_id=hit.summary.scene_id,
                    document_id=hit.summary.source_document_id,
                    document_revision=hit.summary.source_revision,
                    reason=hit.match_reason,
                )
        return hits

    def read(self, session_id: UUID, *, chapter_id: UUID, scene_id: UUID) -> ExactSceneText:
        session = self._open(session_id)
        result = self._memory.read_scene_before_order(
            chapter_id=chapter_id,
            scene_id=scene_id,
            before_narrative_order=session.target_narrative_order,
        )
        self._record(
            session,
            RetrievalKind.EXACT_SCENE,
            chapter_id=chapter_id,
            scene_id=scene_id,
            document_id=result.document.document_id,
            document_revision=result.document.revision,
            reason="Exact approved Scene read for Writing Session",
        )
        return result

    def entity_line(self, session_id: UUID, entity_id: UUID) -> EntityLine:
        session = self._open(session_id)
        result = self._memory.entity_line_before_order(
            entity_id=entity_id,
            before_narrative_order=session.target_narrative_order,
        )
        for item in result.occurrences:
            self._record(
                session,
                RetrievalKind.SCENE_TRACE,
                chapter_id=item.chapter.chapter_id,
                scene_id=item.scene.scene_id,
                document_id=item.scene_trace.source_document_id,
                document_revision=item.scene_trace.source_revision,
                reason=f"Entity occurrence line for {entity_id}",
            )
        return result

    def validate_canon_scene_ids(
        self,
        session_id: UUID,
        scene_ids: tuple[UUID, ...],
    ) -> WritingSession:
        session = self._open(session_id)
        for scene_id in scene_ids:
            scene = self._canon.get_scene(scene_id)
            if scene is None:
                raise SceneNotFoundError(f"Canon query Scene does not exist: {scene_id}")
            if scene.narrative_order >= session.target_narrative_order:
                raise WorkflowStateError(
                    "Session Canon query cannot cross its Narrative Order boundary"
                )
        return session

    def record_canon_query(
        self,
        session_id: UUID,
        *,
        source_refs,
        reason: str,
    ) -> tuple[RetrievedSource, ...]:
        session = self._open(session_id)
        refs = tuple(source_refs)
        if not refs:
            return (
                self._record(
                    session,
                    RetrievalKind.CANON_QUERY,
                    reason=reason,
                ),
            )
        return tuple(
            self._record(
                session,
                RetrievalKind.CANON_QUERY,
                scene_id=source_ref.scene_id,
                document_id=source_ref.document_id,
                document_revision=source_ref.document_revision,
                reason=reason,
            )
            for source_ref in refs
        )

    def _open(self, session_id: UUID) -> WritingSession:
        session = self._sessions.load_session(session_id)
        if session.status is not WritingSessionStatus.OPEN:
            raise WorkflowStateError("Writing Session is closed")
        return session

    def _record(
        self,
        session: WritingSession,
        kind: RetrievalKind,
        *,
        reason: str,
        chapter_id: UUID | None = None,
        scene_id: UUID | None = None,
        document_id: UUID | None = None,
        document_revision: str | None = None,
    ) -> RetrievedSource:
        source = RetrievedSource(
            retrieved_source_id=self._new_id(),
            writing_session_id=session.writing_session_id,
            retrieval_kind=kind,
            chapter_id=chapter_id,
            scene_id=scene_id,
            document_id=document_id,
            document_revision=document_revision,
            retrieval_reason=reason,
            retrieved_at=self._clock(),
        )
        self._sessions.save_retrieved_source(source)
        return source


class EntityResolutionService:
    """Recall visible exact-name candidates and materialize reviewed Scene Traces."""

    def __init__(
        self,
        *,
        ledger: CanonLedgerStore,
        runs: WritingRunStore,
    ) -> None:
        self._ledger = ledger
        self._runs = runs

    def draft_candidates(
        self,
        writing_session_id: UUID,
        draft_revision: str,
    ) -> DraftEntityCandidates:
        session = self._open_session(writing_session_id)
        draft, content = self._runs.load_draft(writing_session_id, draft_revision)
        if manuscript_revision(content) != draft.content_digest:
            raise RevisionConflictError("Draft bytes do not match Draft metadata")
        text = content.decode("utf-8")
        entries = self._ledger.read_entries()
        snapshot = replay_ledger(entries)
        names, _entities = self._visible_identity_names(session, entries, snapshot)
        return DraftEntityCandidates(
            writing_session_id=writing_session_id,
            draft_revision=draft_revision,
            matches=self._exact_matches(text, names),
        )

    def resolve_existing(
        self,
        alias_text: str,
        *,
        writing_session_id: UUID,
    ) -> tuple[Entity, ...]:
        session = self._open_session(writing_session_id)
        entries = self._ledger.read_entries()
        snapshot = replay_ledger(entries)
        names, entities = self._visible_identity_names(session, entries, snapshot)
        entity_ids = names.get(alias_text, ())
        return tuple(entities[entity_id] for entity_id in entity_ids)

    def materialize(
        self,
        *,
        session: WritingSession,
        draft_revision: str,
        manuscript: bytes,
        draft: SceneTraceDraft,
        chapter: Chapter,
        scene: Scene,
        document: Document,
        new_id: IdFactory,
    ) -> tuple[SceneTrace, tuple[Entity, ...]]:
        entries = self._ledger.read_entries()
        snapshot = replay_ledger(entries)
        if snapshot.revision != session.base_canon_revision:
            raise RevisionConflictError("Canon changed after Writing Session start")
        names, entities = self._visible_identity_names(session, entries, snapshot)
        return self._materialize(
            source_revision=draft_revision,
            manuscript=manuscript,
            draft=draft,
            chapter=chapter,
            scene=scene,
            document=document,
            snapshot=snapshot,
            names=names,
            available_entity_ids=set(entities),
            unknown_entity_label="outside the Session boundary",
            new_id=new_id,
        )

    def approved_scene_candidates(
        self,
        text: str,
        *,
        story_time: StoryTime,
    ) -> tuple[DraftEntityMatchCandidate, ...]:
        snapshot = replay_ledger(self._ledger.read_entries())
        names, _entities = self._all_identity_names(snapshot, story_time)
        return self._exact_matches(text, names)

    def materialize_backfill(
        self,
        *,
        base_canon_revision: str,
        source_revision: str,
        manuscript: bytes,
        draft: SceneTraceDraft,
        chapter: Chapter,
        scene: Scene,
        document: Document,
        new_id: IdFactory,
    ) -> tuple[SceneTrace, tuple[Entity, ...]]:
        snapshot = replay_ledger(self._ledger.read_entries())
        if snapshot.revision != base_canon_revision:
            raise RevisionConflictError("Canon changed after Trace Backfill source read")
        names, entities = self._all_identity_names(snapshot, scene.story_time)
        return self._materialize(
            source_revision=source_revision,
            manuscript=manuscript,
            draft=draft,
            chapter=chapter,
            scene=scene,
            document=document,
            snapshot=snapshot,
            names=names,
            available_entity_ids=set(entities),
            unknown_entity_label="outside the current Entity Registry",
            new_id=new_id,
        )

    def _materialize(
        self,
        *,
        source_revision: str,
        manuscript: bytes,
        draft: SceneTraceDraft,
        chapter: Chapter,
        scene: Scene,
        document: Document,
        snapshot,
        names: dict[str, tuple[UUID, ...]],
        available_entity_ids: set[UUID],
        unknown_entity_label: str,
        new_id: IdFactory,
    ) -> tuple[SceneTrace, tuple[Entity, ...]]:
        text = manuscript.decode("utf-8")
        exact_matches = self._exact_matches(text, names)
        exact_by_span = {
            (item.start_offset, item.end_offset, item.surface_text): item for item in exact_matches
        }
        draft_by_span = {
            (item.start_offset, item.end_offset, item.surface_text): item for item in draft.mentions
        }
        for key, match in exact_by_span.items():
            mention = draft_by_span.get(key)
            if mention is None:
                raise WorkflowStateError(
                    "Scene Trace Draft does not cover exact Entity candidate at "
                    f"{match.start_offset}:{match.end_offset} ({match.surface_text})"
                )
            missing_candidates = set(match.candidate_entity_ids) - set(
                mention.considered_entity_ids
            )
            if missing_candidates:
                raise WorkflowStateError(
                    "Scene Trace Draft did not consider all exact Entity candidates: "
                    + ", ".join(str(entity_id) for entity_id in sorted(missing_candidates, key=str))
                )

        for mention in draft.mentions:
            if text[mention.start_offset : mention.end_offset] != mention.surface_text:
                raise WorkflowStateError(
                    f"Scene Trace Mention span does not match Draft text: "
                    f"{mention.start_offset}:{mention.end_offset}"
                )
            unknown_considered = set(mention.considered_entity_ids) - available_entity_ids
            if unknown_considered:
                raise WorkflowStateError(
                    f"Scene Trace Mention considered Entities {unknown_entity_label}: "
                    + ", ".join(str(entity_id) for entity_id in sorted(unknown_considered, key=str))
                )
            if mention.resolution_status is EntityResolutionStatus.AMBIGUOUS:
                raise WorkflowStateError(
                    f"Scene Trace Mention remains ambiguous: {mention.surface_text}"
                )

        new_entity_ids: dict[str, UUID] = {}
        new_entities: list[Entity] = []
        for entity_draft in draft.new_entities:
            collision_ids = set(names.get(entity_draft.display_name, ()))
            considered_for_new = {
                entity_id
                for mention in draft.mentions
                if mention.new_entity_temporary_name == entity_draft.temporary_name
                for entity_id in mention.considered_entity_ids
            }
            missing_collisions = collision_ids - considered_for_new
            if missing_collisions:
                raise WorkflowStateError(
                    f"new Entity {entity_draft.display_name} did not consider existing "
                    "exact-name candidates: "
                    + ", ".join(str(entity_id) for entity_id in sorted(missing_collisions, key=str))
                )
            entity_id = new_id()
            new_entity_ids[entity_draft.temporary_name] = entity_id
            new_entities.append(
                Entity(
                    entity_id=entity_id,
                    entity_type=entity_draft.entity_type,
                    display_name=entity_draft.display_name,
                    created_revision=snapshot.revision,
                )
            )

        mention_ids: dict[int, UUID] = {}
        mentions: list[EntityMention] = []
        for mention_draft in draft.mentions:
            mention_id = new_id()
            mention_ids[mention_draft.mention_ordinal] = mention_id
            resolved_entity_id = mention_draft.resolved_entity_id
            if mention_draft.new_entity_temporary_name is not None:
                resolved_entity_id = new_entity_ids[mention_draft.new_entity_temporary_name]
            exact_match = exact_by_span.get(
                (
                    mention_draft.start_offset,
                    mention_draft.end_offset,
                    mention_draft.surface_text,
                )
            )
            mentions.append(
                EntityMention(
                    mention_id=mention_id,
                    mention_ordinal=mention_draft.mention_ordinal,
                    start_offset=mention_draft.start_offset,
                    end_offset=mention_draft.end_offset,
                    surface_text=mention_draft.surface_text,
                    mention_form=mention_draft.mention_form,
                    exact_candidate_entity_ids=(
                        exact_match.candidate_entity_ids if exact_match is not None else ()
                    ),
                    considered_entity_ids=mention_draft.considered_entity_ids,
                    resolution_status=mention_draft.resolution_status,
                    resolved_entity_id=resolved_entity_id,
                    resolution_reason=mention_draft.resolution_reason,
                )
            )

        occurrences: list[SceneEntityOccurrence] = []
        for occurrence_draft in draft.entity_occurrences:
            entity_id = occurrence_draft.resolved_entity_id
            if occurrence_draft.new_entity_temporary_name is not None:
                entity_id = new_entity_ids[occurrence_draft.new_entity_temporary_name]
            assert entity_id is not None
            occurrences.append(
                SceneEntityOccurrence(
                    occurrence_id=new_id(),
                    entity_id=entity_id,
                    presence_kind=occurrence_draft.presence_kind,
                    prominence=occurrence_draft.prominence,
                    mention_ids=tuple(
                        mention_ids[ordinal] for ordinal in occurrence_draft.mention_ordinals
                    ),
                )
            )

        return (
            SceneTrace(
                scene_trace_id=new_id(),
                scene_id=scene.scene_id,
                chapter_id=chapter.chapter_id,
                source_document_id=document.document_id,
                source_revision=source_revision,
                mentions=tuple(mentions),
                entity_occurrences=tuple(occurrences),
                scan_notes=draft.scan_notes,
            ),
            tuple(new_entities),
        )

    def _open_session(self, writing_session_id: UUID) -> WritingSession:
        session = self._runs.load_session(writing_session_id)
        if session.status is not WritingSessionStatus.OPEN:
            raise WorkflowStateError("Entity resolution requires an open Writing Session")
        return session

    @staticmethod
    def _visible_identity_names(session, entries, snapshot):
        scenes = {scene.scene_id: scene for scene in snapshot.scenes}
        visible_entity_ids: set[UUID] = set()
        visible_aliases = []
        for entry in entries:
            source_scene = (
                scenes.get(entry.source_scene_id) if entry.source_scene_id is not None else None
            )
            if entry.source_scene_id is not None and (
                source_scene is None
                or source_scene.narrative_order >= session.target_narrative_order
            ):
                continue
            for record in entry.records:
                if record.record_type == "entity":
                    visible_entity_ids.add(record.value.entity_id)
                elif record.record_type == "entity_alias":
                    visible_aliases.append(record.value)

        entities = {
            entity.entity_id: entity
            for entity in snapshot.entities
            if entity.entity_id in visible_entity_ids
        }
        names: dict[str, set[UUID]] = {}
        for entity in entities.values():
            names.setdefault(entity.display_name, set()).add(entity.entity_id)
        for alias in visible_aliases:
            if alias.entity_id not in visible_entity_ids:
                continue
            if not EntityResolutionService._alias_is_visible_at(
                alias,
                session.target_story_time,
            ):
                continue
            names.setdefault(alias.alias_text, set()).add(alias.entity_id)
        return (
            {
                name: tuple(sorted(entity_ids, key=str))
                for name, entity_ids in names.items()
                if name
            },
            entities,
        )

    @staticmethod
    def _all_identity_names(snapshot, story_time: StoryTime):
        entities = {entity.entity_id: entity for entity in snapshot.entities}
        names: dict[str, set[UUID]] = {}
        for entity in entities.values():
            names.setdefault(entity.display_name, set()).add(entity.entity_id)
        for alias in snapshot.entity_aliases:
            if alias.entity_id not in entities:
                continue
            if not EntityResolutionService._alias_is_visible_at(alias, story_time):
                continue
            names.setdefault(alias.alias_text, set()).add(alias.entity_id)
        return (
            {
                name: tuple(sorted(entity_ids, key=str))
                for name, entity_ids in names.items()
                if name
            },
            entities,
        )

    @staticmethod
    def _alias_is_visible_at(alias, target_story_time: StoryTime) -> bool:
        if alias.valid_from is None:
            return True
        if (
            alias.valid_from.timeline_id != target_story_time.timeline_id
            or alias.valid_from.kind is not StoryTimeKind.ORDINAL
            or target_story_time.kind is not StoryTimeKind.ORDINAL
        ):
            return True
        target_ordinal = int(target_story_time.story_time_start)
        if target_ordinal < int(alias.valid_from.story_time_start):
            return False
        if alias.valid_to is None or alias.valid_to.kind is not StoryTimeKind.ORDINAL:
            return True
        return target_ordinal <= int(alias.valid_to.story_time_start)

    @staticmethod
    def _exact_matches(
        text: str,
        names: dict[str, tuple[UUID, ...]],
    ) -> tuple[DraftEntityMatchCandidate, ...]:
        grouped: dict[tuple[int, int, str], set[UUID]] = {}
        for surface_text, entity_ids in names.items():
            start = 0
            while True:
                start = text.find(surface_text, start)
                if start < 0:
                    break
                end = start + len(surface_text)
                grouped.setdefault((start, end, surface_text), set()).update(entity_ids)
                start += 1

        candidates = tuple(
            DraftEntityMatchCandidate(
                start_offset=start,
                end_offset=end,
                surface_text=surface_text,
                candidate_entity_ids=tuple(sorted(entity_ids, key=str)),
            )
            for (start, end, surface_text), entity_ids in grouped.items()
        )
        retained = tuple(
            candidate
            for candidate in candidates
            if not any(
                other.start_offset <= candidate.start_offset
                and other.end_offset >= candidate.end_offset
                and (
                    other.start_offset < candidate.start_offset
                    or other.end_offset > candidate.end_offset
                )
                and set(candidate.candidate_entity_ids).issubset(other.candidate_entity_ids)
                for other in candidates
            )
        )
        return tuple(
            sorted(
                retained,
                key=lambda item: (item.start_offset, item.end_offset, item.surface_text),
            )
        )


class DraftService:
    def __init__(
        self,
        *,
        runs: WritingRunStore,
        sessions: WritingSessionService,
        clock: Clock = _utc_now,
    ) -> None:
        self._runs = runs
        self._sessions = sessions
        self._clock = clock

    def save(
        self,
        writing_session_id: UUID,
        content: bytes,
        *,
        parent_revision: str | None = None,
    ) -> DraftRevision:
        session = self._runs.load_session(writing_session_id)
        if session.status is not WritingSessionStatus.OPEN:
            raise WorkflowStateError("cannot save Draft to a closed Writing Session")
        if not content:
            raise ValueError("Draft manuscript must not be empty")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Draft manuscript must be UTF-8") from exc
        revision = manuscript_revision(content)
        drafts = self._runs.list_drafts(writing_session_id)
        by_revision = {item.draft_revision: item for item in drafts}
        if parent_revision is None and drafts:
            parent_revision = drafts[-1].draft_revision
        if parent_revision is not None and parent_revision not in by_revision:
            raise RevisionConflictError(f"parent Draft does not exist: {parent_revision}")
        self._sessions.require_continuity(writing_session_id)
        self._sessions.require_draft_format(writing_session_id, text)
        draft = DraftRevision(
            writing_session_id=writing_session_id,
            draft_revision=revision,
            parent_revision=parent_revision,
            content_digest=revision,
            base_document_revision=session.base_document_revision,
            created_at=self._clock(),
        )
        self._runs.save_draft(draft, content)
        return draft

    def list(self, writing_session_id: UUID) -> tuple[DraftRevision, ...]:
        self._runs.load_session(writing_session_id)
        return self._runs.list_drafts(writing_session_id)

    def show(self, writing_session_id: UUID, draft_revision: str) -> tuple[DraftRevision, str]:
        draft, content = self._runs.load_draft(writing_session_id, draft_revision)
        if manuscript_revision(content) != draft.content_digest:
            raise RevisionConflictError("stored Draft bytes do not match metadata")
        return draft, content.decode("utf-8")

    def diff(
        self,
        writing_session_id: UUID,
        draft_revision: str,
        *,
        from_revision: str | None,
    ) -> str:
        draft, content = self._runs.load_draft(writing_session_id, draft_revision)
        base = b""
        base_label = "/dev/null"
        if from_revision is not None:
            _base_meta, base = self._runs.load_draft(writing_session_id, from_revision)
            base_label = from_revision
        elif draft.parent_revision is not None:
            _base_meta, base = self._runs.load_draft(
                writing_session_id,
                draft.parent_revision,
            )
            base_label = draft.parent_revision
        return _text_diff(
            base.decode("utf-8"),
            content.decode("utf-8"),
            base_label,
            draft_revision,
        )


class ReviewService:
    def __init__(
        self,
        *,
        runs: WritingRunStore,
        new_id: IdFactory = uuid4,
        clock: Clock = _utc_now,
    ) -> None:
        self._runs = runs
        self._new_id = new_id
        self._clock = clock

    def save(
        self,
        *,
        writing_session_id: UUID,
        draft_revision: str,
        recommendation: ReviewRecommendation,
        conclusion: str,
        findings: tuple[str, ...] = (),
        uncertainties: tuple[str, ...] = (),
        retrieved_source_ids: tuple[UUID, ...] = (),
    ) -> Review:
        session = self._runs.load_session(writing_session_id)
        if session.status is not WritingSessionStatus.OPEN:
            raise WorkflowStateError("cannot save Review to a closed Writing Session")
        draft, content = self._runs.load_draft(writing_session_id, draft_revision)
        if manuscript_revision(content) != draft.content_digest:
            raise RevisionConflictError("Review Draft bytes do not match metadata")
        known_sources = {
            item.retrieved_source_id
            for item in self._runs.list_retrieved_sources(writing_session_id)
        }
        missing = set(retrieved_source_ids) - known_sources
        if missing:
            raise RevisionConflictError(
                f"Review references unknown retrieved sources: {sorted(map(str, missing))}"
            )
        review = Review(
            review_id=self._new_id(),
            writing_session_id=writing_session_id,
            draft_revision=draft_revision,
            recommendation=recommendation,
            conclusion=conclusion,
            findings=findings,
            uncertainties=uncertainties,
            retrieved_source_ids=retrieved_source_ids,
            created_at=self._clock(),
        )
        self._runs.save_review(review)
        return review

    def list(self, writing_session_id: UUID) -> tuple[Review, ...]:
        self._runs.load_session(writing_session_id)
        return self._runs.list_reviews(writing_session_id)

    def show(self, writing_session_id: UUID, review_id: UUID) -> Review:
        return self._runs.load_review(writing_session_id, review_id)


class PublicationService:
    def __init__(
        self,
        *,
        projects: ProjectStore,
        ledger: CanonLedgerStore,
        projection: ProjectionStore,
        intent: IntentStore,
        intent_revisions: IntentRevisionStore,
        writing: WritingRunStore,
        publications: PublicationStore,
        manuscripts: ManuscriptPublicationStore,
        navigation_sources: NavigationSourceStore,
        navigation: NavigationQueryPort,
        write_lock: ProjectWriteLock,
        sessions: WritingSessionService,
        intent_service: IntentService,
        entity_resolution: EntityResolutionService,
        new_id: IdFactory = uuid4,
        clock: Clock = _utc_now,
    ) -> None:
        self._projects = projects
        self._ledger = ledger
        self._projection = projection
        self._intent = intent
        self._intent_revisions = intent_revisions
        self._writing = writing
        self._publications = publications
        self._manuscripts = manuscripts
        self._navigation_sources = navigation_sources
        self._navigation = navigation
        self._write_lock = write_lock
        self._sessions = sessions
        self._intent_service = intent_service
        self._entity_resolution = entity_resolution
        self._new_id = new_id
        self._clock = clock

    def prepare(
        self,
        *,
        writing_session_id: UUID,
        draft_revision: str,
        scene_summary_text: str,
        chapter_summary_text: str,
        scene_trace_draft: SceneTraceDraft,
        review_refs: tuple[UUID, ...],
        scene_main_entity_ids: tuple[UUID, ...] = (),
        scene_key_changes: tuple[str, ...] = (),
        scene_open_questions: tuple[str, ...] = (),
        chapter_main_entity_ids: tuple[UUID, ...] = (),
        canon_records: tuple[LedgerRecord, ...] = (),
        intent_revision_id: UUID | None = None,
        unresolved_questions: tuple[str, ...] = (),
    ) -> Publication:
        manifest = self._projects.load_manifest()
        _require_ready(manifest)
        session = self._writing.load_session(writing_session_id)
        if session.status is not WritingSessionStatus.OPEN:
            raise WorkflowStateError("Publication requires an open Writing Session")
        if session.project_id != manifest.project_id:
            raise WorkflowStateError("Writing Session belongs to another Project")
        draft, manuscript = self._writing.load_draft(writing_session_id, draft_revision)
        self._sessions.require_draft_format(
            writing_session_id,
            manuscript.decode("utf-8"),
        )
        digest = manuscript_revision(manuscript)
        if draft.content_digest != digest:
            raise RevisionConflictError("Draft bytes do not match Draft metadata")
        snapshot = replay_ledger(self._ledger.read_entries())
        if snapshot.revision != session.base_canon_revision:
            raise RevisionConflictError("Canon changed after Writing Session start")
        current_intent = self._intent.load()
        if intent_revision(current_intent) != session.base_intent_revision:
            raise RevisionConflictError("Intent changed after Writing Session start")

        reviews = tuple(
            self._writing.load_review(writing_session_id, review_id) for review_id in review_refs
        )
        if any(review.draft_revision != draft_revision for review in reviews):
            raise RevisionConflictError("every Publication Review must bind the exact Draft")

        document = Document(
            document_id=session.target_document_id,
            relative_path=session.target_document_path,
            document_kind=DocumentKind.MANUSCRIPT,
            revision=digest,
        )
        scene = Scene(
            scene_id=session.target_scene_id,
            chapter_id=session.target_chapter_id,
            narrative_order=session.target_narrative_order,
            story_time=session.target_story_time,
            pov_entity_id=session.pov_entity_id,
            location_entity_id=session.location_entity_id,
            status=SceneStatus.APPROVED,
            source_document_id=document.document_id,
            revision=digest,
        )
        chapter = self._updated_chapter(session)
        scene_trace, new_entities = self._entity_resolution.materialize(
            session=session,
            draft_revision=draft_revision,
            manuscript=manuscript,
            draft=scene_trace_draft,
            chapter=chapter,
            scene=scene,
            document=document,
            new_id=self._new_id,
        )
        trace_main_entity_ids = tuple(
            occurrence.entity_id
            for occurrence in scene_trace.entity_occurrences
            if occurrence.prominence
            in {
                EntityProminence.FOCUS,
                EntityProminence.SUPPORTING,
            }
        )
        scene_main_entity_ids = _unique_ids((*scene_main_entity_ids, *trace_main_entity_ids))
        chapter_main_entity_ids = _unique_ids((*chapter_main_entity_ids, *trace_main_entity_ids))
        known_entity_ids = {
            *(entity.entity_id for entity in snapshot.entities),
            *(entity.entity_id for entity in new_entities),
        }
        unknown_entity_ids = (
            set(scene_main_entity_ids) | set(chapter_main_entity_ids)
        ) - known_entity_ids
        if unknown_entity_ids:
            raise ValueError(
                "navigation summaries reference unknown Entity IDs: "
                f"{sorted(map(str, unknown_entity_ids))}"
            )
        scene_summary = SceneSummary(
            scene_id=scene.scene_id,
            chapter_id=chapter.chapter_id,
            scene_number_in_chapter=chapter.scene_ids.index(scene.scene_id) + 1,
            source_document_id=document.document_id,
            source_revision=document.revision,
            summary=scene_summary_text,
            main_entity_ids=scene_main_entity_ids,
            key_changes=scene_key_changes,
            open_questions=scene_open_questions,
        )
        chapter_summary = self._build_chapter_summary(
            chapter,
            scene_summary,
            summary_text=chapter_summary_text,
            main_entity_ids=chapter_main_entity_ids,
        )

        prepared_at = self._clock()
        change_sets = [
            record.value for record in canon_records if record.record_type == "canon_change_set"
        ]
        if len(change_sets) > 1:
            raise ValueError("Publication Canon can contain at most one Change Set")
        approved_at = change_sets[0].approved_at if change_sets else prepared_at
        source_scene_id = change_sets[0].source_scene_id if change_sets else scene.scene_id
        if source_scene_id != scene.scene_id:
            raise ValueError("Publication Canon Change Set must bind the target Scene")
        ledger_entry = CanonLedgerEntry(
            ledger_sequence=snapshot.last_sequence + 1,
            ledger_entry_id=self._new_id(),
            base_revision=snapshot.revision,
            approved_at=approved_at,
            source_scene_id=scene.scene_id,
            records=(
                *(EntityLedgerRecord(value=entity) for entity in new_entities),
                DocumentLedgerRecord(value=document),
                SceneLedgerRecord(value=scene),
                *canon_records,
            ),
        )
        replay_ledger((*snapshot.entries, ledger_entry))
        for record in canon_records:
            if isinstance(record, SourceRefLedgerRecord):
                source_ref = record.value
                if (
                    source_ref.document_id != document.document_id
                    or source_ref.scene_id != scene.scene_id
                    or source_ref.document_revision != document.revision
                    or source_ref.excerpt.encode("utf-8") not in manuscript
                ):
                    raise ValueError("new SourceRef must match exact candidate manuscript bytes")

        selected_intent = (
            self._intent_revisions.load(intent_revision_id)
            if intent_revision_id is not None
            else None
        )
        if selected_intent is not None:
            if selected_intent.project_id != manifest.project_id:
                raise WorkflowStateError("Intent Revision belongs to another Project")
            if selected_intent.status is not IntentRevisionStatus.APPROVED:
                raise WorkflowStateError("Publication Intent Revision must be approved")
            if selected_intent.base_intent_revision != session.base_intent_revision:
                raise RevisionConflictError("Intent Revision does not bind the Session base")

        publication_id = self._new_id()
        manuscript_diff = _text_diff(
            "",
            manuscript.decode("utf-8"),
            "/dev/null",
            document.relative_path,
        )
        structure_diff = _text_diff(
            "",
            chapter.to_canonical_json(),
            "/dev/null",
            f"chapter:{chapter.chapter_id}",
        )
        summary_diff = _text_diff(
            "",
            scene_summary.to_canonical_json() + "\n" + chapter_summary.to_canonical_json(),
            "/dev/null",
            "navigation-memory",
        )
        scene_trace_diff = _text_diff(
            "",
            scene_trace.to_canonical_json(),
            "/dev/null",
            f"scene-trace:{scene_trace.scene_id}",
        )
        canon_diff = "\n".join(
            f"+ {record.record_type}:{record.value.to_canonical_json()}"
            for record in ledger_entry.records
        )
        protected = {
            "publication_id": str(publication_id),
            "project_id": str(manifest.project_id),
            "writing_session_id": str(writing_session_id),
            "draft_revision": draft_revision,
            "base_canon_revision": snapshot.revision,
            "base_document_revision": session.base_document_revision,
            "base_intent_revision": session.base_intent_revision,
            "target_document": document.model_dump(mode="json"),
            "scene_change": scene.model_dump(mode="json"),
            "chapter_change": chapter.model_dump(mode="json"),
            "scene_summary_change": scene_summary.model_dump(mode="json"),
            "chapter_summary_change": chapter_summary.model_dump(mode="json"),
            "scene_trace_change": scene_trace.model_dump(mode="json"),
            "intent_revision_id": str(intent_revision_id) if intent_revision_id else None,
            "intent_candidate_revision": (
                selected_intent.candidate_revision if selected_intent else None
            ),
            "ledger_entry": ledger_entry.model_dump(mode="json"),
            "review_refs": [str(value) for value in review_refs],
            "manuscript_digest": digest,
            "unresolved_questions": list(unresolved_questions),
        }
        plan = PublicationPlan(
            publication_id=publication_id,
            project_id=manifest.project_id,
            writing_session_id=writing_session_id,
            draft_revision=draft_revision,
            base_canon_revision=snapshot.revision,
            base_document_revision=session.base_document_revision,
            base_intent_revision=session.base_intent_revision,
            target_document=document,
            scene_change=scene,
            chapter_change=chapter,
            scene_summary_change=scene_summary,
            chapter_summary_change=chapter_summary,
            scene_trace_change=scene_trace,
            intent_revision_id=intent_revision_id,
            intent_candidate_revision=(
                selected_intent.candidate_revision if selected_intent else None
            ),
            ledger_entry=ledger_entry,
            review_refs=review_refs,
            manuscript_digest=digest,
            manuscript_diff=manuscript_diff,
            structure_diff=structure_diff,
            summary_diff=summary_diff,
            scene_trace_diff=scene_trace_diff,
            intent_diff=selected_intent.intent_diff if selected_intent else None,
            canon_diff=canon_diff,
            unresolved_questions=unresolved_questions,
            approval_digest=approval_digest("publication", protected),
            prepared_at=prepared_at,
        )
        publication = Publication(plan=plan, status=PublicationStatus.PREPARED)
        self._publications.create(publication)
        return publication

    def inspect(self, publication_id: UUID) -> Publication:
        return self._publications.load(publication_id)

    def approve(self, publication_id: UUID, digest: str) -> Publication:
        publication = self._publications.load(publication_id)
        if publication.status is not PublicationStatus.PREPARED:
            raise WorkflowStateError("only a prepared Publication can be approved")
        if digest != publication.plan.approval_digest:
            raise ApprovalMismatchError("Publication approval digest does not match")
        approved = publication.model_copy(
            update={
                "status": PublicationStatus.APPROVED,
                "approval": Approval(
                    operation_id=publication_id,
                    approval_digest=digest,
                    approved_at=self._clock(),
                ),
            }
        )
        self._publications.replace(approved)
        return approved

    def apply(self, publication_id: UUID) -> Publication:
        return self._advance(publication_id)

    def recover(self, publication_id: UUID) -> Publication:
        return self._advance(publication_id)

    def _advance(self, publication_id: UUID) -> Publication:
        with self._write_lock.acquire():
            publication = self._publications.load(publication_id)
            if publication.status is PublicationStatus.COMPLETED:
                return publication
            if publication.status is PublicationStatus.PREPARED:
                raise WorkflowStateError("Publication must be approved before apply")
            try:
                return self._advance_under_lock(publication)
            except Exception as exc:
                stored = self._publications.load(publication_id)
                if stored.status is PublicationStatus.APPROVED:
                    raise
                raise PublicationRecoveryRequiredError(
                    f"Publication {publication_id} requires recover: {exc}"
                ) from exc

    def _advance_under_lock(self, publication: Publication) -> Publication:
        plan = publication.plan
        manifest = self._projects.load_manifest()
        if manifest.project_id != plan.project_id:
            raise WorkflowStateError("Publication belongs to another Project")
        session = self._writing.load_session(plan.writing_session_id)
        draft, manuscript = self._writing.load_draft(
            plan.writing_session_id,
            plan.draft_revision,
        )
        self._sessions.require_draft_format(
            plan.writing_session_id,
            manuscript.decode("utf-8"),
        )
        if manuscript_revision(manuscript) != plan.manuscript_digest:
            raise RevisionConflictError("Publication Draft bytes changed")
        if draft.content_digest != plan.manuscript_digest:
            raise RevisionConflictError("Publication Draft metadata changed")
        self._validate_preflight(plan, session)

        self._manuscripts.install_document(plan.target_document.relative_path, manuscript)
        publication = self._set_status(publication, PublicationStatus.MANUSCRIPT_INSTALLED)

        self._navigation_sources.save_chapter(plan.chapter_change)
        self._navigation_sources.save_scene_summary(plan.scene_summary_change)
        self._navigation_sources.save_chapter_summary(plan.chapter_summary_change)
        if plan.scene_trace_change is not None:
            self._navigation_sources.save_scene_trace(plan.scene_trace_change)
        publication = self._set_status(publication, PublicationStatus.NAVIGATION_INSTALLED)

        if plan.intent_revision_id is not None:
            applied_intent = self._intent_service.apply_approved_under_lock(plan.intent_revision_id)
            if applied_intent.candidate_revision != plan.intent_candidate_revision:
                raise RevisionConflictError("Publication Intent candidate changed")
        publication = self._set_status(publication, PublicationStatus.INTENT_INSTALLED)

        entries = self._ledger.read_entries()
        existing = next(
            (
                entry
                for entry in entries
                if entry.ledger_entry_id == plan.ledger_entry.ledger_entry_id
            ),
            None,
        )
        snapshot = replay_ledger(entries)
        if existing is None:
            if snapshot.revision != plan.base_canon_revision:
                raise RevisionConflictError("Canon no longer matches Publication base")
            snapshot = replay_ledger((*entries, plan.ledger_entry))
            self._ledger.append_entry(plan.ledger_entry)
        elif existing != plan.ledger_entry:
            raise RevisionConflictError("Publication Ledger entry has different content")
        publication = self._set_status(publication, PublicationStatus.LEDGER_APPENDED)

        snapshot = replay_ledger(self._ledger.read_entries())
        self._projection.replace(manifest, snapshot)
        publication = self._set_status(publication, PublicationStatus.PROJECTION_REBUILT)

        self._sessions.close_under_lock(session)
        completed = publication.model_copy(
            update={
                "status": PublicationStatus.COMPLETED,
                "completed_at": self._clock(),
            }
        )
        self._publications.replace(completed)
        return completed

    def _validate_preflight(
        self,
        plan: PublicationPlan,
        session: WritingSession,
    ) -> None:
        entries = self._ledger.read_entries()
        existing = next(
            (
                entry
                for entry in entries
                if entry.ledger_entry_id == plan.ledger_entry.ledger_entry_id
            ),
            None,
        )
        snapshot = replay_ledger(entries)
        if existing is None and snapshot.revision != plan.base_canon_revision:
            raise RevisionConflictError("Canon no longer matches Publication base")
        if existing is not None and existing != plan.ledger_entry:
            raise RevisionConflictError("Publication Ledger entry has different content")
        current_intent_revision = intent_revision(self._intent.load())
        allowed_intent_revisions = {plan.base_intent_revision}
        if plan.intent_candidate_revision is not None:
            allowed_intent_revisions.add(plan.intent_candidate_revision)
        if current_intent_revision not in allowed_intent_revisions:
            raise RevisionConflictError("Intent no longer matches Publication base or candidate")
        current_chapter = self._navigation.get_chapter(session.target_chapter_id)
        if (
            current_chapter != plan.chapter_change
            and self._updated_chapter(session) != plan.chapter_change
        ):
            raise RevisionConflictError("Chapter structure changed after Publication prepare")

    def _set_status(
        self,
        publication: Publication,
        status: PublicationStatus,
    ) -> Publication:
        if _publication_status_index(publication.status) >= _publication_status_index(status):
            return publication
        updated = publication.model_copy(update={"status": status})
        self._publications.replace(updated)
        return updated

    def _updated_chapter(self, session: WritingSession) -> Chapter:
        current = self._navigation.get_chapter(session.target_chapter_id)
        if current is None:
            return Chapter(
                chapter_id=session.target_chapter_id,
                chapter_number=session.target_chapter_number,
                title=session.target_chapter_title,
                scene_ids=(session.target_scene_id,),
            )
        scene_ids = list(current.scene_ids)
        if session.before_scene_id is None:
            index = 0
        else:
            try:
                index = scene_ids.index(session.before_scene_id) + 1
            except ValueError as exc:
                raise RevisionConflictError("Session before boundary left its Chapter") from exc
        if session.after_scene_id is not None:
            try:
                after_index = scene_ids.index(session.after_scene_id)
            except ValueError as exc:
                raise RevisionConflictError("Session after boundary left its Chapter") from exc
            if after_index != index:
                raise RevisionConflictError("Session Chapter boundaries are no longer adjacent")
        elif index != len(scene_ids):
            raise RevisionConflictError("Session append boundary is no longer Chapter end")
        scene_ids.insert(index, session.target_scene_id)
        return current.model_copy(update={"scene_ids": tuple(scene_ids)})

    def _build_chapter_summary(
        self,
        chapter: Chapter,
        new_scene_summary: SceneSummary,
        *,
        summary_text: str,
        main_entity_ids: tuple[UUID, ...],
    ) -> ChapterSummary:
        summaries: dict[UUID, SceneSummary] = {new_scene_summary.scene_id: new_scene_summary}
        for scene_id in chapter.scene_ids:
            if scene_id == new_scene_summary.scene_id:
                continue
            projected = self._navigation.get_scene_summary(scene_id)
            if projected is None or projected[1]:
                raise WorkflowStateError(
                    f"Publication Chapter Summary requires current Scene Summary: {scene_id}"
                )
            summaries[scene_id] = projected[0]
        ordered = tuple(summaries[scene_id] for scene_id in chapter.scene_ids)
        summary = ChapterSummary(
            chapter_id=chapter.chapter_id,
            chapter_number=chapter.chapter_number,
            title=chapter.title,
            scene_ids=chapter.scene_ids,
            scene_summary_dependencies=tuple(
                SceneSummaryDependency(
                    scene_id=item.scene_id,
                    source_revision=item.source_revision,
                    summary_digest=scene_summary_digest(item),
                )
                for item in ordered
            ),
            summary=summary_text,
            main_entity_ids=main_entity_ids,
        )
        if chapter_summary_is_stale(
            summary,
            chapter=chapter,
            scene_summaries=summaries,
            stale_scene_ids=set(),
        ):
            raise ValueError("Chapter Summary does not bind current Scene Summaries")
        return summary


class SceneTraceBackfillService:
    """Prepare and transactionally install a Trace for approved historical prose."""

    def __init__(
        self,
        *,
        projects: ProjectStore,
        ledger: CanonLedgerStore,
        projection: ProjectionStore,
        manuscripts: ManuscriptPublicationStore,
        navigation_sources: NavigationSourceStore,
        navigation: NavigationQueryPort,
        canon: CanonQueryService,
        write_lock: ProjectWriteLock,
        backfills: SceneTraceBackfillStore,
        entity_resolution: EntityResolutionService,
        new_id: IdFactory = uuid4,
        clock: Clock = _utc_now,
    ) -> None:
        self._projects = projects
        self._ledger = ledger
        self._projection = projection
        self._manuscripts = manuscripts
        self._navigation_sources = navigation_sources
        self._navigation = navigation
        self._canon = canon
        self._write_lock = write_lock
        self._backfills = backfills
        self._entity_resolution = entity_resolution
        self._new_id = new_id
        self._clock = clock

    def source(
        self,
        *,
        chapter_id: UUID,
        scene_id: UUID,
    ) -> SceneTraceBackfillSource:
        manifest = self._projects.load_manifest()
        _require_ready(manifest)
        chapter, scene, document, manuscript = self._approved_scene(
            chapter_id=chapter_id,
            scene_id=scene_id,
        )
        projected_trace = self._navigation.get_scene_trace(scene_id)
        current_trace = projected_trace[0] if projected_trace is not None else None
        snapshot = replay_ledger(self._ledger.read_entries())
        text = manuscript.decode("utf-8")
        exact_candidates = self._entity_resolution.approved_scene_candidates(
            text,
            story_time=scene.story_time,
        )
        candidate_entity_ids = {
            entity_id
            for candidate in exact_candidates
            for entity_id in candidate.candidate_entity_ids
        }
        entities = {entity.entity_id: entity for entity in snapshot.entities}
        return SceneTraceBackfillSource(
            project_id=manifest.project_id,
            base_canon_revision=snapshot.revision,
            chapter=chapter,
            scene=scene,
            document=document,
            text=text,
            exact_candidates=exact_candidates,
            registry_entities=tuple(entities[entity_id] for entity_id in sorted(entities, key=str)),
            candidate_entities=tuple(
                entities[entity_id] for entity_id in sorted(candidate_entity_ids, key=str)
            ),
            current_trace=current_trace,
            current_trace_stale=projected_trace[1] if projected_trace is not None else None,
            current_trace_digest=(
                scene_trace_digest(current_trace) if current_trace is not None else None
            ),
        )

    def entity_line(self, entity_id: UUID) -> EntityLine:
        entity = self._canon.get_entity(entity_id)
        if entity is None:
            raise ValueError(f"entity does not exist: {entity_id}")
        scenes = replay_ledger(self._ledger.read_entries()).scenes
        before_narrative_order = max(scene.narrative_order for scene in scenes) + 1 if scenes else 1
        return EntityLine(
            entity=entity,
            occurrences=self._navigation.entity_occurrences(
                entity_id,
                before_narrative_order=before_narrative_order,
            ),
        )

    def prepare(
        self,
        *,
        chapter_id: UUID,
        scene_id: UUID,
        source_revision: str,
        scene_trace_draft: SceneTraceDraft,
    ) -> SceneTraceBackfill:
        source = self.source(chapter_id=chapter_id, scene_id=scene_id)
        if source.source_revision != source_revision:
            raise RevisionConflictError("Trace Backfill source revision changed")
        manuscript = source.text.encode("utf-8")
        trace, new_entities = self._entity_resolution.materialize_backfill(
            base_canon_revision=source.base_canon_revision,
            source_revision=source_revision,
            manuscript=manuscript,
            draft=scene_trace_draft,
            chapter=source.chapter,
            scene=source.scene,
            document=source.document,
            new_id=self._new_id,
        )
        prepared_at = self._clock()
        entries = self._ledger.read_entries()
        snapshot = replay_ledger(entries)
        if snapshot.revision != source.base_canon_revision:
            raise RevisionConflictError("Canon changed during Trace Backfill prepare")
        ledger_entry = (
            CanonLedgerEntry(
                ledger_sequence=snapshot.last_sequence + 1,
                ledger_entry_id=self._new_id(),
                base_revision=snapshot.revision,
                approved_at=prepared_at,
                source_scene_id=source.scene.scene_id,
                records=tuple(EntityLedgerRecord(value=entity) for entity in new_entities),
            )
            if new_entities
            else None
        )
        if ledger_entry is not None:
            replay_ledger((*entries, ledger_entry))

        before_trace = (
            source.current_trace.to_canonical_json() if source.current_trace is not None else ""
        )
        scene_trace_diff = _text_diff(
            before_trace,
            trace.to_canonical_json(),
            (f"scene-trace:{scene_id}:base" if source.current_trace is not None else "/dev/null"),
            f"scene-trace:{scene_id}:candidate",
        )
        canon_diff = (
            "\n".join(
                f"+ {record.record_type}:{record.value.to_canonical_json()}"
                for record in ledger_entry.records
            )
            if ledger_entry is not None
            else ""
        )
        backfill_id = self._new_id()
        protected = {
            "backfill_id": str(backfill_id),
            "project_id": str(source.project_id),
            "chapter_id": str(chapter_id),
            "scene_id": str(scene_id),
            "source_document_id": str(source.document.document_id),
            "source_revision": source_revision,
            "base_canon_revision": source.base_canon_revision,
            "base_scene_trace_digest": source.current_trace_digest,
            "scene_trace_change": trace.model_dump(mode="json"),
            "ledger_entry": (
                ledger_entry.model_dump(mode="json") if ledger_entry is not None else None
            ),
        }
        plan = SceneTraceBackfillPlan(
            backfill_id=backfill_id,
            project_id=source.project_id,
            chapter_id=chapter_id,
            scene_id=scene_id,
            source_document_id=source.document.document_id,
            source_revision=source_revision,
            base_canon_revision=source.base_canon_revision,
            base_scene_trace_digest=source.current_trace_digest,
            scene_trace_change=trace,
            ledger_entry=ledger_entry,
            scene_trace_diff=scene_trace_diff,
            canon_diff=canon_diff,
            approval_digest=approval_digest("scene_trace_backfill", protected),
            prepared_at=prepared_at,
        )
        backfill = SceneTraceBackfill(
            plan=plan,
            status=SceneTraceBackfillStatus.PREPARED,
        )
        self._backfills.create(backfill)
        return backfill

    def inspect(self, backfill_id: UUID) -> SceneTraceBackfill:
        return self._backfills.load(backfill_id)

    def approve(self, backfill_id: UUID, digest: str) -> SceneTraceBackfill:
        backfill = self._backfills.load(backfill_id)
        if backfill.status is not SceneTraceBackfillStatus.PREPARED:
            raise WorkflowStateError("only a prepared Trace Backfill can be approved")
        if digest != backfill.plan.approval_digest:
            raise ApprovalMismatchError("Trace Backfill approval digest does not match")
        approved = backfill.model_copy(
            update={
                "status": SceneTraceBackfillStatus.APPROVED,
                "approval": Approval(
                    operation_id=backfill_id,
                    approval_digest=digest,
                    approved_at=self._clock(),
                ),
            }
        )
        self._backfills.replace(approved)
        return approved

    def apply(self, backfill_id: UUID) -> SceneTraceBackfill:
        return self._advance(backfill_id)

    def recover(self, backfill_id: UUID) -> SceneTraceBackfill:
        return self._advance(backfill_id)

    def _advance(self, backfill_id: UUID) -> SceneTraceBackfill:
        with self._write_lock.acquire():
            backfill = self._backfills.load(backfill_id)
            if backfill.status is SceneTraceBackfillStatus.COMPLETED:
                return backfill
            if backfill.status is SceneTraceBackfillStatus.PREPARED:
                raise WorkflowStateError("Trace Backfill must be approved before apply")
            try:
                return self._advance_under_lock(backfill)
            except Exception as exc:
                stored = self._backfills.load(backfill_id)
                if stored.status is SceneTraceBackfillStatus.APPROVED:
                    raise
                raise TraceBackfillRecoveryRequiredError(
                    f"Trace Backfill {backfill_id} requires recover: {exc}"
                ) from exc

    def _advance_under_lock(
        self,
        backfill: SceneTraceBackfill,
    ) -> SceneTraceBackfill:
        plan = backfill.plan
        self._validate_preflight(plan)
        manifest = self._projects.load_manifest()

        entry = plan.ledger_entry
        if entry is not None:
            entries = self._ledger.read_entries()
            existing = next(
                (
                    current
                    for current in entries
                    if current.ledger_entry_id == entry.ledger_entry_id
                ),
                None,
            )
            snapshot = replay_ledger(entries)
            if existing is None:
                if snapshot.revision != plan.base_canon_revision:
                    raise RevisionConflictError("Canon no longer matches Trace Backfill base")
                replay_ledger((*entries, entry))
                self._ledger.append_entry(entry)
            elif existing != entry:
                raise RevisionConflictError("Trace Backfill Ledger entry has different content")
        backfill = self._set_status(backfill, SceneTraceBackfillStatus.LEDGER_APPENDED)

        self._navigation_sources.save_scene_trace(plan.scene_trace_change)
        backfill = self._set_status(backfill, SceneTraceBackfillStatus.TRACE_INSTALLED)

        snapshot = replay_ledger(self._ledger.read_entries())
        self._projection.replace(manifest, snapshot)
        backfill = self._set_status(backfill, SceneTraceBackfillStatus.PROJECTION_REBUILT)

        completed = backfill.model_copy(
            update={
                "status": SceneTraceBackfillStatus.COMPLETED,
                "completed_at": self._clock(),
            }
        )
        self._backfills.replace(completed)
        return completed

    def _validate_preflight(self, plan: SceneTraceBackfillPlan) -> None:
        manifest = self._projects.load_manifest()
        if manifest.project_id != plan.project_id:
            raise WorkflowStateError("Trace Backfill belongs to another Project")
        _chapter, _scene, document, _manuscript = self._approved_scene(
            chapter_id=plan.chapter_id,
            scene_id=plan.scene_id,
        )
        if document.document_id != plan.source_document_id:
            raise RevisionConflictError("Trace Backfill source Document changed")
        if document.revision != plan.source_revision:
            raise RevisionConflictError("Trace Backfill source revision changed")

        entries = self._ledger.read_entries()
        snapshot = replay_ledger(entries)
        entry = plan.ledger_entry
        if entry is None:
            if snapshot.revision != plan.base_canon_revision:
                raise RevisionConflictError("Canon no longer matches Trace Backfill base")
        else:
            existing = next(
                (
                    current
                    for current in entries
                    if current.ledger_entry_id == entry.ledger_entry_id
                ),
                None,
            )
            if existing is None and snapshot.revision != plan.base_canon_revision:
                raise RevisionConflictError("Canon no longer matches Trace Backfill base")
            if existing is not None and existing != entry:
                raise RevisionConflictError("Trace Backfill Ledger entry has different content")

        projected_trace = self._navigation.get_scene_trace(plan.scene_id)
        current_trace = projected_trace[0] if projected_trace is not None else None
        current_digest = scene_trace_digest(current_trace) if current_trace is not None else None
        candidate_digest = scene_trace_digest(plan.scene_trace_change)
        if current_digest not in {
            plan.base_scene_trace_digest,
            candidate_digest,
        }:
            raise RevisionConflictError("Scene Trace changed after Backfill prepare")

    def _approved_scene(
        self,
        *,
        chapter_id: UUID,
        scene_id: UUID,
    ) -> tuple[Chapter, Scene, Document, bytes]:
        chapter = self._navigation.get_chapter(chapter_id)
        if chapter is None:
            raise ChapterNotFoundError(f"Trace Backfill Chapter does not exist: {chapter_id}")
        chapter_scene_ids = {
            scene.scene_id for scene, _number in self._navigation.chapter_scenes(chapter_id)
        }
        scene = self._canon.get_scene(scene_id)
        if scene is None:
            raise SceneNotFoundError(f"Trace Backfill Scene does not exist: {scene_id}")
        if scene_id not in chapter_scene_ids or (
            scene.chapter_id is not None and scene.chapter_id != chapter_id
        ):
            raise WorkflowStateError("Trace Backfill Scene does not belong to the Chapter")
        if scene.status is not SceneStatus.APPROVED:
            raise WorkflowStateError("Trace Backfill requires an approved Scene")
        document = self._canon.get_document(scene.source_document_id)
        if document is None:
            raise WorkflowStateError("Trace Backfill source Document does not exist")
        if document.document_kind is not DocumentKind.MANUSCRIPT:
            raise WorkflowStateError("Trace Backfill source is not manuscript")
        if scene.revision != document.revision:
            raise RevisionConflictError("Trace Backfill Scene and Document revisions differ")
        manuscript = self._manuscripts.read_document(document.relative_path)
        if manuscript_revision(manuscript) != document.revision:
            raise RevisionConflictError("Trace Backfill manuscript bytes changed")
        try:
            manuscript.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Trace Backfill manuscript must be UTF-8") from exc
        return chapter, scene, document, manuscript

    def _set_status(
        self,
        backfill: SceneTraceBackfill,
        status: SceneTraceBackfillStatus,
    ) -> SceneTraceBackfill:
        if _trace_backfill_status_index(backfill.status) >= _trace_backfill_status_index(status):
            return backfill
        updated = backfill.model_copy(update={"status": status})
        self._backfills.replace(updated)
        return updated


def _publication_status_index(status: PublicationStatus) -> int:
    return list(PublicationStatus).index(status)


def _trace_backfill_status_index(status: SceneTraceBackfillStatus) -> int:
    return list(SceneTraceBackfillStatus).index(status)


def _unique_ids(values: tuple[UUID, ...]) -> tuple[UUID, ...]:
    return tuple(dict.fromkeys(values))


def _require_ready(manifest) -> None:
    if manifest.status is not ProjectStatus.READY:
        raise ProjectNotBootstrappedError(f"Project {manifest.project_id} is not bootstrapped")


def _intent_diff(current: IntentContent | None, candidate: IntentContent) -> str:
    before = current or IntentContent(
        creative_brief="(empty)",
        story_bible="(empty)",
        writing_rules="(empty)",
        current_outline="(empty)",
    )
    sections: list[str] = []
    for field in (
        "creative_brief",
        "story_bible",
        "writing_rules",
        "current_outline",
    ):
        sections.append(
            _text_diff(
                getattr(before, field) if current is not None else "",
                getattr(candidate, field),
                f"intent/{field}:base",
                f"intent/{field}:candidate",
            )
        )
    return "\n".join(sections)


def _text_diff(before: str, after: str, before_name: str, after_name: str) -> str:
    diff = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=before_name,
            tofile=after_name,
        )
    )
    return diff or f"--- {before_name}\n+++ {after_name}\n"
