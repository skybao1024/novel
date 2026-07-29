"""Versioned Chapter and navigation-memory contracts."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from novel_core._base import VersionedDomainModel
from novel_core.projects import Document, DocumentKind, Scene, SceneStatus

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
Sha256Digest = Annotated[
    str,
    StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$"),
]
IdTuple = Annotated[tuple[UUID, ...], Field(max_length=32)]
TextTuple = Annotated[tuple[NonEmptyText, ...], Field(max_length=32)]


class EntityMentionForm(StrEnum):
    NAME = "name"
    ALIAS = "alias"
    PRONOUN = "pronoun"
    DESCRIPTION = "description"


class EntityResolutionStatus(StrEnum):
    RESOLVED_EXISTING = "resolved_existing"
    RESOLVED_NEW = "resolved_new"
    ANONYMOUS = "anonymous"
    IGNORED = "ignored"
    AMBIGUOUS = "ambiguous"


class EntityPresenceKind(StrEnum):
    PRESENT = "present"
    MENTIONED = "mentioned"
    RECALLED = "recalled"
    OFFSTAGE = "offstage"


class EntityProminence(StrEnum):
    FOCUS = "focus"
    SUPPORTING = "supporting"
    CAMEO = "cameo"
    BACKGROUND = "background"


class EntityMention(VersionedDomainModel):
    """One revision-bound prose span and its explicit Entity resolution."""

    mention_id: UUID
    mention_ordinal: int = Field(ge=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=1)
    surface_text: NonEmptyText
    mention_form: EntityMentionForm
    exact_candidate_entity_ids: Annotated[tuple[UUID, ...], Field(max_length=32)] = ()
    considered_entity_ids: Annotated[tuple[UUID, ...], Field(max_length=32)] = ()
    resolution_status: EntityResolutionStatus
    resolved_entity_id: UUID | None = None
    resolution_reason: NonEmptyText

    @model_validator(mode="after")
    def validate_resolution(self) -> EntityMention:
        if self.end_offset <= self.start_offset:
            raise ValueError("Entity Mention end_offset must be after start_offset")
        for label, ids in (
            ("exact candidate", self.exact_candidate_entity_ids),
            ("considered", self.considered_entity_ids),
        ):
            if len(ids) != len(set(ids)):
                raise ValueError(f"Entity Mention {label} IDs must be unique")
        if not set(self.exact_candidate_entity_ids).issubset(self.considered_entity_ids):
            raise ValueError("exact Entity candidates must be included in considered candidates")
        resolved = self.resolution_status in {
            EntityResolutionStatus.RESOLVED_EXISTING,
            EntityResolutionStatus.RESOLVED_NEW,
        }
        if resolved != (self.resolved_entity_id is not None):
            raise ValueError("resolved Entity Mention status must match resolved_entity_id")
        if (
            self.resolution_status is EntityResolutionStatus.RESOLVED_EXISTING
            and self.resolved_entity_id not in self.considered_entity_ids
        ):
            raise ValueError("existing Entity resolution must be one of the considered candidates")
        return self


class SceneEntityOccurrence(VersionedDomainModel):
    """One resolved Entity's navigational presence in an approved Scene."""

    occurrence_id: UUID
    entity_id: UUID
    presence_kind: EntityPresenceKind
    prominence: EntityProminence
    mention_ids: Annotated[tuple[UUID, ...], Field(max_length=256)] = ()

    @field_validator("mention_ids")
    @classmethod
    def validate_unique_mentions(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Scene Entity occurrence mention IDs must be unique")
        return value


class SceneTrace(VersionedDomainModel):
    """Non-Canon Entity mention and occurrence index for one Scene revision."""

    scene_trace_id: UUID
    scene_id: UUID
    chapter_id: UUID
    source_document_id: UUID
    source_revision: Sha256Digest
    mentions: Annotated[tuple[EntityMention, ...], Field(max_length=512)] = ()
    entity_occurrences: Annotated[
        tuple[SceneEntityOccurrence, ...],
        Field(max_length=256),
    ] = ()
    scan_notes: TextTuple = ()

    @model_validator(mode="after")
    def validate_trace(self) -> SceneTrace:
        mention_ids = tuple(item.mention_id for item in self.mentions)
        mention_ordinals = tuple(item.mention_ordinal for item in self.mentions)
        spans = tuple((item.start_offset, item.end_offset) for item in self.mentions)
        if len(mention_ids) != len(set(mention_ids)):
            raise ValueError("Scene Trace mention IDs must be unique")
        if mention_ordinals != tuple(range(1, len(self.mentions) + 1)):
            raise ValueError("Scene Trace mention ordinals must be contiguous and ordered")
        if len(spans) != len(set(spans)):
            raise ValueError("Scene Trace Mention spans must be unique")
        if any(
            mention.resolution_status is EntityResolutionStatus.AMBIGUOUS
            for mention in self.mentions
        ):
            raise ValueError("published Scene Trace cannot contain ambiguous Entity Mentions")

        occurrence_ids = tuple(item.occurrence_id for item in self.entity_occurrences)
        occurrence_entity_ids = tuple(item.entity_id for item in self.entity_occurrences)
        if len(occurrence_ids) != len(set(occurrence_ids)):
            raise ValueError("Scene Trace occurrence IDs must be unique")
        if len(occurrence_entity_ids) != len(set(occurrence_entity_ids)):
            raise ValueError("Scene Trace can contain only one occurrence per Entity")

        known_mentions = set(mention_ids)
        linked_mentions: list[UUID] = []
        for occurrence in self.entity_occurrences:
            unknown = set(occurrence.mention_ids) - known_mentions
            if unknown:
                raise ValueError("Scene Entity occurrence references unknown Mention IDs")
            linked_mentions.extend(occurrence.mention_ids)
            for mention_id in occurrence.mention_ids:
                mention = next(item for item in self.mentions if item.mention_id == mention_id)
                if mention.resolved_entity_id != occurrence.entity_id:
                    raise ValueError("Scene occurrence Entity must match its resolved Mentions")
        if len(linked_mentions) != len(set(linked_mentions)):
            raise ValueError("resolved Entity Mention can belong to only one Scene occurrence")
        resolved_mentions = {
            mention.mention_id
            for mention in self.mentions
            if mention.resolved_entity_id is not None
        }
        if set(linked_mentions) != resolved_mentions:
            raise ValueError("every resolved Entity Mention must belong to one Scene occurrence")
        return self


class Chapter(VersionedDomainModel):
    """An explicit, stable Chapter boundary over existing Scene IDs."""

    chapter_id: UUID
    chapter_number: int = Field(ge=1)
    title: NonEmptyText
    scene_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]

    @field_validator("scene_ids")
    @classmethod
    def validate_unique_scene_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("chapter scene_ids must be unique")
        return value


class SceneSummary(VersionedDomainModel):
    """Non-Canon navigation memory for one approved Scene revision."""

    scene_id: UUID
    chapter_id: UUID
    scene_number_in_chapter: int = Field(ge=1)
    source_document_id: UUID
    source_revision: Sha256Digest
    summary: NonEmptyText
    main_entity_ids: IdTuple = ()
    key_changes: TextTuple = ()
    open_questions: TextTuple = ()

    @field_validator("main_entity_ids")
    @classmethod
    def validate_unique_entity_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("main_entity_ids must be unique")
        return value

    @field_validator("key_changes", "open_questions")
    @classmethod
    def validate_unique_texts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("navigation-memory text items must be unique")
        return value


class SceneSummaryDependency(VersionedDomainModel):
    """The exact Scene Summary revision consumed by a Chapter Summary."""

    scene_id: UUID
    source_revision: Sha256Digest
    summary_digest: Sha256Digest


class ChapterSummary(VersionedDomainModel):
    """Non-Canon aggregation over one Chapter's Scene Summaries."""

    chapter_id: UUID
    chapter_number: int = Field(ge=1)
    title: NonEmptyText
    scene_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    scene_summary_dependencies: Annotated[
        tuple[SceneSummaryDependency, ...],
        Field(min_length=1),
    ]
    summary: NonEmptyText
    main_entity_ids: IdTuple = ()

    @field_validator("scene_ids", "main_entity_ids")
    @classmethod
    def validate_unique_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("navigation-memory IDs must be unique")
        return value

    @model_validator(mode="after")
    def validate_dependencies(self) -> ChapterSummary:
        dependency_ids = tuple(item.scene_id for item in self.scene_summary_dependencies)
        if dependency_ids != self.scene_ids:
            raise ValueError("chapter summary dependencies must match scene_ids in the same order")
        return self


def scene_summary_digest(summary: SceneSummary) -> str:
    """Return the stable digest consumed by a Chapter Summary."""

    return f"sha256:{sha256(summary.to_canonical_json().encode('utf-8')).hexdigest()}"


def scene_trace_digest(trace: SceneTrace) -> str:
    """Return the stable digest used as a Trace Backfill base."""

    return f"sha256:{sha256(trace.to_canonical_json().encode('utf-8')).hexdigest()}"


def validate_chapter_bindings(
    chapters: tuple[Chapter, ...],
    scenes: tuple[Scene, ...],
) -> None:
    """Validate explicit Chapter boundaries without inferring them from paths."""

    chapter_ids = [chapter.chapter_id for chapter in chapters]
    if len(chapter_ids) != len(set(chapter_ids)):
        raise ValueError("chapter_id must be unique")
    chapter_numbers = [chapter.chapter_number for chapter in chapters]
    if len(chapter_numbers) != len(set(chapter_numbers)):
        raise ValueError("chapter_number must be unique")

    scenes_by_id = {scene.scene_id: scene for scene in scenes}
    assigned_scene_ids: set[UUID] = set()
    for chapter in chapters:
        chapter_orders: list[int] = []
        for scene_id in chapter.scene_ids:
            if scene_id in assigned_scene_ids:
                raise ValueError(f"scene belongs to more than one Chapter: {scene_id}")
            scene = scenes_by_id.get(scene_id)
            if scene is None:
                raise ValueError(f"chapter references an unknown Scene: {scene_id}")
            if scene.chapter_id is not None and scene.chapter_id != chapter.chapter_id:
                raise ValueError(
                    f"scene {scene_id} is bound to another Chapter: {scene.chapter_id}"
                )
            assigned_scene_ids.add(scene_id)
            chapter_orders.append(scene.narrative_order)
        if chapter_orders != sorted(chapter_orders):
            raise ValueError(f"chapter {chapter.chapter_id} scene_ids are not in Narrative Order")


def scene_summary_is_stale(
    summary: SceneSummary,
    *,
    chapter: Chapter,
    scene: Scene,
    document: Document,
) -> bool:
    """Return whether a structurally valid Scene Summary is no longer current."""

    try:
        scene_number = chapter.scene_ids.index(scene.scene_id) + 1
    except ValueError as exc:
        raise ValueError(f"scene is not part of Chapter {chapter.chapter_id}") from exc
    if summary.chapter_id != chapter.chapter_id or summary.scene_id != scene.scene_id:
        raise ValueError("Scene Summary does not match its Chapter and Scene")
    if summary.scene_number_in_chapter != scene_number:
        raise ValueError("Scene Summary has the wrong scene_number_in_chapter")
    if summary.source_document_id != document.document_id:
        raise ValueError("Scene Summary source_document_id does not match the Scene")
    if scene.source_document_id != document.document_id:
        raise ValueError("Scene source_document_id does not match the Document")
    if scene.status is not SceneStatus.APPROVED:
        raise ValueError("Scene Summary can only describe an approved Scene")
    if document.document_kind is not DocumentKind.MANUSCRIPT:
        raise ValueError("Scene Summary can only describe a manuscript Document")
    return summary.source_revision != document.revision or scene.revision != document.revision


def scene_trace_is_stale(
    trace: SceneTrace,
    *,
    chapter: Chapter,
    scene: Scene,
    document: Document,
) -> bool:
    """Return whether a structurally valid Scene Trace no longer matches its Scene."""

    if trace.chapter_id != chapter.chapter_id or trace.scene_id != scene.scene_id:
        raise ValueError("Scene Trace does not match its Chapter and Scene")
    if scene.scene_id not in chapter.scene_ids:
        raise ValueError("Scene Trace Scene is not part of its Chapter")
    if trace.source_document_id != document.document_id:
        raise ValueError("Scene Trace source Document does not match the Scene")
    if scene.source_document_id != document.document_id:
        raise ValueError("Scene source Document does not match the Scene Trace")
    if scene.status is not SceneStatus.APPROVED:
        raise ValueError("Scene Trace can only describe an approved Scene")
    if document.document_kind is not DocumentKind.MANUSCRIPT:
        raise ValueError("Scene Trace can only describe a manuscript Document")
    return trace.source_revision != document.revision or scene.revision != document.revision


def chapter_summary_is_stale(
    summary: ChapterSummary,
    *,
    chapter: Chapter,
    scene_summaries: dict[UUID, SceneSummary],
    stale_scene_ids: set[UUID],
) -> bool:
    """Return whether Chapter metadata or any consumed Scene Summary changed."""

    if summary.chapter_id != chapter.chapter_id:
        raise ValueError("Chapter Summary does not match its Chapter")
    if (
        summary.chapter_number != chapter.chapter_number
        or summary.title != chapter.title
        or summary.scene_ids != chapter.scene_ids
    ):
        return True

    for dependency in summary.scene_summary_dependencies:
        scene_summary = scene_summaries.get(dependency.scene_id)
        if scene_summary is None or dependency.scene_id in stale_scene_ids:
            return True
        if (
            dependency.source_revision != scene_summary.source_revision
            or dependency.summary_digest != scene_summary_digest(scene_summary)
        ):
            return True
    return False
