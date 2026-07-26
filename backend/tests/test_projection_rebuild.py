from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import UUID

from novel_adapters.filesystem import (
    FilesystemCanonLedgerStore,
    FilesystemProjectStore,
    FilesystemProjectWriteLock,
)
from novel_adapters.sqlite import SQLiteProjectionQueries, SQLiteProjectionStore
from novel_application import CanonQueryService, EventOrder, ProjectService
from novel_core import (
    AssertionScope,
    AssertionStance,
    CanonLedgerEntry,
    CharacterStatePhase,
    EventChainDirection,
    ProjectManifest,
)

SHEN_YAN = UUID("00000000-0000-4000-8000-000000000001")
GU_NING = UUID("00000000-0000-4000-8000-000000000002")
NORTH_TOWER = UUID("00000000-0000-4000-8000-000000000003")
TRUE_IDENTITY = UUID("40000000-0000-4000-8000-000000000001")
WRONG_IDENTITY = UUID("40000000-0000-4000-8000-000000000002")
REVELATION_EVENT = UUID("60000000-0000-4000-8000-000000000002")
MISTAKEN_IDENTITY_EVENT = UUID("60000000-0000-4000-8000-000000000001")
RESCUE_EVENT = UUID("60000000-0000-4000-8000-000000000003")
REVELATION_SCENE = UUID("10000000-0000-4000-8000-000000000003")


def _manifest() -> ProjectManifest:
    return ProjectManifest(
        project_id=UUID("b0000000-0000-4000-8000-000000000001"),
        title="银戒身份谜案",
        language="zh-CN",
        minimum_core_version="0.1.0",
    )


def _service(root: Path) -> ProjectService:
    return ProjectService(
        projects=FilesystemProjectStore(root),
        ledger=FilesystemCanonLedgerStore(root),
        projection=SQLiteProjectionStore(root),
        write_lock=FilesystemProjectWriteLock(root),
    )


def _build_project(
    root: Path,
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> ProjectService:
    service = _service(root)
    service.initialize(_manifest())
    for entry in ledger_entries:
        service.append(entry)
    return service


def test_projection_queries_keep_truth_time_and_sources_separate(
    tmp_path: Path,
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    root = tmp_path / "story"
    _build_project(root, ledger_entries)
    queries = CanonQueryService(SQLiteProjectionQueries(root))

    assert queries.find_entities_by_alias("萧砚") == (queries.get_entity(SHEN_YAN),)

    at_twenty = queries.effective_assertions(
        timeline_id="main",
        story_ordinal=20,
        proposition_id=WRONG_IDENTITY,
        scope=AssertionScope.CHARACTER,
        holder_entity_id=GU_NING,
    )
    at_thirty = queries.effective_assertions(
        timeline_id="main",
        story_ordinal=30,
        proposition_id=WRONG_IDENTITY,
        scope=AssertionScope.CHARACTER,
        holder_entity_id=GU_NING,
    )
    world = queries.effective_assertions(
        timeline_id="main",
        story_ordinal=30,
        proposition_id=WRONG_IDENTITY,
        scope=AssertionScope.OBJECTIVE,
    )

    assert [assertion.stance for assertion in at_twenty] == [AssertionStance.TRUE]
    assert [assertion.stance for assertion in at_thirty] == [AssertionStance.FALSE]
    assert [assertion.stance for assertion in world] == [AssertionStance.FALSE]

    hidden_at_twenty = queries.effective_assertions(
        timeline_id="main",
        story_ordinal=20,
        proposition_id=TRUE_IDENTITY,
        scope=AssertionScope.CHARACTER,
        holder_entity_id=GU_NING,
    )
    hidden_at_thirty = queries.effective_assertions(
        timeline_id="main",
        story_ordinal=30,
        proposition_id=TRUE_IDENTITY,
        scope=AssertionScope.CHARACTER,
        holder_entity_id=GU_NING,
    )
    assert [item.stance for item in hidden_at_twenty] == [AssertionStance.DISBELIEVED]
    assert [item.stance for item in hidden_at_thirty] == [AssertionStance.TRUE]
    learned_truth_source = queries.get_source_ref(hidden_at_thirty[0].source_ref_id)
    assert learned_truth_source is not None
    assert "王室铭文" in learned_truth_source.excerpt

    narrative = queries.list_events(order=EventOrder.NARRATIVE)
    story = queries.list_events(order=EventOrder.STORY_ORDINAL)
    assert [event.narrative_order for event in narrative] == [2, 3, 4]
    assert [event.story_time.story_time_start for event in story] == [10, 20, 30]

    filtered = queries.list_events(
        participant_entity_id=GU_NING,
        location_entity_id=NORTH_TOWER,
    )
    assert [event.narrative_order for event in filtered] == [2, 3]
    evidence = queries.source_refs_for_event(REVELATION_EVENT)
    assert len(evidence) == 1
    assert "王室铭文" in evidence[0].excerpt
    incoming = queries.event_edges(REVELATION_EVENT, direction="incoming")
    outgoing = queries.event_edges(REVELATION_EVENT, direction="outgoing")
    assert [edge.edge_type.value for edge in incoming] == ["enables"]
    assert [edge.edge_type.value for edge in outgoing] == ["contradicts"]


def test_projection_keeps_old_assertion_and_correction_rows(
    tmp_path: Path,
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    root = tmp_path / "story"
    _build_project(root, ledger_entries)
    database = root / ".novel" / "project.sqlite"

    connection = sqlite3.connect(database)
    try:
        old = connection.execute(
            """
            SELECT stance FROM assertions
            WHERE assertion_id = '50000000-0000-4000-8000-000000000004'
            """
        ).fetchone()
        correction = connection.execute(
            """
            SELECT op, target_assertion_id, new_assertion_id
            FROM canon_change_operations
            WHERE operation_id = '90000000-0000-4000-8000-000000000005'
            """
        ).fetchone()
        assert old == ("true",)
        assert correction == (
            "supersede",
            "50000000-0000-4000-8000-000000000004",
            "50000000-0000-4000-8000-000000000005",
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        connection.close()


def test_sparse_canon_queries_survive_without_historical_ingest_workflow(
    tmp_path: Path,
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    root = tmp_path / "story"
    _build_project(root, ledger_entries)
    queries = CanonQueryService(SQLiteProjectionQueries(root))

    entry = queries.character_state(
        GU_NING,
        at_scene_id=REVELATION_SCENE,
        phase=CharacterStatePhase.ENTRY,
    )
    exit_state = queries.character_state(
        GU_NING,
        at_scene_id=REVELATION_SCENE,
        phase=CharacterStatePhase.EXIT,
    )
    assert {item.assertion.stance for item in entry.knowledge_and_beliefs} == {
        AssertionStance.TRUE,
        AssertionStance.DISBELIEVED,
    }
    assert {item.assertion.stance for item in exit_state.knowledge_and_beliefs} == {
        AssertionStance.TRUE,
        AssertionStance.FALSE,
    }

    chain = queries.event_chain(
        REVELATION_EVENT,
        direction=EventChainDirection.BOTH,
        max_depth=1,
    )
    assert {event.event_id for event in chain.events} == {
        MISTAKEN_IDENTITY_EVENT,
        REVELATION_EVENT,
        RESCUE_EVENT,
    }
    assert len(chain.edges) == 2


def test_deleted_projection_rebuilds_without_changing_canon(
    tmp_path: Path,
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    root = tmp_path / "story"
    service = _build_project(root, ledger_entries)
    queries = CanonQueryService(SQLiteProjectionQueries(root))
    ledger_path = root / "canon" / "ledger" / "canon.jsonl"
    manifest_path = root / "novel.yaml"
    database = root / ".novel" / "project.sqlite"

    before = _semantic_result(queries)
    ledger_bytes = ledger_path.read_bytes()
    manifest_bytes = manifest_path.read_bytes()
    database.unlink()
    Path(f"{database}-wal").unlink(missing_ok=True)
    Path(f"{database}-shm").unlink(missing_ok=True)

    status = service.rebuild_projection()
    after = _semantic_result(CanonQueryService(SQLiteProjectionQueries(root)))

    assert status.last_ledger_sequence == 2
    assert after == before
    assert ledger_path.read_bytes() == ledger_bytes
    assert manifest_path.read_bytes() == manifest_bytes


def test_schema_version_drift_triggers_projection_rebuild(
    tmp_path: Path,
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    root = tmp_path / "story"
    service = _build_project(root, ledger_entries)
    database = root / ".novel" / "project.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA user_version = 0")
    finally:
        connection.close()

    status = service.ensure_projection_current()
    connection = sqlite3.connect(database)
    try:
        database_version = connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()

    assert status.last_ledger_sequence == 2
    assert database_version == 2


def test_removed_migration_history_is_replaced_from_authoritative_files(
    tmp_path: Path,
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    root = tmp_path / "story"
    service = _build_project(root, ledger_entries)
    database = root / ".novel" / "project.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            INSERT INTO schema_migrations(version, name, checksum, applied_at)
            VALUES (3, 'removed_experiment', 'obsolete', '2026-07-26T00:00:00+00:00')
            """
        )
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
    finally:
        connection.close()

    status = service.ensure_projection_current()
    connection = sqlite3.connect(database)
    try:
        migration_rows = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        database_version = connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()

    assert status.last_ledger_sequence == 2
    assert migration_rows == [(1, "initial"), (2, "creation_runs")]
    assert database_version == 2


def _semantic_result(queries: CanonQueryService) -> tuple[object, ...]:
    return (
        queries.get_entity(SHEN_YAN),
        queries.find_entities_by_alias("萧砚"),
        queries.assertion_history(proposition_id=TRUE_IDENTITY),
        queries.list_events(order=EventOrder.NARRATIVE),
        queries.list_events(order=EventOrder.STORY_ORDINAL),
        queries.source_refs_for_event(REVELATION_EVENT),
    )
