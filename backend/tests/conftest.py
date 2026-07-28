from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from novel_core import (
    EMPTY_CANON_REVISION,
    CanonChangeSet,
    CanonLedgerEntry,
    ChangeSetLedgerRecord,
    Document,
    DocumentKind,
    DocumentLedgerRecord,
    Entity,
    EntityAlias,
    EntityAliasLedgerRecord,
    EntityLedgerRecord,
    Event,
    EventEdge,
    EventEdgeLedgerRecord,
    EventLedgerRecord,
    Scene,
    SceneLedgerRecord,
    SceneStatus,
    SourceRef,
    SourceRefLedgerRecord,
    StoryTime,
    StoryTimeKind,
    next_canon_revision,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "minimal_continuity.json"


@pytest.fixture(autouse=True)
def isolated_novel_application_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_APP_DATA_DIR", str(tmp_path / "novel-app-data"))


def from_mapping(model: type[Any], value: dict[str, Any]) -> Any:
    return model.model_validate_json(json.dumps(value, ensure_ascii=False))


@pytest.fixture(scope="session")
def continuity_case() -> dict[str, Any]:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {
        "metadata": {
            "schema_version": raw["schema_version"],
            "title": raw["title"],
        },
        "entities": tuple(from_mapping(Entity, item) for item in raw["entities"]),
        "source_refs": tuple(from_mapping(SourceRef, item) for item in raw["source_refs"]),
        "events": tuple(from_mapping(Event, item) for item in raw["events"]),
        "event_edges": tuple(from_mapping(EventEdge, item) for item in raw["event_edges"]),
        "change_sets": tuple(from_mapping(CanonChangeSet, item) for item in raw["change_sets"]),
    }


@pytest.fixture(scope="session")
def ledger_entries(continuity_case: dict[str, Any]) -> tuple[CanonLedgerEntry, ...]:
    document = Document(
        document_id=UUID("20000000-0000-4000-8000-000000000001"),
        relative_path="manuscript/volume-001/chapter-001.md",
        document_kind=DocumentKind.MANUSCRIPT,
        revision="sha256:chapter-001-current",
    )
    scenes = (
        _scene(1, story_ordinal=15, narrative_order=1, document=document),
        _scene(2, story_ordinal=20, narrative_order=2, document=document),
        _scene(3, story_ordinal=30, narrative_order=3, document=document),
        _scene(4, story_ordinal=10, narrative_order=4, document=document),
    )
    alias = EntityAlias(
        alias_id=UUID("01000000-0000-4000-8000-000000000001"),
        entity_id=UUID("00000000-0000-4000-8000-000000000001"),
        alias_text="萧砚",
        alias_type="birth_name",
    )

    first_change_set = _change_set_with_revision(
        continuity_case["change_sets"][0],
        EMPTY_CANON_REVISION,
    )
    first_entry = CanonLedgerEntry(
        ledger_sequence=1,
        ledger_entry_id=UUID("a0000000-0000-4000-8000-000000000001"),
        base_revision=EMPTY_CANON_REVISION,
        approved_at=first_change_set.approved_at,
        source_scene_id=first_change_set.source_scene_id,
        records=(
            *(EntityLedgerRecord(value=entity) for entity in continuity_case["entities"]),
            EntityAliasLedgerRecord(value=alias),
            DocumentLedgerRecord(value=document),
            *(SceneLedgerRecord(value=scene) for scene in scenes),
            *(
                SourceRefLedgerRecord(value=source_ref)
                for source_ref in continuity_case["source_refs"]
            ),
            *(EventLedgerRecord(value=event) for event in continuity_case["events"]),
            *(EventEdgeLedgerRecord(value=edge) for edge in continuity_case["event_edges"]),
            ChangeSetLedgerRecord(value=first_change_set),
        ),
    )

    second_revision = next_canon_revision(EMPTY_CANON_REVISION, first_entry)
    second_change_set = _change_set_with_revision(
        continuity_case["change_sets"][1],
        second_revision,
    )
    second_entry = CanonLedgerEntry(
        ledger_sequence=2,
        ledger_entry_id=UUID("a0000000-0000-4000-8000-000000000002"),
        base_revision=second_revision,
        approved_at=second_change_set.approved_at,
        source_scene_id=second_change_set.source_scene_id,
        records=(ChangeSetLedgerRecord(value=second_change_set),),
    )
    return first_entry, second_entry


def _scene(
    suffix: int,
    *,
    story_ordinal: int,
    narrative_order: int,
    document: Document,
) -> Scene:
    return Scene(
        scene_id=UUID(f"10000000-0000-4000-8000-{suffix:012d}"),
        chapter_id=UUID("11000000-0000-4000-8000-000000000001"),
        narrative_order=narrative_order,
        story_time=StoryTime(
            kind=StoryTimeKind.ORDINAL,
            story_time_start=story_ordinal,
            display_time=f"故事时间 {story_ordinal}",
        ),
        pov_entity_id=UUID("00000000-0000-4000-8000-000000000002"),
        location_entity_id=UUID("00000000-0000-4000-8000-000000000003"),
        status=SceneStatus.APPROVED,
        source_document_id=document.document_id,
        revision=f"scene-{suffix:03d}-revision",
    )


def _change_set_with_revision(
    change_set: CanonChangeSet,
    base_revision: str,
) -> CanonChangeSet:
    value = change_set.model_dump(mode="json")
    value["base_revision"] = base_revision
    return CanonChangeSet.model_validate_json(json.dumps(value, ensure_ascii=False))
