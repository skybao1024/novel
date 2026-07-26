"""Versioned, append-only Canon Ledger contracts and replay rules."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Annotated, Literal, TypeVar
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from novel_core._base import VersionedDomainModel
from novel_core.canon.assertions import Assertion
from novel_core.canon.changes import (
    CanonChangeSet,
    ChangeSetOperation,
    ChangeSetOperationKind,
)
from novel_core.canon.propositions import Proposition
from novel_core.canon.sources import SourceRef
from novel_core.events import Event, EventEdge
from novel_core.identity import Entity, EntityAlias
from novel_core.projects import Document, Scene

Revision = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
EMPTY_CANON_REVISION: Revision = f"sha256:{hashlib.sha256(b'').hexdigest()}"
ValueType = TypeVar("ValueType")


class EntityLedgerRecord(VersionedDomainModel):
    record_type: Literal["entity"] = "entity"
    value: Entity


class EntityAliasLedgerRecord(VersionedDomainModel):
    record_type: Literal["entity_alias"] = "entity_alias"
    value: EntityAlias


class DocumentLedgerRecord(VersionedDomainModel):
    record_type: Literal["document"] = "document"
    value: Document


class SceneLedgerRecord(VersionedDomainModel):
    record_type: Literal["scene"] = "scene"
    value: Scene


class SourceRefLedgerRecord(VersionedDomainModel):
    record_type: Literal["source_ref"] = "source_ref"
    value: SourceRef


class EventLedgerRecord(VersionedDomainModel):
    record_type: Literal["event"] = "event"
    value: Event


class EventEdgeLedgerRecord(VersionedDomainModel):
    record_type: Literal["event_edge"] = "event_edge"
    value: EventEdge


class ChangeSetLedgerRecord(VersionedDomainModel):
    record_type: Literal["canon_change_set"] = "canon_change_set"
    value: CanonChangeSet


LedgerRecord = Annotated[
    EntityLedgerRecord
    | EntityAliasLedgerRecord
    | DocumentLedgerRecord
    | SceneLedgerRecord
    | SourceRefLedgerRecord
    | EventLedgerRecord
    | EventEdgeLedgerRecord
    | ChangeSetLedgerRecord,
    Field(discriminator="record_type"),
]


class CanonLedgerEntry(VersionedDomainModel):
    """One atomic, approved JSONL entry in the Canon Ledger."""

    ledger_sequence: int = Field(ge=1)
    ledger_entry_id: UUID
    base_revision: Revision
    approved_at: AwareDatetime
    source_scene_id: UUID | None = None
    records: Annotated[tuple[LedgerRecord, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_records(self) -> CanonLedgerEntry:
        record_keys = [record_key(record) for record in self.records]
        if len(record_keys) != len(set(record_keys)):
            raise ValueError("record IDs must be unique within a ledger entry")

        change_sets = [
            record.value for record in self.records if isinstance(record, ChangeSetLedgerRecord)
        ]
        if len(change_sets) > 1:
            raise ValueError("a ledger entry can contain at most one Canon Change Set")
        if change_sets:
            change_set = change_sets[0]
            if change_set.base_revision != self.base_revision:
                raise ValueError("change set base_revision must match its ledger entry")
            if change_set.approved_at != self.approved_at:
                raise ValueError("change set approved_at must match its ledger entry")
            if change_set.source_scene_id != self.source_scene_id:
                raise ValueError("change set source_scene_id must match its ledger entry")
        return self


@dataclass(frozen=True, slots=True)
class CanonLedgerSnapshot:
    """Validated in-memory result of replaying the authoritative Ledger."""

    entries: tuple[CanonLedgerEntry, ...]
    revision: str
    entities: tuple[Entity, ...]
    entity_aliases: tuple[EntityAlias, ...]
    documents: tuple[Document, ...]
    scenes: tuple[Scene, ...]
    source_refs: tuple[SourceRef, ...]
    propositions: tuple[Proposition, ...]
    assertions: tuple[Assertion, ...]
    change_sets: tuple[CanonChangeSet, ...]
    events: tuple[Event, ...]
    event_edges: tuple[EventEdge, ...]
    invalidations: tuple[tuple[UUID, ChangeSetOperation], ...]

    @property
    def last_sequence(self) -> int:
        return self.entries[-1].ledger_sequence if self.entries else 0


class LedgerReplayError(ValueError):
    """Raised when append-only Canon records cannot be replayed safely."""


def record_key(record: LedgerRecord) -> tuple[str, UUID]:
    value = record.value
    if isinstance(record, EntityLedgerRecord):
        return record.record_type, value.entity_id
    if isinstance(record, EntityAliasLedgerRecord):
        return record.record_type, value.alias_id
    if isinstance(record, DocumentLedgerRecord):
        return record.record_type, value.document_id
    if isinstance(record, SceneLedgerRecord):
        return record.record_type, value.scene_id
    if isinstance(record, SourceRefLedgerRecord):
        return record.record_type, value.source_ref_id
    if isinstance(record, EventLedgerRecord):
        return record.record_type, value.event_id
    if isinstance(record, EventEdgeLedgerRecord):
        return record.record_type, value.event_edge_id
    return record.record_type, value.change_set_id


def next_canon_revision(base_revision: str, entry: CanonLedgerEntry) -> str:
    """Hash one canonical entry onto the prior revision."""

    digest = hashlib.sha256()
    digest.update(base_revision.encode("ascii"))
    digest.update(b"\n")
    digest.update(entry.to_canonical_json().encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


def replay_ledger(entries: tuple[CanonLedgerEntry, ...]) -> CanonLedgerSnapshot:
    """Validate and reduce ordered Ledger entries without storage dependencies."""

    state = _LedgerReplayState()
    revision = EMPTY_CANON_REVISION
    entry_ids: set[UUID] = set()

    for expected_sequence, entry in enumerate(entries, start=1):
        if entry.ledger_sequence != expected_sequence:
            raise LedgerReplayError(
                f"ledger sequence {entry.ledger_sequence} is not expected {expected_sequence}"
            )
        if entry.ledger_entry_id in entry_ids:
            raise LedgerReplayError(f"duplicate ledger_entry_id: {entry.ledger_entry_id}")
        if entry.base_revision != revision:
            raise LedgerReplayError(
                f"ledger entry {entry.ledger_sequence} base_revision does not match"
            )

        state.apply_entry(entry)
        entry_ids.add(entry.ledger_entry_id)
        revision = next_canon_revision(revision, entry)

    state.validate_time_anchors()
    return state.snapshot(entries=entries, revision=revision)


class _LedgerReplayState:
    def __init__(self) -> None:
        self.entities: dict[UUID, Entity] = {}
        self.entity_aliases: dict[UUID, EntityAlias] = {}
        self.documents: dict[UUID, Document] = {}
        self.scenes: dict[UUID, Scene] = {}
        self.source_refs: dict[UUID, SourceRef] = {}
        self.propositions: dict[UUID, Proposition] = {}
        self.assertions: dict[UUID, Assertion] = {}
        self.effective_assertion_ids: set[UUID] = set()
        self.change_sets: dict[UUID, CanonChangeSet] = {}
        self.events: dict[UUID, Event] = {}
        self.event_edges: dict[UUID, EventEdge] = {}
        self.invalidations: dict[UUID, ChangeSetOperation] = {}
        self.operation_ids: set[UUID] = set()

    def apply_entry(self, entry: CanonLedgerEntry) -> None:
        records_by_type = {
            record_type: [record for record in entry.records if record.record_type == record_type]
            for record_type in (
                "entity",
                "document",
                "entity_alias",
                "scene",
                "source_ref",
                "event",
                "event_edge",
                "canon_change_set",
            )
        }

        for record in records_by_type["entity"]:
            self._add_unique(self.entities, record.value.entity_id, record.value, "entity")
        for record in records_by_type["document"]:
            self._add_unique(
                self.documents,
                record.value.document_id,
                record.value,
                "document",
            )
        for record in records_by_type["entity_alias"]:
            alias = record.value
            self._require(self.entities, alias.entity_id, "alias entity")
            if alias.used_by_entity_id is not None:
                self._require(self.entities, alias.used_by_entity_id, "alias used_by entity")
            self._add_unique(self.entity_aliases, alias.alias_id, alias, "entity alias")
        for record in records_by_type["scene"]:
            scene = record.value
            self._require(self.documents, scene.source_document_id, "scene source document")
            for entity_id, label in (
                (scene.pov_entity_id, "scene POV entity"),
                (scene.location_entity_id, "scene location entity"),
            ):
                if entity_id is not None:
                    self._require(self.entities, entity_id, label)
            self._add_unique(self.scenes, scene.scene_id, scene, "scene")
        for record in records_by_type["source_ref"]:
            source_ref = record.value
            self._require(
                self.documents,
                source_ref.document_id,
                "SourceRef document",
            )
            scene = self._require(self.scenes, source_ref.scene_id, "SourceRef scene")
            if scene.source_document_id != source_ref.document_id:
                raise LedgerReplayError(
                    f"SourceRef {source_ref.source_ref_id} document does not own its scene"
                )
            quote_hash = hashlib.sha256(source_ref.excerpt.encode("utf-8")).hexdigest()
            if source_ref.quote_hash != quote_hash:
                raise LedgerReplayError(
                    f"SourceRef {source_ref.source_ref_id} quote_hash does not match excerpt"
                )
            self._add_unique(
                self.source_refs,
                source_ref.source_ref_id,
                source_ref,
                "SourceRef",
            )
        for record in records_by_type["event"]:
            event = record.value
            self._require(self.scenes, event.source_scene_id, "event source scene")
            for entity_id in (*event.participant_entity_ids, *event.location_entity_ids):
                self._require(self.entities, entity_id, "event entity")
            for source_ref_id in event.source_ref_ids:
                source_ref = self._require(self.source_refs, source_ref_id, "event SourceRef")
                if source_ref.scene_id != event.source_scene_id:
                    raise LedgerReplayError(
                        f"event {event.event_id} SourceRef belongs to another scene"
                    )
            self._add_unique(self.events, event.event_id, event, "event")
        for record in records_by_type["event_edge"]:
            edge = record.value
            self._require(self.events, edge.source_event_id, "event edge source")
            self._require(self.events, edge.target_event_id, "event edge target")
            if edge.source_ref_id is not None:
                self._require(self.source_refs, edge.source_ref_id, "event edge SourceRef")
            self._add_unique(self.event_edges, edge.event_edge_id, edge, "event edge")
        for record in records_by_type["canon_change_set"]:
            self._apply_change_set(record.value)

        if entry.source_scene_id is not None:
            self._require(self.scenes, entry.source_scene_id, "ledger source scene")

    def _apply_change_set(self, change_set: CanonChangeSet) -> None:
        self._add_unique(
            self.change_sets,
            change_set.change_set_id,
            change_set,
            "change set",
        )
        if change_set.source_scene_id is not None:
            self._require(self.scenes, change_set.source_scene_id, "change set source scene")

        for operation in change_set.operations:
            if operation.operation_id in self.operation_ids:
                raise LedgerReplayError(f"duplicate change operation ID: {operation.operation_id}")
            self.operation_ids.add(operation.operation_id)
            if operation.source_ref_id is not None:
                self._require(
                    self.source_refs,
                    operation.source_ref_id,
                    "operation SourceRef",
                )

            target_assertion: Assertion | None = None
            if operation.target_assertion_id is not None:
                target_assertion = self._require(
                    self.assertions,
                    operation.target_assertion_id,
                    "operation target assertion",
                )
                if operation.target_assertion_id not in self.effective_assertion_ids:
                    raise LedgerReplayError(
                        f"assertion {operation.target_assertion_id} is already invalidated"
                    )

            if operation.proposition is not None:
                proposition = operation.proposition
                self._require(
                    self.entities,
                    proposition.subject_entity_id,
                    "proposition subject",
                )
                if proposition.object_entity_id is not None:
                    self._require(
                        self.entities,
                        proposition.object_entity_id,
                        "proposition object",
                    )
                self._add_unique(
                    self.propositions,
                    proposition.proposition_id,
                    proposition,
                    "proposition",
                )

            if operation.assertion is not None:
                assertion = operation.assertion
                if target_assertion is not None:
                    if (
                        assertion.scope != target_assertion.scope
                        or assertion.holder_entity_id != target_assertion.holder_entity_id
                    ):
                        raise LedgerReplayError(
                            "replacement assertion must preserve scope and holder"
                        )
                    if assertion.valid_from.timeline_id != target_assertion.valid_from.timeline_id:
                        raise LedgerReplayError(
                            "replacement assertion must remain on the target timeline"
                        )
                    if (
                        operation.op is ChangeSetOperationKind.SUPERSEDE
                        and assertion.proposition_id != target_assertion.proposition_id
                    ):
                        raise LedgerReplayError(
                            "supersede replacement must reference the same proposition"
                        )
                self._require(
                    self.propositions,
                    assertion.proposition_id,
                    "assertion proposition",
                )
                self._require(
                    self.source_refs,
                    assertion.source_ref_id,
                    "assertion SourceRef",
                )
                if assertion.holder_entity_id is not None:
                    self._require(
                        self.entities,
                        assertion.holder_entity_id,
                        "assertion holder",
                    )
                self._add_unique(
                    self.assertions,
                    assertion.assertion_id,
                    assertion,
                    "assertion",
                )
                self.effective_assertion_ids.add(assertion.assertion_id)

            if operation.target_assertion_id is not None:
                self.effective_assertion_ids.remove(operation.target_assertion_id)
                self.invalidations[operation.target_assertion_id] = operation

    def validate_time_anchors(self) -> None:
        story_times = [
            *(alias.valid_from for alias in self.entity_aliases.values()),
            *(alias.valid_to for alias in self.entity_aliases.values()),
            *(scene.story_time for scene in self.scenes.values()),
            *(event.story_time for event in self.events.values()),
            *(assertion.valid_from for assertion in self.assertions.values()),
            *(assertion.valid_to for assertion in self.assertions.values()),
        ]
        for story_time in story_times:
            if story_time is None or story_time.time_anchor_event_id is None:
                continue
            self._require(
                self.events,
                story_time.time_anchor_event_id,
                "StoryTime anchor event",
            )

    def snapshot(
        self,
        *,
        entries: tuple[CanonLedgerEntry, ...],
        revision: str,
    ) -> CanonLedgerSnapshot:
        return CanonLedgerSnapshot(
            entries=entries,
            revision=revision,
            entities=tuple(self.entities.values()),
            entity_aliases=tuple(self.entity_aliases.values()),
            documents=tuple(self.documents.values()),
            scenes=tuple(self.scenes.values()),
            source_refs=tuple(self.source_refs.values()),
            propositions=tuple(self.propositions.values()),
            assertions=tuple(self.assertions.values()),
            change_sets=tuple(self.change_sets.values()),
            events=tuple(self.events.values()),
            event_edges=tuple(self.event_edges.values()),
            invalidations=tuple(self.invalidations.items()),
        )

    @staticmethod
    def _add_unique(
        values: dict[UUID, ValueType],
        object_id: UUID,
        value: ValueType,
        label: str,
    ) -> None:
        if object_id in values:
            raise LedgerReplayError(f"duplicate {label} ID: {object_id}")
        values[object_id] = value

    @staticmethod
    def _require(
        values: dict[UUID, ValueType],
        object_id: UUID,
        label: str,
    ) -> ValueType:
        try:
            return values[object_id]
        except KeyError as exc:
            raise LedgerReplayError(f"missing {label}: {object_id}") from exc
