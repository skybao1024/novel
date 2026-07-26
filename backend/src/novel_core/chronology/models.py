"""Chronology domain contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import StringConstraints, model_validator

from novel_core._base import VersionedDomainModel

TimelineId = Annotated[str, StringConstraints(min_length=1)]
StoryTimeValue = str | int


class StoryTimeKind(StrEnum):
    EXACT = "exact"
    ORDINAL = "ordinal"
    RELATIVE = "relative"
    INTERVAL = "interval"
    UNKNOWN = "unknown"


class StoryTime(VersionedDomainModel):
    """A calendar-neutral position on a story timeline.

    Narrative order deliberately does not belong to this value object. It is a
    property of the scene or event through which readers encounter the event.
    """

    timeline_id: TimelineId = "main"
    kind: StoryTimeKind
    story_time_start: StoryTimeValue | None = None
    story_time_end: StoryTimeValue | None = None
    time_anchor_event_id: UUID | None = None
    relative_offset: int | None = None
    display_time: str | None = None

    @model_validator(mode="after")
    def validate_kind_shape(self) -> StoryTime:
        start = self.story_time_start
        end = self.story_time_end
        anchor = self.time_anchor_event_id
        offset = self.relative_offset

        if self.kind is StoryTimeKind.EXACT:
            if (
                not isinstance(start, str)
                or end is not None
                or anchor is not None
                or offset is not None
            ):
                raise ValueError("exact story time requires only a string story_time_start")

        elif self.kind is StoryTimeKind.ORDINAL:
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or end is not None
                or anchor is not None
                or offset is not None
            ):
                raise ValueError("ordinal story time requires only an integer story_time_start")

        elif self.kind is StoryTimeKind.RELATIVE:
            if start is not None or end is not None or anchor is None or offset is None:
                raise ValueError(
                    "relative story time requires time_anchor_event_id and relative_offset"
                )

        elif self.kind is StoryTimeKind.INTERVAL:
            if start is None or end is None or anchor is not None or offset is not None:
                raise ValueError("interval story time requires story_time_start and story_time_end")
            if type(start) is not type(end):
                raise ValueError("interval endpoints must use the same representation")
            if isinstance(start, int) and start > end:
                raise ValueError("ordinal interval start cannot be after its end")

        elif any(value is not None for value in (start, end, anchor, offset)):
            raise ValueError("unknown story time cannot contain a machine-readable position")

        return self
