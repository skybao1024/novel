"""Scoped positions toward truth-neutral propositions."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from novel_core._base import VersionedDomainModel
from novel_core.chronology import StoryTime, StoryTimeKind


class AssertionScope(StrEnum):
    OBJECTIVE = "objective"
    CHARACTER = "character"
    READER = "reader"
    NARRATOR = "narrator"


class AssertionStance(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"
    SUSPECTED = "suspected"
    CLAIMED = "claimed"
    DISBELIEVED = "disbelieved"


class Assertion(VersionedDomainModel):
    """A scope's time-bounded stance toward a Proposition."""

    assertion_id: UUID
    proposition_id: UUID
    scope: AssertionScope
    holder_entity_id: UUID | None = None
    stance: AssertionStance
    certainty: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    valid_from: StoryTime
    valid_to: StoryTime | None = None
    source_ref_id: UUID
    change_set_id: UUID

    @model_validator(mode="after")
    def validate_scope_and_time(self) -> Assertion:
        if self.scope is AssertionScope.CHARACTER and self.holder_entity_id is None:
            raise ValueError("character assertions require holder_entity_id")
        if self.scope in {AssertionScope.OBJECTIVE, AssertionScope.READER}:
            if self.holder_entity_id is not None:
                raise ValueError(f"{self.scope.value} assertions cannot have holder_entity_id")

        if self.valid_to is not None:
            if self.valid_from.timeline_id != self.valid_to.timeline_id:
                raise ValueError("assertion validity endpoints must share a timeline")
            if (
                self.valid_from.kind is StoryTimeKind.ORDINAL
                and self.valid_to.kind is StoryTimeKind.ORDINAL
                and self.valid_from.story_time_start > self.valid_to.story_time_start
            ):
                raise ValueError("assertion valid_from cannot be after valid_to")
        return self
