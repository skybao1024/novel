"""Read models for sparse, explicitly approved Canon."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

from novel_core._base import VersionedDomainModel
from novel_core.canon.assertions import Assertion
from novel_core.canon.propositions import Proposition
from novel_core.canon.sources import SourceRef
from novel_core.chronology import StoryTime
from novel_core.events import Event, EventEdge

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
QueryWarningCode = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[a-z][a-z0-9_]*$"),
]

CHARACTER_LOCATION_PREDICATE = "character.location"
CHARACTER_GOAL_PREDICATE = "character.goal"


class QueryWarning(VersionedDomainModel):
    """A mechanical limitation that keeps a query result from being definitive."""

    code: QueryWarningCode
    message: NonEmptyText
    related_ids: tuple[str, ...] = ()


class SourcedAssertion(VersionedDomainModel):
    """One approved Assertion with the Proposition and exact SourceRef it names."""

    assertion: Assertion
    proposition: Proposition
    source_ref: SourceRef


class CharacterStatePhase(StrEnum):
    ENTRY = "entry"
    EXIT = "exit"


class CharacterState(VersionedDomainModel):
    """A sparse Canon view, never a claim that prose contains no other state."""

    character_id: UUID
    target_chapter_id: UUID
    phase: CharacterStatePhase
    story_time: StoryTime
    location: SourcedAssertion | None = None
    active_goals: tuple[SourcedAssertion, ...] = ()
    knowledge_and_beliefs: tuple[SourcedAssertion, ...] = ()
    objective_state: tuple[SourcedAssertion, ...] = ()
    warnings: tuple[QueryWarning, ...] = ()


class EventChainDirection(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"
    BOTH = "both"


class EventChain(VersionedDomainModel):
    """A chain over sparse approved Events, not a complete causal graph."""

    root_event_id: UUID
    direction: EventChainDirection
    max_depth: int = Field(ge=0, le=20)
    events: tuple[Event, ...]
    edges: tuple[EventEdge, ...]
    source_refs: tuple[SourceRef, ...]
    warnings: tuple[QueryWarning, ...] = ()
