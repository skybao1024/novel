"""Append-only Canon change contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from novel_core._base import VersionedDomainModel
from novel_core.canon.assertions import Assertion
from novel_core.canon.propositions import Proposition

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]


class ChangeSetOperationKind(StrEnum):
    ASSERT = "assert"
    RETRACT = "retract"
    SUPERSEDE = "supersede"
    CORRECT = "correct"


class ChangeSetOperation(VersionedDomainModel):
    """One append-only operation against the Canon assertion history."""

    operation_id: UUID
    op: ChangeSetOperationKind
    target_assertion_id: UUID | None = None
    source_ref_id: UUID | None = None
    assertion: Assertion | None = None
    proposition: Proposition | None = None
    reason: NonEmptyText

    @model_validator(mode="after")
    def validate_operation_shape(self) -> ChangeSetOperation:
        if self.op is ChangeSetOperationKind.ASSERT:
            if self.target_assertion_id is not None or self.assertion is None:
                raise ValueError("assert requires a new assertion and no target_assertion_id")

        elif self.op is ChangeSetOperationKind.RETRACT:
            if (
                self.target_assertion_id is None
                or self.assertion is not None
                or self.proposition is not None
            ):
                raise ValueError("retract requires only target_assertion_id")

        else:
            if self.target_assertion_id is None or self.assertion is None:
                raise ValueError(f"{self.op.value} requires a target and a replacement assertion")
            if self.target_assertion_id == self.assertion.assertion_id:
                raise ValueError("replacement assertion must have a new assertion_id")

        if self.proposition is not None:
            if self.assertion is None:
                raise ValueError("a new proposition requires a new assertion")
            if self.assertion.proposition_id != self.proposition.proposition_id:
                raise ValueError("new assertion must reference the operation's proposition")
        return self


class CanonChangeSet(VersionedDomainModel):
    """An immutable, approved group of append-only Canon operations."""

    change_set_id: UUID
    base_revision: NonEmptyText
    source_chapter_id: UUID | None = None
    operations: Annotated[tuple[ChangeSetOperation, ...], Field(min_length=1)]
    approved_at: AwareDatetime

    @model_validator(mode="after")
    def validate_operations(self) -> CanonChangeSet:
        operation_ids = [operation.operation_id for operation in self.operations]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("operation_id values must be unique within a change set")

        assertion_ids = [
            operation.assertion.assertion_id
            for operation in self.operations
            if operation.assertion is not None
        ]
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("new assertion_id values must be unique within a change set")

        for operation in self.operations:
            if (
                operation.assertion is not None
                and operation.assertion.change_set_id != self.change_set_id
            ):
                raise ValueError("new assertions must reference their containing change_set_id")
        return self
