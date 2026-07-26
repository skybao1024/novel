"""Project Catalog workflows and the single project-selection boundary."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from novel_application.errors import (
    ProjectCatalogEntryNotFoundError,
    ProjectCatalogPathConflictError,
    ProjectIdentityConflictError,
    ProjectNotFoundError,
    ProjectSelectionMismatchError,
)
from novel_application.models import (
    ProjectCreationResult,
    ProjectDetails,
    ProjectHealth,
    ProjectionStatus,
    ProjectListItem,
    ProjectRegistrationResult,
    ProjectResolution,
)
from novel_application.ports import (
    ProjectCatalogStore,
    ProjectCatalogWriteLock,
    ProjectWorkspace,
)
from novel_core import (
    ProjectCatalog,
    ProjectCatalogEntry,
    ProjectManifest,
)


class ProjectCatalogService:
    """Create, register, resolve, inspect, and forget local novel projects."""

    def __init__(
        self,
        *,
        catalog: ProjectCatalogStore,
        catalog_write_lock: ProjectCatalogWriteLock,
        workspace: ProjectWorkspace,
        initialize_project: Callable[[str, ProjectManifest], ProjectionStatus],
        inspect_project: Callable[[str], ProjectHealth],
        new_project_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._catalog = catalog
        self._catalog_write_lock = catalog_write_lock
        self._workspace = workspace
        self._initialize_project = initialize_project
        self._inspect_project = inspect_project
        self._new_project_id = new_project_id

    def create(
        self,
        *,
        project_path: str,
        title: str,
        language: str,
        minimum_core_version: str,
    ) -> ProjectCreationResult:
        normalized_path = self._workspace.normalize_path(project_path)
        manifest = ProjectManifest(
            project_id=self._new_project_id(),
            title=title,
            language=language,
            minimum_core_version=minimum_core_version,
        )

        with self._catalog_write_lock.acquire():
            catalog = self._catalog.load()
            self._ensure_new_path_available(catalog, normalized_path)
            if self._entry_by_id(catalog, manifest.project_id) is not None:
                raise ProjectIdentityConflictError(
                    f"generated Project ID already exists in Catalog: {manifest.project_id}"
                )

            projection = self._initialize_project(normalized_path, manifest)
            entry = self._entry_from_manifest(manifest, normalized_path)
            self._catalog.replace(
                ProjectCatalog(
                    catalog_format_version=catalog.catalog_format_version,
                    projects=(*catalog.projects, entry),
                )
            )
        return ProjectCreationResult(
            entry=entry,
            manifest=manifest,
            projection=projection,
        )

    def add(self, *, project_path: str) -> ProjectRegistrationResult:
        normalized_path = self._workspace.normalize_path(project_path)

        with self._catalog_write_lock.acquire():
            manifest = self._workspace.load_manifest(normalized_path)
            catalog = self._catalog.load()
            path_entry = self._entry_by_path(catalog, normalized_path)
            if path_entry is not None:
                if path_entry.project_id == manifest.project_id:
                    raise ProjectCatalogPathConflictError(
                        f"project path is already registered: {normalized_path}"
                    )
                raise ProjectCatalogPathConflictError(
                    f"project path is registered to another Project ID: {path_entry.project_id}"
                )

            id_entry = self._entry_by_id(catalog, manifest.project_id)
            entry = self._entry_from_manifest(manifest, normalized_path)
            if id_entry is None:
                projects = (*catalog.projects, entry)
                path_updated = False
            else:
                if self._workspace.manifest_exists(id_entry.project_path):
                    raise ProjectIdentityConflictError(
                        "Project ID is already registered at an existing project path: "
                        f"{id_entry.project_path}"
                    )
                projects = tuple(
                    entry if item.project_id == manifest.project_id else item
                    for item in catalog.projects
                )
                path_updated = True

            self._catalog.replace(
                ProjectCatalog(
                    catalog_format_version=catalog.catalog_format_version,
                    projects=projects,
                )
            )
        return ProjectRegistrationResult(entry=entry, path_updated=path_updated)

    def list_projects(self) -> tuple[ProjectListItem, ...]:
        catalog = self._catalog.load()
        return tuple(
            ProjectListItem(
                entry=entry,
                path_exists=self._workspace.path_exists(entry.project_path),
            )
            for entry in catalog.projects
        )

    def resolve(
        self,
        *,
        project_id: UUID | None,
        project_path: str | None,
        discovery_start: str,
    ) -> ProjectResolution:
        catalog = self._catalog.load() if project_id is not None else ProjectCatalog()
        catalog_entry = self._entry_by_id(catalog, project_id) if project_id is not None else None
        if project_id is not None and catalog_entry is None:
            raise ProjectCatalogEntryNotFoundError(f"Project ID is not registered: {project_id}")

        normalized_explicit = (
            self._workspace.normalize_path(project_path) if project_path is not None else None
        )
        if normalized_explicit is not None:
            selected_path = normalized_explicit
        elif catalog_entry is not None:
            selected_path = catalog_entry.project_path
        else:
            discovered = self._workspace.discover_path(discovery_start)
            if discovered is None:
                raise ProjectNotFoundError(
                    "cannot find novel.yaml in this directory or its parents"
                )
            selected_path = discovered

        manifest = self._workspace.load_manifest(selected_path)
        if project_id is not None and manifest.project_id != project_id:
            raise ProjectSelectionMismatchError(
                f"selected path contains Project ID {manifest.project_id}, "
                f"not requested Project ID {project_id}"
            )
        if (
            catalog_entry is not None
            and normalized_explicit is not None
            and catalog_entry.project_path != normalized_explicit
        ):
            raise ProjectSelectionMismatchError(
                "--project-id and --project resolve to different project paths"
            )

        catalog_path_matches = (
            catalog_entry is not None and catalog_entry.project_path == selected_path
        )
        return ProjectResolution(
            manifest=manifest,
            project_path=selected_path,
            catalog_entry=catalog_entry,
            catalog_path_matches=catalog_path_matches,
        )

    def show(
        self,
        *,
        project_id: UUID | None,
        project_path: str | None,
        discovery_start: str,
    ) -> ProjectDetails:
        resolution = self.resolve(
            project_id=project_id,
            project_path=project_path,
            discovery_start=discovery_start,
        )
        if resolution.catalog_entry is None:
            entry = self._entry_by_id(self._catalog.load(), resolution.manifest.project_id)
            resolution = ProjectResolution(
                manifest=resolution.manifest,
                project_path=resolution.project_path,
                catalog_entry=entry,
                catalog_path_matches=(
                    entry is not None and entry.project_path == resolution.project_path
                ),
            )
        return ProjectDetails(
            resolution=resolution,
            health=self._inspect_project(resolution.project_path),
        )

    def remove(self, *, project_id: UUID) -> ProjectCatalogEntry:
        with self._catalog_write_lock.acquire():
            catalog = self._catalog.load()
            entry = self._entry_by_id(catalog, project_id)
            if entry is None:
                raise ProjectCatalogEntryNotFoundError(
                    f"Project ID is not registered: {project_id}"
                )
            projects = tuple(item for item in catalog.projects if item.project_id != project_id)
            self._catalog.replace(
                ProjectCatalog(
                    catalog_format_version=catalog.catalog_format_version,
                    projects=projects,
                )
            )
        return entry

    def refresh(self, *, project_path: str) -> ProjectCatalogEntry | None:
        """Refresh content-free Catalog metadata after a project lifecycle change."""

        normalized_path = self._workspace.normalize_path(project_path)
        manifest = self._workspace.load_manifest(normalized_path)
        with self._catalog_write_lock.acquire():
            catalog = self._catalog.load()
            existing = self._entry_by_id(catalog, manifest.project_id)
            if existing is None:
                return None
            if existing.project_path != normalized_path:
                raise ProjectSelectionMismatchError(
                    "Catalog Project ID is registered at another path"
                )
            refreshed = self._entry_from_manifest(manifest, normalized_path)
            self._catalog.replace(
                ProjectCatalog(
                    catalog_format_version=catalog.catalog_format_version,
                    projects=tuple(
                        refreshed if item.project_id == manifest.project_id else item
                        for item in catalog.projects
                    ),
                )
            )
            return refreshed

    @staticmethod
    def _entry_from_manifest(
        manifest: ProjectManifest,
        normalized_path: str,
    ) -> ProjectCatalogEntry:
        return ProjectCatalogEntry(
            project_id=manifest.project_id,
            title=manifest.title,
            project_path=normalized_path,
            status=manifest.status,
        )

    @staticmethod
    def _entry_by_id(
        catalog: ProjectCatalog,
        project_id: UUID,
    ) -> ProjectCatalogEntry | None:
        return next(
            (entry for entry in catalog.projects if entry.project_id == project_id),
            None,
        )

    @staticmethod
    def _entry_by_path(
        catalog: ProjectCatalog,
        project_path: str,
    ) -> ProjectCatalogEntry | None:
        return next(
            (entry for entry in catalog.projects if entry.project_path == project_path),
            None,
        )

    @classmethod
    def _ensure_new_path_available(
        cls,
        catalog: ProjectCatalog,
        project_path: str,
    ) -> None:
        entry = cls._entry_by_path(catalog, project_path)
        if entry is not None:
            raise ProjectCatalogPathConflictError(
                f"project path is already registered to {entry.project_id}: {project_path}"
            )
