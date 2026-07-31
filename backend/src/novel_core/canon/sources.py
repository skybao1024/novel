"""Stable references from structured Canon back to approved prose."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

from novel_core._base import VersionedDomainModel

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
Sha256Hex = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$"),
]


class SourceRef(VersionedDomainModel):
    """A revision-aware source pointer that survives ordinary text movement."""

    source_ref_id: UUID
    document_id: UUID
    chapter_id: UUID
    document_revision: NonEmptyText
    fragment_ordinal: int = Field(ge=1)
    quote_hash: Sha256Hex
    excerpt: NonEmptyText
