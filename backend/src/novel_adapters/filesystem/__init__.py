"""Filesystem-backed project, Ledger, navigation, and manuscript adapters."""

from novel_adapters.filesystem.catalog import (
    APP_DATA_ENVIRONMENT_VARIABLE,
    CATALOG_FILENAME,
    FilesystemProjectCatalogStore,
    FilesystemProjectCatalogWriteLock,
    FilesystemProjectWorkspace,
    default_app_data_directory,
)
from novel_adapters.filesystem.creation import (
    FilesystemBootstrapRunStore,
    FilesystemIntentRevisionStore,
    FilesystemIntentStore,
    FilesystemPublicationStore,
    FilesystemRunIndexStore,
    FilesystemWritingRunStore,
    RunSourceSnapshot,
)
from novel_adapters.filesystem.diagnostics import (
    DIAGNOSTIC_RETENTION_DAYS,
    DIAGNOSTIC_SCHEMA_VERSION,
    DiagnosticLogWriteError,
    DiagnosticOutcome,
    DiagnosticRecord,
    DiagnosticRecordNotFoundError,
    FilesystemDiagnosticLog,
)
from novel_adapters.filesystem.manuscript import FilesystemManuscriptStore
from novel_adapters.filesystem.navigation import (
    FilesystemNavigationStore,
    NavigationSourceSnapshot,
)
from novel_adapters.filesystem.project import (
    FilesystemCanonLedgerStore,
    FilesystemProjectStore,
    FilesystemProjectWriteLock,
    ProjectLayout,
)

__all__ = [
    "APP_DATA_ENVIRONMENT_VARIABLE",
    "CATALOG_FILENAME",
    "DIAGNOSTIC_RETENTION_DAYS",
    "DIAGNOSTIC_SCHEMA_VERSION",
    "DiagnosticLogWriteError",
    "DiagnosticOutcome",
    "DiagnosticRecord",
    "DiagnosticRecordNotFoundError",
    "FilesystemCanonLedgerStore",
    "FilesystemBootstrapRunStore",
    "FilesystemIntentRevisionStore",
    "FilesystemIntentStore",
    "FilesystemDiagnosticLog",
    "FilesystemManuscriptStore",
    "FilesystemNavigationStore",
    "FilesystemProjectCatalogStore",
    "FilesystemProjectCatalogWriteLock",
    "FilesystemProjectStore",
    "FilesystemProjectWorkspace",
    "FilesystemProjectWriteLock",
    "FilesystemPublicationStore",
    "FilesystemRunIndexStore",
    "FilesystemWritingRunStore",
    "NavigationSourceSnapshot",
    "RunSourceSnapshot",
    "ProjectLayout",
    "default_app_data_directory",
]
