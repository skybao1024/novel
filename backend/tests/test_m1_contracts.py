from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from novel_core import (
    EMPTY_CANON_REVISION,
    CanonLedgerEntry,
    ChangeSetLedgerRecord,
    Chapter,
    ChapterLedgerRecord,
    ChapterStatus,
    Document,
    DocumentKind,
    DocumentLedgerRecord,
    EntityAlias,
    LedgerReplayError,
    StoryTime,
    StoryTimeKind,
    next_canon_revision,
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
        r"manuscript\chapter.md",
        "C:/outside.md",
        "manuscript//chapter.md",
        "manuscript/\nchapter.md",
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


def test_chapter_keeps_story_time_separate_from_narrative_order() -> None:
    chapter = Chapter(
        chapter_id=UUID("10000000-0000-4000-8000-000000000099"),
        chapter_number=9,
        title="错序",
        narrative_order=9,
        story_time=StoryTime(kind=StoryTimeKind.ORDINAL, story_time_start=2),
        status=ChapterStatus.APPROVED,
        source_document_id=UUID("20000000-0000-4000-8000-000000000001"),
        revision="revision-1",
    )
    assert chapter.narrative_order == 9
    assert chapter.story_time.story_time_start == 2


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


def test_ledger_replay_applies_same_identity_document_and_chapter_revisions() -> None:
    document_id = UUID("20000000-0000-4000-8000-000000000098")
    chapter_id = UUID("10000000-0000-4000-8000-000000000098")
    volume_id = UUID("11000000-0000-4000-8000-000000000098")
    base_revision = "sha256:" + "1" * 64
    revised_revision = "sha256:" + "2" * 64
    document = Document(
        document_id=document_id,
        relative_path=f"manuscript/{chapter_id}.md",
        document_kind=DocumentKind.MANUSCRIPT,
        revision=base_revision,
    )
    chapter = Chapter(
        chapter_id=chapter_id,
        volume_id=volume_id,
        chapter_number=1,
        title="初见",
        narrative_order=1,
        story_time=StoryTime(kind=StoryTimeKind.ORDINAL, story_time_start=1),
        status=ChapterStatus.APPROVED,
        source_document_id=document_id,
        revision=base_revision,
    )
    first = CanonLedgerEntry(
        ledger_sequence=1,
        ledger_entry_id=UUID("a0000000-0000-4000-8000-000000000098"),
        base_revision=EMPTY_CANON_REVISION,
        approved_at=datetime.now(UTC),
        source_chapter_id=chapter_id,
        records=(
            DocumentLedgerRecord(value=document),
            ChapterLedgerRecord(value=chapter),
        ),
    )
    revised_document = document.model_copy(update={"revision": revised_revision})
    revised_chapter = chapter.model_copy(update={"revision": revised_revision})
    second = CanonLedgerEntry(
        ledger_sequence=2,
        ledger_entry_id=UUID("a0000000-0000-4000-8000-000000000099"),
        base_revision=next_canon_revision(EMPTY_CANON_REVISION, first),
        approved_at=datetime.now(UTC),
        source_chapter_id=chapter_id,
        records=(
            DocumentLedgerRecord(value=revised_document),
            ChapterLedgerRecord(value=revised_chapter),
        ),
    )

    snapshot = replay_ledger((first, second))

    assert snapshot.documents == (revised_document,)
    assert snapshot.chapters == (revised_chapter,)

    moved_chapter = revised_chapter.model_copy(update={"narrative_order": 2})
    invalid = second.model_copy(
        update={
            "records": (
                DocumentLedgerRecord(value=revised_document),
                ChapterLedgerRecord(value=moved_chapter),
            )
        }
    )
    with pytest.raises(LedgerReplayError, match="change only approved manuscript bytes"):
        replay_ledger((first, invalid))

    renamed_chapter = revised_chapter.model_copy(update={"title": "偷换章名"})
    invalid = second.model_copy(
        update={
            "records": (
                DocumentLedgerRecord(value=revised_document),
                ChapterLedgerRecord(value=renamed_chapter),
            )
        }
    )
    with pytest.raises(LedgerReplayError, match="change only approved manuscript bytes"):
        replay_ledger((first, invalid))


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
    chapter_record = next(
        record for record in entry.records if isinstance(record, ChapterLedgerRecord)
    )
    relative_time = StoryTime(
        kind=StoryTimeKind.RELATIVE,
        time_anchor_event_id=UUID("60000000-0000-4000-8000-000000000099"),
        relative_offset=-1,
    )
    bad_chapter = chapter_record.value.model_copy(update={"story_time": relative_time})
    bad_records = tuple(
        ChapterLedgerRecord(value=bad_chapter) if record is chapter_record else record
        for record in entry.records
    )
    bad_entry = entry.model_copy(update={"records": bad_records})

    with pytest.raises(LedgerReplayError, match="StoryTime anchor"):
        replay_ledger((bad_entry,))
