"""Reviewable project-local creation run artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TypeVar
from uuid import UUID, uuid4

from pydantic import ValidationError

from novel_adapters.filesystem.project import ProjectLayout
from novel_application.errors import (
    RevisionConflictError,
    WorkflowNotFoundError,
    WorkflowStateError,
)
from novel_core import (
    BootstrapRun,
    DraftRevision,
    IntentContent,
    IntentRevision,
    Publication,
    RetrievedSource,
    Review,
    SceneTraceBackfill,
    WritingSession,
)
from novel_core._base import VersionedDomainModel

ModelType = TypeVar("ModelType", bound=VersionedDomainModel)

INTENT_FILES = {
    "creative_brief": "creative-brief.md",
    "story_bible": "story-bible.md",
    "writing_rules": "writing-rules.md",
    "current_outline": "current-outline.md",
}


class RunSourceSnapshot:
    def __init__(
        self,
        *,
        bootstrap_runs: tuple[BootstrapRun, ...],
        intent_revisions: tuple[IntentRevision, ...],
        writing_sessions: tuple[WritingSession, ...],
        drafts: tuple[DraftRevision, ...],
        reviews: tuple[Review, ...],
        retrieved_sources: tuple[RetrievedSource, ...],
        publications: tuple[Publication, ...],
        trace_backfills: tuple[SceneTraceBackfill, ...],
        revision: str,
    ) -> None:
        self.bootstrap_runs = bootstrap_runs
        self.intent_revisions = intent_revisions
        self.writing_sessions = writing_sessions
        self.drafts = drafts
        self.reviews = reviews
        self.retrieved_sources = retrieved_sources
        self.publications = publications
        self.trace_backfills = trace_backfills
        self.revision = revision


class FilesystemRunIndexStore:
    """Load complete run metadata and hash every preserved run artifact."""

    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    def load_snapshot(self) -> RunSourceSnapshot:
        bootstrap = self._load_pattern(
            self.layout.bootstrap_runs,
            "*/bootstrap.json",
            BootstrapRun,
            "Bootstrap Run",
        )
        intent = self._load_pattern(
            self.layout.intent_runs,
            "*/intent-revision.json",
            IntentRevision,
            "Intent Revision",
        )
        sessions = self._load_pattern(
            self.layout.writing_runs,
            "*/session.json",
            WritingSession,
            "Writing Session",
        )
        drafts = self._load_pattern(
            self.layout.writing_runs,
            "*/drafts/*.json",
            DraftRevision,
            "Draft Revision",
        )
        reviews = self._load_pattern(
            self.layout.writing_runs,
            "*/reviews/*.json",
            Review,
            "Review",
        )
        sources = self._load_pattern(
            self.layout.writing_runs,
            "*/retrieved-sources/*.json",
            RetrievedSource,
            "Retrieved Source",
        )
        publications = self._load_pattern(
            self.layout.publication_runs,
            "*/publication.json",
            Publication,
            "Publication",
        )
        trace_backfills = self._load_pattern(
            self.layout.trace_backfill_runs,
            "*/backfill.json",
            SceneTraceBackfill,
            "Scene Trace Backfill",
        )
        hasher = hashlib.sha256()
        runs_root = self.layout.root / "runs"
        if runs_root.is_dir():
            for path in sorted(item for item in runs_root.rglob("*") if item.is_file()):
                try:
                    content = path.read_bytes()
                except OSError as exc:
                    raise WorkflowStateError(f"cannot read run artifact: {path}") from exc
                hasher.update(path.relative_to(self.layout.root).as_posix().encode("utf-8"))
                hasher.update(b"\0")
                hasher.update(content)
                hasher.update(b"\0")
        return RunSourceSnapshot(
            bootstrap_runs=bootstrap,
            intent_revisions=intent,
            writing_sessions=sessions,
            drafts=drafts,
            reviews=reviews,
            retrieved_sources=sources,
            publications=publications,
            trace_backfills=trace_backfills,
            revision=f"sha256:{hasher.hexdigest()}",
        )

    def health_issues(self) -> tuple[str, ...]:
        snapshot = self.load_snapshot()
        active_transaction_states = {
            "manuscript_installed",
            "navigation_installed",
            "intent_installed",
            "ledger_appended",
            "projection_rebuilt",
        }
        return tuple(
            "unfinished Publication transaction: "
            f"{publication.plan.publication_id} ({publication.status.value})"
            for publication in snapshot.publications
            if publication.status.value in active_transaction_states
        ) + tuple(
            "unfinished Trace Backfill transaction: "
            f"{backfill.plan.backfill_id} ({backfill.status.value})"
            for backfill in snapshot.trace_backfills
            if backfill.status.value
            in {
                "ledger_appended",
                "trace_installed",
                "projection_rebuilt",
            }
        )

    @staticmethod
    def _load_pattern(
        root: Path,
        pattern: str,
        model: type[ModelType],
        label: str,
    ) -> tuple[ModelType, ...]:
        if not root.is_dir():
            return ()
        return tuple(_load_model(path, model, label) for path in sorted(root.glob(pattern)))


class FilesystemIntentStore:
    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    def load(self) -> IntentContent | None:
        paths = {field: self.layout.intent / filename for field, filename in INTENT_FILES.items()}
        present = {field: path.is_file() for field, path in paths.items()}
        if not any(present.values()):
            return None
        if not all(present.values()):
            missing = ", ".join(field for field, exists in present.items() if not exists)
            raise WorkflowStateError(f"Intent Canon is incomplete; missing: {missing}")
        try:
            return IntentContent(
                **{field: path.read_text(encoding="utf-8") for field, path in paths.items()}
            )
        except (OSError, UnicodeDecodeError, ValidationError) as exc:
            raise WorkflowStateError("Intent Canon is unreadable or invalid") from exc

    def replace(self, content: IntentContent) -> None:
        for field, filename in INTENT_FILES.items():
            _replace_bytes(
                self.layout.intent / filename,
                getattr(content, field).encode("utf-8"),
            )


class FilesystemBootstrapRunStore:
    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    def create(self, run: BootstrapRun) -> None:
        _create_model(self._path(run.bootstrap_id), run)

    def load(self, bootstrap_id: UUID) -> BootstrapRun:
        return _load_model(self._path(bootstrap_id), BootstrapRun, "Bootstrap Run")

    def replace(self, run: BootstrapRun) -> None:
        _replace_model(self._path(run.bootstrap_id), run)

    def _path(self, bootstrap_id: UUID) -> Path:
        return self.layout.bootstrap_runs / str(bootstrap_id) / "bootstrap.json"


class FilesystemIntentRevisionStore:
    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    def create(self, revision: IntentRevision) -> None:
        _create_model(self._path(revision.intent_revision_id), revision)

    def load(self, intent_revision_id: UUID) -> IntentRevision:
        return _load_model(
            self._path(intent_revision_id),
            IntentRevision,
            "Intent Revision",
        )

    def replace(self, revision: IntentRevision) -> None:
        _replace_model(self._path(revision.intent_revision_id), revision)

    def _path(self, intent_revision_id: UUID) -> Path:
        return self.layout.intent_runs / str(intent_revision_id) / "intent-revision.json"


class FilesystemWritingRunStore:
    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    def create_session(self, session: WritingSession) -> None:
        _create_model(self._session_path(session.writing_session_id), session)

    def load_session(self, writing_session_id: UUID) -> WritingSession:
        return _load_model(
            self._session_path(writing_session_id),
            WritingSession,
            "Writing Session",
        )

    def replace_session(self, session: WritingSession) -> None:
        _replace_model(self._session_path(session.writing_session_id), session)

    def save_draft(self, draft: DraftRevision, content: bytes) -> None:
        directory = self._run(draft.writing_session_id) / "drafts"
        metadata = directory / f"{draft.draft_revision.removeprefix('sha256:')}.json"
        manuscript = directory / f"{draft.draft_revision.removeprefix('sha256:')}.md"
        if metadata.exists() or manuscript.exists():
            try:
                existing, existing_content = self.load_draft(
                    draft.writing_session_id,
                    draft.draft_revision,
                )
            except WorkflowNotFoundError as exc:
                raise RevisionConflictError("Draft revision is only partially stored") from exc
            if existing == draft and existing_content == content:
                return
            raise RevisionConflictError(f"Draft revision already exists: {draft.draft_revision}")
        _create_bytes(manuscript, content)
        try:
            _create_model(metadata, draft)
        except Exception:
            manuscript.unlink(missing_ok=True)
            raise

    def load_draft(
        self,
        writing_session_id: UUID,
        draft_revision: str,
    ) -> tuple[DraftRevision, bytes]:
        stem = _digest_stem(draft_revision)
        directory = self._run(writing_session_id) / "drafts"
        metadata = _load_model(directory / f"{stem}.json", DraftRevision, "Draft Revision")
        manuscript = directory / f"{stem}.md"
        try:
            content = manuscript.read_bytes()
        except FileNotFoundError as exc:
            raise WorkflowNotFoundError(
                f"Draft manuscript does not exist: {draft_revision}"
            ) from exc
        except OSError as exc:
            raise WorkflowStateError(f"cannot read Draft manuscript: {draft_revision}") from exc
        return metadata, content

    def list_drafts(self, writing_session_id: UUID) -> tuple[DraftRevision, ...]:
        directory = self._run(writing_session_id) / "drafts"
        if not directory.is_dir():
            return ()
        drafts = [
            _load_model(path, DraftRevision, "Draft Revision")
            for path in sorted(directory.glob("*.json"))
        ]
        return tuple(sorted(drafts, key=lambda item: (item.created_at, item.draft_revision)))

    def save_review(self, review: Review) -> None:
        _create_model(
            self._run(review.writing_session_id) / "reviews" / f"{review.review_id}.json",
            review,
        )

    def load_review(self, writing_session_id: UUID, review_id: UUID) -> Review:
        return _load_model(
            self._run(writing_session_id) / "reviews" / f"{review_id}.json",
            Review,
            "Review",
        )

    def list_reviews(self, writing_session_id: UUID) -> tuple[Review, ...]:
        directory = self._run(writing_session_id) / "reviews"
        if not directory.is_dir():
            return ()
        reviews = [_load_model(path, Review, "Review") for path in sorted(directory.glob("*.json"))]
        return tuple(sorted(reviews, key=lambda item: (item.created_at, str(item.review_id))))

    def save_retrieved_source(self, source: RetrievedSource) -> None:
        _create_model(
            self._run(source.writing_session_id)
            / "retrieved-sources"
            / f"{source.retrieved_source_id}.json",
            source,
        )

    def list_retrieved_sources(
        self,
        writing_session_id: UUID,
    ) -> tuple[RetrievedSource, ...]:
        directory = self._run(writing_session_id) / "retrieved-sources"
        if not directory.is_dir():
            return ()
        sources = [
            _load_model(path, RetrievedSource, "Retrieved Source")
            for path in sorted(directory.glob("*.json"))
        ]
        return tuple(
            sorted(
                sources,
                key=lambda item: (
                    item.retrieved_at,
                    str(item.retrieved_source_id),
                ),
            )
        )

    def _session_path(self, writing_session_id: UUID) -> Path:
        return self._run(writing_session_id) / "session.json"

    def _run(self, writing_session_id: UUID) -> Path:
        return self.layout.writing_runs / str(writing_session_id)


class FilesystemPublicationStore:
    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    def create(self, publication: Publication) -> None:
        _create_model(self._path(publication.plan.publication_id), publication)

    def load(self, publication_id: UUID) -> Publication:
        return _load_model(self._path(publication_id), Publication, "Publication")

    def replace(self, publication: Publication) -> None:
        _replace_model(self._path(publication.plan.publication_id), publication)

    def _path(self, publication_id: UUID) -> Path:
        return self.layout.publication_runs / str(publication_id) / "publication.json"


class FilesystemSceneTraceBackfillStore:
    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    def create(self, backfill: SceneTraceBackfill) -> None:
        _create_model(self._path(backfill.plan.backfill_id), backfill)

    def load(self, backfill_id: UUID) -> SceneTraceBackfill:
        return _load_model(
            self._path(backfill_id),
            SceneTraceBackfill,
            "Scene Trace Backfill",
        )

    def replace(self, backfill: SceneTraceBackfill) -> None:
        _replace_model(self._path(backfill.plan.backfill_id), backfill)

    def _path(self, backfill_id: UUID) -> Path:
        return self.layout.trace_backfill_runs / str(backfill_id) / "backfill.json"


def _digest_stem(revision: str) -> str:
    if not revision.startswith("sha256:") or len(revision) != 71:
        raise WorkflowNotFoundError(f"invalid content revision: {revision}")
    return revision.removeprefix("sha256:")


def _model_bytes(model: VersionedDomainModel) -> bytes:
    return (
        json.dumps(
            model.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _load_model[LoadedModel: VersionedDomainModel](
    path: Path,
    model: type[LoadedModel],
    label: str,
) -> LoadedModel:
    try:
        return model.model_validate_json(path.read_bytes())
    except FileNotFoundError as exc:
        raise WorkflowNotFoundError(f"{label} does not exist: {path}") from exc
    except (OSError, ValidationError) as exc:
        raise WorkflowStateError(f"{label} is unreadable or invalid: {path}") from exc


def _create_model(path: Path, model: VersionedDomainModel) -> None:
    _create_bytes(path, _model_bytes(model))


def _replace_model(path: Path, model: VersionedDomainModel) -> None:
    if not path.is_file():
        raise WorkflowNotFoundError(f"workflow artifact does not exist: {path}")
    _replace_bytes(path, _model_bytes(model))


def _create_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise RevisionConflictError(f"refusing to overwrite immutable artifact: {path}") from exc


def _replace_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
