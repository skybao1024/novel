from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError


def public_models(case: dict[str, Any]) -> tuple[Any, ...]:
    change_sets = case["change_sets"]
    operations = tuple(
        operation for change_set in change_sets for operation in change_set.operations
    )
    assertions = tuple(
        operation.assertion for operation in operations if operation.assertion is not None
    )
    propositions = tuple(
        operation.proposition for operation in operations if operation.proposition is not None
    )
    story_times = tuple(event.story_time for event in case["events"])
    return (
        *case["entities"],
        *case["source_refs"],
        *propositions,
        *assertions,
        *story_times,
        *case["events"],
        *case["event_edges"],
        *operations,
        *change_sets,
    )


def test_every_public_model_has_stable_json_round_trip(
    continuity_case: dict[str, Any],
) -> None:
    for model in public_models(continuity_case):
        serialized = model.to_canonical_json()
        restored = type(model).from_json(serialized)
        assert restored == model
        assert restored.to_canonical_json() == serialized


def test_established_models_are_immutable(continuity_case: dict[str, Any]) -> None:
    entity = continuity_case["entities"][0]
    with pytest.raises(ValidationError, match="frozen"):
        entity.display_name = "被原地修改"

    event = continuity_case["events"][0]
    assert isinstance(event.participant_entity_ids, tuple)
    with pytest.raises(AttributeError):
        event.participant_entity_ids.append(entity.entity_id)
