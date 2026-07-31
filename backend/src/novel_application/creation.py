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
    TraceBackfillRecoveryRequiredError,
    VolumeNotFoundError,
    WorkflowStateError,
)
from novel_application.memory import NavigationMemoryService
from novel_application.models import (
    ChapterTraceBackfillSource,
    EntityLine,
    ExactChapterText,
    SummarySearchHit,
    VolumeChapterItem,
    VolumeSummaryItem,
)
from novel_application.ports import (
    BootstrapRunStore,
    CanonLedgerStore,
    ChapterTraceBackfillStore,
    IntentRevisionStore,
    IntentStore,
    ManuscriptPublicationStore,
    ManuscriptStore,
    NavigationQueryPort,
    NavigationSourceStore,
    ProjectionStore,
    ProjectStore,
    ProjectWriteLock,
    PublicationStore,
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
    ChapterEntityOccurrence,
    ChapterLedgerRecord,
    ChapterStatus,
    ChapterSummary,
    ChapterSummaryDependency,
    ChapterTrace,
    ChapterTraceBackfill,
    ChapterTraceBackfillPlan,
    ChapterTraceBackfillStatus,
    ChapterTraceDraft,
    ContinuityChapterStatus,
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
    SourceRefLedgerRecord,
    StoryTime,
    StoryTimeKind,
    Volume,
    VolumeSummary,
    WritingSession,
    WritingSessionMode,
    WritingSessionStatus,
    approval_digest,
    chapter_heading,
    chapter_summary_digest,
    chapter_trace_digest,
    intent_revision,
    manuscript_revision,
    replay_ledger,
    volume_summary_is_stale,
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
        target_story_time: StoryTime | None,
        volume_id: UUID | None,
        new_volume_number: int | None,
        new_volume_title: str | None,
        new_chapter_number: int | None,
        new_chapter_title: str | None,
        before_chapter_id: UUID | None,
        after_chapter_id: UUID | None,
        revise_chapter_id: UUID | None = None,
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
        mode = (
            WritingSessionMode.REVISE
            if revise_chapter_id is not None
            else WritingSessionMode.CREATE
        )
        if mode is WritingSessionMode.REVISE:
            if any(
                value is not None
                for value in (
                    volume_id,
                    new_volume_number,
                    new_volume_title,
                    new_chapter_number,
                    new_chapter_title,
                    before_chapter_id,
                    after_chapter_id,
                    target_story_time,
                    pov_entity_id,
                    location_entity_id,
                )
            ):
                raise ValueError(
                    "Chapter revision uses the approved target position and metadata; "
                    "pass only --revise-chapter-id"
                )
            assert revise_chapter_id is not None
            volume, target_chapter, target_document, before_chapter_id, after_chapter_id = (
                self._revision_target(revise_chapter_id, snapshot)
            )
            target_chapter_id = target_chapter.chapter_id
            target_document_id = target_document.document_id
            target_document_path = target_document.relative_path
            target_volume_id = volume.volume_id
            narrative_order = target_chapter.narrative_order
            target_story_time = target_chapter.story_time
            pov_entity_id = target_chapter.pov_entity_id
            location_entity_id = target_chapter.location_entity_id
            base_document_revision = target_document.revision
            target_chapter_number = target_chapter.chapter_number
            target_chapter_title = target_chapter.title
            required_heading = chapter_heading(
                language=manifest.language,
                chapter_number=target_chapter_number,
                title=target_chapter_title,
            )
        else:
            if target_story_time is None:
                raise ValueError("new Chapter requires --story-time")
            if new_chapter_number is None or new_chapter_title is None:
                raise ValueError("new Chapter requires number and title")
            if any(chapter.chapter_number == new_chapter_number for chapter in snapshot.chapters):
                raise RevisionConflictError(f"Chapter number already exists: {new_chapter_number}")
            volume = self._resolve_target_volume(
                volume_id=volume_id,
                new_volume_number=new_volume_number,
                new_volume_title=new_volume_title,
            )
            narrative_order = self._target_order(
                before_chapter_id=before_chapter_id,
                after_chapter_id=after_chapter_id,
                target_volume_id=volume.volume_id if volume is not None else volume_id,
            )
            target_volume_id = volume.volume_id if volume is not None else self._new_id()
            target_chapter_id = self._new_id()
            target_document_id = self._new_id()
            target_document_path = f"manuscript/{target_chapter_id}.md"
            base_document_revision = None
            target_chapter_number = new_chapter_number
            target_chapter_title = new_chapter_title
            required_heading = chapter_heading(
                language=manifest.language,
                chapter_number=target_chapter_number,
                title=target_chapter_title,
            )
        session = WritingSession(
            writing_session_id=self._new_id(),
            project_id=manifest.project_id,
            mode=mode,
            target_chapter_id=target_chapter_id,
            target_document_id=target_document_id,
            target_document_path=target_document_path,
            target_chapter_number=target_chapter_number,
            target_chapter_title=target_chapter_title,
            target_volume_id=target_volume_id,
            target_volume_number=(
                volume.volume_number if volume is not None else int(new_volume_number)
            ),
            target_volume_title=(volume.title if volume is not None else str(new_volume_title)),
            required_chapter_heading=required_heading,
            target_narrative_order=narrative_order,
            target_story_time=target_story_time,
            pov_entity_id=pov_entity_id,
            location_entity_id=location_entity_id,
            before_chapter_id=before_chapter_id,
            after_chapter_id=after_chapter_id,
            base_canon_revision=snapshot.revision,
            base_document_revision=base_document_revision,
            base_intent_revision=intent_revision(content),
            author_goal=author_goal,
            creative_constraints=creative_constraints,
            status=WritingSessionStatus.OPEN,
            created_at=self._clock(),
        )
        self._runs.create_session(session)
        return session

    def _revision_target(
        self,
        chapter_id: UUID,
        snapshot,
    ) -> tuple[Volume, Chapter, Document, UUID | None, UUID | None]:
        chapter = self._canon.get_chapter(chapter_id)
        if chapter is None:
            raise ChapterNotFoundError(f"revision target Chapter does not exist: {chapter_id}")
        if chapter.status is not ChapterStatus.APPROVED or chapter.volume_id is None:
            raise WorkflowStateError("revision target must be an approved Volume Chapter")
        volume = self._navigation.get_volume(chapter.volume_id)
        if volume is None or chapter.chapter_id not in volume.chapter_ids:
            raise WorkflowStateError("revision target is not in its current Volume structure")
        document = self._canon.get_document(chapter.source_document_id)
        if document is None or document.document_kind is not DocumentKind.MANUSCRIPT:
            raise WorkflowStateError("revision target has no approved manuscript Document")
        if document.revision != chapter.revision:
            raise RevisionConflictError("revision target Chapter and Document revisions differ")
        document_chapters = tuple(
            item for item in snapshot.chapters if item.source_document_id == document.document_id
        )
        if document_chapters != (chapter,):
            raise WorkflowStateError(
                "Chapter revision requires one Chapter per manuscript Document"
            )

        ordered = tuple(sorted(snapshot.chapters, key=lambda item: item.narrative_order))
        target_index = next(
            index for index, item in enumerate(ordered) if item.chapter_id == chapter.chapter_id
        )
        before_chapter_id = ordered[target_index - 1].chapter_id if target_index else None
        after_chapter_id = (
            ordered[target_index + 1].chapter_id if target_index + 1 < len(ordered) else None
        )
        return volume, chapter, document, before_chapter_id, after_chapter_id

    def show(self, writing_session_id: UUID) -> WritingSession:
        return self._runs.load_session(writing_session_id)

    def context(self, writing_session_id: UUID) -> CreationContext:
        session = self._runs.load_session(writing_session_id)
        content = self._intent.load()
        if content is None:
            raise WorkflowStateError("Project has no formal Intent Canon")
        if intent_revision(content) != session.base_intent_revision:
            raise RevisionConflictError("formal Intent changed after Session start")
        volume = self._navigation.get_volume(session.target_volume_id)
        previous_summary = None
        if session.before_chapter_id is not None:
            projected = self._navigation.get_chapter_summary(session.before_chapter_id)
            previous_summary = projected[0] if projected is not None else None
        continuity_chapters = self._continuity_chapters(session)
        return CreationContext(
            project_id=session.project_id,
            writing_session_id=session.writing_session_id,
            mode=session.mode,
            author_goal=session.author_goal,
            creative_constraints=session.creative_constraints,
            target_chapter_id=session.target_chapter_id,
            target_chapter_number=session.target_chapter_number,
            target_chapter_title=session.target_chapter_title,
            target_volume_id=session.target_volume_id,
            target_narrative_order=session.target_narrative_order,
            required_chapter_heading=session.required_chapter_heading,
            before_chapter_id=session.before_chapter_id,
            after_chapter_id=session.after_chapter_id,
            base_canon_revision=session.base_canon_revision,
            base_document_revision=session.base_document_revision,
            base_intent_revision=session.base_intent_revision,
            intent=content,
            volume=volume,
            previous_chapter_summary=previous_summary,
            previous_chapter_text_available=session.before_chapter_id is not None,
            continuity_volume_id=(
                continuity_chapters[0].volume_id if continuity_chapters else None
            ),
            continuity_chapter_ids=tuple(chapter.chapter_id for chapter in continuity_chapters),
            revision_source_chapter_id=(
                session.target_chapter_id if session.mode is WritingSessionMode.REVISE else None
            ),
            important_entities=self._canon.list_entities(),
            query_capabilities=(
                "session continuity-status",
                "session revision-source",
                "memory volumes",
                "memory chapters",
                "memory search-summaries",
                "memory read-chapter",
                "memory entity-line",
                "draft entity-candidates",
                "resolve entity",
                "query character",
                "query event-chain",
            ),
        )

    def continuity_status(self, writing_session_id: UUID) -> ContinuityStatus:
        session = self._runs.load_session(writing_session_id)
        continuity_chapters = self._continuity_chapters(session)
        retrieved = self._runs.list_retrieved_sources(writing_session_id)
        chapter_statuses = tuple(
            ContinuityChapterStatus(
                volume_id=chapter.volume_id,
                chapter_id=chapter.chapter_id,
                document_id=chapter.source_document_id,
                document_revision=chapter.revision,
                narrative_order=chapter.narrative_order,
                retrieved_source_ids=tuple(
                    source.retrieved_source_id
                    for source in retrieved
                    if source.retrieval_kind is RetrievalKind.EXACT_CHAPTER
                    and source.volume_id == chapter.volume_id
                    and source.chapter_id == chapter.chapter_id
                    and source.document_id == chapter.source_document_id
                    and source.document_revision == chapter.revision
                ),
                satisfied=any(
                    source.retrieval_kind is RetrievalKind.EXACT_CHAPTER
                    and source.volume_id == chapter.volume_id
                    and source.chapter_id == chapter.chapter_id
                    and source.document_id == chapter.source_document_id
                    and source.document_revision == chapter.revision
                    for source in retrieved
                ),
            )
            for chapter in continuity_chapters
        )
        missing_chapter_ids = tuple(
            chapter.chapter_id for chapter in chapter_statuses if not chapter.satisfied
        )
        revision_source_ids = tuple(
            source.retrieved_source_id
            for source in retrieved
            if session.mode is WritingSessionMode.REVISE
            and source.retrieval_kind is RetrievalKind.EXACT_CHAPTER
            and source.volume_id == session.target_volume_id
            and source.chapter_id == session.target_chapter_id
            and source.document_id == session.target_document_id
            and source.document_revision == session.base_document_revision
        )
        revision_source_satisfied = session.mode is WritingSessionMode.CREATE or bool(
            revision_source_ids
        )
        return ContinuityStatus(
            writing_session_id=writing_session_id,
            continuity_volume_id=(
                continuity_chapters[0].volume_id if continuity_chapters else None
            ),
            required_chapters=chapter_statuses,
            missing_chapter_ids=missing_chapter_ids,
            revision_source_chapter_id=(
                session.target_chapter_id if session.mode is WritingSessionMode.REVISE else None
            ),
            revision_source_retrieved_source_ids=revision_source_ids,
            revision_source_satisfied=revision_source_satisfied,
            satisfied=not missing_chapter_ids and revision_source_satisfied,
        )

    def require_continuity(self, writing_session_id: UUID) -> ContinuityStatus:
        status = self.continuity_status(writing_session_id)
        if not status.satisfied:
            requirements = [
                *(f"continuity Chapter {chapter_id}" for chapter_id in status.missing_chapter_ids),
                *(
                    (f"revision source Chapter {status.revision_source_chapter_id}",)
                    if not status.revision_source_satisfied
                    else ()
                ),
            ]
            raise WorkflowStateError("Draft requires exact reads for " + ", ".join(requirements))
        return status

    def require_draft_format(self, writing_session_id: UUID, text: str) -> None:
        session = self._runs.load_session(writing_session_id)
        required = session.required_chapter_heading
        lines = text.splitlines()
        first_line = lines[0] if lines else ""
        if first_line != required:
            raise WorkflowStateError("Chapter Draft must begin with exact heading: " + required)

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

    def _continuity_chapters(self, session: WritingSession) -> tuple[Chapter, ...]:
        if session.before_chapter_id is None:
            return ()
        previous_chapter = self._canon.get_chapter(session.before_chapter_id)
        if previous_chapter is None:
            raise ChapterNotFoundError(
                f"before Chapter does not exist: {session.before_chapter_id}"
            )
        if previous_chapter.volume_id is None:
            raise WorkflowStateError("before Chapter is not assigned to a Volume")
        if (
            previous_chapter.status is not ChapterStatus.APPROVED
            or previous_chapter.narrative_order >= session.target_narrative_order
        ):
            raise WorkflowStateError(
                "before Chapter is not an approved Chapter before the Session boundary"
            )
        return (previous_chapter,)

    def _resolve_target_volume(
        self,
        *,
        volume_id: UUID | None,
        new_volume_number: int | None,
        new_volume_title: str | None,
    ) -> Volume | None:
        new_values = new_volume_number is not None or new_volume_title is not None
        if volume_id is not None and new_values:
            raise ValueError("choose an existing Volume or a new Volume, not both")
        if volume_id is not None:
            volume = self._navigation.get_volume(volume_id)
            if volume is None:
                raise VolumeNotFoundError(f"Volume does not exist: {volume_id}")
            return volume
        if new_volume_number is None or new_volume_title is None:
            raise ValueError("new Volume requires number and title")
        if any(
            volume.volume_number == new_volume_number for volume in self._navigation.list_volumes()
        ):
            raise RevisionConflictError(f"Volume number already exists: {new_volume_number}")
        return None

    def _target_order(
        self,
        *,
        before_chapter_id: UUID | None,
        after_chapter_id: UUID | None,
        target_volume_id: UUID | None,
    ) -> int:
        chapters = sorted(
            (
                chapter
                for volume in self._navigation.list_volumes()
                for chapter, _number in self._navigation.volume_chapters(volume.volume_id)
            ),
            key=lambda chapter: chapter.narrative_order,
        )
        by_id = {chapter.chapter_id: chapter for chapter in chapters}
        before = by_id.get(before_chapter_id) if before_chapter_id is not None else None
        after = by_id.get(after_chapter_id) if after_chapter_id is not None else None
        if before_chapter_id is not None and before is None:
            raise ChapterNotFoundError(f"before Chapter does not exist: {before_chapter_id}")
        if after_chapter_id is not None and after is None:
            raise ChapterNotFoundError(f"after Chapter does not exist: {after_chapter_id}")
        if before is None and after is None:
            if chapters:
                raise WorkflowStateError("non-empty novel requires an explicit Chapter boundary")
            return NARRATIVE_ORDER_STEP
        if before is not None and after is not None:
            if before.narrative_order >= after.narrative_order:
                raise WorkflowStateError("before Chapter must precede after Chapter")
            between = [
                chapter
                for chapter in chapters
                if before.narrative_order < chapter.narrative_order < after.narrative_order
            ]
            if between:
                raise WorkflowStateError("Session boundaries must be adjacent")
            if target_volume_id is not None and (
                before.volume_id != target_volume_id or after.volume_id != target_volume_id
            ):
                raise WorkflowStateError("insertion boundaries must belong to target Volume")
            gap = after.narrative_order - before.narrative_order
            if gap <= 1:
                raise WorkflowStateError("no stable Narrative Order slot remains between Chapters")
            return before.narrative_order + gap // 2
        if before is not None:
            if chapters[-1].chapter_id != before.chapter_id:
                raise WorkflowStateError(
                    "an omitted after boundary means append after the last Chapter"
                )
            return before.narrative_order + NARRATIVE_ORDER_STEP
        assert after is not None
        if chapters[0].chapter_id != after.chapter_id:
            raise WorkflowStateError(
                "an omitted before boundary means insert before the first Chapter"
            )
        if after.narrative_order <= 1:
            raise WorkflowStateError(
                "no stable Narrative Order slot remains before the first Chapter"
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

    def volumes(self, session_id: UUID) -> tuple[VolumeSummaryItem, ...]:
        session = self._open(session_id)
        items = tuple(
            item
            for item in self._memory.volumes()
            if item.summary is None
            or max(
                (
                    chapter.narrative_order
                    for chapter_item in self._memory.chapters(item.volume.volume_id)
                    for chapter in (chapter_item.chapter,)
                ),
                default=0,
            )
            < session.target_narrative_order
        )
        for item in items:
            if item.summary is not None:
                self._record(
                    session,
                    RetrievalKind.VOLUME_SUMMARY,
                    volume_id=item.volume.volume_id,
                    reason="Session Volume navigation",
                )
        return items

    def chapters(self, session_id: UUID, volume_id: UUID) -> tuple[VolumeChapterItem, ...]:
        session = self._open(session_id)
        items = tuple(
            item
            for item in self._memory.chapters(volume_id)
            if item.chapter.narrative_order < session.target_narrative_order
        )
        for item in items:
            if item.summary is not None:
                self._record(
                    session,
                    RetrievalKind.CHAPTER_SUMMARY,
                    volume_id=volume_id,
                    chapter_id=item.chapter.chapter_id,
                    document_id=item.chapter.source_document_id,
                    document_revision=item.chapter.revision,
                    reason="Session Chapter navigation",
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
            if isinstance(hit.summary, VolumeSummary):
                self._record(
                    session,
                    RetrievalKind.VOLUME_SUMMARY,
                    volume_id=hit.summary.volume_id,
                    reason=hit.match_reason,
                )
            else:
                self._record(
                    session,
                    RetrievalKind.CHAPTER_SUMMARY,
                    volume_id=hit.summary.volume_id,
                    chapter_id=hit.summary.chapter_id,
                    document_id=hit.summary.source_document_id,
                    document_revision=hit.summary.source_revision,
                    reason=hit.match_reason,
                )
        return hits

    def read(self, session_id: UUID, *, volume_id: UUID, chapter_id: UUID) -> ExactChapterText:
        session = self._open(session_id)
        result = self._memory.read_chapter_before_order(
            volume_id=volume_id,
            chapter_id=chapter_id,
            before_narrative_order=session.target_narrative_order,
        )
        self._record(
            session,
            RetrievalKind.EXACT_CHAPTER,
            volume_id=volume_id,
            chapter_id=chapter_id,
            document_id=result.document.document_id,
            document_revision=result.document.revision,
            reason="Exact approved Chapter read for Writing Session",
        )
        return result

    def revision_source(self, session_id: UUID) -> ExactChapterText:
        session = self._open(session_id)
        if session.mode is not WritingSessionMode.REVISE:
            raise WorkflowStateError("only a Chapter-revision Session has a revision source")
        result = self._memory.read_approved_chapter(
            volume_id=session.target_volume_id,
            chapter_id=session.target_chapter_id,
        )
        if (
            result.document.document_id != session.target_document_id
            or result.document.relative_path != session.target_document_path
            or result.document.revision != session.base_document_revision
            or result.chapter.revision != session.base_document_revision
        ):
            raise RevisionConflictError("revision source changed after Writing Session start")
        self._record(
            session,
            RetrievalKind.EXACT_CHAPTER,
            volume_id=result.volume.volume_id,
            chapter_id=result.chapter.chapter_id,
            document_id=result.document.document_id,
            document_revision=result.document.revision,
            reason="Exact approved revision source read for Writing Session",
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
                RetrievalKind.CHAPTER_TRACE,
                volume_id=item.volume.volume_id,
                chapter_id=item.chapter.chapter_id,
                document_id=item.chapter_trace.source_document_id,
                document_revision=item.chapter_trace.source_revision,
                reason=f"Entity occurrence line for {entity_id}",
            )
        return result

    def validate_canon_chapter_ids(
        self,
        session_id: UUID,
        chapter_ids: tuple[UUID, ...],
    ) -> WritingSession:
        session = self._open(session_id)
        for chapter_id in chapter_ids:
            chapter = self._canon.get_chapter(chapter_id)
            if chapter is None:
                raise ChapterNotFoundError(f"Canon query Chapter does not exist: {chapter_id}")
            if chapter.narrative_order >= session.target_narrative_order:
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
                chapter_id=source_ref.chapter_id,
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
        volume_id: UUID | None = None,
        chapter_id: UUID | None = None,
        document_id: UUID | None = None,
        document_revision: str | None = None,
    ) -> RetrievedSource:
        source = RetrievedSource(
            retrieved_source_id=self._new_id(),
            writing_session_id=session.writing_session_id,
            retrieval_kind=kind,
            volume_id=volume_id,
            chapter_id=chapter_id,
            document_id=document_id,
            document_revision=document_revision,
            retrieval_reason=reason,
            retrieved_at=self._clock(),
        )
        self._sessions.save_retrieved_source(source)
        return source


class EntityResolutionService:
    """Recall visible exact-name candidates and materialize reviewed Chapter Traces."""

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
        draft: ChapterTraceDraft,
        volume: Volume,
        chapter: Chapter,
        document: Document,
        new_id: IdFactory,
    ) -> tuple[ChapterTrace, tuple[Entity, ...]]:
        entries = self._ledger.read_entries()
        snapshot = replay_ledger(entries)
        if snapshot.revision != session.base_canon_revision:
            raise RevisionConflictError("Canon changed after Writing Session start")
        names, entities = self._visible_identity_names(session, entries, snapshot)
        return self._materialize(
            source_revision=draft_revision,
            manuscript=manuscript,
            draft=draft,
            volume=volume,
            chapter=chapter,
            document=document,
            snapshot=snapshot,
            names=names,
            available_entity_ids=set(entities),
            unknown_entity_label="outside the Session boundary",
            new_id=new_id,
        )

    def approved_chapter_candidates(
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
        draft: ChapterTraceDraft,
        volume: Volume,
        chapter: Chapter,
        document: Document,
        new_id: IdFactory,
    ) -> tuple[ChapterTrace, tuple[Entity, ...]]:
        snapshot = replay_ledger(self._ledger.read_entries())
        if snapshot.revision != base_canon_revision:
            raise RevisionConflictError("Canon changed after Trace Backfill source read")
        names, entities = self._all_identity_names(snapshot, chapter.story_time)
        return self._materialize(
            source_revision=source_revision,
            manuscript=manuscript,
            draft=draft,
            volume=volume,
            chapter=chapter,
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
        draft: ChapterTraceDraft,
        volume: Volume,
        chapter: Chapter,
        document: Document,
        snapshot,
        names: dict[str, tuple[UUID, ...]],
        available_entity_ids: set[UUID],
        unknown_entity_label: str,
        new_id: IdFactory,
    ) -> tuple[ChapterTrace, tuple[Entity, ...]]:
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
                    "Chapter Trace Draft does not cover exact Entity candidate at "
                    f"{match.start_offset}:{match.end_offset} ({match.surface_text})"
                )
            missing_candidates = set(match.candidate_entity_ids) - set(
                mention.considered_entity_ids
            )
            if missing_candidates:
                raise WorkflowStateError(
                    "Chapter Trace Draft did not consider all exact Entity candidates: "
                    + ", ".join(str(entity_id) for entity_id in sorted(missing_candidates, key=str))
                )

        for mention in draft.mentions:
            if text[mention.start_offset : mention.end_offset] != mention.surface_text:
                raise WorkflowStateError(
                    f"Chapter Trace Mention span does not match Draft text: "
                    f"{mention.start_offset}:{mention.end_offset}"
                )
            unknown_considered = set(mention.considered_entity_ids) - available_entity_ids
            if unknown_considered:
                raise WorkflowStateError(
                    f"Chapter Trace Mention considered Entities {unknown_entity_label}: "
                    + ", ".join(str(entity_id) for entity_id in sorted(unknown_considered, key=str))
                )
            if mention.resolution_status is EntityResolutionStatus.AMBIGUOUS:
                raise WorkflowStateError(
                    f"Chapter Trace Mention remains ambiguous: {mention.surface_text}"
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

        occurrences: list[ChapterEntityOccurrence] = []
        for occurrence_draft in draft.entity_occurrences:
            entity_id = occurrence_draft.resolved_entity_id
            if occurrence_draft.new_entity_temporary_name is not None:
                entity_id = new_entity_ids[occurrence_draft.new_entity_temporary_name]
            assert entity_id is not None
            occurrences.append(
                ChapterEntityOccurrence(
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
            ChapterTrace(
                chapter_trace_id=new_id(),
                chapter_id=chapter.chapter_id,
                volume_id=volume.volume_id,
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
        chapters = {chapter.chapter_id: chapter for chapter in snapshot.chapters}
        visible_entity_ids: set[UUID] = set()
        visible_aliases = []
        for entry in entries:
            source_chapter = (
                chapters.get(entry.source_chapter_id)
                if entry.source_chapter_id is not None
                else None
            )
            if entry.source_chapter_id is not None and (
                source_chapter is None
                or source_chapter.narrative_order > session.target_narrative_order
                or (
                    source_chapter.narrative_order == session.target_narrative_order
                    and session.mode is WritingSessionMode.CREATE
                )
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
        manuscripts: ManuscriptStore,
        clock: Clock = _utc_now,
    ) -> None:
        self._runs = runs
        self._sessions = sessions
        self._manuscripts = manuscripts
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
        else:
            session = self._runs.load_session(writing_session_id)
            if session.mode is WritingSessionMode.REVISE:
                base = self._manuscripts.read_document(session.target_document_path)
                if manuscript_revision(base) != session.base_document_revision:
                    raise RevisionConflictError(
                        "revision source manuscript changed after Writing Session start"
                    )
                base_label = str(session.base_document_revision)
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
        chapter_summary_text: str,
        volume_summary_text: str,
        chapter_trace_draft: ChapterTraceDraft,
        review_refs: tuple[UUID, ...],
        chapter_main_entity_ids: tuple[UUID, ...] = (),
        chapter_key_changes: tuple[str, ...] = (),
        chapter_open_questions: tuple[str, ...] = (),
        volume_main_entity_ids: tuple[UUID, ...] = (),
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
        if draft.base_document_revision != session.base_document_revision:
            raise RevisionConflictError("Draft does not bind the Writing Session Document base")
        snapshot = replay_ledger(self._ledger.read_entries())
        if snapshot.revision != session.base_canon_revision:
            raise RevisionConflictError("Canon changed after Writing Session start")
        current_intent = self._intent.load()
        if intent_revision(current_intent) != session.base_intent_revision:
            raise RevisionConflictError("Intent changed after Writing Session start")

        current_documents = {item.document_id: item for item in snapshot.documents}
        current_chapters = {item.chapter_id: item for item in snapshot.chapters}
        base_document = current_documents.get(session.target_document_id)
        base_chapter = current_chapters.get(session.target_chapter_id)
        if session.mode is WritingSessionMode.REVISE:
            if base_document is None or base_chapter is None:
                raise RevisionConflictError("revision target left current Text Canon")
            if (
                base_document.relative_path != session.target_document_path
                or base_document.document_kind is not DocumentKind.MANUSCRIPT
                or base_document.revision != session.base_document_revision
                or base_chapter.volume_id != session.target_volume_id
                or base_chapter.chapter_number != session.target_chapter_number
                or base_chapter.title != session.target_chapter_title
                or base_chapter.narrative_order != session.target_narrative_order
                or base_chapter.story_time != session.target_story_time
                or base_chapter.pov_entity_id != session.pov_entity_id
                or base_chapter.location_entity_id != session.location_entity_id
                or base_chapter.status is not ChapterStatus.APPROVED
                or base_chapter.source_document_id != base_document.document_id
                or base_chapter.revision != base_document.revision
            ):
                raise RevisionConflictError("revision target changed after Writing Session start")
            current_manuscript = self._manuscripts.read_document(base_document.relative_path)
            if manuscript_revision(current_manuscript) != session.base_document_revision:
                raise RevisionConflictError("revision source manuscript bytes changed")
            if digest == session.base_document_revision:
                raise ValueError("Chapter revision must change the approved manuscript bytes")
        elif base_document is not None or base_chapter is not None:
            raise RevisionConflictError("new Chapter target identity already exists")

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
        chapter = Chapter(
            chapter_id=session.target_chapter_id,
            volume_id=session.target_volume_id,
            chapter_number=session.target_chapter_number,
            title=session.target_chapter_title,
            narrative_order=session.target_narrative_order,
            story_time=session.target_story_time,
            pov_entity_id=session.pov_entity_id,
            location_entity_id=session.location_entity_id,
            status=ChapterStatus.APPROVED,
            source_document_id=document.document_id,
            revision=digest,
        )
        volume = self._updated_volume(session)
        projected_chapter_summary = self._navigation.get_chapter_summary(session.target_chapter_id)
        projected_volume_summary = self._navigation.get_volume_summary(session.target_volume_id)
        projected_chapter_trace = self._navigation.get_chapter_trace(session.target_chapter_id)
        base_chapter_summary = (
            projected_chapter_summary[0] if projected_chapter_summary is not None else None
        )
        base_volume_summary = (
            projected_volume_summary[0] if projected_volume_summary is not None else None
        )
        base_chapter_trace = (
            projected_chapter_trace[0] if projected_chapter_trace is not None else None
        )
        if session.mode is WritingSessionMode.CREATE and any(
            item is not None for item in (base_chapter_summary, base_chapter_trace)
        ):
            raise RevisionConflictError("new Chapter already has navigation memory")
        chapter_trace, new_entities = self._entity_resolution.materialize(
            session=session,
            draft_revision=draft_revision,
            manuscript=manuscript,
            draft=chapter_trace_draft,
            volume=volume,
            chapter=chapter,
            document=document,
            new_id=self._new_id,
        )
        trace_main_entity_ids = tuple(
            occurrence.entity_id
            for occurrence in chapter_trace.entity_occurrences
            if occurrence.prominence
            in {
                EntityProminence.FOCUS,
                EntityProminence.SUPPORTING,
            }
        )
        chapter_main_entity_ids = _unique_ids((*chapter_main_entity_ids, *trace_main_entity_ids))
        volume_main_entity_ids = _unique_ids((*volume_main_entity_ids, *trace_main_entity_ids))
        known_entity_ids = {
            *(entity.entity_id for entity in snapshot.entities),
            *(entity.entity_id for entity in new_entities),
        }
        unknown_entity_ids = (
            set(chapter_main_entity_ids) | set(volume_main_entity_ids)
        ) - known_entity_ids
        if unknown_entity_ids:
            raise ValueError(
                "navigation summaries reference unknown Entity IDs: "
                f"{sorted(map(str, unknown_entity_ids))}"
            )
        chapter_summary = ChapterSummary(
            chapter_id=chapter.chapter_id,
            volume_id=volume.volume_id,
            chapter_number_in_volume=volume.chapter_ids.index(chapter.chapter_id) + 1,
            source_document_id=document.document_id,
            source_revision=document.revision,
            summary=chapter_summary_text,
            main_entity_ids=chapter_main_entity_ids,
            key_changes=chapter_key_changes,
            open_questions=chapter_open_questions,
        )
        volume_summary = self._build_volume_summary(
            volume,
            chapter_summary,
            summary_text=volume_summary_text,
            main_entity_ids=volume_main_entity_ids,
        )

        prepared_at = self._clock()
        change_sets = [
            record.value for record in canon_records if record.record_type == "canon_change_set"
        ]
        if len(change_sets) > 1:
            raise ValueError("Publication Canon can contain at most one Change Set")
        approved_at = change_sets[0].approved_at if change_sets else prepared_at
        source_chapter_id = change_sets[0].source_chapter_id if change_sets else chapter.chapter_id
        if source_chapter_id != chapter.chapter_id:
            raise ValueError("Publication Canon Change Set must bind the target Chapter")
        ledger_entry = CanonLedgerEntry(
            ledger_sequence=snapshot.last_sequence + 1,
            ledger_entry_id=self._new_id(),
            base_revision=snapshot.revision,
            approved_at=approved_at,
            source_chapter_id=chapter.chapter_id,
            records=(
                *(EntityLedgerRecord(value=entity) for entity in new_entities),
                DocumentLedgerRecord(value=document),
                ChapterLedgerRecord(value=chapter),
                *canon_records,
            ),
        )
        replay_ledger((*snapshot.entries, ledger_entry))
        for record in canon_records:
            if isinstance(record, SourceRefLedgerRecord):
                source_ref = record.value
                if (
                    source_ref.document_id != document.document_id
                    or source_ref.chapter_id != chapter.chapter_id
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
            (
                current_manuscript.decode("utf-8")
                if session.mode is WritingSessionMode.REVISE
                else ""
            ),
            manuscript.decode("utf-8"),
            (
                f"{document.relative_path}@{session.base_document_revision}"
                if session.mode is WritingSessionMode.REVISE
                else "/dev/null"
            ),
            document.relative_path,
        )
        before_structure = (
            base_chapter.to_canonical_json() + "\n" + volume.to_canonical_json()
            if session.mode is WritingSessionMode.REVISE
            else ""
        )
        structure_diff = _text_diff(
            before_structure,
            chapter.to_canonical_json() + "\n" + volume.to_canonical_json(),
            (
                f"chapter-structure:{chapter.chapter_id}:base"
                if session.mode is WritingSessionMode.REVISE
                else "/dev/null"
            ),
            f"volume:{volume.volume_id}",
        )
        before_summaries = "\n".join(
            item.to_canonical_json()
            for item in (base_chapter_summary, base_volume_summary)
            if item is not None
        )
        summary_diff = _text_diff(
            before_summaries,
            chapter_summary.to_canonical_json() + "\n" + volume_summary.to_canonical_json(),
            (f"navigation-memory:{chapter.chapter_id}:base" if before_summaries else "/dev/null"),
            "navigation-memory",
        )
        chapter_trace_diff = _text_diff(
            base_chapter_trace.to_canonical_json() if base_chapter_trace is not None else "",
            chapter_trace.to_canonical_json(),
            (
                f"chapter-trace:{chapter_trace.chapter_id}:base"
                if base_chapter_trace is not None
                else "/dev/null"
            ),
            f"chapter-trace:{chapter_trace.chapter_id}",
        )
        canon_diff = "\n".join(
            f"+ {record.record_type}:{record.value.to_canonical_json()}"
            for record in ledger_entry.records
        )
        protected = {
            "publication_id": str(publication_id),
            "project_id": str(manifest.project_id),
            "writing_session_id": str(writing_session_id),
            "mode": session.mode.value,
            "draft_revision": draft_revision,
            "base_canon_revision": snapshot.revision,
            "base_document_revision": session.base_document_revision,
            "base_chapter_summary_digest": _model_digest(base_chapter_summary),
            "base_volume_summary_digest": _model_digest(base_volume_summary),
            "base_chapter_trace_digest": _model_digest(base_chapter_trace),
            "base_intent_revision": session.base_intent_revision,
            "target_document": document.model_dump(mode="json"),
            "chapter_change": chapter.model_dump(mode="json"),
            "volume_change": volume.model_dump(mode="json"),
            "chapter_summary_change": chapter_summary.model_dump(mode="json"),
            "volume_summary_change": volume_summary.model_dump(mode="json"),
            "chapter_trace_change": chapter_trace.model_dump(mode="json"),
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
            mode=session.mode,
            draft_revision=draft_revision,
            base_canon_revision=snapshot.revision,
            base_document_revision=session.base_document_revision,
            base_chapter_summary_digest=_model_digest(base_chapter_summary),
            base_volume_summary_digest=_model_digest(base_volume_summary),
            base_chapter_trace_digest=_model_digest(base_chapter_trace),
            base_intent_revision=session.base_intent_revision,
            target_document=document,
            chapter_change=chapter,
            volume_change=volume,
            chapter_summary_change=chapter_summary,
            volume_summary_change=volume_summary,
            chapter_trace_change=chapter_trace,
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
            chapter_trace_diff=chapter_trace_diff,
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

        publication = self._set_status(publication, PublicationStatus.APPLYING)
        if plan.mode is WritingSessionMode.REVISE:
            assert plan.base_document_revision is not None
            self._manuscripts.replace_document(
                plan.target_document.relative_path,
                expected_revision=plan.base_document_revision,
                content=manuscript,
            )
        else:
            self._manuscripts.install_document(plan.target_document.relative_path, manuscript)
        publication = self._set_status(publication, PublicationStatus.MANUSCRIPT_INSTALLED)

        self._navigation_sources.save_volume(plan.volume_change)
        self._navigation_sources.save_chapter_summary(plan.chapter_summary_change)
        self._navigation_sources.save_volume_summary(plan.volume_summary_change)
        if plan.chapter_trace_change is not None:
            self._navigation_sources.save_chapter_trace(plan.chapter_trace_change)
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
        if session.mode is not plan.mode:
            raise RevisionConflictError("Publication mode no longer matches its Writing Session")
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
        current_documents = {document.document_id: document for document in snapshot.documents}
        current_chapters = {chapter.chapter_id: chapter for chapter in snapshot.chapters}
        current_document = current_documents.get(plan.target_document.document_id)
        current_chapter = current_chapters.get(plan.chapter_change.chapter_id)
        if existing is None:
            if plan.mode is WritingSessionMode.REVISE:
                if (
                    current_document is None
                    or current_chapter is None
                    or current_document.relative_path != plan.target_document.relative_path
                    or current_document.document_kind is not plan.target_document.document_kind
                    or current_document.revision != plan.base_document_revision
                    or current_chapter.revision != plan.base_document_revision
                    or current_chapter.model_copy(update={"revision": plan.chapter_change.revision})
                    != plan.chapter_change
                ):
                    raise RevisionConflictError(
                        "Chapter revision target no longer matches Publication base"
                    )
            elif current_document is not None or current_chapter is not None:
                raise RevisionConflictError("new Chapter target identity already exists")
        elif current_document != plan.target_document or current_chapter != plan.chapter_change:
            raise RevisionConflictError("installed Text Canon differs from Publication plan")
        current_intent_revision = intent_revision(self._intent.load())
        allowed_intent_revisions = {plan.base_intent_revision}
        if plan.intent_candidate_revision is not None:
            allowed_intent_revisions.add(plan.intent_candidate_revision)
        if current_intent_revision not in allowed_intent_revisions:
            raise RevisionConflictError("Intent no longer matches Publication base or candidate")
        current_volume = self._navigation.get_volume(session.target_volume_id)
        if (
            current_volume != plan.volume_change
            and self._updated_volume(session) != plan.volume_change
        ):
            raise RevisionConflictError("Volume structure changed after Publication prepare")
        self._validate_navigation_base(
            label="Chapter Summary",
            current=(
                projected[0]
                if (projected := self._navigation.get_chapter_summary(session.target_chapter_id))
                is not None
                else None
            ),
            base_digest=plan.base_chapter_summary_digest,
            target=plan.chapter_summary_change,
        )
        self._validate_navigation_base(
            label="Volume Summary",
            current=(
                projected[0]
                if (projected := self._navigation.get_volume_summary(session.target_volume_id))
                is not None
                else None
            ),
            base_digest=plan.base_volume_summary_digest,
            target=plan.volume_summary_change,
        )
        self._validate_navigation_base(
            label="Chapter Trace",
            current=(
                projected[0]
                if (projected := self._navigation.get_chapter_trace(session.target_chapter_id))
                is not None
                else None
            ),
            base_digest=plan.base_chapter_trace_digest,
            target=plan.chapter_trace_change,
        )

    @staticmethod
    def _validate_navigation_base(
        *,
        label: str,
        current,
        base_digest: str | None,
        target,
    ) -> None:
        current_digest = _model_digest(current)
        target_digest = _model_digest(target)
        if current_digest not in {base_digest, target_digest}:
            raise RevisionConflictError(f"{label} changed after Publication prepare")

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

    def _updated_volume(self, session: WritingSession) -> Volume:
        current = self._navigation.get_volume(session.target_volume_id)
        if session.mode is WritingSessionMode.REVISE:
            if current is None or session.target_chapter_id not in current.chapter_ids:
                raise RevisionConflictError("revision target left its Volume")
            if (
                current.volume_number != session.target_volume_number
                or current.title != session.target_volume_title
            ):
                raise RevisionConflictError("revision target Volume metadata changed")
            return current
        if current is None:
            return Volume(
                volume_id=session.target_volume_id,
                volume_number=session.target_volume_number,
                title=session.target_volume_title,
                chapter_ids=(session.target_chapter_id,),
            )
        chapter_ids = list(current.chapter_ids)
        if session.before_chapter_id is None:
            index = 0
        else:
            try:
                index = chapter_ids.index(session.before_chapter_id) + 1
            except ValueError as exc:
                raise RevisionConflictError("Session before boundary left its Volume") from exc
        if session.after_chapter_id is not None:
            try:
                after_index = chapter_ids.index(session.after_chapter_id)
            except ValueError as exc:
                raise RevisionConflictError("Session after boundary left its Volume") from exc
            if after_index != index:
                raise RevisionConflictError("Session Volume boundaries are no longer adjacent")
        elif index != len(chapter_ids):
            raise RevisionConflictError("Session append boundary is no longer Volume end")
        chapter_ids.insert(index, session.target_chapter_id)
        return current.model_copy(update={"chapter_ids": tuple(chapter_ids)})

    def _build_volume_summary(
        self,
        volume: Volume,
        new_chapter_summary: ChapterSummary,
        *,
        summary_text: str,
        main_entity_ids: tuple[UUID, ...],
    ) -> VolumeSummary:
        summaries: dict[UUID, ChapterSummary] = {
            new_chapter_summary.chapter_id: new_chapter_summary
        }
        for chapter_id in volume.chapter_ids:
            if chapter_id == new_chapter_summary.chapter_id:
                continue
            projected = self._navigation.get_chapter_summary(chapter_id)
            if projected is None or projected[1]:
                raise WorkflowStateError(
                    f"Publication Volume Summary requires current Chapter Summary: {chapter_id}"
                )
            summaries[chapter_id] = projected[0]
        ordered = tuple(summaries[chapter_id] for chapter_id in volume.chapter_ids)
        summary = VolumeSummary(
            volume_id=volume.volume_id,
            volume_number=volume.volume_number,
            title=volume.title,
            chapter_ids=volume.chapter_ids,
            chapter_summary_dependencies=tuple(
                ChapterSummaryDependency(
                    chapter_id=item.chapter_id,
                    source_revision=item.source_revision,
                    summary_digest=chapter_summary_digest(item),
                )
                for item in ordered
            ),
            summary=summary_text,
            main_entity_ids=main_entity_ids,
        )
        if volume_summary_is_stale(
            summary,
            volume=volume,
            chapter_summaries=summaries,
            stale_chapter_ids=set(),
        ):
            raise ValueError("Volume Summary does not bind current Chapter Summaries")
        return summary


class ChapterTraceBackfillService:
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
        backfills: ChapterTraceBackfillStore,
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
        volume_id: UUID,
        chapter_id: UUID,
    ) -> ChapterTraceBackfillSource:
        manifest = self._projects.load_manifest()
        _require_ready(manifest)
        volume, chapter, document, manuscript = self._approved_chapter(
            volume_id=volume_id,
            chapter_id=chapter_id,
        )
        projected_trace = self._navigation.get_chapter_trace(chapter_id)
        current_trace = projected_trace[0] if projected_trace is not None else None
        snapshot = replay_ledger(self._ledger.read_entries())
        text = manuscript.decode("utf-8")
        exact_candidates = self._entity_resolution.approved_chapter_candidates(
            text,
            story_time=chapter.story_time,
        )
        candidate_entity_ids = {
            entity_id
            for candidate in exact_candidates
            for entity_id in candidate.candidate_entity_ids
        }
        entities = {entity.entity_id: entity for entity in snapshot.entities}
        return ChapterTraceBackfillSource(
            project_id=manifest.project_id,
            base_canon_revision=snapshot.revision,
            volume=volume,
            chapter=chapter,
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
                chapter_trace_digest(current_trace) if current_trace is not None else None
            ),
        )

    def entity_line(self, entity_id: UUID) -> EntityLine:
        entity = self._canon.get_entity(entity_id)
        if entity is None:
            raise ValueError(f"entity does not exist: {entity_id}")
        chapters = replay_ledger(self._ledger.read_entries()).chapters
        before_narrative_order = (
            max(chapter.narrative_order for chapter in chapters) + 1 if chapters else 1
        )
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
        volume_id: UUID,
        chapter_id: UUID,
        source_revision: str,
        chapter_trace_draft: ChapterTraceDraft,
    ) -> ChapterTraceBackfill:
        source = self.source(volume_id=volume_id, chapter_id=chapter_id)
        if source.source_revision != source_revision:
            raise RevisionConflictError("Trace Backfill source revision changed")
        manuscript = source.text.encode("utf-8")
        trace, new_entities = self._entity_resolution.materialize_backfill(
            base_canon_revision=source.base_canon_revision,
            source_revision=source_revision,
            manuscript=manuscript,
            draft=chapter_trace_draft,
            volume=source.volume,
            chapter=source.chapter,
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
                source_chapter_id=source.chapter.chapter_id,
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
        chapter_trace_diff = _text_diff(
            before_trace,
            trace.to_canonical_json(),
            (
                f"chapter-trace:{chapter_id}:base"
                if source.current_trace is not None
                else "/dev/null"
            ),
            f"chapter-trace:{chapter_id}:candidate",
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
            "volume_id": str(volume_id),
            "chapter_id": str(chapter_id),
            "source_document_id": str(source.document.document_id),
            "source_revision": source_revision,
            "base_canon_revision": source.base_canon_revision,
            "base_chapter_trace_digest": source.current_trace_digest,
            "chapter_trace_change": trace.model_dump(mode="json"),
            "ledger_entry": (
                ledger_entry.model_dump(mode="json") if ledger_entry is not None else None
            ),
        }
        plan = ChapterTraceBackfillPlan(
            backfill_id=backfill_id,
            project_id=source.project_id,
            volume_id=volume_id,
            chapter_id=chapter_id,
            source_document_id=source.document.document_id,
            source_revision=source_revision,
            base_canon_revision=source.base_canon_revision,
            base_chapter_trace_digest=source.current_trace_digest,
            chapter_trace_change=trace,
            ledger_entry=ledger_entry,
            chapter_trace_diff=chapter_trace_diff,
            canon_diff=canon_diff,
            approval_digest=approval_digest("chapter_trace_backfill", protected),
            prepared_at=prepared_at,
        )
        backfill = ChapterTraceBackfill(
            plan=plan,
            status=ChapterTraceBackfillStatus.PREPARED,
        )
        self._backfills.create(backfill)
        return backfill

    def inspect(self, backfill_id: UUID) -> ChapterTraceBackfill:
        return self._backfills.load(backfill_id)

    def approve(self, backfill_id: UUID, digest: str) -> ChapterTraceBackfill:
        backfill = self._backfills.load(backfill_id)
        if backfill.status is not ChapterTraceBackfillStatus.PREPARED:
            raise WorkflowStateError("only a prepared Trace Backfill can be approved")
        if digest != backfill.plan.approval_digest:
            raise ApprovalMismatchError("Trace Backfill approval digest does not match")
        approved = backfill.model_copy(
            update={
                "status": ChapterTraceBackfillStatus.APPROVED,
                "approval": Approval(
                    operation_id=backfill_id,
                    approval_digest=digest,
                    approved_at=self._clock(),
                ),
            }
        )
        self._backfills.replace(approved)
        return approved

    def apply(self, backfill_id: UUID) -> ChapterTraceBackfill:
        return self._advance(backfill_id)

    def recover(self, backfill_id: UUID) -> ChapterTraceBackfill:
        return self._advance(backfill_id)

    def _advance(self, backfill_id: UUID) -> ChapterTraceBackfill:
        with self._write_lock.acquire():
            backfill = self._backfills.load(backfill_id)
            if backfill.status is ChapterTraceBackfillStatus.COMPLETED:
                return backfill
            if backfill.status is ChapterTraceBackfillStatus.PREPARED:
                raise WorkflowStateError("Trace Backfill must be approved before apply")
            try:
                return self._advance_under_lock(backfill)
            except Exception as exc:
                stored = self._backfills.load(backfill_id)
                if stored.status is ChapterTraceBackfillStatus.APPROVED:
                    raise
                raise TraceBackfillRecoveryRequiredError(
                    f"Trace Backfill {backfill_id} requires recover: {exc}"
                ) from exc

    def _advance_under_lock(
        self,
        backfill: ChapterTraceBackfill,
    ) -> ChapterTraceBackfill:
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
        backfill = self._set_status(backfill, ChapterTraceBackfillStatus.LEDGER_APPENDED)

        self._navigation_sources.save_chapter_trace(plan.chapter_trace_change)
        backfill = self._set_status(backfill, ChapterTraceBackfillStatus.TRACE_INSTALLED)

        snapshot = replay_ledger(self._ledger.read_entries())
        self._projection.replace(manifest, snapshot)
        backfill = self._set_status(backfill, ChapterTraceBackfillStatus.PROJECTION_REBUILT)

        completed = backfill.model_copy(
            update={
                "status": ChapterTraceBackfillStatus.COMPLETED,
                "completed_at": self._clock(),
            }
        )
        self._backfills.replace(completed)
        return completed

    def _validate_preflight(self, plan: ChapterTraceBackfillPlan) -> None:
        manifest = self._projects.load_manifest()
        if manifest.project_id != plan.project_id:
            raise WorkflowStateError("Trace Backfill belongs to another Project")
        _volume, _chapter, document, _manuscript = self._approved_chapter(
            volume_id=plan.volume_id,
            chapter_id=plan.chapter_id,
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

        projected_trace = self._navigation.get_chapter_trace(plan.chapter_id)
        current_trace = projected_trace[0] if projected_trace is not None else None
        current_digest = chapter_trace_digest(current_trace) if current_trace is not None else None
        candidate_digest = chapter_trace_digest(plan.chapter_trace_change)
        if current_digest not in {
            plan.base_chapter_trace_digest,
            candidate_digest,
        }:
            raise RevisionConflictError("Chapter Trace changed after Backfill prepare")

    def _approved_chapter(
        self,
        *,
        volume_id: UUID,
        chapter_id: UUID,
    ) -> tuple[Volume, Chapter, Document, bytes]:
        volume = self._navigation.get_volume(volume_id)
        if volume is None:
            raise VolumeNotFoundError(f"Trace Backfill Volume does not exist: {volume_id}")
        volume_chapter_ids = {
            chapter.chapter_id for chapter, _number in self._navigation.volume_chapters(volume_id)
        }
        chapter = self._canon.get_chapter(chapter_id)
        if chapter is None:
            raise ChapterNotFoundError(f"Trace Backfill Chapter does not exist: {chapter_id}")
        if chapter_id not in volume_chapter_ids or (
            chapter.volume_id is not None and chapter.volume_id != volume_id
        ):
            raise WorkflowStateError("Trace Backfill Chapter does not belong to the Volume")
        if chapter.status is not ChapterStatus.APPROVED:
            raise WorkflowStateError("Trace Backfill requires an approved Chapter")
        document = self._canon.get_document(chapter.source_document_id)
        if document is None:
            raise WorkflowStateError("Trace Backfill source Document does not exist")
        if document.document_kind is not DocumentKind.MANUSCRIPT:
            raise WorkflowStateError("Trace Backfill source is not manuscript")
        if chapter.revision != document.revision:
            raise RevisionConflictError("Trace Backfill Chapter and Document revisions differ")
        manuscript = self._manuscripts.read_document(document.relative_path)
        if manuscript_revision(manuscript) != document.revision:
            raise RevisionConflictError("Trace Backfill manuscript bytes changed")
        try:
            manuscript.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Trace Backfill manuscript must be UTF-8") from exc
        return volume, chapter, document, manuscript

    def _set_status(
        self,
        backfill: ChapterTraceBackfill,
        status: ChapterTraceBackfillStatus,
    ) -> ChapterTraceBackfill:
        if _trace_backfill_status_index(backfill.status) >= _trace_backfill_status_index(status):
            return backfill
        updated = backfill.model_copy(update={"status": status})
        self._backfills.replace(updated)
        return updated


def _publication_status_index(status: PublicationStatus) -> int:
    return list(PublicationStatus).index(status)


def _trace_backfill_status_index(status: ChapterTraceBackfillStatus) -> int:
    return list(ChapterTraceBackfillStatus).index(status)


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


def _model_digest(model) -> str | None:
    if model is None:
        return None
    return "sha256:" + hashlib.sha256(model.to_canonical_json().encode("utf-8")).hexdigest()


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
