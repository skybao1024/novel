from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from novel_core import (
    EMPTY_CANON_REVISION,
    CanonLedgerEntry,
    ChangeSetLedgerRecord,
    Document,
    DocumentKind,
    EntityAlias,
    LedgerReplayError,
    Scene,
    SceneLedgerRecord,
    SceneStatus,
    StoryTime,
    StoryTimeKind,
    replay_ledger,
)


def test_m1_contracts_are_frozen_and_round_trip(
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    entry = ledger_entries[0]
    assert CanonLedgerEntry.from_json(entry.to_canonical_json()) == entry

    with pytest.raises(ValidationError):
        entry.ledger_sequence = 9  # type: ignore[misc]


@pytest.mark.parametrize(
    "relative_path",
    [
        "/absolute.md",
        "../outside.md",
        "manuscript/../outside.md",
        r"manuscript\scene.md",
        "C:/outside.md",
        "manuscript//scene.md",
        "manuscript/\nscene.md",
    ],
)
def test_document_rejects_non_project_relative_paths(relative_path: str) -> None:
    with pytest.raises(ValidationError):
        Document(
            document_id=UUID("20000000-0000-4000-8000-000000000099"),
            relative_path=relative_path,
            document_kind=DocumentKind.MANUSCRIPT,
            revision="revision-1",
        )


def test_alias_rejects_invalid_ordinal_range() -> None:
    with pytest.raises(ValidationError):
        EntityAlias(
            alias_id=UUID("01000000-0000-4000-8000-000000000099"),
            entity_id=UUID("00000000-0000-4000-8000-000000000001"),
            alias_text="旧名",
            alias_type="former_name",
            valid_from=StoryTime(kind=StoryTimeKind.ORDINAL, story_time_start=20),
            valid_to=StoryTime(kind=StoryTimeKind.ORDINAL, story_time_start=10),
        )


def test_scene_keeps_story_time_separate_from_narrative_order() -> None:
    scene = Scene(
        scene_id=UUID("10000000-0000-4000-8000-000000000099"),
        narrative_order=9,
        story_time=StoryTime(kind=StoryTimeKind.ORDINAL, story_time_start=2),
        status=SceneStatus.APPROVED,
        source_document_id=UUID("20000000-0000-4000-8000-000000000001"),
        revision="revision-1",
    )
    assert scene.narrative_order == 9
    assert scene.story_time.story_time_start == 2


def test_ledger_replay_rejects_sequence_and_revision_gaps(
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    wrong_sequence = ledger_entries[0].model_copy(update={"ledger_sequence": 2})
    with pytest.raises(LedgerReplayError, match="sequence"):
        replay_ledger((wrong_sequence,))

    wrong_revision = ledger_entries[0].model_copy(update={"base_revision": f"sha256:{'0' * 64}"})
    assert wrong_revision.base_revision != EMPTY_CANON_REVISION
    with pytest.raises(LedgerReplayError, match="base_revision"):
        replay_ledger((wrong_revision,))


def test_ledger_replay_keeps_invalidated_assertions(
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    snapshot = replay_ledger(ledger_entries)
    old_assertion_id = UUID("50000000-0000-4000-8000-000000000004")
    new_assertion_id = UUID("50000000-0000-4000-8000-000000000005")

    assert old_assertion_id in {item.assertion_id for item in snapshot.assertions}
    assert new_assertion_id in {item.assertion_id for item in snapshot.assertions}
    invalidations = dict(snapshot.invalidations)
    assert invalidations[old_assertion_id].target_assertion_id == old_assertion_id


def test_ledger_replay_rejects_scope_changing_replacement(
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    entry = ledger_entries[1]
    record = entry.records[0]
    assert isinstance(record, ChangeSetLedgerRecord)
    operation = record.value.operations[0]
    assert operation.assertion is not None
    replacement = operation.assertion.model_copy(
        update={"holder_entity_id": UUID("00000000-0000-4000-8000-000000000001")}
    )
    bad_operation = operation.model_copy(update={"assertion": replacement})
    bad_change_set = record.value.model_copy(
        update={"operations": (bad_operation, *record.value.operations[1:])}
    )
    bad_entry = entry.model_copy(update={"records": (ChangeSetLedgerRecord(value=bad_change_set),)})

    with pytest.raises(LedgerReplayError, match="preserve scope and holder"):
        replay_ledger((ledger_entries[0], bad_entry))


def test_ledger_replay_rejects_missing_relative_time_anchor(
    ledger_entries: tuple[CanonLedgerEntry, ...],
) -> None:
    entry = ledger_entries[0]
    scene_record = next(record for record in entry.records if isinstance(record, SceneLedgerRecord))
    relative_time = StoryTime(
        kind=StoryTimeKind.RELATIVE,
        time_anchor_event_id=UUID("60000000-0000-4000-8000-000000000099"),
        relative_offset=-1,
    )
    bad_scene = scene_record.value.model_copy(update={"story_time": relative_time})
    bad_records = tuple(
        SceneLedgerRecord(value=bad_scene) if record is scene_record else record
        for record in entry.records
    )
    bad_entry = entry.model_copy(update={"records": bad_records})

    with pytest.raises(LedgerReplayError, match="StoryTime anchor"):
        replay_ledger((bad_entry,))
