"""Truth-neutral proposition contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import StringConstraints, model_validator

from novel_core._base import DomainModel, JsonScalar, VersionedDomainModel

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
Predicate = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[a-z][a-z0-9_.-]*$"),
]


class ObjectKind(StrEnum):
    ENTITY = "entity"
    VALUE = "value"


class Qualifier(DomainModel):
    """An immutable scalar qualifier attached to a proposition."""

    key: NonEmptyText
    value: JsonScalar


class Proposition(VersionedDomainModel):
    """A claim-shaped statement that intentionally carries no truth value."""

    proposition_id: UUID
    subject_entity_id: UUID
    predicate: Predicate
    object_kind: ObjectKind
    object_entity_id: UUID | None = None
    object_value: JsonScalar | None = None
    qualifiers_json: tuple[Qualifier, ...] = ()

    @model_validator(mode="after")
    def validate_object(self) -> Proposition:
        has_entity = self.object_entity_id is not None
        has_value = self.object_value is not None
        if has_entity == has_value:
            raise ValueError("exactly one of object_entity_id and object_value is required")
        if self.object_kind is ObjectKind.ENTITY and not has_entity:
            raise ValueError("entity object_kind requires object_entity_id")
        if self.object_kind is ObjectKind.VALUE and not has_value:
            raise ValueError("value object_kind requires object_value")
        return self
