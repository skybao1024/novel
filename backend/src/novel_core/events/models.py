"""Event domain contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from novel_core._base import VersionedDomainModel
from novel_core.chronology import StoryTime

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
EventType = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[a-z][a-z0-9_.-]*$"),
]
IdTuple = tuple[UUID, ...]
NonEmptyIdTuple = Annotated[IdTuple, Field(min_length=1)]


class EventCanonStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class EventEdgeType(StrEnum):
    CAUSES = "causes"
    ENABLES = "enables"
    PREVENTS = "prevents"
    REVEALS = "reveals"
    FORESHADOWS = "foreshadows"
    PAYS_OFF = "pays_off"
    CONTRADICTS = "contradicts"


class Event(VersionedDomainModel):
    """A story-world occurrence and the order in which readers encounter it."""

    event_id: UUID
    event_type: EventType
    story_time: StoryTime
    narrative_order: int = Field(ge=1)
    participant_entity_ids: NonEmptyIdTuple
    location_entity_ids: IdTuple = ()
    source_chapter_id: UUID
    source_ref_ids: NonEmptyIdTuple
    summary: NonEmptyText
    canon_status: EventCanonStatus = EventCanonStatus.APPROVED

    @field_validator(
        "participant_entity_ids",
        "location_entity_ids",
        "source_ref_ids",
    )
    @classmethod
    def validate_unique_ids(cls, value: IdTuple) -> IdTuple:
        if len(value) != len(set(value)):
            raise ValueError("ID collections cannot contain duplicates")
        return value


class EventEdge(VersionedDomainModel):
    """A directed semantic relation between two distinct events."""

    event_edge_id: UUID
    source_event_id: UUID
    target_event_id: UUID
    edge_type: EventEdgeType
    source_ref_id: UUID | None = None

    @model_validator(mode="after")
    def validate_distinct_events(self) -> EventEdge:
        if self.source_event_id == self.target_event_id:
            raise ValueError("event edges cannot point from an event to itself")
        return self
