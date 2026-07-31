from __future__ import annotations

from typing import Any
from uuid import UUID

from novel_core import (
    AssertionScope,
    AssertionStance,
    ChangeSetOperationKind,
)


def all_assertions(case: dict[str, Any]) -> dict[UUID, Any]:
    return {
        operation.assertion.assertion_id: operation.assertion
        for change_set in case["change_sets"]
        for operation in change_set.operations
        if operation.assertion is not None
    }


def test_world_fact_and_character_knowledge_are_distinct(
    continuity_case: dict[str, Any],
) -> None:
    assertions = all_assertions(continuity_case)
    hidden_identity_id = UUID("40000000-0000-4000-8000-000000000001")

    objective = [
        assertion
        for assertion in assertions.values()
        if assertion.proposition_id == hidden_identity_id
        and assertion.scope is AssertionScope.OBJECTIVE
    ]
    character = [
        assertion
        for assertion in assertions.values()
        if assertion.proposition_id == hidden_identity_id
        and assertion.scope is AssertionScope.CHARACTER
    ]

    assert [item.stance for item in objective] == [AssertionStance.TRUE]
    assert {item.stance for item in character} == {
        AssertionStance.DISBELIEVED,
        AssertionStance.TRUE,
    }
    assert all(item.holder_entity_id is not None for item in character)


def test_wrong_belief_is_not_an_objective_world_conflict(
    continuity_case: dict[str, Any],
) -> None:
    assertions = all_assertions(continuity_case)
    wrong_identity_id = UUID("40000000-0000-4000-8000-000000000002")

    world_stances = {
        assertion.stance
        for assertion in assertions.values()
        if assertion.proposition_id == wrong_identity_id
        and assertion.scope is AssertionScope.OBJECTIVE
    }
    character_stances = {
        assertion.stance
        for assertion in assertions.values()
        if assertion.proposition_id == wrong_identity_id
        and assertion.scope is AssertionScope.CHARACTER
    }

    assert world_stances == {AssertionStance.FALSE}
    assert character_stances == {AssertionStance.TRUE, AssertionStance.FALSE}
    assert not ({AssertionStance.TRUE, AssertionStance.FALSE} <= world_stances)


def test_flashback_separates_story_time_from_narrative_order(
    continuity_case: dict[str, Any],
) -> None:
    events_by_type = {event.event_type: event for event in continuity_case["events"]}
    flashback = events_by_type["rescue.from_fire"]
    revelation = events_by_type["identity.revelation"]

    assert flashback.story_time.story_time_start < revelation.story_time.story_time_start
    assert flashback.narrative_order > revelation.narrative_order


def test_assertions_and_events_resolve_to_source_refs(
    continuity_case: dict[str, Any],
) -> None:
    source_refs = {
        source_ref.source_ref_id: source_ref for source_ref in continuity_case["source_refs"]
    }
    assertions = all_assertions(continuity_case)

    for assertion in assertions.values():
        assert assertion.source_ref_id in source_refs
    for event in continuity_case["events"]:
        assert event.source_chapter_id in {
            source_refs[source_ref_id].chapter_id for source_ref_id in event.source_ref_ids
        }

    learned_truth = assertions[UUID("50000000-0000-4000-8000-000000000006")]
    evidence = source_refs[learned_truth.source_ref_id]
    assert "王室铭文" in evidence.excerpt
    assert evidence.document_revision == "sha256:chapter-003-rev-005"


def test_supersede_appends_instead_of_overwriting(
    continuity_case: dict[str, Any],
) -> None:
    assertions = all_assertions(continuity_case)
    correction = continuity_case["change_sets"][1].operations[0]
    old_id = UUID("50000000-0000-4000-8000-000000000004")

    assert correction.op is ChangeSetOperationKind.SUPERSEDE
    assert correction.target_assertion_id == old_id
    assert correction.assertion.assertion_id != old_id
    assert assertions[old_id].stance is AssertionStance.TRUE
    assert correction.assertion.stance is AssertionStance.FALSE
    assert len(assertions) == 6
