"""Strict, versioned contracts for the approved local creation loop."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from novel_core._base import VersionedDomainModel
from novel_core.canon import CanonLedgerEntry
from novel_core.chronology import StoryTime
from novel_core.identity import Entity
from novel_core.identity.models import EntityType
from novel_core.navigation import (
    ChapterSummary,
    ChapterTrace,
    EntityMentionForm,
    EntityPresenceKind,
    EntityProminence,
    EntityResolutionStatus,
    Volume,
    VolumeSummary,
)
from novel_core.projects import Chapter, Document

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
IntentText = Annotated[
    str,
    StringConstraints(min_length=1, strip_whitespace=False),
]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
TextTuple = Annotated[tuple[NonEmptyText, ...], Field(max_length=64)]


def _digest_payload(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class IntentContent(VersionedDomainModel):
    """The four authoritative, reviewable Intent Canon documents."""

    creative_brief: IntentText
    story_bible: IntentText
    writing_rules: IntentText
    current_outline: IntentText

    @field_validator(
        "creative_brief",
        "story_bible",
        "writing_rules",
        "current_outline",
    )
    @classmethod
    def validate_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Intent documents must contain non-whitespace text")
        return value


def intent_revision(content: IntentContent | None) -> str:
    """Return the stable revision of a complete Intent snapshot."""

    if content is None:
        return f"sha256:{hashlib.sha256(b'').hexdigest()}"
    return _digest_payload(content.model_dump(mode="json"))


def approval_digest(kind: str, protected_content: Any) -> str:
    """Bind an approval to one operation kind and its exact protected content."""

    return _digest_payload({"kind": kind, "protected_content": protected_content})


class Approval(VersionedDomainModel):
    operation_id: UUID
    approval_digest: Sha256Digest
    approved_at: AwareDatetime


class BootstrapEntityDraft(VersionedDomainModel):
    temporary_name: NonEmptyText
    entity_type: EntityType
    display_name: NonEmptyText


class BootstrapEntityResolution(VersionedDomainModel):
    temporary_name: NonEmptyText
    entity: Entity


class BootstrapDraft(VersionedDomainModel):
    intent: IntentContent
    entity_drafts: tuple[BootstrapEntityDraft, ...] = ()
    initial_goal: NonEmptyText
    unresolved_questions: TextTuple = ()

    @field_validator("entity_drafts")
    @classmethod
    def validate_unique_drafts(
        cls,
        value: tuple[BootstrapEntityDraft, ...],
    ) -> tuple[BootstrapEntityDraft, ...]:
        names = [draft.temporary_name for draft in value]
        if len(names) != len(set(names)):
            raise ValueError("Bootstrap temporary Entity names must be unique")
        return value


class BootstrapContent(VersionedDomainModel):
    intent: IntentContent
    entity_resolutions: tuple[BootstrapEntityResolution, ...] = ()
    initial_goal: NonEmptyText
    unresolved_questions: TextTuple = ()

    @field_validator("entity_resolutions")
    @classmethod
    def validate_unique_entities(
        cls,
        value: tuple[BootstrapEntityResolution, ...],
    ) -> tuple[BootstrapEntityResolution, ...]:
        ids = [resolution.entity.entity_id for resolution in value]
        names = [resolution.temporary_name for resolution in value]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)):
            raise ValueError("Bootstrap Entity resolutions must have unique names and IDs")
        return value


class BootstrapStatus(StrEnum):
    DRAFTING = "drafting"
    PREPARED = "prepared"
    APPROVED = "approved"
    APPLIED = "applied"


class BootstrapRun(VersionedDomainModel):
    bootstrap_id: UUID
    project_id: UUID
    base_canon_revision: Sha256Digest
    base_intent_revision: Sha256Digest
    revision: int = Field(ge=0)
    status: BootstrapStatus
    content: BootstrapContent | None = None
    content_digest: Sha256Digest | None = None
    intent_diff: NonEmptyText | None = None
    approval_digest: Sha256Digest | None = None
    approval: Approval | None = None
    created_at: AwareDatetime
    applied_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_state(self) -> BootstrapRun:
        prepared = self.status is not BootstrapStatus.DRAFTING
        protected = (
            self.content,
            self.content_digest,
            self.intent_diff,
            self.approval_digest,
        )
        if prepared and any(value is None for value in protected):
            raise ValueError("prepared Bootstrap requires content, Diff, and digests")
        if self.status is BootstrapStatus.DRAFTING and any(
            value is not None for value in protected
        ):
            raise ValueError("drafting Bootstrap cannot contain a prepared plan")
        if self.status in {BootstrapStatus.APPROVED, BootstrapStatus.APPLIED}:
            if self.approval is None or self.approval.operation_id != self.bootstrap_id:
                raise ValueError("approved Bootstrap requires its exact approval")
            if self.approval.approval_digest != self.approval_digest:
                raise ValueError("Bootstrap approval digest does not match the plan")
        elif self.approval is not None:
            raise ValueError("unapproved Bootstrap cannot contain approval")
        if self.status is BootstrapStatus.APPLIED and self.applied_at is None:
            raise ValueError("applied Bootstrap requires applied_at")
        if self.status is not BootstrapStatus.APPLIED and self.applied_at is not None:
            raise ValueError("only applied Bootstrap can contain applied_at")
        return self


class IntentRevisionStatus(StrEnum):
    PREPARED = "prepared"
    APPROVED = "approved"
    APPLIED = "applied"


class IntentRevision(VersionedDomainModel):
    intent_revision_id: UUID
    project_id: UUID
    base_intent_revision: Sha256Digest
    candidate: IntentContent
    candidate_revision: Sha256Digest
    intent_diff: NonEmptyText
    approval_digest: Sha256Digest
    status: IntentRevisionStatus
    approval: Approval | None = None
    created_at: AwareDatetime
    applied_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_state(self) -> IntentRevision:
        if self.candidate_revision != intent_revision(self.candidate):
            raise ValueError("Intent candidate_revision does not match candidate content")
        if self.status in {IntentRevisionStatus.APPROVED, IntentRevisionStatus.APPLIED}:
            if self.approval is None or self.approval.operation_id != self.intent_revision_id:
                raise ValueError("approved Intent Revision requires its exact approval")
            if self.approval.approval_digest != self.approval_digest:
                raise ValueError("Intent approval digest does not match the plan")
        elif self.approval is not None:
            raise ValueError("prepared Intent Revision cannot contain approval")
        if self.status is IntentRevisionStatus.APPLIED and self.applied_at is None:
            raise ValueError("applied Intent Revision requires applied_at")
        if self.status is not IntentRevisionStatus.APPLIED and self.applied_at is not None:
            raise ValueError("only applied Intent Revision can contain applied_at")
        return self


class WritingSessionStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class WritingSessionMode(StrEnum):
    CREATE = "create"
    REVISE = "revise"


class WritingSession(VersionedDomainModel):
    writing_session_id: UUID
    project_id: UUID
    mode: WritingSessionMode = WritingSessionMode.CREATE
    target_chapter_id: UUID
    target_document_id: UUID
    target_document_path: NonEmptyText
    target_chapter_number: int = Field(ge=1)
    target_chapter_title: NonEmptyText
    target_volume_id: UUID
    target_volume_number: int = Field(ge=1)
    target_volume_title: NonEmptyText
    required_chapter_heading: NonEmptyText
    target_narrative_order: int = Field(ge=1)
    target_story_time: StoryTime
    pov_entity_id: UUID | None = None
    location_entity_id: UUID | None = None
    before_chapter_id: UUID | None = None
    after_chapter_id: UUID | None = None
    base_canon_revision: Sha256Digest
    base_document_revision: Sha256Digest | None = None
    base_intent_revision: Sha256Digest
    author_goal: NonEmptyText
    creative_constraints: TextTuple = ()
    status: WritingSessionStatus
    created_at: AwareDatetime
    closed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_state(self) -> WritingSession:
        if self.target_chapter_id in {self.before_chapter_id, self.after_chapter_id}:
            raise ValueError("target Chapter cannot be one of its position boundaries")
        if self.before_chapter_id is not None and self.before_chapter_id == self.after_chapter_id:
            raise ValueError("Session boundaries must be different Chapters")
        if self.status is WritingSessionStatus.CLOSED and self.closed_at is None:
            raise ValueError("closed Writing Session requires closed_at")
        if self.status is WritingSessionStatus.OPEN and self.closed_at is not None:
            raise ValueError("open Writing Session cannot contain closed_at")
        if not self.target_document_path.startswith("manuscript/"):
            raise ValueError("target_document_path must be inside manuscript/")
        if self.mode is WritingSessionMode.CREATE and self.base_document_revision is not None:
            raise ValueError("new-Chapter Writing Session cannot have a base Document revision")
        if self.mode is WritingSessionMode.REVISE and self.base_document_revision is None:
            raise ValueError("Chapter-revision Writing Session requires a base Document revision")
        return self


class RetrievalKind(StrEnum):
    VOLUME_SUMMARY = "volume_summary"
    CHAPTER_SUMMARY = "chapter_summary"
    CHAPTER_TRACE = "chapter_trace"
    EXACT_CHAPTER = "exact_chapter"
    CANON_QUERY = "canon_query"


class RetrievedSource(VersionedDomainModel):
    retrieved_source_id: UUID
    writing_session_id: UUID
    retrieval_kind: RetrievalKind
    volume_id: UUID | None = None
    chapter_id: UUID | None = None
    document_id: UUID | None = None
    document_revision: Sha256Digest | None = None
    retrieval_reason: NonEmptyText
    retrieved_at: AwareDatetime


class ContinuityChapterStatus(VersionedDomainModel):
    volume_id: UUID
    chapter_id: UUID
    document_id: UUID
    document_revision: Sha256Digest
    narrative_order: int = Field(ge=1)
    retrieved_source_ids: tuple[UUID, ...] = ()
    satisfied: bool

    @model_validator(mode="after")
    def validate_state(self) -> ContinuityChapterStatus:
        if len(self.retrieved_source_ids) != len(set(self.retrieved_source_ids)):
            raise ValueError("Continuity retrieved_source_ids must be unique")
        if self.satisfied != bool(self.retrieved_source_ids):
            raise ValueError("Continuity Chapter satisfaction must match exact retrieved sources")
        return self


class ContinuityStatus(VersionedDomainModel):
    writing_session_id: UUID
    continuity_volume_id: UUID | None = None
    required_chapters: tuple[ContinuityChapterStatus, ...] = ()
    missing_chapter_ids: tuple[UUID, ...] = ()
    revision_source_chapter_id: UUID | None = None
    revision_source_retrieved_source_ids: tuple[UUID, ...] = ()
    revision_source_satisfied: bool = True
    satisfied: bool

    @model_validator(mode="after")
    def validate_state(self) -> ContinuityStatus:
        if not self.required_chapters:
            if self.continuity_volume_id is not None:
                raise ValueError("empty continuity window cannot identify a Volume")
        else:
            if self.continuity_volume_id is None:
                raise ValueError("continuity window requires a Volume")
            if any(
                chapter.volume_id != self.continuity_volume_id for chapter in self.required_chapters
            ):
                raise ValueError("continuity Chapters must belong to the continuity Volume")
        chapter_ids = tuple(chapter.chapter_id for chapter in self.required_chapters)
        if len(chapter_ids) != len(set(chapter_ids)):
            raise ValueError("continuity window contains duplicate Chapters")
        orders = tuple(chapter.narrative_order for chapter in self.required_chapters)
        if orders != tuple(sorted(orders)) or len(orders) != len(set(orders)):
            raise ValueError("continuity Chapters must have unique ascending Narrative Order")
        expected_missing = tuple(
            chapter.chapter_id for chapter in self.required_chapters if not chapter.satisfied
        )
        if self.missing_chapter_ids != expected_missing:
            raise ValueError("missing_chapter_ids must match unsatisfied continuity Chapters")
        if len(self.revision_source_retrieved_source_ids) != len(
            set(self.revision_source_retrieved_source_ids)
        ):
            raise ValueError("revision source retrieved IDs must be unique")
        if self.revision_source_chapter_id is None:
            if self.revision_source_retrieved_source_ids:
                raise ValueError("new-Chapter continuity cannot contain revision source reads")
            if not self.revision_source_satisfied:
                raise ValueError("new-Chapter continuity has no required revision source")
        elif self.revision_source_satisfied != bool(self.revision_source_retrieved_source_ids):
            raise ValueError("revision source satisfaction must match exact retrieved sources")
        expected_satisfied = not expected_missing and self.revision_source_satisfied
        if self.satisfied != expected_satisfied:
            raise ValueError("continuity satisfaction must include the revision source")
        return self


class CreationContext(VersionedDomainModel):
    project_id: UUID
    writing_session_id: UUID
    mode: WritingSessionMode = WritingSessionMode.CREATE
    author_goal: NonEmptyText
    creative_constraints: TextTuple = ()
    target_chapter_id: UUID
    target_chapter_number: int = Field(ge=1)
    target_chapter_title: NonEmptyText
    target_volume_id: UUID
    target_narrative_order: int = Field(ge=1)
    required_chapter_heading: NonEmptyText
    before_chapter_id: UUID | None = None
    after_chapter_id: UUID | None = None
    base_canon_revision: Sha256Digest
    base_document_revision: Sha256Digest | None = None
    base_intent_revision: Sha256Digest
    intent: IntentContent
    volume: Volume | None = None
    previous_chapter_summary: ChapterSummary | None = None
    previous_chapter_text_available: bool = False
    continuity_volume_id: UUID | None = None
    continuity_chapter_ids: tuple[UUID, ...] = ()
    revision_source_chapter_id: UUID | None = None
    important_entities: tuple[Entity, ...] = ()
    query_capabilities: tuple[str, ...]

    @model_validator(mode="after")
    def validate_continuity_window(self) -> CreationContext:
        if len(self.continuity_chapter_ids) != len(set(self.continuity_chapter_ids)):
            raise ValueError("continuity_chapter_ids must be unique")
        if bool(self.continuity_chapter_ids) != (self.continuity_volume_id is not None):
            raise ValueError("continuity Volume and Chapter IDs must be present together")
        if self.mode is WritingSessionMode.CREATE:
            if (
                self.base_document_revision is not None
                or self.revision_source_chapter_id is not None
            ):
                raise ValueError("new-Chapter context cannot contain a revision source")
        elif (
            self.base_document_revision is None
            or self.revision_source_chapter_id != self.target_chapter_id
        ):
            raise ValueError("Chapter-revision context requires its exact revision source")
        return self


class DraftRevision(VersionedDomainModel):
    writing_session_id: UUID
    draft_revision: Sha256Digest
    parent_revision: Sha256Digest | None = None
    content_digest: Sha256Digest
    base_document_revision: Sha256Digest | None = None
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_digest(self) -> DraftRevision:
        if self.draft_revision != self.content_digest:
            raise ValueError("Draft revision must equal its exact content digest")
        if self.parent_revision == self.draft_revision:
            raise ValueError("Draft cannot be its own parent")
        return self


class ChapterTraceEntityDraft(VersionedDomainModel):
    temporary_name: NonEmptyText
    entity_type: EntityType
    display_name: NonEmptyText


class EntityMentionDraft(VersionedDomainModel):
    mention_ordinal: int = Field(ge=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=1)
    surface_text: NonEmptyText
    mention_form: EntityMentionForm
    resolution_status: EntityResolutionStatus
    considered_entity_ids: Annotated[tuple[UUID, ...], Field(max_length=32)] = ()
    resolved_entity_id: UUID | None = None
    new_entity_temporary_name: NonEmptyText | None = None
    resolution_reason: NonEmptyText

    @model_validator(mode="after")
    def validate_resolution(self) -> EntityMentionDraft:
        if self.end_offset <= self.start_offset:
            raise ValueError("Entity Mention Draft end_offset must be after start_offset")
        if len(self.considered_entity_ids) != len(set(self.considered_entity_ids)):
            raise ValueError("Entity Mention Draft considered IDs must be unique")
        if self.resolution_status is EntityResolutionStatus.RESOLVED_EXISTING:
            if (
                self.resolved_entity_id is None
                or self.new_entity_temporary_name is not None
                or self.resolved_entity_id not in self.considered_entity_ids
            ):
                raise ValueError(
                    "existing Entity resolution requires one considered resolved_entity_id"
                )
        elif self.resolution_status is EntityResolutionStatus.RESOLVED_NEW:
            if self.resolved_entity_id is not None or self.new_entity_temporary_name is None:
                raise ValueError("new Entity resolution requires a temporary Entity name")
        elif self.resolved_entity_id is not None or self.new_entity_temporary_name is not None:
            raise ValueError("unresolved or unlinked Mention cannot identify an Entity")
        return self


class ChapterEntityOccurrenceDraft(VersionedDomainModel):
    resolved_entity_id: UUID | None = None
    new_entity_temporary_name: NonEmptyText | None = None
    presence_kind: EntityPresenceKind
    prominence: EntityProminence
    mention_ordinals: Annotated[tuple[int, ...], Field(max_length=256)] = ()

    @model_validator(mode="after")
    def validate_reference(self) -> ChapterEntityOccurrenceDraft:
        if (self.resolved_entity_id is None) == (self.new_entity_temporary_name is None):
            raise ValueError("Chapter occurrence Draft requires exactly one Entity reference")
        if len(self.mention_ordinals) != len(set(self.mention_ordinals)):
            raise ValueError("Chapter occurrence Draft mention ordinals must be unique")
        if any(ordinal < 1 for ordinal in self.mention_ordinals):
            raise ValueError("Chapter occurrence Draft mention ordinals must be positive")
        return self


class ChapterTraceDraft(VersionedDomainModel):
    new_entities: Annotated[tuple[ChapterTraceEntityDraft, ...], Field(max_length=64)] = ()
    mentions: Annotated[tuple[EntityMentionDraft, ...], Field(max_length=512)] = ()
    entity_occurrences: Annotated[
        tuple[ChapterEntityOccurrenceDraft, ...],
        Field(max_length=256),
    ] = ()
    scan_notes: TextTuple = ()

    @model_validator(mode="after")
    def validate_trace(self) -> ChapterTraceDraft:
        temporary_names = tuple(item.temporary_name for item in self.new_entities)
        if len(temporary_names) != len(set(temporary_names)):
            raise ValueError("Chapter Trace new Entity temporary names must be unique")
        known_temporary_names = set(temporary_names)

        mention_ordinals = tuple(item.mention_ordinal for item in self.mentions)
        spans = tuple((item.start_offset, item.end_offset) for item in self.mentions)
        if mention_ordinals != tuple(range(1, len(self.mentions) + 1)):
            raise ValueError("Chapter Trace Draft mention ordinals must be contiguous and ordered")
        if len(spans) != len(set(spans)):
            raise ValueError("Chapter Trace Draft Mention spans must be unique")
        mentions_by_ordinal = {item.mention_ordinal: item for item in self.mentions}
        for mention in self.mentions:
            if (
                mention.new_entity_temporary_name is not None
                and mention.new_entity_temporary_name not in known_temporary_names
            ):
                raise ValueError("Entity Mention Draft references an unknown new Entity")

        occurrence_keys: list[tuple[str, str]] = []
        linked_ordinals: list[int] = []
        used_temporary_names: set[str] = set()
        for occurrence in self.entity_occurrences:
            if occurrence.resolved_entity_id is not None:
                occurrence_key = ("existing", str(occurrence.resolved_entity_id))
            else:
                temporary_name = str(occurrence.new_entity_temporary_name)
                if temporary_name not in known_temporary_names:
                    raise ValueError("Chapter occurrence Draft references an unknown new Entity")
                occurrence_key = ("new", temporary_name)
                used_temporary_names.add(temporary_name)
            occurrence_keys.append(occurrence_key)
            for ordinal in occurrence.mention_ordinals:
                mention = mentions_by_ordinal.get(ordinal)
                if mention is None:
                    raise ValueError("Chapter occurrence Draft references an unknown Mention")
                if occurrence.resolved_entity_id is not None:
                    if (
                        mention.resolution_status is not EntityResolutionStatus.RESOLVED_EXISTING
                        or mention.resolved_entity_id != occurrence.resolved_entity_id
                    ):
                        raise ValueError(
                            "Chapter occurrence existing Entity must match its Mention resolutions"
                        )
                elif (
                    mention.resolution_status is not EntityResolutionStatus.RESOLVED_NEW
                    or mention.new_entity_temporary_name != occurrence.new_entity_temporary_name
                ):
                    raise ValueError(
                        "Chapter occurrence new Entity must match its Mention resolutions"
                    )
                linked_ordinals.append(ordinal)

        if len(occurrence_keys) != len(set(occurrence_keys)):
            raise ValueError("Chapter Trace Draft can contain only one occurrence per Entity")
        if len(linked_ordinals) != len(set(linked_ordinals)):
            raise ValueError("resolved Mention Draft can belong to only one occurrence")
        resolved_ordinals = {
            mention.mention_ordinal
            for mention in self.mentions
            if mention.resolution_status
            in {
                EntityResolutionStatus.RESOLVED_EXISTING,
                EntityResolutionStatus.RESOLVED_NEW,
            }
        }
        if set(linked_ordinals) != resolved_ordinals:
            raise ValueError("every resolved Mention Draft must belong to one occurrence")
        if used_temporary_names != known_temporary_names:
            raise ValueError("every new Chapter Trace Entity must have one occurrence")
        return self


class DraftEntityMatchCandidate(VersionedDomainModel):
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=1)
    surface_text: NonEmptyText
    candidate_entity_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def validate_match(self) -> DraftEntityMatchCandidate:
        if self.end_offset <= self.start_offset:
            raise ValueError("Entity candidate end_offset must be after start_offset")
        if len(self.candidate_entity_ids) != len(set(self.candidate_entity_ids)):
            raise ValueError("Entity candidate IDs must be unique")
        return self


class DraftEntityCandidates(VersionedDomainModel):
    writing_session_id: UUID
    draft_revision: Sha256Digest
    matches: Annotated[tuple[DraftEntityMatchCandidate, ...], Field(max_length=512)] = ()

    @model_validator(mode="after")
    def validate_matches(self) -> DraftEntityCandidates:
        keys = tuple(
            (item.start_offset, item.end_offset, item.surface_text) for item in self.matches
        )
        if len(keys) != len(set(keys)):
            raise ValueError("Draft Entity candidates cannot contain duplicate spans")
        if keys != tuple(sorted(keys)):
            raise ValueError("Draft Entity candidates must be ordered by text span")
        return self


class ReviewRecommendation(StrEnum):
    REVISE = "revise"
    READY = "ready"


class Review(VersionedDomainModel):
    review_id: UUID
    writing_session_id: UUID
    draft_revision: Sha256Digest
    recommendation: ReviewRecommendation
    conclusion: NonEmptyText
    findings: TextTuple = ()
    uncertainties: TextTuple = ()
    retrieved_source_ids: tuple[UUID, ...] = ()
    created_at: AwareDatetime

    @field_validator("retrieved_source_ids")
    @classmethod
    def validate_unique_sources(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Review retrieved_source_ids must be unique")
        return value


class PublicationPlan(VersionedDomainModel):
    publication_id: UUID
    project_id: UUID
    writing_session_id: UUID
    mode: WritingSessionMode = WritingSessionMode.CREATE
    draft_revision: Sha256Digest
    base_canon_revision: Sha256Digest
    base_document_revision: Sha256Digest | None = None
    base_chapter_summary_digest: Sha256Digest | None = None
    base_volume_summary_digest: Sha256Digest | None = None
    base_chapter_trace_digest: Sha256Digest | None = None
    base_intent_revision: Sha256Digest
    target_document: Document
    chapter_change: Chapter
    volume_change: Volume
    chapter_summary_change: ChapterSummary
    volume_summary_change: VolumeSummary
    chapter_trace_change: ChapterTrace | None = None
    intent_revision_id: UUID | None = None
    intent_candidate_revision: Sha256Digest | None = None
    ledger_entry: CanonLedgerEntry
    review_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    manuscript_digest: Sha256Digest
    manuscript_diff: NonEmptyText
    structure_diff: NonEmptyText
    summary_diff: NonEmptyText
    chapter_trace_diff: NonEmptyText | None = None
    intent_diff: str | None = None
    canon_diff: NonEmptyText
    unresolved_questions: TextTuple = ()
    approval_digest: Sha256Digest
    prepared_at: AwareDatetime

    @model_validator(mode="after")
    def validate_bindings(self) -> PublicationPlan:
        document = self.target_document
        chapter = self.chapter_change
        volume = self.volume_change
        chapter_summary = self.chapter_summary_change
        if document.revision != self.manuscript_digest:
            raise ValueError("target Document revision must match manuscript_digest")
        if (
            chapter.source_document_id != document.document_id
            or chapter.revision != document.revision
        ):
            raise ValueError("published Chapter must bind the exact target Document revision")
        if chapter.chapter_id not in volume.chapter_ids or chapter.volume_id != volume.volume_id:
            raise ValueError("published Chapter must belong to the changed Volume")
        if (
            chapter_summary.chapter_id != chapter.chapter_id
            or chapter_summary.volume_id != volume.volume_id
            or chapter_summary.source_document_id != document.document_id
            or chapter_summary.source_revision != document.revision
        ):
            raise ValueError("Chapter Summary must bind the exact published Chapter revision")
        if (self.chapter_trace_change is None) != (self.chapter_trace_diff is None):
            raise ValueError("Chapter Trace change and Diff must be present together")
        if self.chapter_trace_change is not None:
            trace = self.chapter_trace_change
            if (
                trace.chapter_id != chapter.chapter_id
                or trace.volume_id != volume.volume_id
                or trace.source_document_id != document.document_id
                or trace.source_revision != document.revision
            ):
                raise ValueError("Chapter Trace must bind the exact published Chapter revision")
        if self.intent_revision_id is None and self.intent_candidate_revision is not None:
            raise ValueError("Intent candidate revision requires intent_revision_id")
        if self.intent_revision_id is not None and self.intent_candidate_revision is None:
            raise ValueError("intent_revision_id requires its candidate revision")
        if len(self.review_refs) != len(set(self.review_refs)):
            raise ValueError("Publication review_refs must be unique")
        if self.ledger_entry.base_revision != self.base_canon_revision:
            raise ValueError("Publication Ledger entry must bind base_canon_revision")
        if self.mode is WritingSessionMode.CREATE and self.base_document_revision is not None:
            raise ValueError("new-Chapter Publication cannot replace a Document revision")
        if self.mode is WritingSessionMode.REVISE and self.base_document_revision is None:
            raise ValueError("Chapter-revision Publication requires a base Document revision")
        return self


class PublicationStatus(StrEnum):
    PREPARED = "prepared"
    APPROVED = "approved"
    APPLYING = "applying"
    MANUSCRIPT_INSTALLED = "manuscript_installed"
    NAVIGATION_INSTALLED = "navigation_installed"
    INTENT_INSTALLED = "intent_installed"
    LEDGER_APPENDED = "ledger_appended"
    PROJECTION_REBUILT = "projection_rebuilt"
    COMPLETED = "completed"


class Publication(VersionedDomainModel):
    plan: PublicationPlan
    status: PublicationStatus
    approval: Approval | None = None
    completed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_state(self) -> Publication:
        if self.status is not PublicationStatus.PREPARED:
            if self.approval is None or self.approval.operation_id != self.plan.publication_id:
                raise ValueError("started Publication requires its exact approval")
            if self.approval.approval_digest != self.plan.approval_digest:
                raise ValueError("Publication approval digest does not match the plan")
        elif self.approval is not None:
            raise ValueError("prepared Publication cannot contain approval")
        if self.status is PublicationStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed Publication requires completed_at")
        if self.status is not PublicationStatus.COMPLETED and self.completed_at is not None:
            raise ValueError("only completed Publication can contain completed_at")
        return self


class ChapterTraceBackfillPlan(VersionedDomainModel):
    backfill_id: UUID
    project_id: UUID
    volume_id: UUID
    chapter_id: UUID
    source_document_id: UUID
    source_revision: Sha256Digest
    base_canon_revision: Sha256Digest
    base_chapter_trace_digest: Sha256Digest | None = None
    chapter_trace_change: ChapterTrace
    ledger_entry: CanonLedgerEntry | None = None
    chapter_trace_diff: NonEmptyText
    canon_diff: str = ""
    approval_digest: Sha256Digest
    prepared_at: AwareDatetime

    @model_validator(mode="after")
    def validate_bindings(self) -> ChapterTraceBackfillPlan:
        trace = self.chapter_trace_change
        if (
            trace.volume_id != self.volume_id
            or trace.chapter_id != self.chapter_id
            or trace.source_document_id != self.source_document_id
            or trace.source_revision != self.source_revision
        ):
            raise ValueError("Trace Backfill must bind the exact approved Chapter revision")
        if self.ledger_entry is None:
            if self.canon_diff:
                raise ValueError("Trace Backfill without a Ledger entry cannot contain Canon Diff")
            return self
        if self.ledger_entry.base_revision != self.base_canon_revision:
            raise ValueError("Trace Backfill Ledger entry must bind base_canon_revision")
        if self.ledger_entry.source_chapter_id != self.chapter_id:
            raise ValueError("Trace Backfill Ledger entry must bind the target Chapter")
        if any(record.record_type != "entity" for record in self.ledger_entry.records):
            raise ValueError("Trace Backfill Ledger entry can contain only new Entities")
        if not self.canon_diff:
            raise ValueError("Trace Backfill Ledger entry requires Canon Diff")
        return self


class ChapterTraceBackfillStatus(StrEnum):
    PREPARED = "prepared"
    APPROVED = "approved"
    LEDGER_APPENDED = "ledger_appended"
    TRACE_INSTALLED = "trace_installed"
    PROJECTION_REBUILT = "projection_rebuilt"
    COMPLETED = "completed"


class ChapterTraceBackfill(VersionedDomainModel):
    plan: ChapterTraceBackfillPlan
    status: ChapterTraceBackfillStatus
    approval: Approval | None = None
    completed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_state(self) -> ChapterTraceBackfill:
        if self.status is not ChapterTraceBackfillStatus.PREPARED:
            if self.approval is None or self.approval.operation_id != self.plan.backfill_id:
                raise ValueError("started Trace Backfill requires its exact approval")
            if self.approval.approval_digest != self.plan.approval_digest:
                raise ValueError("Trace Backfill approval digest does not match the plan")
        elif self.approval is not None:
            raise ValueError("prepared Trace Backfill cannot contain approval")
        if self.status is ChapterTraceBackfillStatus.COMPLETED and self.completed_at is None:
            raise ValueError("completed Trace Backfill requires completed_at")
        if (
            self.status is not ChapterTraceBackfillStatus.COMPLETED
            and self.completed_at is not None
        ):
            raise ValueError("only completed Trace Backfill can contain completed_at")
        return self
