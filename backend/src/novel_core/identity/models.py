"""Identity domain contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import StringConstraints, model_validator

from novel_core._base import VersionedDomainModel
from novel_core.chronology import StoryTime, StoryTimeKind

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
EntityType = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$"),
]


class EntityStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class Entity(VersionedDomainModel):
    """A long-lived narrative object addressed only through an opaque UUID."""

    entity_id: UUID
    entity_type: EntityType
    display_name: NonEmptyText
    status: EntityStatus = EntityStatus.ACTIVE
    created_revision: NonEmptyText
    retired_revision: NonEmptyText | None = None

    @model_validator(mode="after")
    def validate_retirement(self) -> Entity:
        if self.status is EntityStatus.RETIRED and self.retired_revision is None:
            raise ValueError("retired entities require retired_revision")
        if self.status is EntityStatus.ACTIVE and self.retired_revision is not None:
            raise ValueError("active entities cannot have retired_revision")
        return self


class EntityAlias(VersionedDomainModel):
    """A time-bounded name for an entity; never an association key."""

    alias_id: UUID
    entity_id: UUID
    alias_text: NonEmptyText
    alias_type: EntityType
    valid_from: StoryTime | None = None
    valid_to: StoryTime | None = None
    used_by_entity_id: UUID | None = None

    @model_validator(mode="after")
    def validate_validity(self) -> EntityAlias:
        if self.valid_to is not None and self.valid_from is None:
            raise ValueError("alias valid_to requires valid_from")
        if self.valid_from is None or self.valid_to is None:
            return self
        if self.valid_from.timeline_id != self.valid_to.timeline_id:
            raise ValueError("alias validity endpoints must share a timeline")
        if (
            self.valid_from.kind is StoryTimeKind.ORDINAL
            and self.valid_to.kind is StoryTimeKind.ORDINAL
            and self.valid_from.story_time_start > self.valid_to.story_time_start
        ):
            raise ValueError("alias valid_from cannot be after valid_to")
        return self
