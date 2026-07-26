from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from novel_core import (
    Assertion,
    AssertionScope,
    AssertionStance,
    ChangeSetOperation,
    ChangeSetOperationKind,
    Entity,
    EventEdge,
    EventEdgeType,
    ObjectKind,
    ProjectCatalog,
    ProjectCatalogEntry,
    ProjectStatus,
    Proposition,
    StoryTime,
    StoryTimeKind,
)


def ordinal_time(value: int) -> StoryTime:
    return StoryTime(kind=StoryTimeKind.ORDINAL, story_time_start=value)


def test_contract_enums_cover_every_locked_value() -> None:
    assert {item.value for item in AssertionScope} == {
        "objective",
        "character",
        "reader",
        "narrator",
    }
    assert {item.value for item in AssertionStance} == {
        "true",
        "false",
        "unknown",
        "suspected",
        "claimed",
        "disbelieved",
    }
    assert {item.value for item in EventEdgeType} == {
        "causes",
        "enables",
        "prevents",
        "reveals",
        "foreshadows",
        "pays_off",
        "contradicts",
    }
    assert {item.value for item in ChangeSetOperationKind} == {
        "assert",
        "retract",
        "supersede",
        "correct",
    }


def test_entity_id_cannot_be_a_display_name() -> None:
    payload = (
        '{"entity_id":"沈砚","entity_type":"character","display_name":"沈砚",'
        '"created_revision":"rev-001"}'
    )
    with pytest.raises(ValidationError, match="UUID"):
        Entity.model_validate_json(payload)


def test_story_time_accepts_every_locked_representation() -> None:
    anchor_id = uuid4()
    valid_times = (
        StoryTime(kind=StoryTimeKind.EXACT, story_time_start="架空历十七年霜月初三"),
        ordinal_time(12),
        StoryTime(
            kind=StoryTimeKind.RELATIVE,
            time_anchor_event_id=anchor_id,
            relative_offset=-2,
        ),
        StoryTime(
            kind=StoryTimeKind.INTERVAL,
            story_time_start=10,
            story_time_end=15,
        ),
        StoryTime(kind=StoryTimeKind.UNKNOWN, display_time="年代不明"),
    )
    assert {item.kind for item in valid_times} == set(StoryTimeKind)


@pytest.mark.parametrize(
    ("object_entity_id", "object_value"),
    [
        (None, None),
        (uuid4(), "both"),
    ],
)
def test_proposition_requires_exactly_one_object(
    object_entity_id: UUID | None,
    object_value: str | None,
) -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        Proposition(
            proposition_id=uuid4(),
            subject_entity_id=uuid4(),
            predicate="identity.is",
            object_kind=ObjectKind.VALUE,
            object_entity_id=object_entity_id,
            object_value=object_value,
        )


def test_character_assertion_requires_holder() -> None:
    with pytest.raises(ValidationError, match="holder_entity_id"):
        Assertion(
            assertion_id=uuid4(),
            proposition_id=uuid4(),
            scope=AssertionScope.CHARACTER,
            stance=AssertionStance.SUSPECTED,
            certainty=0.5,
            valid_from=ordinal_time(1),
            source_ref_id=uuid4(),
            change_set_id=uuid4(),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": StoryTimeKind.EXACT},
        {
            "kind": StoryTimeKind.UNKNOWN,
            "story_time_start": "not allowed",
        },
        {
            "kind": StoryTimeKind.INTERVAL,
            "story_time_start": 3,
            "story_time_end": "four",
        },
        {
            "kind": StoryTimeKind.RELATIVE,
            "time_anchor_event_id": uuid4(),
        },
    ],
)
def test_story_time_rejects_kind_field_mismatches(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        StoryTime(**payload)


def test_event_edge_cannot_reference_itself() -> None:
    event_id = uuid4()
    with pytest.raises(ValidationError, match="itself"):
        EventEdge(
            event_edge_id=uuid4(),
            source_event_id=event_id,
            target_event_id=event_id,
            edge_type=EventEdgeType.CAUSES,
        )


def test_retract_cannot_smuggle_in_a_replacement_assertion() -> None:
    assertion = Assertion(
        assertion_id=uuid4(),
        proposition_id=uuid4(),
        scope=AssertionScope.OBJECTIVE,
        stance=AssertionStance.TRUE,
        certainty=1.0,
        valid_from=ordinal_time(1),
        source_ref_id=uuid4(),
        change_set_id=uuid4(),
    )
    with pytest.raises(ValidationError, match="retract requires only"):
        ChangeSetOperation(
            operation_id=uuid4(),
            op=ChangeSetOperationKind.RETRACT,
            target_assertion_id=uuid4(),
            assertion=assertion,
            reason="invalid shape",
        )


@pytest.mark.parametrize(
    "operation_kind",
    [
        ChangeSetOperationKind.SUPERSEDE,
        ChangeSetOperationKind.CORRECT,
    ],
)
def test_replacement_operations_keep_old_and_new_ids_distinct(
    operation_kind: ChangeSetOperationKind,
) -> None:
    old_assertion_id = uuid4()
    replacement = Assertion(
        assertion_id=uuid4(),
        proposition_id=uuid4(),
        scope=AssertionScope.OBJECTIVE,
        stance=AssertionStance.TRUE,
        certainty=1.0,
        valid_from=ordinal_time(2),
        source_ref_id=uuid4(),
        change_set_id=uuid4(),
    )
    operation = ChangeSetOperation(
        operation_id=uuid4(),
        op=operation_kind,
        target_assertion_id=old_assertion_id,
        assertion=replacement,
        reason="append-only replacement",
    )
    assert operation.target_assertion_id == old_assertion_id
    assert operation.assertion.assertion_id != old_assertion_id


def test_project_catalog_is_strict_unique_and_round_trips() -> None:
    entry = ProjectCatalogEntry(
        project_id=uuid4(),
        title="第一部",
        project_path="/absolute/first",
        status=ProjectStatus.NOT_BOOTSTRAPPED,
    )
    catalog = ProjectCatalog(projects=(entry,))

    assert ProjectCatalog.from_json(catalog.to_canonical_json()) == catalog
    with pytest.raises(ValidationError, match="duplicate project_id"):
        ProjectCatalog(
            projects=(
                entry,
                entry.model_copy(update={"project_path": "/absolute/second"}),
            )
        )
    with pytest.raises(ValidationError, match="duplicate project_path"):
        ProjectCatalog(
            projects=(
                entry,
                entry.model_copy(update={"project_id": uuid4()}),
            )
        )
