"""Versioned Volume and navigation-memory contracts."""

from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from novel_core._base import VersionedDomainModel
from novel_core.projects import Chapter, ChapterStatus, Document, DocumentKind

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


class ChapterEntityOccurrence(VersionedDomainModel):
    """One resolved Entity's navigational presence in an approved Chapter."""

    occurrence_id: UUID
    entity_id: UUID
    presence_kind: EntityPresenceKind
    prominence: EntityProminence
    mention_ids: Annotated[tuple[UUID, ...], Field(max_length=256)] = ()

    @field_validator("mention_ids")
    @classmethod
    def validate_unique_mentions(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Chapter Entity occurrence mention IDs must be unique")
        return value


class ChapterTrace(VersionedDomainModel):
    """Non-Canon Entity mention and occurrence index for one Chapter revision."""

    chapter_trace_id: UUID
    chapter_id: UUID
    volume_id: UUID
    source_document_id: UUID
    source_revision: Sha256Digest
    mentions: Annotated[tuple[EntityMention, ...], Field(max_length=512)] = ()
    entity_occurrences: Annotated[
        tuple[ChapterEntityOccurrence, ...],
        Field(max_length=256),
    ] = ()
    scan_notes: TextTuple = ()

    @model_validator(mode="after")
    def validate_trace(self) -> ChapterTrace:
        mention_ids = tuple(item.mention_id for item in self.mentions)
        mention_ordinals = tuple(item.mention_ordinal for item in self.mentions)
        spans = tuple((item.start_offset, item.end_offset) for item in self.mentions)
        if len(mention_ids) != len(set(mention_ids)):
            raise ValueError("Chapter Trace mention IDs must be unique")
        if mention_ordinals != tuple(range(1, len(self.mentions) + 1)):
            raise ValueError("Chapter Trace mention ordinals must be contiguous and ordered")
        if len(spans) != len(set(spans)):
            raise ValueError("Chapter Trace Mention spans must be unique")
        if any(
            mention.resolution_status is EntityResolutionStatus.AMBIGUOUS
            for mention in self.mentions
        ):
            raise ValueError("published Chapter Trace cannot contain ambiguous Entity Mentions")

        occurrence_ids = tuple(item.occurrence_id for item in self.entity_occurrences)
        occurrence_entity_ids = tuple(item.entity_id for item in self.entity_occurrences)
        if len(occurrence_ids) != len(set(occurrence_ids)):
            raise ValueError("Chapter Trace occurrence IDs must be unique")
        if len(occurrence_entity_ids) != len(set(occurrence_entity_ids)):
            raise ValueError("Chapter Trace can contain only one occurrence per Entity")

        known_mentions = set(mention_ids)
        linked_mentions: list[UUID] = []
        for occurrence in self.entity_occurrences:
            unknown = set(occurrence.mention_ids) - known_mentions
            if unknown:
                raise ValueError("Chapter Entity occurrence references unknown Mention IDs")
            linked_mentions.extend(occurrence.mention_ids)
            for mention_id in occurrence.mention_ids:
                mention = next(item for item in self.mentions if item.mention_id == mention_id)
                if mention.resolved_entity_id != occurrence.entity_id:
                    raise ValueError("Chapter occurrence Entity must match its resolved Mentions")
        if len(linked_mentions) != len(set(linked_mentions)):
            raise ValueError("resolved Entity Mention can belong to only one Chapter occurrence")
        resolved_mentions = {
            mention.mention_id
            for mention in self.mentions
            if mention.resolved_entity_id is not None
        }
        if set(linked_mentions) != resolved_mentions:
            raise ValueError("every resolved Entity Mention must belong to one Chapter occurrence")
        return self


class Volume(VersionedDomainModel):
    """An explicit, stable Volume boundary over existing Chapter IDs."""

    volume_id: UUID
    volume_number: int = Field(ge=1)
    title: NonEmptyText
    chapter_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]

    @field_validator("chapter_ids")
    @classmethod
    def validate_unique_chapter_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("volume chapter_ids must be unique")
        return value


class ChapterSummary(VersionedDomainModel):
    """Non-Canon navigation memory for one approved Chapter revision."""

    chapter_id: UUID
    volume_id: UUID
    chapter_number_in_volume: int = Field(ge=1)
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


class ChapterSummaryDependency(VersionedDomainModel):
    """The exact Chapter Summary revision consumed by a Volume Summary."""

    chapter_id: UUID
    source_revision: Sha256Digest
    summary_digest: Sha256Digest


class VolumeSummary(VersionedDomainModel):
    """Non-Canon aggregation over one Volume's Chapter Summaries."""

    volume_id: UUID
    volume_number: int = Field(ge=1)
    title: NonEmptyText
    chapter_ids: Annotated[tuple[UUID, ...], Field(min_length=1)]
    chapter_summary_dependencies: Annotated[
        tuple[ChapterSummaryDependency, ...],
        Field(min_length=1),
    ]
    summary: NonEmptyText
    main_entity_ids: IdTuple = ()

    @field_validator("chapter_ids", "main_entity_ids")
    @classmethod
    def validate_unique_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("navigation-memory IDs must be unique")
        return value

    @model_validator(mode="after")
    def validate_dependencies(self) -> VolumeSummary:
        dependency_ids = tuple(item.chapter_id for item in self.chapter_summary_dependencies)
        if dependency_ids != self.chapter_ids:
            raise ValueError("volume summary dependencies must match chapter_ids in the same order")
        return self


def chapter_summary_digest(summary: ChapterSummary) -> str:
    """Return the stable digest consumed by a Volume Summary."""

    return f"sha256:{sha256(summary.to_canonical_json().encode('utf-8')).hexdigest()}"


def chapter_trace_digest(trace: ChapterTrace) -> str:
    """Return the stable digest used as a Trace Backfill base."""

    return f"sha256:{sha256(trace.to_canonical_json().encode('utf-8')).hexdigest()}"


def validate_volume_bindings(
    volumes: tuple[Volume, ...],
    chapters: tuple[Chapter, ...],
) -> None:
    """Validate explicit Volume boundaries without inferring them from paths."""

    volume_ids = [volume.volume_id for volume in volumes]
    if len(volume_ids) != len(set(volume_ids)):
        raise ValueError("volume_id must be unique")
    volume_numbers = [volume.volume_number for volume in volumes]
    if len(volume_numbers) != len(set(volume_numbers)):
        raise ValueError("volume_number must be unique")

    chapter_ids = [chapter.chapter_id for chapter in chapters]
    if len(chapter_ids) != len(set(chapter_ids)):
        raise ValueError("chapter_id must be unique")
    chapter_numbers = [chapter.chapter_number for chapter in chapters]
    if len(chapter_numbers) != len(set(chapter_numbers)):
        raise ValueError("chapter_number must be unique")
    narrative_orders = [chapter.narrative_order for chapter in chapters]
    if len(narrative_orders) != len(set(narrative_orders)):
        raise ValueError("Chapter Narrative Order must be unique")

    chapters_by_id = {chapter.chapter_id: chapter for chapter in chapters}
    assigned_chapter_ids: set[UUID] = set()
    for volume in volumes:
        volume_orders: list[int] = []
        for chapter_id in volume.chapter_ids:
            if chapter_id in assigned_chapter_ids:
                raise ValueError(f"chapter belongs to more than one Volume: {chapter_id}")
            chapter = chapters_by_id.get(chapter_id)
            if chapter is None:
                raise ValueError(f"volume references an unknown Chapter: {chapter_id}")
            if chapter.volume_id is not None and chapter.volume_id != volume.volume_id:
                raise ValueError(
                    f"chapter {chapter_id} is bound to another Volume: {chapter.volume_id}"
                )
            assigned_chapter_ids.add(chapter_id)
            volume_orders.append(chapter.narrative_order)
        if volume_orders != sorted(volume_orders):
            raise ValueError(f"volume {volume.volume_id} chapter_ids are not in Narrative Order")


def chapter_summary_is_stale(
    summary: ChapterSummary,
    *,
    volume: Volume,
    chapter: Chapter,
    document: Document,
) -> bool:
    """Return whether a structurally valid Chapter Summary is no longer current."""

    try:
        chapter_number = volume.chapter_ids.index(chapter.chapter_id) + 1
    except ValueError as exc:
        raise ValueError(f"chapter is not part of Volume {volume.volume_id}") from exc
    if summary.volume_id != volume.volume_id or summary.chapter_id != chapter.chapter_id:
        raise ValueError("Chapter Summary does not match its Volume and Chapter")
    if summary.chapter_number_in_volume != chapter_number:
        raise ValueError("Chapter Summary has the wrong chapter_number_in_volume")
    if summary.source_document_id != document.document_id:
        raise ValueError("Chapter Summary source_document_id does not match the Chapter")
    if chapter.source_document_id != document.document_id:
        raise ValueError("Chapter source_document_id does not match the Document")
    if chapter.status is not ChapterStatus.APPROVED:
        raise ValueError("Chapter Summary can only describe an approved Chapter")
    if document.document_kind is not DocumentKind.MANUSCRIPT:
        raise ValueError("Chapter Summary can only describe a manuscript Document")
    return summary.source_revision != document.revision or chapter.revision != document.revision


def chapter_trace_is_stale(
    trace: ChapterTrace,
    *,
    volume: Volume,
    chapter: Chapter,
    document: Document,
) -> bool:
    """Return whether a structurally valid Chapter Trace no longer matches its Chapter."""

    if trace.volume_id != volume.volume_id or trace.chapter_id != chapter.chapter_id:
        raise ValueError("Chapter Trace does not match its Volume and Chapter")
    if chapter.chapter_id not in volume.chapter_ids:
        raise ValueError("Chapter Trace Chapter is not part of its Volume")
    if trace.source_document_id != document.document_id:
        raise ValueError("Chapter Trace source Document does not match the Chapter")
    if chapter.source_document_id != document.document_id:
        raise ValueError("Chapter source Document does not match the Chapter Trace")
    if chapter.status is not ChapterStatus.APPROVED:
        raise ValueError("Chapter Trace can only describe an approved Chapter")
    if document.document_kind is not DocumentKind.MANUSCRIPT:
        raise ValueError("Chapter Trace can only describe a manuscript Document")
    return trace.source_revision != document.revision or chapter.revision != document.revision


def volume_summary_is_stale(
    summary: VolumeSummary,
    *,
    volume: Volume,
    chapter_summaries: dict[UUID, ChapterSummary],
    stale_chapter_ids: set[UUID],
) -> bool:
    """Return whether Volume metadata or any consumed Chapter Summary changed."""

    if summary.volume_id != volume.volume_id:
        raise ValueError("Volume Summary does not match its Volume")
    if (
        summary.volume_number != volume.volume_number
        or summary.title != volume.title
        or summary.chapter_ids != volume.chapter_ids
    ):
        return True

    for dependency in summary.chapter_summary_dependencies:
        chapter_summary = chapter_summaries.get(dependency.chapter_id)
        if chapter_summary is None or dependency.chapter_id in stale_chapter_ids:
            return True
        if (
            dependency.source_revision != chapter_summary.source_revision
            or dependency.summary_digest != chapter_summary_digest(chapter_summary)
        ):
            return True
    return False
