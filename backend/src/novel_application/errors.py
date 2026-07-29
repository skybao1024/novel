"""Application-level failures with no adapter-specific details."""


class NovelApplicationError(RuntimeError):
    """Base class for expected project workflow failures."""


class ProjectAlreadyExistsError(NovelApplicationError):
    pass


class ProjectNotFoundError(NovelApplicationError):
    pass


class ProjectManifestInvalidError(NovelApplicationError):
    pass


class ProjectPathInvalidError(NovelApplicationError):
    pass


class ProjectCatalogEntryNotFoundError(NovelApplicationError):
    pass


class ProjectCatalogPathConflictError(NovelApplicationError):
    pass


class ProjectIdentityConflictError(NovelApplicationError):
    pass


class ProjectSelectionMismatchError(NovelApplicationError):
    pass


class ProjectBusyError(NovelApplicationError):
    pass


class ProjectCatalogBusyError(NovelApplicationError):
    pass


class ProjectCatalogReadError(NovelApplicationError):
    pass


class ProjectCatalogWriteError(NovelApplicationError):
    pass


class LedgerReadError(NovelApplicationError):
    pass


class LedgerConflictError(NovelApplicationError):
    pass


class ManuscriptReadError(NovelApplicationError):
    pass


class NavigationMemoryReadError(NovelApplicationError):
    """A Chapter or Summary source file is unreadable or inconsistent."""


class ChapterNotFoundError(NovelApplicationError):
    """A requested stable Chapter ID is not in the explicit structure."""


class SceneNotFoundError(NovelApplicationError):
    """A requested stable Scene ID is not in the approved projection."""


class SceneHistoryAccessError(NovelApplicationError):
    """A Scene cannot be returned through ordinary historical reading."""


class ProjectionOutOfDateError(NovelApplicationError):
    """The Ledger commit succeeded but its derived projection did not."""

    def __init__(self, revision: str) -> None:
        self.revision = revision
        super().__init__(
            f"Canon Ledger committed at {revision}, but the SQLite projection is out of date"
        )


class FullTextSearchUnavailableError(NovelApplicationError):
    """The local SQLite build cannot provide required FTS5 trigram semantics."""


class ProjectNotBootstrappedError(NovelApplicationError):
    """A creation workflow requires approved project Intent."""


class WorkflowNotFoundError(NovelApplicationError):
    """A requested run, Session, Draft, Review, Publication, or Backfill does not exist."""


class WorkflowStateError(NovelApplicationError):
    """A workflow transition is not valid from the stored state."""


class ApprovalMismatchError(NovelApplicationError):
    """An approval does not bind the current protected content."""


class RevisionConflictError(NovelApplicationError):
    """An authoritative or immutable revision no longer matches its base."""


class PublicationRecoveryRequiredError(NovelApplicationError):
    """Approved publication made progress but did not reach a consistent projection."""


class TraceBackfillRecoveryRequiredError(NovelApplicationError):
    """Approved Trace Backfill made progress but did not reach a consistent projection."""
