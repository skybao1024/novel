"""Stable human and JSON command protocol for Novel."""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from novel_adapters.filesystem import (
    FilesystemBootstrapRunStore,
    FilesystemCanonLedgerStore,
    FilesystemIntentRevisionStore,
    FilesystemIntentStore,
    FilesystemManuscriptStore,
    FilesystemNavigationStore,
    FilesystemProjectCatalogStore,
    FilesystemProjectCatalogWriteLock,
    FilesystemProjectStore,
    FilesystemProjectWorkspace,
    FilesystemProjectWriteLock,
    FilesystemPublicationStore,
    FilesystemRunIndexStore,
    FilesystemWritingRunStore,
    default_app_data_directory,
)
from novel_adapters.sqlite import (
    SQLiteProjectionQueries,
    SQLiteProjectionStore,
)
from novel_application import (
    ApprovalMismatchError,
    BootstrapService,
    CanonQueryService,
    ChapterNotFoundError,
    DraftService,
    FullTextSearchUnavailableError,
    IntentService,
    LedgerConflictError,
    LedgerReadError,
    ManuscriptReadError,
    NavigationMemoryReadError,
    NavigationMemoryService,
    ProjectAlreadyExistsError,
    ProjectBusyError,
    ProjectCatalogBusyError,
    ProjectCatalogEntryNotFoundError,
    ProjectCatalogPathConflictError,
    ProjectCatalogReadError,
    ProjectCatalogService,
    ProjectCatalogWriteError,
    ProjectHealth,
    ProjectIdentityConflictError,
    ProjectionOutOfDateError,
    ProjectionStatus,
    ProjectManifestInvalidError,
    ProjectNotBootstrappedError,
    ProjectNotFoundError,
    ProjectPathInvalidError,
    ProjectResolution,
    ProjectSelectionMismatchError,
    ProjectService,
    PublicationRecoveryRequiredError,
    PublicationService,
    ReviewService,
    RevisionConflictError,
    SceneHistoryAccessError,
    SceneNotFoundError,
    SessionNavigationService,
    WorkflowNotFoundError,
    WorkflowStateError,
    WritingSessionService,
)
from novel_core import (
    SCHEMA_VERSION,
    BootstrapDraft,
    BootstrapEntityDraft,
    ChapterSummary,
    CharacterStatePhase,
    EventChainDirection,
    IntentContent,
    ProjectCatalogEntry,
    ProjectManifest,
    ReviewRecommendation,
    StoryTime,
)
from novel_core.canon.ledger import LedgerRecord
from novel_core.schemas import schema_documents

PROTOCOL_VERSION = "1.0"
EXIT_OK = 0
EXIT_INVALID_INPUT = 2
EXIT_PROJECT = 3
EXIT_CONFLICT = 4
EXIT_BUSY = 5
EXIT_STORAGE = 6
EXIT_INTERNAL = 10


class CliUsageError(ValueError):
    """An argparse failure that must cross the versioned CLI envelope."""


class EnvelopeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    machine = "--json" in arguments
    arguments = [item for item in arguments if item != "--json"]
    parser = _build_parser()
    try:
        args = parser.parse_args(arguments)
    except CliUsageError as exc:
        _emit_error(
            _command_hint(arguments),
            "invalid_input",
            str(exc),
            machine=machine,
        )
        return EXIT_INVALID_INPUT
    except SystemExit as exc:
        return int(exc.code)

    command = " ".join(part for part in (args.command, getattr(args, "subcommand", None)) if part)
    try:
        data, warnings = _dispatch(args)
        _emit_success(command, data, warnings=warnings, machine=machine)
        return EXIT_OK
    except Exception as exc:  # CLI is the error-to-protocol boundary.
        code, exit_code = _map_error(exc)
        _emit_error(command, code, str(exc), machine=machine)
        return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = EnvelopeArgumentParser(prog="novel")
    parser.add_argument("--project", type=Path, default=None)
    parser.add_argument("--project-id", type=UUID, default=None)
    parser.add_argument(
        "--catalog-dir",
        type=Path,
        default=None,
        help="override the user-level Novel application data directory",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("version")
    subparsers.add_parser("protocol-version")

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--repair", action="store_true")

    project = subparsers.add_parser("project")
    project_sub = project.add_subparsers(dest="subcommand", required=True)
    project_sub.add_parser("list")
    project_create = project_sub.add_parser("create")
    project_create.add_argument("path", type=Path)
    project_create.add_argument("--title", required=True)
    project_create.add_argument("--language", default="zh-CN")
    project_add = project_sub.add_parser("add")
    project_add.add_argument("path", type=Path)
    project_show = project_sub.add_parser("show")
    project_show.add_argument("--project", dest="show_project", type=Path, default=None)
    project_show.add_argument("--project-id", dest="show_project_id", type=UUID, default=None)
    project_remove = project_sub.add_parser("remove")
    project_remove.add_argument(
        "--project-id",
        dest="remove_project_id",
        type=UUID,
        default=None,
    )

    bootstrap = subparsers.add_parser("bootstrap")
    bootstrap_sub = bootstrap.add_subparsers(dest="subcommand", required=True)
    bootstrap_sub.add_parser("start")
    bootstrap_save = bootstrap_sub.add_parser("save")
    bootstrap_save.add_argument("--bootstrap-id", type=UUID, required=True)
    _add_intent_file_arguments(bootstrap_save, required=True)
    bootstrap_save.add_argument("--entities", type=Path)
    bootstrap_save.add_argument("--initial-goal", required=True)
    bootstrap_save.add_argument("--unresolved-question", action="append", default=[])
    bootstrap_inspect = bootstrap_sub.add_parser("inspect")
    bootstrap_inspect.add_argument("--bootstrap-id", type=UUID, required=True)
    bootstrap_approve = bootstrap_sub.add_parser("approve")
    bootstrap_approve.add_argument("--bootstrap-id", type=UUID, required=True)
    bootstrap_approve.add_argument("--approval-digest", required=True)
    bootstrap_apply = bootstrap_sub.add_parser("apply")
    bootstrap_apply.add_argument("--bootstrap-id", type=UUID, required=True)

    intent = subparsers.add_parser("intent")
    intent_sub = intent.add_subparsers(dest="subcommand", required=True)
    intent_sub.add_parser("show")
    intent_prepare = intent_sub.add_parser("prepare")
    _add_intent_file_arguments(intent_prepare, required=False)
    intent_inspect = intent_sub.add_parser("inspect")
    intent_inspect.add_argument("--intent-revision-id", type=UUID, required=True)
    intent_approve = intent_sub.add_parser("approve")
    intent_approve.add_argument("--intent-revision-id", type=UUID, required=True)
    intent_approve.add_argument("--approval-digest", required=True)
    intent_apply = intent_sub.add_parser("apply")
    intent_apply.add_argument("--intent-revision-id", type=UUID, required=True)

    session = subparsers.add_parser("session")
    session_sub = session.add_subparsers(dest="subcommand", required=True)
    session_start = session_sub.add_parser("start")
    session_start.add_argument("--author-goal", required=True)
    session_start.add_argument("--story-time", type=Path, required=True)
    session_start.add_argument("--chapter-id", type=UUID)
    session_start.add_argument("--new-chapter-number", type=int)
    session_start.add_argument("--new-chapter-title")
    session_start.add_argument("--before-scene-id", type=UUID)
    session_start.add_argument("--after-scene-id", type=UUID)
    session_start.add_argument("--constraint", action="append", default=[])
    session_start.add_argument("--pov-entity-id", type=UUID)
    session_start.add_argument("--location-entity-id", type=UUID)
    session_show = session_sub.add_parser("show")
    session_show.add_argument("--session-id", type=UUID, required=True)
    session_context = session_sub.add_parser("context")
    session_context.add_argument("--session-id", type=UUID, required=True)
    session_close = session_sub.add_parser("close")
    session_close.add_argument("--session-id", type=UUID, required=True)

    resolve = subparsers.add_parser("resolve")
    resolve_sub = resolve.add_subparsers(dest="subcommand", required=True)
    resolve_entity = resolve_sub.add_parser("entity")
    resolve_entity.add_argument("alias")
    resolve_entity.add_argument("--session-id", type=UUID)

    query = subparsers.add_parser("query")
    query_sub = query.add_subparsers(dest="subcommand", required=True)
    character = query_sub.add_parser("character")
    character.add_argument("character_id", type=UUID)
    character.add_argument("--at-scene", type=UUID, required=True)
    character.add_argument("--session-id", type=UUID)
    character.add_argument(
        "--phase",
        choices=[item.value for item in CharacterStatePhase],
        default=CharacterStatePhase.ENTRY.value,
    )
    event_chain = query_sub.add_parser("event-chain")
    event_chain.add_argument("event_id", type=UUID)
    event_chain.add_argument(
        "--direction",
        choices=[item.value for item in EventChainDirection],
        default=EventChainDirection.BOTH.value,
    )
    event_chain.add_argument("--depth", type=int, default=3)
    event_chain.add_argument("--session-id", type=UUID)

    memory = subparsers.add_parser("memory")
    memory_sub = memory.add_subparsers(dest="subcommand", required=True)
    memory_chapters = memory_sub.add_parser("chapters")
    memory_chapters.add_argument("--session-id", type=UUID)
    memory_scenes = memory_sub.add_parser("scenes")
    memory_scenes.add_argument("--chapter-id", type=UUID, required=True)
    memory_scenes.add_argument("--session-id", type=UUID)
    memory_search = memory_sub.add_parser("search-summaries")
    memory_search.add_argument("--query")
    memory_search.add_argument("--entity", type=UUID)
    memory_search.add_argument("--before-scene", type=UUID)
    memory_search.add_argument("--session-id", type=UUID)
    memory_search.add_argument("--limit", type=int, default=20)
    memory_read = memory_sub.add_parser("read-scene")
    memory_read.add_argument("--chapter-id", type=UUID, required=True)
    memory_read.add_argument("--scene-id", type=UUID, required=True)
    memory_read.add_argument("--before-scene", type=UUID)
    memory_read.add_argument("--session-id", type=UUID)

    draft = subparsers.add_parser("draft")
    draft_sub = draft.add_subparsers(dest="subcommand", required=True)
    draft_save = draft_sub.add_parser("save")
    draft_save.add_argument("--session-id", type=UUID, required=True)
    draft_save.add_argument("--file", type=Path, required=True)
    draft_save.add_argument("--parent-revision")
    draft_list = draft_sub.add_parser("list")
    draft_list.add_argument("--session-id", type=UUID, required=True)
    draft_show = draft_sub.add_parser("show")
    draft_show.add_argument("--session-id", type=UUID, required=True)
    draft_show.add_argument("--draft-revision", required=True)
    draft_diff = draft_sub.add_parser("diff")
    draft_diff.add_argument("--session-id", type=UUID, required=True)
    draft_diff.add_argument("--draft-revision", required=True)
    draft_diff.add_argument("--from-revision")

    review = subparsers.add_parser("review")
    review_sub = review.add_subparsers(dest="subcommand", required=True)
    review_save = review_sub.add_parser("save")
    review_save.add_argument("--session-id", type=UUID, required=True)
    review_save.add_argument("--draft-revision", required=True)
    review_save.add_argument(
        "--recommendation",
        choices=[item.value for item in ReviewRecommendation],
        required=True,
    )
    review_save.add_argument("--conclusion", required=True)
    review_save.add_argument("--finding", action="append", default=[])
    review_save.add_argument("--uncertainty", action="append", default=[])
    review_save.add_argument("--retrieved-source-id", type=UUID, action="append", default=[])
    review_list = review_sub.add_parser("list")
    review_list.add_argument("--session-id", type=UUID, required=True)
    review_show = review_sub.add_parser("show")
    review_show.add_argument("--session-id", type=UUID, required=True)
    review_show.add_argument("--review-id", type=UUID, required=True)

    publish = subparsers.add_parser("publish")
    publish_sub = publish.add_subparsers(dest="subcommand", required=True)
    publish_prepare = publish_sub.add_parser("prepare")
    publish_prepare.add_argument("--session-id", type=UUID, required=True)
    publish_prepare.add_argument("--draft-revision", required=True)
    publish_prepare.add_argument("--scene-summary", type=Path, required=True)
    publish_prepare.add_argument("--chapter-summary", type=Path, required=True)
    publish_prepare.add_argument("--review-id", type=UUID, action="append", required=True)
    publish_prepare.add_argument("--scene-main-entity-id", type=UUID, action="append", default=[])
    publish_prepare.add_argument("--scene-key-change", action="append", default=[])
    publish_prepare.add_argument("--scene-open-question", action="append", default=[])
    publish_prepare.add_argument(
        "--chapter-main-entity-id",
        type=UUID,
        action="append",
        default=[],
    )
    publish_prepare.add_argument("--canon-records", type=Path)
    publish_prepare.add_argument("--intent-revision-id", type=UUID)
    publish_prepare.add_argument("--unresolved-question", action="append", default=[])
    publish_inspect = publish_sub.add_parser("inspect")
    publish_inspect.add_argument("--publication-id", type=UUID, required=True)
    publish_approve = publish_sub.add_parser("approve")
    publish_approve.add_argument("--publication-id", type=UUID, required=True)
    publish_approve.add_argument("--approval-digest", required=True)
    publish_apply = publish_sub.add_parser("apply")
    publish_apply.add_argument("--publication-id", type=UUID, required=True)
    publish_recover = publish_sub.add_parser("recover")
    publish_recover.add_argument("--publication-id", type=UUID, required=True)

    subparsers.add_parser("rebuild")

    schema = subparsers.add_parser("schema")
    schema_sub = schema.add_subparsers(dest="subcommand", required=True)
    schema_show = schema_sub.add_parser("show")
    schema_show.add_argument("name")
    return parser


def _add_intent_file_arguments(
    parser: argparse.ArgumentParser,
    *,
    required: bool,
) -> None:
    parser.add_argument("--creative-brief", type=Path, required=required)
    parser.add_argument("--story-bible", type=Path, required=required)
    parser.add_argument("--writing-rules", type=Path, required=required)
    parser.add_argument("--current-outline", type=Path, required=required)


def _dispatch(args: argparse.Namespace) -> tuple[Any, tuple[str, ...]]:
    if args.command == "version":
        return {
            "version": _package_version(),
            "core_schema_version": SCHEMA_VERSION,
            "protocol_version": PROTOCOL_VERSION,
        }, ()
    if args.command == "protocol-version":
        return {"protocol_version": PROTOCOL_VERSION}, ()
    if args.command == "schema":
        return _show_schema(args.name), ()
    catalog = _catalog_service(args.catalog_dir)
    if args.command == "project":
        return _project_command(args, catalog), ()

    resolution = catalog.resolve(
        project_id=args.project_id,
        project_path=str(args.project) if args.project is not None else None,
        discovery_start=str(Path.cwd()),
    )
    services = _services(resolution)
    root = Path(resolution.project_path)
    if args.command == "bootstrap":
        data = _bootstrap_command(args, services)
        if args.subcommand == "apply":
            catalog.refresh(project_path=resolution.project_path)
        if args.subcommand != "inspect":
            services.projects.rebuild_projection()
        return data, ()
    if args.command == "intent":
        data = _intent_command(args, services)
        if args.subcommand not in {"show", "inspect"}:
            services.projects.rebuild_projection()
        return data, ()
    if args.command == "session":
        data = _session_command(args, services)
        if args.subcommand in {"start", "close"}:
            services.projects.rebuild_projection()
        return data, ()
    if args.command == "draft":
        data = _draft_command(args, services)
        if args.subcommand == "save":
            services.projects.rebuild_projection()
        return data, ()
    if args.command == "review":
        data = _review_command(args, services)
        if args.subcommand == "save":
            services.projects.rebuild_projection()
        return data, ()
    if args.command == "publish":
        data = _publish_command(args, services)
        if args.subcommand != "inspect":
            services.projects.rebuild_projection()
        return data, ()
    if args.command == "doctor":
        status = (
            services.projects.rebuild_projection()
            if args.repair
            else services.projects.ensure_projection_current()
        )
        health = services.projects.inspect_health()
        return {
            "project_id": str(resolution.manifest.project_id),
            "project": str(root),
            "canon_revision": status.canon_revision,
            "last_ledger_sequence": status.last_ledger_sequence,
            "healthy": health.storage_healthy,
            "issues": list(health.issues),
        }, tuple(health.issues)
    if args.command == "resolve":
        entities = services.queries.find_entities_by_alias(args.alias)
        if args.session_id is not None:
            services.session_memory.record_canon_query(
                args.session_id,
                source_refs=(),
                reason=f"Entity alias resolution: {args.alias}",
            )
            services.projects.rebuild_projection()
        return {
            "alias": args.alias,
            "matches": [item.model_dump(mode="json") for item in entities],
        }, ()
    if args.command == "query":
        if args.subcommand == "character":
            if args.session_id is not None:
                services.session_memory.validate_canon_scene_ids(
                    args.session_id,
                    (args.at_scene,),
                )
            state = services.queries.character_state(
                args.character_id,
                at_scene_id=args.at_scene,
                phase=CharacterStatePhase(args.phase),
            )
            if args.session_id is not None:
                services.session_memory.record_canon_query(
                    args.session_id,
                    source_refs=_character_source_refs(state),
                    reason=f"Character state at Scene {args.at_scene}",
                )
                services.projects.rebuild_projection()
            return state.model_dump(mode="json"), tuple(item.message for item in state.warnings)
        chain = services.queries.event_chain(
            args.event_id,
            direction=EventChainDirection(args.direction),
            max_depth=args.depth,
        )
        if args.session_id is not None:
            services.session_memory.validate_canon_scene_ids(
                args.session_id,
                tuple(event.source_scene_id for event in chain.events),
            )
            services.session_memory.record_canon_query(
                args.session_id,
                source_refs=chain.source_refs,
                reason=f"Event chain for {args.event_id}",
            )
            services.projects.rebuild_projection()
        return chain.model_dump(mode="json"), tuple(item.message for item in chain.warnings)
    if args.command == "memory":
        data = _memory_command(args, services)
        if getattr(args, "session_id", None) is not None:
            services.projects.rebuild_projection()
        return data, ()
    if args.command == "rebuild":
        status = services.projects.rebuild_projection()
        return {
            "project_id": str(resolution.manifest.project_id),
            "project": resolution.project_path,
            "canon_revision": status.canon_revision,
            "last_ledger_sequence": status.last_ledger_sequence,
        }, ()
    raise ValueError(f"unsupported command: {args.command}")


def _bootstrap_command(args: argparse.Namespace, services: _ServiceBundle) -> dict[str, Any]:
    if args.subcommand == "start":
        run = services.bootstrap.start()
    elif args.subcommand == "save":
        run = services.bootstrap.save(
            args.bootstrap_id,
            BootstrapDraft(
                intent=_intent_from_arguments(args, current=None),
                entity_drafts=(
                    _read_tuple(args.entities, tuple[BootstrapEntityDraft, ...])
                    if args.entities is not None
                    else ()
                ),
                initial_goal=args.initial_goal,
                unresolved_questions=tuple(args.unresolved_question),
            ),
        )
    elif args.subcommand == "inspect":
        run = services.bootstrap.inspect(args.bootstrap_id)
    elif args.subcommand == "approve":
        run = services.bootstrap.approve(args.bootstrap_id, args.approval_digest)
    else:
        run = services.bootstrap.apply(args.bootstrap_id)
    return run.model_dump(mode="json")


def _intent_command(args: argparse.Namespace, services: _ServiceBundle) -> dict[str, Any]:
    if args.subcommand == "show":
        content, revision = services.intent.show()
        return {
            "schema_version": SCHEMA_VERSION,
            "intent_revision": revision,
            "intent": content.model_dump(mode="json"),
        }
    if args.subcommand == "prepare":
        current, _revision = services.intent.show()
        candidate = _intent_from_arguments(args, current=current)
        return services.intent.prepare(candidate).model_dump(mode="json")
    if args.subcommand == "inspect":
        revision = services.intent.inspect(args.intent_revision_id)
    elif args.subcommand == "approve":
        revision = services.intent.approve(
            args.intent_revision_id,
            args.approval_digest,
        )
    else:
        revision = services.intent.apply(args.intent_revision_id)
    return revision.model_dump(mode="json")


def _session_command(args: argparse.Namespace, services: _ServiceBundle) -> dict[str, Any]:
    if args.subcommand == "start":
        session = services.sessions.start(
            author_goal=args.author_goal,
            target_story_time=_read_model(args.story_time, StoryTime),
            chapter_id=args.chapter_id,
            new_chapter_number=args.new_chapter_number,
            new_chapter_title=args.new_chapter_title,
            before_scene_id=args.before_scene_id,
            after_scene_id=args.after_scene_id,
            creative_constraints=tuple(args.constraint),
            pov_entity_id=args.pov_entity_id,
            location_entity_id=args.location_entity_id,
        )
        return session.model_dump(mode="json")
    if args.subcommand == "show":
        session = services.sessions.show(args.session_id)
        data = session.model_dump(mode="json")
        data["retrieved_sources"] = [
            item.model_dump(mode="json")
            for item in services.stores.writing.list_retrieved_sources(args.session_id)
        ]
        return data
    if args.subcommand == "context":
        return services.sessions.context(args.session_id).model_dump(mode="json")
    return services.sessions.close(args.session_id).model_dump(mode="json")


def _draft_command(args: argparse.Namespace, services: _ServiceBundle) -> dict[str, Any]:
    if args.subcommand == "save":
        content = _read_bytes(args.file)
        return services.drafts.save(
            args.session_id,
            content,
            parent_revision=args.parent_revision,
        ).model_dump(mode="json")
    if args.subcommand == "list":
        return {
            "schema_version": SCHEMA_VERSION,
            "writing_session_id": str(args.session_id),
            "drafts": [
                item.model_dump(mode="json") for item in services.drafts.list(args.session_id)
            ],
        }
    if args.subcommand == "show":
        draft, text = services.drafts.show(args.session_id, args.draft_revision)
        return {**draft.model_dump(mode="json"), "text": text}
    return {
        "schema_version": SCHEMA_VERSION,
        "writing_session_id": str(args.session_id),
        "draft_revision": args.draft_revision,
        "diff": services.drafts.diff(
            args.session_id,
            args.draft_revision,
            from_revision=args.from_revision,
        ),
    }


def _review_command(args: argparse.Namespace, services: _ServiceBundle) -> dict[str, Any]:
    if args.subcommand == "save":
        review = services.reviews.save(
            writing_session_id=args.session_id,
            draft_revision=args.draft_revision,
            recommendation=ReviewRecommendation(args.recommendation),
            conclusion=args.conclusion,
            findings=tuple(args.finding),
            uncertainties=tuple(args.uncertainty),
            retrieved_source_ids=tuple(args.retrieved_source_id),
        )
        return review.model_dump(mode="json")
    if args.subcommand == "list":
        return {
            "schema_version": SCHEMA_VERSION,
            "writing_session_id": str(args.session_id),
            "reviews": [
                item.model_dump(mode="json") for item in services.reviews.list(args.session_id)
            ],
        }
    return services.reviews.show(
        args.session_id,
        args.review_id,
    ).model_dump(mode="json")


def _publish_command(args: argparse.Namespace, services: _ServiceBundle) -> dict[str, Any]:
    if args.subcommand == "prepare":
        canon_records = (
            _read_tuple(args.canon_records, tuple[LedgerRecord, ...])
            if args.canon_records is not None
            else ()
        )
        publication = services.publications.prepare(
            writing_session_id=args.session_id,
            draft_revision=args.draft_revision,
            scene_summary_text=_read_text(args.scene_summary),
            chapter_summary_text=_read_text(args.chapter_summary),
            review_refs=tuple(args.review_id),
            scene_main_entity_ids=tuple(args.scene_main_entity_id),
            scene_key_changes=tuple(args.scene_key_change),
            scene_open_questions=tuple(args.scene_open_question),
            chapter_main_entity_ids=tuple(args.chapter_main_entity_id),
            canon_records=canon_records,
            intent_revision_id=args.intent_revision_id,
            unresolved_questions=tuple(args.unresolved_question),
        )
    elif args.subcommand == "inspect":
        publication = services.publications.inspect(args.publication_id)
    elif args.subcommand == "approve":
        publication = services.publications.approve(
            args.publication_id,
            args.approval_digest,
        )
    elif args.subcommand == "apply":
        publication = services.publications.apply(args.publication_id)
    else:
        publication = services.publications.recover(args.publication_id)
    return publication.model_dump(mode="json")


def _project_command(
    args: argparse.Namespace,
    catalog: ProjectCatalogService,
) -> dict[str, Any]:
    if args.subcommand == "list":
        _reject_global_selection(args)
        return {
            "schema_version": SCHEMA_VERSION,
            "projects": [
                {
                    **_catalog_entry_data(item.entry),
                    "path_exists": item.path_exists,
                }
                for item in catalog.list_projects()
            ],
        }
    if args.subcommand == "create":
        _reject_global_selection(args)
        result = catalog.create(
            project_path=str(args.path),
            title=args.title,
            language=args.language,
            minimum_core_version=_package_version(),
        )
        return {
            **_catalog_entry_data(result.entry),
            "manifest": result.manifest.model_dump(mode="json"),
            "canon_revision": result.projection.canon_revision,
            "last_ledger_sequence": result.projection.last_ledger_sequence,
        }
    if args.subcommand == "add":
        _reject_global_selection(args)
        result = catalog.add(project_path=str(args.path))
        return {
            **_catalog_entry_data(result.entry),
            "catalog_action": "path_updated" if result.path_updated else "registered",
        }
    if args.subcommand == "show":
        project_id = _merge_selection(
            args.project_id,
            args.show_project_id,
            option="--project-id",
        )
        project_path = _merge_selection(
            args.project,
            args.show_project,
            option="--project",
        )
        details = catalog.show(
            project_id=project_id,
            project_path=str(project_path) if project_path is not None else None,
            discovery_start=str(Path.cwd()),
        )
        resolution = details.resolution
        entry = resolution.catalog_entry
        return {
            "project_id": str(resolution.manifest.project_id),
            "project_path": resolution.project_path,
            "status": resolution.manifest.status.value,
            "manifest": resolution.manifest.model_dump(mode="json"),
            "catalog": {
                "registered": entry is not None,
                "path_matches": resolution.catalog_path_matches,
                "entry": _catalog_entry_data(entry) if entry is not None else None,
            },
            "health": {
                "path_exists": True,
                "manifest_valid": True,
                "ledger_readable": details.health.ledger_readable,
                "projection_current": details.health.projection_current,
                "storage_healthy": details.health.storage_healthy,
                "issues": list(details.health.issues),
            },
        }

    project_id = _merge_selection(
        args.project_id,
        args.remove_project_id,
        option="--project-id",
    )
    if project_id is None:
        raise ValueError("project remove requires --project-id")
    if args.project is not None:
        raise ValueError("project remove accepts only --project-id")
    entry = catalog.remove(project_id=project_id)
    return {
        "project_id": str(entry.project_id),
        "project_path": entry.project_path,
        "removed": True,
    }


def _memory_command(
    args: argparse.Namespace,
    services: _ServiceBundle,
) -> dict[str, Any]:
    if args.subcommand == "chapters":
        items = (
            services.session_memory.chapters(args.session_id)
            if args.session_id is not None
            else services.memory.chapters()
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "chapters": [
                {
                    "chapter": item.chapter.model_dump(mode="json"),
                    "summary": (
                        item.summary.model_dump(mode="json") if item.summary is not None else None
                    ),
                    "stale": item.stale,
                }
                for item in items
            ],
        }
    if args.subcommand == "scenes":
        items = (
            services.session_memory.scenes(args.session_id, args.chapter_id)
            if args.session_id is not None
            else services.memory.scenes(args.chapter_id)
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "chapter_id": str(args.chapter_id),
            "scenes": [
                {
                    "scene": item.scene.model_dump(mode="json"),
                    "scene_number_in_chapter": item.scene_number_in_chapter,
                    "summary": (
                        item.summary.model_dump(mode="json") if item.summary is not None else None
                    ),
                    "stale": item.stale,
                }
                for item in items
            ],
        }
    if args.subcommand == "search-summaries":
        _require_one_boundary(args)
        hits = (
            services.session_memory.search(
                args.session_id,
                query=args.query,
                entity_id=args.entity,
                limit=args.limit,
            )
            if args.session_id is not None
            else services.memory.search_summaries(
                query=args.query,
                entity_id=args.entity,
                before_scene_id=args.before_scene,
                limit=args.limit,
            )
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "query": args.query,
            "entity_id": str(args.entity) if args.entity is not None else None,
            "before_scene_id": (str(args.before_scene) if args.before_scene is not None else None),
            "writing_session_id": (str(args.session_id) if args.session_id is not None else None),
            "hits": [
                {
                    "summary_kind": (
                        "chapter" if isinstance(item.summary, ChapterSummary) else "scene"
                    ),
                    "retrieval_method": item.retrieval_method.value,
                    "match_reason": item.match_reason,
                    "stale": item.stale,
                    "summary": item.summary.model_dump(mode="json"),
                }
                for item in hits
            ],
        }

    _require_one_boundary(args)
    result = (
        services.session_memory.read(
            args.session_id,
            chapter_id=args.chapter_id,
            scene_id=args.scene_id,
        )
        if args.session_id is not None
        else services.memory.read_scene(
            chapter_id=args.chapter_id,
            scene_id=args.scene_id,
            before_scene_id=args.before_scene,
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "chapter_id": str(result.chapter.chapter_id),
        "chapter_number": result.chapter.chapter_number,
        "chapter_title": result.chapter.title,
        "scene_id": str(result.scene.scene_id),
        "scene_number_in_chapter": result.scene_number_in_chapter,
        "document_id": str(result.document.document_id),
        "document_revision": result.document.revision,
        "story_time": result.scene.story_time.model_dump(mode="json"),
        "narrative_order": result.scene.narrative_order,
        "pov_entity_id": (
            str(result.scene.pov_entity_id) if result.scene.pov_entity_id is not None else None
        ),
        "location_entity_id": (
            str(result.scene.location_entity_id)
            if result.scene.location_entity_id is not None
            else None
        ),
        "text": result.text,
        "source_refs": [source_ref.model_dump(mode="json") for source_ref in result.source_refs],
    }


def _require_one_boundary(args: argparse.Namespace) -> None:
    if (args.session_id is None) == (args.before_scene is None):
        raise ValueError("choose exactly one of --session-id or --before-scene")


def _initialize_project(
    project_path: str,
    manifest: ProjectManifest,
) -> ProjectionStatus:
    root = Path(project_path)
    stores = _storage(root)
    project = ProjectService(
        projects=stores.project_store,
        ledger=stores.ledger,
        projection=stores.projection,
        write_lock=stores.write_lock,
    )
    return project.initialize(manifest)


def _inspect_project(project_path: str) -> ProjectHealth:
    stores = _storage(Path(project_path))
    return ProjectService(
        projects=stores.project_store,
        ledger=stores.ledger,
        projection=stores.projection,
        write_lock=stores.write_lock,
        runs=stores.run_index,
    ).inspect_health()


class _StorageBundle:
    def __init__(self, root: Path) -> None:
        self.project_store = FilesystemProjectStore(root)
        self.ledger = FilesystemCanonLedgerStore(root)
        self.projection = SQLiteProjectionStore(root)
        self.write_lock = FilesystemProjectWriteLock(root)
        self.intent = FilesystemIntentStore(root)
        self.bootstrap = FilesystemBootstrapRunStore(root)
        self.intent_revisions = FilesystemIntentRevisionStore(root)
        self.writing = FilesystemWritingRunStore(root)
        self.publication = FilesystemPublicationStore(root)
        self.manuscripts = FilesystemManuscriptStore(root)
        self.navigation_sources = FilesystemNavigationStore(root)
        self.run_index = FilesystemRunIndexStore(root)


class _ServiceBundle:
    def __init__(self, resolution: ProjectResolution) -> None:
        root = Path(resolution.project_path)
        self.identity = resolution
        stores = _storage(root)
        self.stores = stores
        stores.projection.ensure_summary_search_available()
        self.projects = ProjectService(
            projects=stores.project_store,
            ledger=stores.ledger,
            projection=stores.projection,
            write_lock=stores.write_lock,
            runs=stores.run_index,
        )
        self.projects.ensure_projection_current()
        projection_queries = SQLiteProjectionQueries(root)
        self.queries = CanonQueryService(projection_queries)
        self.memory = NavigationMemoryService(
            navigation=projection_queries,
            canon=self.queries,
            manuscripts=stores.manuscripts,
        )
        self.bootstrap = BootstrapService(
            projects=stores.project_store,
            ledger=stores.ledger,
            projection=stores.projection,
            intent=stores.intent,
            runs=stores.bootstrap,
            write_lock=stores.write_lock,
        )
        self.intent = IntentService(
            projects=stores.project_store,
            intent=stores.intent,
            revisions=stores.intent_revisions,
            write_lock=stores.write_lock,
        )
        self.sessions = WritingSessionService(
            projects=stores.project_store,
            ledger=stores.ledger,
            intent=stores.intent,
            navigation=projection_queries,
            canon=self.queries,
            runs=stores.writing,
        )
        self.session_memory = SessionNavigationService(
            sessions=stores.writing,
            memory=self.memory,
            canon=self.queries,
        )
        self.drafts = DraftService(runs=stores.writing)
        self.reviews = ReviewService(runs=stores.writing)
        self.publications = PublicationService(
            projects=stores.project_store,
            ledger=stores.ledger,
            projection=stores.projection,
            intent=stores.intent,
            intent_revisions=stores.intent_revisions,
            writing=stores.writing,
            publications=stores.publication,
            manuscripts=stores.manuscripts,
            navigation_sources=stores.navigation_sources,
            navigation=projection_queries,
            write_lock=stores.write_lock,
            sessions=self.sessions,
            intent_service=self.intent,
        )


def _storage(root: Path) -> _StorageBundle:
    return _StorageBundle(root)


def _services(resolution: ProjectResolution) -> _ServiceBundle:
    return _ServiceBundle(resolution)


def _catalog_service(catalog_directory: Path | None) -> ProjectCatalogService:
    directory = (
        catalog_directory.expanduser().resolve()
        if catalog_directory is not None
        else default_app_data_directory()
    )
    return ProjectCatalogService(
        catalog=FilesystemProjectCatalogStore(directory),
        catalog_write_lock=FilesystemProjectCatalogWriteLock(directory),
        workspace=FilesystemProjectWorkspace(),
        initialize_project=_initialize_project,
        inspect_project=_inspect_project,
    )


def _catalog_entry_data(entry: ProjectCatalogEntry) -> dict[str, Any]:
    return {
        "project_id": str(entry.project_id),
        "title": entry.title,
        "project_path": entry.project_path,
        "status": entry.status.value,
    }


def _reject_global_selection(args: argparse.Namespace) -> None:
    if args.project_id is not None or args.project is not None:
        raise ValueError(f"project {args.subcommand} does not accept project selection options")


def _merge_selection(global_value, local_value, *, option: str):
    if global_value is not None and local_value is not None and global_value != local_value:
        raise ValueError(f"conflicting {option} values")
    return local_value if local_value is not None else global_value


def _command_hint(arguments: list[str]) -> str:
    values: list[str] = []
    skip_value = False
    options_with_values = {"--catalog-dir", "--project", "--project-id"}
    for argument in arguments:
        if skip_value:
            skip_value = False
            continue
        if argument in options_with_values:
            skip_value = True
            continue
        if argument.startswith("-"):
            continue
        values.append(argument)
        if len(values) == 2:
            break
    return " ".join(values) if values else "unknown"


def _show_schema(name: str) -> dict[str, Any]:
    expected = name if name.endswith(".schema.json") else f"{name}.schema.json"
    for filename, schema in schema_documents():
        if filename == expected:
            return schema
    raise ValueError(f"unknown schema: {name}")


def _intent_from_arguments(
    args: argparse.Namespace,
    *,
    current: IntentContent | None,
) -> IntentContent:
    values: dict[str, str] = {}
    for field in (
        "creative_brief",
        "story_bible",
        "writing_rules",
        "current_outline",
    ):
        path = getattr(args, field)
        if path is not None:
            values[field] = _read_text(path)
        elif current is not None:
            values[field] = getattr(current, field)
        else:
            raise ValueError(f"missing required Intent file: --{field.replace('_', '-')}")
    return IntentContent(**values)


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read input file: {path}") from exc


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"input file must be readable UTF-8: {path}") from exc


def _read_model(path: Path, model):
    try:
        return model.model_validate_json(_read_bytes(path))
    except ValidationError as exc:
        raise ValueError(f"invalid {model.__name__} input: {path}") from exc


def _read_tuple(path: Path, annotation):
    try:
        return TypeAdapter(annotation).validate_json(_read_bytes(path), strict=True)
    except ValidationError as exc:
        raise ValueError(f"invalid versioned JSON input: {path}") from exc


def _character_source_refs(state) -> tuple:
    sourced = (
        *((state.location,) if state.location is not None else ()),
        *state.active_goals,
        *state.knowledge_and_beliefs,
        *state.objective_state,
    )
    unique = {item.source_ref.source_ref_id: item.source_ref for item in sourced}
    return tuple(unique[key] for key in sorted(unique, key=str))


def _emit_success(
    command: str,
    data: Any,
    *,
    warnings: tuple[str, ...],
    machine: bool,
) -> None:
    if machine:
        print(
            json.dumps(
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "ok": True,
                    "command": command,
                    "data": data,
                    "warnings": list(warnings),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return
    print(f"novel {command}: ok")
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)


def _emit_error(command: str, code: str, message: str, *, machine: bool) -> None:
    if machine:
        print(
            json.dumps(
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "ok": False,
                    "command": command,
                    "error": {"code": code, "message": message},
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return
    print(f"novel {command}: {code}: {message}", file=sys.stderr)


def _map_error(exc: Exception) -> tuple[str, int]:
    if isinstance(exc, ProjectCatalogBusyError):
        return "catalog_busy", EXIT_BUSY
    if isinstance(exc, ProjectBusyError):
        return "project_busy", EXIT_BUSY
    if isinstance(exc, ProjectCatalogEntryNotFoundError):
        return "catalog_entry_not_found", EXIT_PROJECT
    if isinstance(exc, ProjectManifestInvalidError):
        return "invalid_project_manifest", EXIT_PROJECT
    if isinstance(exc, ProjectPathInvalidError):
        return "invalid_project_path", EXIT_INVALID_INPUT
    if isinstance(exc, ProjectSelectionMismatchError):
        return "project_selection_mismatch", EXIT_CONFLICT
    if isinstance(exc, ProjectCatalogPathConflictError):
        return "catalog_path_conflict", EXIT_CONFLICT
    if isinstance(exc, ProjectIdentityConflictError):
        return "project_identity_conflict", EXIT_CONFLICT
    if isinstance(exc, ProjectAlreadyExistsError):
        return "project_already_exists", EXIT_CONFLICT
    if isinstance(exc, ProjectNotBootstrappedError):
        return "project_not_bootstrapped", EXIT_PROJECT
    if isinstance(exc, WorkflowNotFoundError):
        return "workflow_not_found", EXIT_PROJECT
    if isinstance(exc, ApprovalMismatchError):
        return "approval_mismatch", EXIT_CONFLICT
    if isinstance(exc, RevisionConflictError):
        return "revision_conflict", EXIT_CONFLICT
    if isinstance(exc, PublicationRecoveryRequiredError):
        return "publication_recovery_required", EXIT_STORAGE
    if isinstance(exc, WorkflowStateError):
        return "invalid_workflow_state", EXIT_CONFLICT
    if isinstance(exc, ChapterNotFoundError):
        return "chapter_not_found", EXIT_PROJECT
    if isinstance(exc, SceneNotFoundError):
        return "scene_not_found", EXIT_PROJECT
    if isinstance(exc, ProjectNotFoundError):
        return "project_not_found", EXIT_PROJECT
    if isinstance(exc, LedgerConflictError):
        return "canon_conflict", EXIT_CONFLICT
    if isinstance(exc, ManuscriptReadError):
        return "manuscript_error", EXIT_INVALID_INPUT
    if isinstance(exc, SceneHistoryAccessError):
        return "scene_not_historical", EXIT_INVALID_INPUT
    if isinstance(exc, (ValidationError, ValueError, UnicodeDecodeError)):
        return "invalid_input", EXIT_INVALID_INPUT
    if isinstance(exc, ProjectionOutOfDateError):
        return "projection_out_of_date", EXIT_STORAGE
    if isinstance(exc, FullTextSearchUnavailableError):
        return "fts_unavailable", EXIT_STORAGE
    if isinstance(exc, ProjectCatalogReadError):
        return "catalog_read_error", EXIT_STORAGE
    if isinstance(exc, ProjectCatalogWriteError):
        return "catalog_write_error", EXIT_STORAGE
    if isinstance(exc, (LedgerReadError, NavigationMemoryReadError, OSError)):
        return "storage_error", EXIT_STORAGE
    return "internal_error", EXIT_INTERNAL


def _package_version() -> str:
    try:
        return version("novel-core")
    except PackageNotFoundError:
        return "0.1.0"


if __name__ == "__main__":
    raise SystemExit(main())
