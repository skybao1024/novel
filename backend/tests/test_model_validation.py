from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from novel_core import (
    Approval,
    Assertion,
    AssertionScope,
    AssertionStance,
    ChangeSetOperation,
    ChangeSetOperationKind,
    ChapterEntityOccurrence,
    ChapterTrace,
    ChapterTraceBackfill,
    ChapterTraceBackfillPlan,
    ChapterTraceBackfillStatus,
    ContinuityChapterStatus,
    ContinuityStatus,
    Entity,
    EntityMention,
    EntityMentionForm,
    EntityPresenceKind,
    EntityProminence,
    EntityResolutionStatus,
    EventEdge,
    EventEdgeType,
    ObjectKind,
    ProjectCatalog,
    ProjectCatalogEntry,
    ProjectStatus,
    Proposition,
    StoryTime,
    StoryTimeKind,
    chapter_heading,
)


def ordinal_time(value: int) -> StoryTime:
    return StoryTime(kind=StoryTimeKind.ORDINAL, story_time_start=value)


@pytest.mark.parametrize(
    ("chapter_number", "expected"),
    [
        (1, "# 第一章　县在纸外"),
        (10, "# 第十章　县在纸外"),
        (11, "# 第十一章　县在纸外"),
        (20, "# 第二十章　县在纸外"),
        (101, "# 第一百零一章　县在纸外"),
        (1001, "# 第一千零一章　县在纸外"),
        (10000, "# 第10000章　县在纸外"),
    ],
)
def test_chinese_chapter_heading_is_deterministic(
    chapter_number: int,
    expected: str,
) -> None:
    assert (
        chapter_heading(
            language="zh-CN",
            chapter_number=chapter_number,
            title="县在纸外",
        )
        == expected
    )


def test_non_chinese_chapter_heading_is_deterministic() -> None:
    assert (
        chapter_heading(
            language="en",
            chapter_number=2,
            title="Outside the County",
        )
        == "# Chapter 2: Outside the County"
    )


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


def test_chapter_trace_requires_resolved_mentions_to_link_to_one_occurrence() -> None:
    entity_id = uuid4()
    mention = EntityMention(
        mention_id=uuid4(),
        mention_ordinal=1,
        start_offset=0,
        end_offset=2,
        surface_text="沈砚",
        mention_form=EntityMentionForm.NAME,
        exact_candidate_entity_ids=(entity_id,),
        considered_entity_ids=(entity_id,),
        resolution_status=EntityResolutionStatus.RESOLVED_EXISTING,
        resolved_entity_id=entity_id,
        resolution_reason="唯一候选并与上下文一致。",
    )
    occurrence = ChapterEntityOccurrence(
        occurrence_id=uuid4(),
        entity_id=entity_id,
        presence_kind=EntityPresenceKind.PRESENT,
        prominence=EntityProminence.FOCUS,
        mention_ids=(mention.mention_id,),
    )
    trace = ChapterTrace(
        chapter_trace_id=uuid4(),
        chapter_id=uuid4(),
        volume_id=uuid4(),
        source_document_id=uuid4(),
        source_revision="sha256:" + "1" * 64,
        mentions=(mention,),
        entity_occurrences=(occurrence,),
    )
    assert ChapterTrace.from_json(trace.to_canonical_json()) == trace

    with pytest.raises(ValidationError, match="every resolved Entity Mention"):
        ChapterTrace(
            chapter_trace_id=uuid4(),
            chapter_id=trace.chapter_id,
            volume_id=trace.volume_id,
            source_document_id=trace.source_document_id,
            source_revision=trace.source_revision,
            mentions=(mention,),
        )


def test_published_chapter_trace_rejects_ambiguous_mentions() -> None:
    with pytest.raises(ValidationError, match="ambiguous"):
        ChapterTrace(
            chapter_trace_id=uuid4(),
            chapter_id=uuid4(),
            volume_id=uuid4(),
            source_document_id=uuid4(),
            source_revision="sha256:" + "2" * 64,
            mentions=(
                EntityMention(
                    mention_id=uuid4(),
                    mention_ordinal=1,
                    start_offset=0,
                    end_offset=2,
                    surface_text="沈砚",
                    mention_form=EntityMentionForm.NAME,
                    considered_entity_ids=(uuid4(), uuid4()),
                    resolution_status=EntityResolutionStatus.AMBIGUOUS,
                    resolution_reason="两个同名人物均可能成立。",
                ),
            ),
        )


def test_chapter_trace_backfill_binds_exact_trace_and_approval() -> None:
    trace = ChapterTrace(
        chapter_trace_id=uuid4(),
        chapter_id=uuid4(),
        volume_id=uuid4(),
        source_document_id=uuid4(),
        source_revision="sha256:" + "3" * 64,
    )
    backfill_id = uuid4()
    approval_value = "sha256:" + "4" * 64
    plan = ChapterTraceBackfillPlan(
        backfill_id=backfill_id,
        project_id=uuid4(),
        volume_id=trace.volume_id,
        chapter_id=trace.chapter_id,
        source_document_id=trace.source_document_id,
        source_revision=trace.source_revision,
        base_canon_revision="sha256:" + "5" * 64,
        chapter_trace_change=trace,
        chapter_trace_diff="--- /dev/null\n+++ chapter-trace\n",
        approval_digest=approval_value,
        prepared_at=datetime.now(UTC),
    )
    prepared = ChapterTraceBackfill(
        plan=plan,
        status=ChapterTraceBackfillStatus.PREPARED,
    )
    assert ChapterTraceBackfill.from_json(prepared.to_canonical_json()) == prepared

    approved = ChapterTraceBackfill(
        plan=plan,
        status=ChapterTraceBackfillStatus.APPROVED,
        approval=Approval(
            operation_id=backfill_id,
            approval_digest=approval_value,
            approved_at=datetime.now(UTC),
        ),
    )
    assert approved.approval is not None
    with pytest.raises(ValidationError, match="exact approval"):
        ChapterTraceBackfill(
            plan=plan,
            status=ChapterTraceBackfillStatus.APPROVED,
        )
    with pytest.raises(ValidationError, match="cannot contain Canon Diff"):
        ChapterTraceBackfillPlan(
            **{
                **plan.model_dump(),
                "canon_diff": "+ entity:unexpected",
            }
        )


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


def test_continuity_status_is_consistent_and_round_trips() -> None:
    volume_id = uuid4()
    missing_chapter_id = uuid4()
    chapter = ContinuityChapterStatus(
        volume_id=volume_id,
        chapter_id=missing_chapter_id,
        document_id=uuid4(),
        document_revision=f"sha256:{'1' * 64}",
        narrative_order=1,
        satisfied=False,
    )
    status = ContinuityStatus(
        writing_session_id=uuid4(),
        continuity_volume_id=volume_id,
        required_chapters=(chapter,),
        missing_chapter_ids=(missing_chapter_id,),
        satisfied=False,
    )

    assert ContinuityStatus.from_json(status.to_canonical_json()) == status
    with pytest.raises(ValidationError, match="missing_chapter_ids"):
        ContinuityStatus(
            writing_session_id=status.writing_session_id,
            continuity_volume_id=volume_id,
            required_chapters=(chapter,),
            missing_chapter_ids=(),
            satisfied=True,
        )
    with pytest.raises(ValidationError, match="satisfaction"):
        ContinuityChapterStatus.model_validate(
            {
                **chapter.model_dump(),
                "retrieved_source_ids": (uuid4(),),
                "satisfied": False,
            }
        )
