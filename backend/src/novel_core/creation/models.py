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
from novel_core.navigation import Chapter, ChapterSummary, SceneSummary
from novel_core.projects import Document, Scene

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


class WritingSession(VersionedDomainModel):
    writing_session_id: UUID
    project_id: UUID
    target_scene_id: UUID
    target_document_id: UUID
    target_document_path: NonEmptyText
    target_chapter_id: UUID
    target_chapter_number: int = Field(ge=1)
    target_chapter_title: NonEmptyText
    target_narrative_order: int = Field(ge=1)
    target_story_time: StoryTime
    pov_entity_id: UUID | None = None
    location_entity_id: UUID | None = None
    before_scene_id: UUID | None = None
    after_scene_id: UUID | None = None
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
        if self.target_scene_id in {self.before_scene_id, self.after_scene_id}:
            raise ValueError("target Scene cannot be one of its position boundaries")
        if self.before_scene_id is not None and self.before_scene_id == self.after_scene_id:
            raise ValueError("Session boundaries must be different Scenes")
        if self.status is WritingSessionStatus.CLOSED and self.closed_at is None:
            raise ValueError("closed Writing Session requires closed_at")
        if self.status is WritingSessionStatus.OPEN and self.closed_at is not None:
            raise ValueError("open Writing Session cannot contain closed_at")
        if not self.target_document_path.startswith("manuscript/"):
            raise ValueError("target_document_path must be inside manuscript/")
        return self


class RetrievalKind(StrEnum):
    CHAPTER_SUMMARY = "chapter_summary"
    SCENE_SUMMARY = "scene_summary"
    EXACT_SCENE = "exact_scene"
    CANON_QUERY = "canon_query"


class RetrievedSource(VersionedDomainModel):
    retrieved_source_id: UUID
    writing_session_id: UUID
    retrieval_kind: RetrievalKind
    chapter_id: UUID | None = None
    scene_id: UUID | None = None
    document_id: UUID | None = None
    document_revision: Sha256Digest | None = None
    retrieval_reason: NonEmptyText
    retrieved_at: AwareDatetime


class CreationContext(VersionedDomainModel):
    project_id: UUID
    writing_session_id: UUID
    author_goal: NonEmptyText
    creative_constraints: TextTuple = ()
    target_scene_id: UUID
    target_chapter_id: UUID
    target_narrative_order: int = Field(ge=1)
    before_scene_id: UUID | None = None
    after_scene_id: UUID | None = None
    base_canon_revision: Sha256Digest
    base_intent_revision: Sha256Digest
    intent: IntentContent
    chapter: Chapter | None = None
    previous_scene_summary: SceneSummary | None = None
    previous_scene_text_available: bool = False
    important_entities: tuple[Entity, ...] = ()
    query_capabilities: tuple[str, ...]


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
    draft_revision: Sha256Digest
    base_canon_revision: Sha256Digest
    base_document_revision: Sha256Digest | None = None
    base_intent_revision: Sha256Digest
    target_document: Document
    scene_change: Scene
    chapter_change: Chapter
    scene_summary_change: SceneSummary
    chapter_summary_change: ChapterSummary
    intent_revision_id: UUID | None = None
    intent_candidate_revision: Sha256Digest | None = None
    ledger_entry: CanonLedgerEntry
    review_refs: Annotated[tuple[UUID, ...], Field(min_length=1)]
    manuscript_digest: Sha256Digest
    manuscript_diff: NonEmptyText
    structure_diff: NonEmptyText
    summary_diff: NonEmptyText
    intent_diff: str | None = None
    canon_diff: NonEmptyText
    unresolved_questions: TextTuple = ()
    approval_digest: Sha256Digest
    prepared_at: AwareDatetime

    @model_validator(mode="after")
    def validate_bindings(self) -> PublicationPlan:
        document = self.target_document
        scene = self.scene_change
        chapter = self.chapter_change
        scene_summary = self.scene_summary_change
        if document.revision != self.manuscript_digest:
            raise ValueError("target Document revision must match manuscript_digest")
        if scene.source_document_id != document.document_id or scene.revision != document.revision:
            raise ValueError("published Scene must bind the exact target Document revision")
        if scene.scene_id not in chapter.scene_ids or scene.chapter_id != chapter.chapter_id:
            raise ValueError("published Scene must belong to the changed Chapter")
        if (
            scene_summary.scene_id != scene.scene_id
            or scene_summary.chapter_id != chapter.chapter_id
            or scene_summary.source_document_id != document.document_id
            or scene_summary.source_revision != document.revision
        ):
            raise ValueError("Scene Summary must bind the exact published Scene revision")
        if self.intent_revision_id is None and self.intent_candidate_revision is not None:
            raise ValueError("Intent candidate revision requires intent_revision_id")
        if self.intent_revision_id is not None and self.intent_candidate_revision is None:
            raise ValueError("intent_revision_id requires its candidate revision")
        if len(self.review_refs) != len(set(self.review_refs)):
            raise ValueError("Publication review_refs must be unique")
        if self.ledger_entry.base_revision != self.base_canon_revision:
            raise ValueError("Publication Ledger entry must bind base_canon_revision")
        return self


class PublicationStatus(StrEnum):
    PREPARED = "prepared"
    APPROVED = "approved"
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
