"""Versioned project, document, and scene contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from novel_core._base import VersionedDomainModel
from novel_core.chronology import StoryTime

NonEmptyText = Annotated[str, StringConstraints(min_length=1)]
RelativeProjectPath = Annotated[
    str,
    StringConstraints(min_length=1, pattern=r"^[^\\]+$"),
]
LanguageTag = Annotated[
    str,
    StringConstraints(min_length=2, pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$"),
]


class DocumentKind(StrEnum):
    MANUSCRIPT = "manuscript"
    MANUAL = "manual"
    STRUCTURE = "structure"


class SceneStatus(StrEnum):
    PLANNED = "planned"
    DRAFTING = "drafting"
    CANDIDATE = "candidate"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class ProjectStatus(StrEnum):
    """The minimum lifecycle state needed to select a local novel safely."""

    NOT_BOOTSTRAPPED = "not_bootstrapped"
    READY = "ready"


class ProjectManifest(VersionedDomainModel):
    """The small, stable manifest stored as ``novel.yaml``."""

    project_format_version: Literal[1] = 1
    project_id: UUID
    title: NonEmptyText
    language: LanguageTag
    status: ProjectStatus = ProjectStatus.NOT_BOOTSTRAPPED
    default_timeline_id: NonEmptyText = "main"
    minimum_core_version: NonEmptyText


class ProjectCatalogEntry(VersionedDomainModel):
    """One content-free project reference in the user-level Catalog."""

    project_id: UUID
    title: NonEmptyText
    project_path: NonEmptyText
    status: ProjectStatus


class ProjectCatalog(VersionedDomainModel):
    """The versioned user-level collection of local project references."""

    catalog_format_version: Literal[1] = 1
    projects: tuple[ProjectCatalogEntry, ...] = ()

    @model_validator(mode="after")
    def validate_unique_projects(self) -> ProjectCatalog:
        project_ids = [project.project_id for project in self.projects]
        project_paths = [project.project_path for project in self.projects]
        if len(project_ids) != len(set(project_ids)):
            raise ValueError("Project Catalog contains a duplicate project_id")
        if len(project_paths) != len(set(project_paths)):
            raise ValueError("Project Catalog contains a duplicate project_path")
        return self


class Document(VersionedDomainModel):
    """A versioned Canon or structure document inside a novel project."""

    document_id: UUID
    relative_path: RelativeProjectPath
    document_kind: DocumentKind
    revision: NonEmptyText

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        parts = value.split("/")
        if (
            value.startswith("/")
            or (len(value) >= 3 and value[1:3] == ":/")
            or any(part in {"", ".", ".."} for part in parts)
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("document path must be a normalized project-relative path")
        return value


class Scene(VersionedDomainModel):
    """A scene's story position and reader-facing order."""

    scene_id: UUID
    chapter_id: UUID | None = None
    narrative_order: int = Field(ge=1)
    story_time: StoryTime
    pov_entity_id: UUID | None = None
    location_entity_id: UUID | None = None
    status: SceneStatus
    source_document_id: UUID
    revision: NonEmptyText

    @model_validator(mode="after")
    def validate_timeline(self) -> Scene:
        if not self.story_time.timeline_id:
            raise ValueError("scene story_time requires a timeline_id")
        return self
