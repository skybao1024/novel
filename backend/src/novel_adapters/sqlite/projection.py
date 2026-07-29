"""Rebuildable SQLite projection and typed deterministic queries."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from novel_adapters.filesystem import (
    FilesystemNavigationStore,
    FilesystemRunIndexStore,
    NavigationSourceSnapshot,
    ProjectLayout,
    RunSourceSnapshot,
)
from novel_adapters.sqlite.connection import connect_database
from novel_adapters.sqlite.migrations import (
    DEFAULT_MIGRATIONS,
    MigrationError,
    MigrationRunner,
)
from novel_application.errors import (
    FullTextSearchUnavailableError,
    NavigationMemoryReadError,
)
from novel_application.models import (
    AssertionHistoryItem,
    EntityOccurrenceItem,
    EventOrder,
    ProjectionStatus,
    SummaryRetrievalMethod,
    SummarySearchHit,
)
from novel_core import (
    Assertion,
    AssertionScope,
    CanonLedgerSnapshot,
    ChangeSetOperation,
    Chapter,
    ChapterSummary,
    Document,
    Entity,
    Event,
    EventEdge,
    ProjectManifest,
    Proposition,
    Scene,
    SceneEntityOccurrence,
    SceneSummary,
    SceneTrace,
    SourceRef,
    StoryTime,
    StoryTimeKind,
    chapter_summary_is_stale,
    next_canon_revision,
    scene_summary_is_stale,
    scene_trace_is_stale,
    validate_chapter_bindings,
)
from novel_core.canon.ledger import record_key


class SQLiteProjectionStore:
    def __init__(
        self,
        root: Path,
        *,
        migrations_directory: Path = DEFAULT_MIGRATIONS,
    ) -> None:
        self.layout = ProjectLayout(root.resolve())
        self.migrations_directory = migrations_directory

    def ensure_summary_search_available(self) -> None:
        _ensure_fts5_trigram_supported()

    def replace(
        self,
        manifest: ProjectManifest,
        snapshot: CanonLedgerSnapshot,
    ) -> ProjectionStatus:
        _ensure_fts5_trigram_supported()
        navigation = FilesystemNavigationStore(self.layout.root).load_snapshot()
        runs = FilesystemRunIndexStore(self.layout.root).load_snapshot()
        self.layout.runtime_tmp.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix="project-rebuild-",
            suffix=".sqlite",
            dir=self.layout.runtime_tmp,
        )
        os.close(file_descriptor)
        temporary_path = Path(temporary_name)

        try:
            MigrationRunner(
                temporary_path,
                migrations_directory=self.migrations_directory,
            ).apply(backup=False)
            connection = connect_database(temporary_path, wal=False)
            try:
                connection.execute("BEGIN IMMEDIATE")
                _write_snapshot(
                    connection,
                    manifest,
                    snapshot,
                    navigation,
                    runs,
                )
                foreign_key_failures = connection.execute("PRAGMA foreign_key_check").fetchall()
                if foreign_key_failures:
                    raise sqlite3.IntegrityError(
                        f"projection contains foreign key failures: {foreign_key_failures}"
                    )
                connection.commit()
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise sqlite3.DatabaseError(
                        f"temporary projection integrity check failed: {integrity}"
                    )
                connection.execute("PRAGMA journal_mode = DELETE")
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
            finally:
                connection.close()

            self._install_projection(temporary_path)

            connection = connect_database(self.layout.database, wal=True)
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise sqlite3.DatabaseError(
                        f"installed projection integrity check failed: {integrity}"
                    )
            finally:
                connection.close()
            return ProjectionStatus(
                canon_revision=snapshot.revision,
                last_ledger_sequence=snapshot.last_sequence,
            )
        finally:
            temporary_path.unlink(missing_ok=True)
            Path(f"{temporary_path}-wal").unlink(missing_ok=True)
            Path(f"{temporary_path}-shm").unlink(missing_ok=True)

    def status(self) -> ProjectionStatus | None:
        database = self.layout.database
        if not database.is_file():
            return None
        try:
            runner = MigrationRunner(
                database,
                migrations_directory=self.migrations_directory,
            )
            if runner.pending():
                return None
            migrations = runner.discover()
            connection = connect_database(database, read_only=True, wal=False)
            try:
                database_version = connection.execute("PRAGMA user_version").fetchone()[0]
                expected_version = migrations[-1].version if migrations else 0
                if database_version != expected_version:
                    return None
                row = connection.execute(
                    """
                    SELECT canon_revision, last_ledger_sequence, navigation_revision,
                           run_revision
                    FROM projection_state
                    WHERE singleton = 1
                    """
                ).fetchone()
            finally:
                connection.close()
        except (MigrationError, sqlite3.Error):
            return None
        if row is None:
            return None
        navigation = FilesystemNavigationStore(self.layout.root).load_snapshot()
        if row["navigation_revision"] != navigation.revision:
            return None
        runs = FilesystemRunIndexStore(self.layout.root).load_snapshot()
        if row["run_revision"] != runs.revision:
            return None
        return ProjectionStatus(
            canon_revision=row["canon_revision"],
            last_ledger_sequence=row["last_ledger_sequence"],
        )

    def _install_projection(self, temporary_path: Path) -> None:
        database = self.layout.database
        if not database.exists():
            os.replace(temporary_path, database)
            return

        try:
            source = connect_database(temporary_path, read_only=True, wal=False)
            destination = connect_database(database, wal=True)
            try:
                source.backup(destination)
            finally:
                destination.close()
                source.close()
            temporary_path.unlink()
            return
        except sqlite3.Error:
            pass

        self._checkpoint_existing()
        os.replace(temporary_path, database)

    def _checkpoint_existing(self) -> None:
        database = self.layout.database
        try:
            connection = connect_database(database, wal=False)
            try:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                connection.close()
        except sqlite3.Error:
            pass
        Path(f"{database}-wal").unlink(missing_ok=True)
        Path(f"{database}-shm").unlink(missing_ok=True)


class SQLiteProjectionQueries:
    def __init__(self, root: Path) -> None:
        self.layout = ProjectLayout(root.resolve())

    def get_entity(self, entity_id: UUID) -> Entity | None:
        return self._get_model("entities", "entity_id", entity_id, Entity)

    def list_entities(self) -> tuple[Entity, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM entities ORDER BY entity_id"
            ).fetchall()
        return tuple(Entity.from_json(row["payload_json"]) for row in rows)

    def find_entities_by_alias(self, alias_text: str) -> tuple[Entity, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT e.payload_json
                FROM entities AS e
                WHERE e.display_name = ?
                    OR EXISTS (
                        SELECT 1
                        FROM entity_aliases AS a
                        WHERE a.entity_id = e.entity_id AND a.alias_text = ?
                    )
                ORDER BY e.entity_id
                """,
                (alias_text, alias_text),
            ).fetchall()
        return tuple(Entity.from_json(row["payload_json"]) for row in rows)

    def get_document(self, document_id: UUID) -> Document | None:
        return self._get_model("documents", "document_id", document_id, Document)

    def get_scene(self, scene_id: UUID) -> Scene | None:
        return self._get_model("scenes", "scene_id", scene_id, Scene)

    def list_chapters(self) -> tuple[Chapter, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM chapters
                ORDER BY chapter_number, chapter_id
                """
            ).fetchall()
        return tuple(Chapter.from_json(row["payload_json"]) for row in rows)

    def get_chapter(self, chapter_id: UUID) -> Chapter | None:
        return self._get_model("chapters", "chapter_id", chapter_id, Chapter)

    def chapter_scenes(self, chapter_id: UUID) -> tuple[tuple[Scene, int], ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT s.payload_json, link.scene_number_in_chapter
                FROM chapter_scenes AS link
                JOIN scenes AS s ON s.scene_id = link.scene_id
                WHERE link.chapter_id = ?
                ORDER BY link.scene_number_in_chapter
                """,
                (str(chapter_id),),
            ).fetchall()
        return tuple(
            (
                Scene.from_json(row["payload_json"]),
                row["scene_number_in_chapter"],
            )
            for row in rows
        )

    def get_chapter_summary(
        self,
        chapter_id: UUID,
    ) -> tuple[ChapterSummary, bool] | None:
        projected = self._get_navigation_summary(
            "chapter",
            "chapter_id",
            chapter_id,
        )
        if projected is None:
            return None
        payload, stale = projected
        return ChapterSummary.from_json(payload), stale

    def get_scene_summary(
        self,
        scene_id: UUID,
    ) -> tuple[SceneSummary, bool] | None:
        projected = self._get_navigation_summary(
            "scene",
            "scene_id",
            scene_id,
        )
        if projected is None:
            return None
        payload, stale = projected
        return SceneSummary.from_json(payload), stale

    def get_scene_trace(
        self,
        scene_id: UUID,
    ) -> tuple[SceneTrace, bool] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT payload_json, is_stale
                FROM scene_traces
                WHERE scene_id = ?
                """,
                (str(scene_id),),
            ).fetchone()
        if row is None:
            return None
        return SceneTrace.from_json(row["payload_json"]), bool(row["is_stale"])

    def entity_occurrences(
        self,
        entity_id: UUID,
        *,
        before_narrative_order: int,
    ) -> tuple[EntityOccurrenceItem, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT c.payload_json AS chapter_json,
                       s.payload_json AS scene_json,
                       t.payload_json AS trace_json,
                       o.payload_json AS occurrence_json,
                       t.is_stale
                FROM scene_entity_occurrences AS o
                JOIN scene_traces AS t ON t.scene_id = o.scene_id
                JOIN scenes AS s ON s.scene_id = o.scene_id
                JOIN chapters AS c ON c.chapter_id = t.chapter_id
                WHERE o.entity_id = ? AND s.narrative_order < ?
                ORDER BY s.narrative_order, o.occurrence_order
                """,
                (str(entity_id), before_narrative_order),
            ).fetchall()
        return tuple(
            EntityOccurrenceItem(
                chapter=Chapter.from_json(row["chapter_json"]),
                scene=Scene.from_json(row["scene_json"]),
                scene_trace=SceneTrace.from_json(row["trace_json"]),
                occurrence=SceneEntityOccurrence.from_json(row["occurrence_json"]),
                stale=bool(row["is_stale"]),
            )
            for row in rows
        )

    def search_summaries(
        self,
        query: str | None,
        *,
        entity_id: UUID | None,
        before_narrative_order: int,
        limit: int,
    ) -> tuple[SummarySearchHit, ...]:
        where = ["n.max_narrative_order < ?"]
        parameters: list[str | int] = [before_narrative_order]
        from_sql = "navigation_summaries AS n"
        if query is None:
            method = SummaryRetrievalMethod.ENTITY_FILTER
            match_reason = f"main_entity_ids contains {entity_id}"
            order_sql = "n.max_narrative_order DESC, n.summary_key"
        elif len(query) >= 3:
            method = SummaryRetrievalMethod.FTS5_TRIGRAM
            match_reason = f"summary text matched query: {query}"
            expression = '"' + query.replace('"', '""') + '"'
            from_sql = """
                navigation_summaries_fts AS f
                JOIN navigation_summaries AS n ON n.rowid = f.rowid
            """
            where.append("navigation_summaries_fts MATCH ?")
            parameters.append(expression)
            order_sql = "bm25(navigation_summaries_fts), n.max_narrative_order DESC"
        else:
            method = SummaryRetrievalMethod.LITERAL
            match_reason = f"summary text contains literal: {query}"
            where.append("instr(n.summary, ?) > 0")
            parameters.append(query)
            order_sql = "n.max_narrative_order DESC, n.summary_key"
        if entity_id is not None:
            if query is not None:
                match_reason += f"; main_entity_ids contains {entity_id}"
            where.append(
                """
                EXISTS (
                    SELECT 1
                    FROM navigation_summary_entities AS e
                    WHERE e.summary_key = n.summary_key AND e.entity_id = ?
                )
                """
            )
            parameters.append(str(entity_id))
        parameters.append(limit)

        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT n.summary_kind, n.payload_json, n.is_stale
                FROM {from_sql}
                WHERE {" AND ".join(where)}
                ORDER BY {order_sql}
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return tuple(
            SummarySearchHit(
                summary=(
                    ChapterSummary.from_json(row["payload_json"])
                    if row["summary_kind"] == "chapter"
                    else SceneSummary.from_json(row["payload_json"])
                ),
                stale=bool(row["is_stale"]),
                retrieval_method=method,
                match_reason=match_reason,
            )
            for row in rows
        )

    def get_event(self, event_id: UUID) -> Event | None:
        return self._get_model("events", "event_id", event_id, Event)

    def get_source_ref(self, source_ref_id: UUID) -> SourceRef | None:
        return self._get_model(
            "source_refs",
            "source_ref_id",
            source_ref_id,
            SourceRef,
        )

    def get_proposition(self, proposition_id: UUID) -> Proposition | None:
        return self._get_model(
            "propositions",
            "proposition_id",
            proposition_id,
            Proposition,
        )

    def assertion_history(
        self,
        *,
        proposition_id: UUID | None = None,
        subject_entity_id: UUID | None = None,
        predicate: str | None = None,
        scope: AssertionScope | None = None,
        holder_entity_id: UUID | None = None,
    ) -> tuple[AssertionHistoryItem, ...]:
        where: list[str] = []
        parameters: list[str] = []
        if proposition_id is not None:
            where.append("a.proposition_id = ?")
            parameters.append(str(proposition_id))
        if subject_entity_id is not None:
            where.append("p.subject_entity_id = ?")
            parameters.append(str(subject_entity_id))
        if predicate is not None:
            where.append("p.predicate = ?")
            parameters.append(predicate)
        if scope is not None:
            where.append("a.scope = ?")
            parameters.append(scope.value)
        if holder_entity_id is not None:
            where.append("a.holder_entity_id = ?")
            parameters.append(str(holder_entity_id))

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    a.payload_json AS assertion_json,
                    introduced.ledger_sequence AS introduced_sequence,
                    invalidating.payload_json AS invalidating_json,
                    invalidating_change.ledger_sequence AS invalidated_sequence
                FROM assertions AS a
                JOIN propositions AS p ON p.proposition_id = a.proposition_id
                JOIN canon_changesets AS introduced
                    ON introduced.change_set_id = a.change_set_id
                LEFT JOIN canon_change_operations AS invalidating
                    ON invalidating.target_assertion_id = a.assertion_id
                LEFT JOIN canon_changesets AS invalidating_change
                    ON invalidating_change.change_set_id = invalidating.change_set_id
                {where_sql}
                ORDER BY introduced.ledger_sequence, a.assertion_id
                """,
                parameters,
            ).fetchall()
        return tuple(
            AssertionHistoryItem(
                assertion=Assertion.from_json(row["assertion_json"]),
                introduced_sequence=row["introduced_sequence"],
                invalidating_operation=(
                    ChangeSetOperation.from_json(row["invalidating_json"])
                    if row["invalidating_json"] is not None
                    else None
                ),
                invalidated_sequence=row["invalidated_sequence"],
            )
            for row in rows
        )

    def list_events(
        self,
        *,
        participant_entity_id: UUID | None = None,
        location_entity_id: UUID | None = None,
        source_scene_id: UUID | None = None,
        order: EventOrder = EventOrder.NARRATIVE,
    ) -> tuple[Event, ...]:
        where: list[str] = []
        parameters: list[str] = []
        if participant_entity_id is not None:
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM event_participants AS ep
                    WHERE ep.event_id = e.event_id AND ep.entity_id = ?
                )
                """
            )
            parameters.append(str(participant_entity_id))
        if location_entity_id is not None:
            where.append(
                """
                EXISTS (
                    SELECT 1 FROM event_locations AS el
                    WHERE el.event_id = e.event_id AND el.entity_id = ?
                )
                """
            )
            parameters.append(str(location_entity_id))
        if source_scene_id is not None:
            where.append("e.source_scene_id = ?")
            parameters.append(str(source_scene_id))

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        if order is EventOrder.NARRATIVE:
            order_sql = "e.narrative_order, e.event_id"
        else:
            order_sql = """
                CASE WHEN e.story_time_kind = 'ordinal' THEN 0 ELSE 1 END,
                e.story_ordinal_start,
                e.narrative_order,
                e.event_id
            """

        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT e.payload_json
                FROM events AS e
                {where_sql}
                ORDER BY {order_sql}
                """,
                parameters,
            ).fetchall()
        return tuple(Event.from_json(row["payload_json"]) for row in rows)

    def event_edges(
        self,
        event_id: UUID,
        *,
        direction: str,
    ) -> tuple[EventEdge, ...]:
        if direction == "incoming":
            column = "target_event_id"
        elif direction == "outgoing":
            column = "source_event_id"
        else:
            raise ValueError("direction must be 'incoming' or 'outgoing'")
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT payload_json
                FROM event_edges
                WHERE {column} = ?
                ORDER BY event_edge_id
                """,
                (str(event_id),),
            ).fetchall()
        return tuple(EventEdge.from_json(row["payload_json"]) for row in rows)

    def source_refs_for_event(self, event_id: UUID) -> tuple[SourceRef, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT s.payload_json
                FROM event_source_refs AS link
                JOIN source_refs AS s ON s.source_ref_id = link.source_ref_id
                WHERE link.event_id = ?
                ORDER BY link.source_order
                """,
                (str(event_id),),
            ).fetchall()
        return tuple(SourceRef.from_json(row["payload_json"]) for row in rows)

    def source_refs_for_scene(self, scene_id: UUID) -> tuple[SourceRef, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM source_refs
                WHERE scene_id = ?
                ORDER BY fragment_ordinal, source_ref_id
                """,
                (str(scene_id),),
            ).fetchall()
        return tuple(SourceRef.from_json(row["payload_json"]) for row in rows)

    def _get_model(
        self,
        table: str,
        id_column: str,
        object_id: UUID,
        model: type[Any],
    ) -> Any | None:
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT payload_json FROM {table} WHERE {id_column} = ?",
                (str(object_id),),
            ).fetchone()
        return model.from_json(row["payload_json"]) if row is not None else None

    def _get_navigation_summary(
        self,
        summary_kind: str,
        id_column: str,
        object_id: UUID,
    ) -> tuple[str, bool] | None:
        with self._connection() as connection:
            row = connection.execute(
                f"""
                SELECT payload_json, is_stale
                FROM navigation_summaries
                WHERE summary_kind = ? AND {id_column} = ?
                """,
                (summary_kind, str(object_id)),
            ).fetchone()
        if row is None:
            return None
        return row["payload_json"], bool(row["is_stale"])

    def _connection(self) -> sqlite3.Connection:
        return connect_database(self.layout.database, read_only=True, wal=False)


def _write_snapshot(
    connection: sqlite3.Connection,
    manifest: ProjectManifest,
    snapshot: CanonLedgerSnapshot,
    navigation: NavigationSourceSnapshot,
    runs: RunSourceSnapshot,
) -> None:
    connection.execute(
        """
        INSERT INTO project_metadata(
            project_id, project_format_version, schema_version, manifest_json
        ) VALUES (?, ?, ?, ?)
        """,
        (
            str(manifest.project_id),
            manifest.project_format_version,
            manifest.schema_version,
            manifest.to_canonical_json(),
        ),
    )
    connection.execute(
        """
        INSERT INTO projection_state(
            singleton, canon_revision, last_ledger_sequence, navigation_revision,
            run_revision
        )
        VALUES (1, ?, ?, ?, ?)
        """,
        (
            snapshot.revision,
            snapshot.last_sequence,
            navigation.revision,
            runs.revision,
        ),
    )

    record_sequences, change_set_sequences = _record_sequences(snapshot)
    revision = snapshot.entries[0].base_revision if snapshot.entries else snapshot.revision
    for entry in snapshot.entries:
        result_revision = next_canon_revision(revision, entry)
        connection.execute(
            """
            INSERT INTO ledger_entries(
                ledger_sequence, ledger_entry_id, base_revision, result_revision,
                approved_at, source_scene_id, schema_version, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.ledger_sequence,
                str(entry.ledger_entry_id),
                entry.base_revision,
                result_revision,
                entry.approved_at.isoformat(),
                _uuid(entry.source_scene_id),
                entry.schema_version,
                entry.to_canonical_json(),
            ),
        )
        revision = result_revision

    for entity in snapshot.entities:
        connection.execute(
            """
            INSERT INTO entities(
                entity_id, entity_type, display_name, status, created_revision,
                retired_revision, schema_version, ledger_sequence, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(entity.entity_id),
                entity.entity_type,
                entity.display_name,
                entity.status.value,
                entity.created_revision,
                entity.retired_revision,
                entity.schema_version,
                record_sequences[("entity", entity.entity_id)],
                entity.to_canonical_json(),
            ),
        )

    for document in snapshot.documents:
        connection.execute(
            """
            INSERT INTO documents(
                document_id, relative_path, document_kind, revision,
                schema_version, ledger_sequence, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(document.document_id),
                document.relative_path,
                document.document_kind.value,
                document.revision,
                document.schema_version,
                record_sequences[("document", document.document_id)],
                document.to_canonical_json(),
            ),
        )

    for alias in snapshot.entity_aliases:
        connection.execute(
            """
            INSERT INTO entity_aliases(
                alias_id, entity_id, alias_text, alias_type, used_by_entity_id,
                valid_from_json, valid_to_json, schema_version, ledger_sequence,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(alias.alias_id),
                str(alias.entity_id),
                alias.alias_text,
                alias.alias_type,
                _uuid(alias.used_by_entity_id),
                _model_json(alias.valid_from),
                _model_json(alias.valid_to),
                alias.schema_version,
                record_sequences[("entity_alias", alias.alias_id)],
                alias.to_canonical_json(),
            ),
        )

    for scene in snapshot.scenes:
        story = _story_columns(scene.story_time)
        connection.execute(
            """
            INSERT INTO scenes(
                scene_id, chapter_id, narrative_order, timeline_id,
                story_time_kind, story_ordinal_start, story_ordinal_end,
                story_text_start, story_text_end, story_time_json,
                pov_entity_id, location_entity_id, status, source_document_id,
                revision, schema_version, ledger_sequence, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(scene.scene_id),
                _uuid(scene.chapter_id),
                scene.narrative_order,
                *story,
                _uuid(scene.pov_entity_id),
                _uuid(scene.location_entity_id),
                scene.status.value,
                str(scene.source_document_id),
                scene.revision,
                scene.schema_version,
                record_sequences[("scene", scene.scene_id)],
                scene.to_canonical_json(),
            ),
        )

    for source_ref in snapshot.source_refs:
        connection.execute(
            """
            INSERT INTO source_refs(
                source_ref_id, document_id, scene_id, document_revision,
                fragment_ordinal, quote_hash, excerpt, schema_version,
                ledger_sequence, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(source_ref.source_ref_id),
                str(source_ref.document_id),
                str(source_ref.scene_id),
                source_ref.document_revision,
                source_ref.fragment_ordinal,
                source_ref.quote_hash,
                source_ref.excerpt,
                source_ref.schema_version,
                record_sequences[("source_ref", source_ref.source_ref_id)],
                source_ref.to_canonical_json(),
            ),
        )

    for change_set in snapshot.change_sets:
        sequence = change_set_sequences[change_set.change_set_id]
        connection.execute(
            """
            INSERT INTO canon_changesets(
                change_set_id, base_revision, source_scene_id, approved_at,
                schema_version, ledger_sequence, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(change_set.change_set_id),
                change_set.base_revision,
                _uuid(change_set.source_scene_id),
                change_set.approved_at.isoformat(),
                change_set.schema_version,
                sequence,
                change_set.to_canonical_json(),
            ),
        )
        for operation in change_set.operations:
            if operation.proposition is not None:
                _insert_proposition(connection, operation.proposition, sequence)
            if operation.assertion is not None:
                _insert_assertion(connection, operation.assertion, sequence)
        for operation_order, operation in enumerate(change_set.operations, start=1):
            connection.execute(
                """
                INSERT INTO canon_change_operations(
                    operation_id, change_set_id, operation_order, op,
                    target_assertion_id, new_assertion_id, new_proposition_id,
                    reason, schema_version, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(operation.operation_id),
                    str(change_set.change_set_id),
                    operation_order,
                    operation.op.value,
                    _uuid(operation.target_assertion_id),
                    (
                        str(operation.assertion.assertion_id)
                        if operation.assertion is not None
                        else None
                    ),
                    (
                        str(operation.proposition.proposition_id)
                        if operation.proposition is not None
                        else None
                    ),
                    operation.reason,
                    operation.schema_version,
                    operation.to_canonical_json(),
                ),
            )

    for event in snapshot.events:
        story = _story_columns(event.story_time)
        sequence = record_sequences[("event", event.event_id)]
        connection.execute(
            """
            INSERT INTO events(
                event_id, event_type, timeline_id, story_time_kind,
                story_ordinal_start, story_ordinal_end, story_text_start,
                story_text_end, story_time_json, narrative_order,
                source_scene_id, summary, canon_status, schema_version,
                ledger_sequence, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.event_id),
                event.event_type,
                *story,
                event.narrative_order,
                str(event.source_scene_id),
                event.summary,
                event.canon_status.value,
                event.schema_version,
                sequence,
                event.to_canonical_json(),
            ),
        )
        connection.executemany(
            """
            INSERT INTO event_participants(event_id, entity_id, participant_order)
            VALUES (?, ?, ?)
            """,
            [
                (str(event.event_id), str(entity_id), order)
                for order, entity_id in enumerate(event.participant_entity_ids, start=1)
            ],
        )
        connection.executemany(
            """
            INSERT INTO event_locations(event_id, entity_id, location_order)
            VALUES (?, ?, ?)
            """,
            [
                (str(event.event_id), str(entity_id), order)
                for order, entity_id in enumerate(event.location_entity_ids, start=1)
            ],
        )
        connection.executemany(
            """
            INSERT INTO event_source_refs(event_id, source_ref_id, source_order)
            VALUES (?, ?, ?)
            """,
            [
                (str(event.event_id), str(source_ref_id), order)
                for order, source_ref_id in enumerate(event.source_ref_ids, start=1)
            ],
        )

    for edge in snapshot.event_edges:
        connection.execute(
            """
            INSERT INTO event_edges(
                event_edge_id, source_event_id, target_event_id, edge_type,
                source_ref_id, schema_version, ledger_sequence, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(edge.event_edge_id),
                str(edge.source_event_id),
                str(edge.target_event_id),
                edge.edge_type.value,
                _uuid(edge.source_ref_id),
                edge.schema_version,
                record_sequences[("event_edge", edge.event_edge_id)],
                edge.to_canonical_json(),
            ),
        )

    _write_navigation_memory(connection, snapshot, navigation)
    _write_run_indexes(connection, runs)


def _write_run_indexes(
    connection: sqlite3.Connection,
    runs: RunSourceSnapshot,
) -> None:
    connection.executemany(
        """
        INSERT INTO bootstrap_runs(bootstrap_id, project_id, status, payload_json)
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                str(run.bootstrap_id),
                str(run.project_id),
                run.status.value,
                run.to_canonical_json(),
            )
            for run in runs.bootstrap_runs
        ],
    )
    connection.executemany(
        """
        INSERT INTO intent_revisions(
            intent_revision_id, project_id, status, base_intent_revision,
            candidate_revision, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                str(revision.intent_revision_id),
                str(revision.project_id),
                revision.status.value,
                revision.base_intent_revision,
                revision.candidate_revision,
                revision.to_canonical_json(),
            )
            for revision in runs.intent_revisions
        ],
    )
    connection.executemany(
        """
        INSERT INTO writing_sessions(
            writing_session_id, project_id, target_scene_id, target_chapter_id,
            target_narrative_order, base_canon_revision, base_intent_revision,
            status, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                str(session.writing_session_id),
                str(session.project_id),
                str(session.target_scene_id),
                str(session.target_chapter_id),
                session.target_narrative_order,
                session.base_canon_revision,
                session.base_intent_revision,
                session.status.value,
                session.to_canonical_json(),
            )
            for session in runs.writing_sessions
        ],
    )
    connection.executemany(
        """
        INSERT INTO draft_revisions(
            writing_session_id, draft_revision, parent_revision,
            content_digest, payload_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                str(draft.writing_session_id),
                draft.draft_revision,
                draft.parent_revision,
                draft.content_digest,
                draft.to_canonical_json(),
            )
            for draft in runs.drafts
        ],
    )
    connection.executemany(
        """
        INSERT INTO retrieved_sources(
            retrieved_source_id, writing_session_id, retrieval_kind,
            scene_id, document_id, document_revision, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                str(source.retrieved_source_id),
                str(source.writing_session_id),
                source.retrieval_kind.value,
                _uuid(source.scene_id),
                _uuid(source.document_id),
                source.document_revision,
                source.to_canonical_json(),
            )
            for source in runs.retrieved_sources
        ],
    )
    connection.executemany(
        """
        INSERT INTO reviews(
            review_id, writing_session_id, draft_revision,
            recommendation, payload_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                str(review.review_id),
                str(review.writing_session_id),
                review.draft_revision,
                review.recommendation.value,
                review.to_canonical_json(),
            )
            for review in runs.reviews
        ],
    )
    connection.executemany(
        """
        INSERT INTO publications(
            publication_id, project_id, writing_session_id, draft_revision,
            status, approval_digest, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                str(publication.plan.publication_id),
                str(publication.plan.project_id),
                str(publication.plan.writing_session_id),
                publication.plan.draft_revision,
                publication.status.value,
                publication.plan.approval_digest,
                publication.to_canonical_json(),
            )
            for publication in runs.publications
        ],
    )


def _write_navigation_memory(
    connection: sqlite3.Connection,
    snapshot: CanonLedgerSnapshot,
    navigation: NavigationSourceSnapshot,
) -> None:
    try:
        validate_chapter_bindings(navigation.chapters, snapshot.scenes)
        chapters = {chapter.chapter_id: chapter for chapter in navigation.chapters}
        scenes = {scene.scene_id: scene for scene in snapshot.scenes}
        documents = {document.document_id: document for document in snapshot.documents}
        entity_ids = {entity.entity_id for entity in snapshot.entities}

        for chapter in navigation.chapters:
            connection.execute(
                """
                INSERT INTO chapters(
                    chapter_id, chapter_number, title, schema_version, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(chapter.chapter_id),
                    chapter.chapter_number,
                    chapter.title,
                    chapter.schema_version,
                    chapter.to_canonical_json(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO chapter_scenes(
                    chapter_id, scene_id, scene_number_in_chapter
                ) VALUES (?, ?, ?)
                """,
                [
                    (str(chapter.chapter_id), str(scene_id), scene_number)
                    for scene_number, scene_id in enumerate(chapter.scene_ids, start=1)
                ],
            )

        for trace in navigation.scene_traces:
            chapter = chapters.get(trace.chapter_id)
            scene = scenes.get(trace.scene_id)
            document = documents.get(trace.source_document_id)
            if chapter is None:
                raise ValueError(f"Scene Trace references an unknown Chapter: {trace.chapter_id}")
            if scene is None:
                raise ValueError(f"Scene Trace references an unknown Scene: {trace.scene_id}")
            if document is None:
                raise ValueError(
                    f"Scene Trace references an unknown Document: {trace.source_document_id}"
                )
            _validate_navigation_entities(
                tuple(item.entity_id for item in trace.entity_occurrences),
                entity_ids,
            )
            stale = scene_trace_is_stale(
                trace,
                chapter=chapter,
                scene=scene,
                document=document,
            )
            connection.execute(
                """
                INSERT INTO scene_traces(
                    scene_id, scene_trace_id, chapter_id, source_document_id,
                    source_revision, is_stale, schema_version, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(trace.scene_id),
                    str(trace.scene_trace_id),
                    str(trace.chapter_id),
                    str(trace.source_document_id),
                    trace.source_revision,
                    int(stale),
                    trace.schema_version,
                    trace.to_canonical_json(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO scene_entity_occurrences(
                    scene_id, entity_id, occurrence_order, presence_kind,
                    prominence, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(trace.scene_id),
                        str(occurrence.entity_id),
                        occurrence_order,
                        occurrence.presence_kind.value,
                        occurrence.prominence.value,
                        occurrence.to_canonical_json(),
                    )
                    for occurrence_order, occurrence in enumerate(
                        trace.entity_occurrences,
                        start=1,
                    )
                ],
            )

        scene_summaries: dict[UUID, SceneSummary] = {}
        stale_scene_ids: set[UUID] = set()
        for summary in navigation.scene_summaries:
            chapter = chapters.get(summary.chapter_id)
            scene = scenes.get(summary.scene_id)
            document = documents.get(summary.source_document_id)
            if chapter is None:
                raise ValueError(
                    f"Scene Summary references an unknown Chapter: {summary.chapter_id}"
                )
            if scene is None:
                raise ValueError(f"Scene Summary references an unknown Scene: {summary.scene_id}")
            if document is None:
                raise ValueError(
                    f"Scene Summary references an unknown Document: {summary.source_document_id}"
                )
            stale = scene_summary_is_stale(
                summary,
                chapter=chapter,
                scene=scene,
                document=document,
            )
            _validate_navigation_entities(summary.main_entity_ids, entity_ids)
            if stale:
                stale_scene_ids.add(summary.scene_id)
            scene_summaries[summary.scene_id] = summary
            _insert_navigation_summary(
                connection,
                summary_key=f"scene:{summary.scene_id}",
                summary_kind="scene",
                chapter_id=summary.chapter_id,
                scene_id=summary.scene_id,
                source_revision=summary.source_revision,
                max_narrative_order=scene.narrative_order,
                summary=summary.summary,
                stale=stale,
                payload_json=summary.to_canonical_json(),
                schema_version=summary.schema_version,
                main_entity_ids=summary.main_entity_ids,
            )

        for summary in navigation.chapter_summaries:
            chapter = chapters.get(summary.chapter_id)
            if chapter is None:
                raise ValueError(
                    f"Chapter Summary references an unknown Chapter: {summary.chapter_id}"
                )
            stale = chapter_summary_is_stale(
                summary,
                chapter=chapter,
                scene_summaries=scene_summaries,
                stale_scene_ids=stale_scene_ids,
            )
            _validate_navigation_entities(summary.main_entity_ids, entity_ids)
            _insert_navigation_summary(
                connection,
                summary_key=f"chapter:{summary.chapter_id}",
                summary_kind="chapter",
                chapter_id=summary.chapter_id,
                scene_id=None,
                source_revision=None,
                max_narrative_order=max(
                    scenes[scene_id].narrative_order for scene_id in chapter.scene_ids
                ),
                summary=summary.summary,
                stale=stale,
                payload_json=summary.to_canonical_json(),
                schema_version=summary.schema_version,
                main_entity_ids=summary.main_entity_ids,
            )
        connection.execute(
            "INSERT INTO navigation_summaries_fts(navigation_summaries_fts) VALUES ('rebuild')"
        )
    except ValueError as exc:
        raise NavigationMemoryReadError(str(exc)) from exc


def _validate_navigation_entities(
    summary_entity_ids: tuple[UUID, ...],
    known_entity_ids: set[UUID],
) -> None:
    unknown = tuple(
        entity_id for entity_id in summary_entity_ids if entity_id not in known_entity_ids
    )
    if unknown:
        raise ValueError(
            "navigation summary references unknown Entity IDs: "
            + ", ".join(str(entity_id) for entity_id in unknown)
        )


def _insert_navigation_summary(
    connection: sqlite3.Connection,
    *,
    summary_key: str,
    summary_kind: str,
    chapter_id: UUID,
    scene_id: UUID | None,
    source_revision: str | None,
    max_narrative_order: int,
    summary: str,
    stale: bool,
    payload_json: str,
    schema_version: str,
    main_entity_ids: tuple[UUID, ...],
) -> None:
    connection.execute(
        """
        INSERT INTO navigation_summaries(
            summary_key, summary_kind, chapter_id, scene_id, source_revision,
            max_narrative_order, summary, is_stale, schema_version, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            summary_key,
            summary_kind,
            str(chapter_id),
            _uuid(scene_id),
            source_revision,
            max_narrative_order,
            summary,
            int(stale),
            schema_version,
            payload_json,
        ),
    )
    connection.executemany(
        """
        INSERT INTO navigation_summary_entities(summary_key, entity_id, entity_order)
        VALUES (?, ?, ?)
        """,
        [
            (summary_key, str(entity_id), entity_order)
            for entity_order, entity_id in enumerate(main_entity_ids, start=1)
        ],
    )


def _insert_proposition(
    connection: sqlite3.Connection,
    proposition: Proposition,
    ledger_sequence: int,
) -> None:
    object_value_json = (
        json.dumps(
            proposition.model_dump(mode="json")["object_value"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if proposition.object_value is not None
        else None
    )
    qualifiers_json = json.dumps(
        [qualifier.model_dump(mode="json") for qualifier in proposition.qualifiers_json],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    connection.execute(
        """
        INSERT INTO propositions(
            proposition_id, subject_entity_id, predicate, object_kind,
            object_entity_id, object_value_json, qualifiers_json,
            schema_version, ledger_sequence, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(proposition.proposition_id),
            str(proposition.subject_entity_id),
            proposition.predicate,
            proposition.object_kind.value,
            _uuid(proposition.object_entity_id),
            object_value_json,
            qualifiers_json,
            proposition.schema_version,
            ledger_sequence,
            proposition.to_canonical_json(),
        ),
    )


def _insert_assertion(
    connection: sqlite3.Connection,
    assertion: Assertion,
    ledger_sequence: int,
) -> None:
    valid_from_ordinal = _ordinal_start(assertion.valid_from)
    valid_to_ordinal = (
        _ordinal_start(assertion.valid_to) if assertion.valid_to is not None else None
    )
    connection.execute(
        """
        INSERT INTO assertions(
            assertion_id, proposition_id, scope, holder_entity_id, stance,
            certainty, valid_from_timeline_id, valid_from_kind,
            valid_from_ordinal, valid_from_json, valid_to_timeline_id,
            valid_to_kind, valid_to_ordinal, valid_to_json, source_ref_id,
            change_set_id, schema_version, ledger_sequence, payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(assertion.assertion_id),
            str(assertion.proposition_id),
            assertion.scope.value,
            _uuid(assertion.holder_entity_id),
            assertion.stance.value,
            assertion.certainty,
            assertion.valid_from.timeline_id,
            assertion.valid_from.kind.value,
            valid_from_ordinal,
            assertion.valid_from.to_canonical_json(),
            assertion.valid_to.timeline_id if assertion.valid_to is not None else None,
            assertion.valid_to.kind.value if assertion.valid_to is not None else None,
            valid_to_ordinal,
            _model_json(assertion.valid_to),
            str(assertion.source_ref_id),
            str(assertion.change_set_id),
            assertion.schema_version,
            ledger_sequence,
            assertion.to_canonical_json(),
        ),
    )


def _record_sequences(
    snapshot: CanonLedgerSnapshot,
) -> tuple[dict[tuple[str, UUID], int], dict[UUID, int]]:
    records: dict[tuple[str, UUID], int] = {}
    change_sets: dict[UUID, int] = {}
    for entry in snapshot.entries:
        for record in entry.records:
            key = record_key(record)
            records[key] = entry.ledger_sequence
            if key[0] == "canon_change_set":
                change_sets[key[1]] = entry.ledger_sequence
    return records, change_sets


def _story_columns(
    story_time: StoryTime,
) -> tuple[str, str, int | None, int | None, str | None, str | None, str]:
    ordinal_start: int | None = None
    ordinal_end: int | None = None
    text_start: str | None = None
    text_end: str | None = None
    if story_time.kind is StoryTimeKind.ORDINAL:
        ordinal_start = story_time.story_time_start
    elif story_time.kind is StoryTimeKind.EXACT:
        text_start = story_time.story_time_start
    elif story_time.kind is StoryTimeKind.INTERVAL:
        if isinstance(story_time.story_time_start, int):
            ordinal_start = story_time.story_time_start
            ordinal_end = story_time.story_time_end
        else:
            text_start = story_time.story_time_start
            text_end = story_time.story_time_end
    return (
        story_time.timeline_id,
        story_time.kind.value,
        ordinal_start,
        ordinal_end,
        text_start,
        text_end,
        story_time.to_canonical_json(),
    )


def _ordinal_start(story_time: StoryTime) -> int | None:
    if story_time.kind is StoryTimeKind.ORDINAL:
        return story_time.story_time_start
    if story_time.kind is StoryTimeKind.INTERVAL and isinstance(story_time.story_time_start, int):
        return story_time.story_time_start
    return None


def _model_json(model: Any | None) -> str | None:
    return model.to_canonical_json() if model is not None else None


def _uuid(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _ensure_fts5_trigram_supported() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        if not connection.execute("SELECT sqlite_compileoption_used('ENABLE_FTS5')").fetchone()[0]:
            raise FullTextSearchUnavailableError(
                "SQLite FTS5 with the trigram tokenizer is unavailable"
            )
        connection.execute(
            "CREATE VIRTUAL TABLE summary_fts_probe USING fts5(text, tokenize='trigram')"
        )
        connection.execute("INSERT INTO summary_fts_probe(text) VALUES ('中文三字检索')")
        hit = connection.execute(
            "SELECT 1 FROM summary_fts_probe WHERE summary_fts_probe MATCH '\"中文三\"'"
        ).fetchone()
        if hit is None:
            raise FullTextSearchUnavailableError(
                "SQLite trigram tokenizer did not return the required Chinese phrase match"
            )
    except sqlite3.Error as exc:
        raise FullTextSearchUnavailableError(
            "SQLite FTS5 trigram support is required for local summary search"
        ) from exc
    finally:
        connection.close()
