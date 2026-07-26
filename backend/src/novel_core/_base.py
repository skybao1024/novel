"""Shared behavior for immutable Narrative Core domain values."""

from __future__ import annotations

import json
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = "1.0.0"


class DomainModel(BaseModel):
    """Strict, immutable base used by every domain model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    def to_canonical_json(self) -> str:
        """Return deterministic JSON suitable for hashing and fixture storage."""

        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, data: str | bytes | bytearray) -> Self:
        """Restore a model from its JSON representation."""

        return cls.model_validate_json(data)


class VersionedDomainModel(DomainModel):
    """A public domain contract with an explicit serialized schema version."""

    schema_version: Literal["1.0.0"] = SCHEMA_VERSION


JsonScalar = str | int | float | bool
JsonObject = dict[str, Any]
