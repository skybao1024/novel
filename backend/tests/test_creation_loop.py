from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID

from novel_adapters.filesystem import FilesystemManuscriptStore
from novel_adapters.sqlite import SQLiteProjectionStore
from novel_cli.main import EXIT_CONFLICT, EXIT_OK, EXIT_PROJECT, EXIT_STORAGE, main
from novel_core import (
    BootstrapEntityDraft,
    ChapterEntityOccurrenceDraft,
    ChapterTraceDraft,
    ChapterTraceEntityDraft,
    EntityMentionDraft,
    EntityMentionForm,
    EntityPresenceKind,
    EntityProminence,
    EntityResolutionStatus,
    StoryTime,
    StoryTimeKind,
)


def _invoke_json(capsys, *arguments: str) -> tuple[int, dict]:
    exit_code = main([*arguments, "--json"])
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, json.loads(captured.out)


def _project_call(capsys, catalog: Path, root: Path, *arguments: str) -> dict:
    exit_code, payload = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        *arguments,
    )
    assert exit_code == EXIT_OK, payload
    assert payload["ok"] is True
    return payload["data"]


def _write_intent_files(root: Path, *, outline: str) -> dict[str, Path]:
    inputs = root.parent / f"{root.name}-inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    values = {
        "creative_brief": "一部关于记忆与选择的长篇小说。\n",
        "story_bible": "主角林澜居住在潮汐城。\n",
        "writing_rules": "限制视角，克制叙述，不解释主题。\n",
        "current_outline": outline,
    }
    paths: dict[str, Path] = {}
    for field, content in values.items():
        path = inputs / f"{field}.md"
        path.write_text(content, encoding="utf-8")
        paths[field] = path
    return paths


def _intent_arguments(paths: dict[str, Path]) -> list[str]:
    return [
        "--creative-brief",
        str(paths["creative_brief"]),
        "--story-bible",
        str(paths["story_bible"]),
        "--writing-rules",
        str(paths["writing_rules"]),
        "--current-outline",
        str(paths["current_outline"]),
    ]


def _write_story_time(path: Path, ordinal: int) -> None:
    value = StoryTime(
        kind=StoryTimeKind.ORDINAL,
        story_time_start=ordinal,
        display_time=f"第 {ordinal} 日",
    )
    path.write_text(value.model_dump_json(indent=2), encoding="utf-8")


def _write_summaries(
    directory: Path,
    *,
    chapter_number: int,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    chapter_path = directory / f"chapter-{chapter_number}.md"
    volume_path = directory / f"volume-{chapter_number}.md"
    chapter_path.write_text(
        f"第 {chapter_number} 章推进了主角的选择。\n",
        encoding="utf-8",
    )
    volume_path.write_text(
        f"本卷已有 {chapter_number} 个正式章节。\n",
        encoding="utf-8",
    )
    return chapter_path, volume_path


def _write_chapter_trace(
    path: Path,
    text: str,
    *,
    protagonist_id: str,
    include_new_character: bool = False,
) -> Path:
    protagonist_uuid = UUID(protagonist_id)
    protagonist_start = text.index("林澜")
    mentions = [
        EntityMentionDraft(
            mention_ordinal=1,
            start_offset=protagonist_start,
            end_offset=protagonist_start + len("林澜"),
            surface_text="林澜",
            mention_form=EntityMentionForm.NAME,
            resolution_status=EntityResolutionStatus.RESOLVED_EXISTING,
            considered_entity_ids=(protagonist_uuid,),
            resolved_entity_id=protagonist_uuid,
            resolution_reason="唯一精确候选，并承接当前主角行动。",
        )
    ]
    occurrences = [
        ChapterEntityOccurrenceDraft(
            resolved_entity_id=protagonist_uuid,
            presence_kind=EntityPresenceKind.PRESENT,
            prominence=EntityProminence.FOCUS,
            mention_ordinals=(1,),
        )
    ]
    new_entities = ()
    if include_new_character:
        new_start = text.index("秦渡")
        mentions.append(
            EntityMentionDraft(
                mention_ordinal=2,
                start_offset=new_start,
                end_offset=new_start + len("秦渡"),
                surface_text="秦渡",
                mention_form=EntityMentionForm.NAME,
                resolution_status=EntityResolutionStatus.RESOLVED_NEW,
                new_entity_temporary_name="messenger",
                resolution_reason="历史候选为空，本章明确引入有名人物。",
            )
        )
        occurrences.append(
            ChapterEntityOccurrenceDraft(
                new_entity_temporary_name="messenger",
                presence_kind=EntityPresenceKind.PRESENT,
                prominence=EntityProminence.SUPPORTING,
                mention_ordinals=(2,),
            )
        )
        new_entities = (
            ChapterTraceEntityDraft(
                temporary_name="messenger",
                entity_type="character",
                display_name="秦渡",
            ),
        )
    trace = ChapterTraceDraft(
        new_entities=new_entities,
        mentions=tuple(mentions),
        entity_occurrences=tuple(occurrences),
        scan_notes=("已核对准确 Draft 的人物名称与上下文。",),
    )
    path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    return path


def test_full_approved_creation_loop_publishes_two_queryable_chapters(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    catalog = tmp_path / "catalog"
    root = tmp_path / "novel"
    exit_code, created = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "create",
        str(root),
        "--title",
        "潮汐记忆",
        "--language",
        "zh-CN",
    )
    assert exit_code == EXIT_OK
    project_id = created["data"]["project_id"]

    started = _project_call(capsys, catalog, root, "bootstrap", "start")
    intent_files = _write_intent_files(root, outline="第一章：林澜收到一封旧信。\n")
    entity_drafts = tmp_path / "entity-drafts.json"
    entity_drafts.write_text(
        json.dumps(
            [
                BootstrapEntityDraft(
                    temporary_name="protagonist",
                    entity_type="character",
                    display_name="林澜",
                ).model_dump(mode="json")
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    saved = _project_call(
        capsys,
        catalog,
        root,
        "bootstrap",
        "save",
        "--bootstrap-id",
        started["bootstrap_id"],
        *_intent_arguments(intent_files),
        "--entities",
        str(entity_drafts),
        "--initial-goal",
        "完成第一章开场",
    )
    assert saved["status"] == "prepared"
    assert saved["content"]["entity_resolutions"][0]["temporary_name"] == "protagonist"
    protagonist_id = saved["content"]["entity_resolutions"][0]["entity"]["entity_id"]
    assert not (root / "intent" / "creative-brief.md").exists()

    exit_code, rejected = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        "bootstrap",
        "approve",
        "--bootstrap-id",
        started["bootstrap_id"],
        "--approval-digest",
        "sha256:" + "0" * 64,
    )
    assert exit_code == EXIT_CONFLICT
    assert rejected["error"]["code"] == "approval_mismatch"

    _project_call(
        capsys,
        catalog,
        root,
        "bootstrap",
        "approve",
        "--bootstrap-id",
        started["bootstrap_id"],
        "--approval-digest",
        saved["approval_digest"],
    )
    applied = _project_call(
        capsys,
        catalog,
        root,
        "bootstrap",
        "apply",
        "--bootstrap-id",
        started["bootstrap_id"],
    )
    assert applied["status"] == "applied"
    assert (
        (root / "intent" / "creative-brief.md").read_text(encoding="utf-8").startswith("一部关于")
    )

    listed_code, listed = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "list",
    )
    assert listed_code == EXIT_OK
    assert listed["data"]["projects"][0]["project_id"] == project_id
    assert listed["data"]["projects"][0]["status"] == "ready"

    revised_brief = tmp_path / "revised-brief.md"
    revised_brief.write_text(
        "一部发生在潮汐城、关于记忆与选择的长篇小说。\n",
        encoding="utf-8",
    )
    standalone_intent = _project_call(
        capsys,
        catalog,
        root,
        "intent",
        "prepare",
        "--creative-brief",
        str(revised_brief),
    )
    _project_call(
        capsys,
        catalog,
        root,
        "intent",
        "approve",
        "--intent-revision-id",
        standalone_intent["intent_revision_id"],
        "--approval-digest",
        standalone_intent["approval_digest"],
    )
    standalone_applied = _project_call(
        capsys,
        catalog,
        root,
        "intent",
        "apply",
        "--intent-revision-id",
        standalone_intent["intent_revision_id"],
    )
    assert standalone_applied["status"] == "applied"
    assert (root / "intent" / "creative-brief.md").read_bytes() == revised_brief.read_bytes()

    story_time = tmp_path / "story-time-1.json"
    _write_story_time(story_time, 1)
    first_session = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "start",
        "--author-goal",
        "写出林澜打开旧信的章节",
        "--story-time",
        str(story_time),
        "--new-volume-number",
        "1",
        "--new-volume-title",
        "潮汐旧事",
        "--new-chapter-number",
        "1",
        "--new-chapter-title",
        "旧信",
    )
    context = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "context",
        "--session-id",
        first_session["writing_session_id"],
    )
    assert context["intent"]["current_outline"].startswith("第一章")
    assert context["previous_chapter_text_available"] is False
    assert context["continuity_volume_id"] is None
    assert context["continuity_chapter_ids"] == []
    assert context["target_chapter_number"] == 1
    assert context["target_chapter_title"] == "旧信"
    assert context["required_chapter_heading"] == "# 第一章　旧信"

    first_draft_file = tmp_path / "first-chapter.md"
    first_draft_file.write_text("潮声退去时，林澜拆开了那封信。\n", encoding="utf-8")
    heading_blocked_code, heading_blocked = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        "draft",
        "save",
        "--session-id",
        first_session["writing_session_id"],
        "--file",
        str(first_draft_file),
    )
    assert heading_blocked_code == EXIT_CONFLICT
    assert heading_blocked["error"]["code"] == "invalid_workflow_state"
    assert "# 第一章　旧信" in heading_blocked["error"]["message"]
    first_draft_file.write_text(
        "# 第一章　旧信\n\n潮声退去时，林澜拆开了那封信。\n",
        encoding="utf-8",
    )
    first_draft = _project_call(
        capsys,
        catalog,
        root,
        "draft",
        "save",
        "--session-id",
        first_session["writing_session_id"],
        "--file",
        str(first_draft_file),
    )
    first_review = _project_call(
        capsys,
        catalog,
        root,
        "review",
        "save",
        "--session-id",
        first_session["writing_session_id"],
        "--draft-revision",
        first_draft["draft_revision"],
        "--recommendation",
        "ready",
        "--conclusion",
        "视角稳定，可以发布。",
    )
    first_session["draft_revision"] = first_draft["draft_revision"]
    first_chapter_path, first_volume_path = _write_summaries(
        tmp_path / "summaries",
        chapter_number=1,
    )
    first_trace_path = _write_chapter_trace(
        tmp_path / "first-chapter-trace.json",
        first_draft_file.read_text(encoding="utf-8"),
        protagonist_id=protagonist_id,
    )
    first_candidates = _project_call(
        capsys,
        catalog,
        root,
        "draft",
        "entity-candidates",
        "--session-id",
        first_session["writing_session_id"],
        "--draft-revision",
        first_draft["draft_revision"],
    )
    assert first_candidates["matches"][0]["surface_text"] == "林澜"
    assert first_candidates["matches"][0]["candidate_entity_ids"] == [protagonist_id]
    empty_trace_path = tmp_path / "empty-chapter-trace.json"
    empty_trace_path.write_text(
        ChapterTraceDraft().model_dump_json(indent=2),
        encoding="utf-8",
    )
    missing_trace_code, missing_trace = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        "publish",
        "prepare",
        "--session-id",
        first_session["writing_session_id"],
        "--draft-revision",
        first_draft["draft_revision"],
        "--chapter-summary",
        str(first_chapter_path),
        "--volume-summary",
        str(first_volume_path),
        "--chapter-trace",
        str(empty_trace_path),
        "--review-id",
        first_review["review_id"],
    )
    assert missing_trace_code == EXIT_CONFLICT
    assert missing_trace["error"]["code"] == "invalid_workflow_state"
    assert "does not cover exact Entity candidate" in missing_trace["error"]["message"]
    first_publication = _project_call(
        capsys,
        catalog,
        root,
        "publish",
        "prepare",
        "--session-id",
        first_session["writing_session_id"],
        "--draft-revision",
        first_draft["draft_revision"],
        "--chapter-summary",
        str(first_chapter_path),
        "--volume-summary",
        str(first_volume_path),
        "--chapter-trace",
        str(first_trace_path),
        "--review-id",
        first_review["review_id"],
    )
    first_plan = first_publication["plan"]
    assert first_publication["status"] == "prepared"
    assert first_plan["manuscript_diff"].startswith("--- /dev/null")
    assert not (root / first_session["target_document_path"]).exists()

    _project_call(
        capsys,
        catalog,
        root,
        "publish",
        "approve",
        "--publication-id",
        first_plan["publication_id"],
        "--approval-digest",
        first_plan["approval_digest"],
    )
    first_applied = _project_call(
        capsys,
        catalog,
        root,
        "publish",
        "apply",
        "--publication-id",
        first_plan["publication_id"],
    )
    assert first_applied["status"] == "completed"
    assert (root / first_session["target_document_path"]).read_bytes() == (
        first_draft_file.read_bytes()
    )

    story_time_2 = tmp_path / "story-time-2.json"
    _write_story_time(story_time_2, 2)
    second_session = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "start",
        "--author-goal",
        "写出林澜追查寄信人的章节",
        "--story-time",
        str(story_time_2),
        "--volume-id",
        first_session["target_volume_id"],
        "--new-chapter-number",
        "2",
        "--new-chapter-title",
        "盐渍",
        "--before-chapter-id",
        first_session["target_chapter_id"],
    )
    second_context = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "context",
        "--session-id",
        second_session["writing_session_id"],
    )
    assert second_context["continuity_volume_id"] == first_session["target_volume_id"]
    assert second_context["continuity_chapter_ids"] == [first_session["target_chapter_id"]]
    assert second_context["required_chapter_heading"] == "# 第二章　盐渍"
    second_continuity = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "continuity-status",
        "--session-id",
        second_session["writing_session_id"],
    )
    assert second_continuity["satisfied"] is False
    assert second_continuity["missing_chapter_ids"] == [first_session["target_chapter_id"]]
    historical = _project_call(
        capsys,
        catalog,
        root,
        "memory",
        "read-chapter",
        "--session-id",
        second_session["writing_session_id"],
        "--volume-id",
        first_session["target_volume_id"],
        "--chapter-id",
        first_session["target_chapter_id"],
    )
    assert "林澜拆开了那封信" in historical["text"]
    second_continuity = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "continuity-status",
        "--session-id",
        second_session["writing_session_id"],
    )
    assert second_continuity["satisfied"] is True
    assert second_continuity["missing_chapter_ids"] == []
    shown_session = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "show",
        "--session-id",
        second_session["writing_session_id"],
    )
    retrieved_id = shown_session["retrieved_sources"][0]["retrieved_source_id"]

    evolved_outline = _write_intent_files(
        root,
        outline="第一章：林澜循着旧信上的盐渍寻找寄信人。\n",
    )
    intent_candidate = _project_call(
        capsys,
        catalog,
        root,
        "intent",
        "prepare",
        "--current-outline",
        str(evolved_outline["current_outline"]),
    )
    _project_call(
        capsys,
        catalog,
        root,
        "intent",
        "approve",
        "--intent-revision-id",
        intent_candidate["intent_revision_id"],
        "--approval-digest",
        intent_candidate["approval_digest"],
    )
    assert "收到一封旧信" in (root / "intent" / "current-outline.md").read_text(encoding="utf-8")

    second_draft_file = tmp_path / "second-chapter.md"
    second_draft_file.write_text(
        "# 第二章　盐渍\n\n林澜把信纸举向灯下，秦渡指着潮汐留下的地图。\n",
        encoding="utf-8",
    )
    second_draft = _project_call(
        capsys,
        catalog,
        root,
        "draft",
        "save",
        "--session-id",
        second_session["writing_session_id"],
        "--file",
        str(second_draft_file),
    )
    second_review = _project_call(
        capsys,
        catalog,
        root,
        "review",
        "save",
        "--session-id",
        second_session["writing_session_id"],
        "--draft-revision",
        second_draft["draft_revision"],
        "--recommendation",
        "ready",
        "--conclusion",
        "承接准确，可以发布。",
        "--retrieved-source-id",
        retrieved_id,
    )
    second_session["draft_revision"] = second_draft["draft_revision"]
    second_chapter_path, second_volume_path = _write_summaries(
        tmp_path / "summaries",
        chapter_number=2,
    )
    second_trace_path = _write_chapter_trace(
        tmp_path / "second-chapter-trace.json",
        second_draft_file.read_text(encoding="utf-8"),
        protagonist_id=protagonist_id,
        include_new_character=True,
    )
    second_publication = _project_call(
        capsys,
        catalog,
        root,
        "publish",
        "prepare",
        "--session-id",
        second_session["writing_session_id"],
        "--draft-revision",
        second_draft["draft_revision"],
        "--chapter-summary",
        str(second_chapter_path),
        "--volume-summary",
        str(second_volume_path),
        "--chapter-trace",
        str(second_trace_path),
        "--review-id",
        second_review["review_id"],
        "--intent-revision-id",
        intent_candidate["intent_revision_id"],
    )
    second_plan = second_publication["plan"]
    _project_call(
        capsys,
        catalog,
        root,
        "publish",
        "approve",
        "--publication-id",
        second_plan["publication_id"],
        "--approval-digest",
        second_plan["approval_digest"],
    )
    original_replace = SQLiteProjectionStore.replace

    def fail_projection(*_args, **_kwargs):
        raise OSError("injected projection failure")

    monkeypatch.setattr(SQLiteProjectionStore, "replace", fail_projection)
    failed_code, failed = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        "publish",
        "apply",
        "--publication-id",
        second_plan["publication_id"],
    )
    assert failed_code == EXIT_STORAGE
    assert failed["error"]["code"] == "publication_recovery_required"
    monkeypatch.setattr(SQLiteProjectionStore, "replace", original_replace)

    unhealthy = _project_call(capsys, catalog, root, "doctor")
    assert unhealthy["healthy"] is False
    assert "unfinished Publication transaction" in unhealthy["issues"][0]

    second_applied = _project_call(
        capsys,
        catalog,
        root,
        "publish",
        "recover",
        "--publication-id",
        second_plan["publication_id"],
    )
    assert second_applied["status"] == "completed"
    assert "循着旧信" in (root / "intent" / "current-outline.md").read_text(encoding="utf-8")

    insertion_story_time = tmp_path / "story-time-insertion.json"
    _write_story_time(insertion_story_time, 1)
    insertion_session = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "start",
        "--author-goal",
        "检查插入位置的身份可见边界",
        "--story-time",
        str(insertion_story_time),
        "--volume-id",
        first_session["target_volume_id"],
        "--new-chapter-number",
        "99",
        "--new-chapter-title",
        "插入验证",
        "--before-chapter-id",
        first_session["target_chapter_id"],
        "--after-chapter-id",
        second_session["target_chapter_id"],
    )
    hidden_future_entity = _project_call(
        capsys,
        catalog,
        root,
        "resolve",
        "entity",
        "秦渡",
        "--session-id",
        insertion_session["writing_session_id"],
    )
    assert hidden_future_entity["matches"] == []
    _project_call(
        capsys,
        catalog,
        root,
        "session",
        "close",
        "--session-id",
        insertion_session["writing_session_id"],
    )

    ledger_lines = (
        (root / "canon" / "ledger" / "canon.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(ledger_lines) == 3
    connection = sqlite3.connect(root / ".novel" / "project.sqlite")
    try:
        assert connection.execute("SELECT COUNT(*) FROM chapters").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM chapter_traces").fetchone()[0] == 2
        assert (
            connection.execute("SELECT COUNT(*) FROM chapter_entity_occurrences").fetchone()[0] == 3
        )
        assert connection.execute("SELECT COUNT(*) FROM draft_revisions").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 2
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM publications WHERE status = 'completed'"
            ).fetchone()[0]
            == 2
        )
        assert connection.execute("SELECT COUNT(*) FROM retrieved_sources").fetchone()[0] >= 1
    finally:
        connection.close()

    # Simulate an upgraded project whose first approved Chapter predates Chapter Trace support.
    first_trace_source = root / "memory" / "traces" / f"{first_session['target_chapter_id']}.json"
    first_trace_source.unlink()
    backfill_source = _project_call(
        capsys,
        catalog,
        root,
        "trace-backfill",
        "source",
        "--volume-id",
        first_session["target_volume_id"],
        "--chapter-id",
        first_session["target_chapter_id"],
    )
    assert backfill_source["current_trace"] is None
    assert backfill_source["source_revision"] == first_draft["draft_revision"]
    assert "林澜拆开了那封信" in backfill_source["text"]
    assert backfill_source["exact_candidates"][0]["surface_text"] == "林澜"
    assert backfill_source["exact_candidates"][0]["candidate_entity_ids"] == [protagonist_id]
    assert backfill_source["candidate_entities"][0]["entity_id"] == protagonist_id
    assert {entity["display_name"] for entity in backfill_source["registry_entities"]} == {
        "林澜",
        "秦渡",
    }

    missing_backfill_code, missing_backfill = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        "trace-backfill",
        "prepare",
        "--volume-id",
        first_session["target_volume_id"],
        "--chapter-id",
        first_session["target_chapter_id"],
        "--source-revision",
        backfill_source["source_revision"],
        "--chapter-trace",
        str(empty_trace_path),
    )
    assert missing_backfill_code == EXIT_CONFLICT
    assert missing_backfill["error"]["code"] == "invalid_workflow_state"

    backfill_text = backfill_source["text"]
    protagonist_start = backfill_text.index("林澜")
    letter_start = backfill_text.index("那封信")
    backfill_trace = ChapterTraceDraft(
        new_entities=(
            ChapterTraceEntityDraft(
                temporary_name="old_letter",
                entity_type="object",
                display_name="旧信",
            ),
        ),
        mentions=(
            EntityMentionDraft(
                mention_ordinal=1,
                start_offset=protagonist_start,
                end_offset=protagonist_start + len("林澜"),
                surface_text="林澜",
                mention_form=EntityMentionForm.NAME,
                resolution_status=EntityResolutionStatus.RESOLVED_EXISTING,
                considered_entity_ids=(UUID(protagonist_id),),
                resolved_entity_id=UUID(protagonist_id),
                resolution_reason="精确候选与本章行动主体一致。",
            ),
            EntityMentionDraft(
                mention_ordinal=2,
                start_offset=letter_start,
                end_offset=letter_start + len("那封信"),
                surface_text="那封信",
                mention_form=EntityMentionForm.DESCRIPTION,
                resolution_status=EntityResolutionStatus.RESOLVED_NEW,
                new_entity_temporary_name="old_letter",
                resolution_reason="正文明确指向贯穿后续章节的具体信件。",
            ),
        ),
        entity_occurrences=(
            ChapterEntityOccurrenceDraft(
                resolved_entity_id=UUID(protagonist_id),
                presence_kind=EntityPresenceKind.PRESENT,
                prominence=EntityProminence.FOCUS,
                mention_ordinals=(1,),
            ),
            ChapterEntityOccurrenceDraft(
                new_entity_temporary_name="old_letter",
                presence_kind=EntityPresenceKind.PRESENT,
                prominence=EntityProminence.SUPPORTING,
                mention_ordinals=(2,),
            ),
        ),
        scan_notes=("按准确批准正文完成历史 Trace 回填。",),
    )
    backfill_trace_path = tmp_path / "first-chapter-backfill-trace.json"
    backfill_trace_path.write_text(
        backfill_trace.model_dump_json(indent=2),
        encoding="utf-8",
    )
    prepared_backfill = _project_call(
        capsys,
        catalog,
        root,
        "trace-backfill",
        "prepare",
        "--volume-id",
        first_session["target_volume_id"],
        "--chapter-id",
        first_session["target_chapter_id"],
        "--source-revision",
        backfill_source["source_revision"],
        "--chapter-trace",
        str(backfill_trace_path),
    )
    backfill_plan = prepared_backfill["plan"]
    assert prepared_backfill["status"] == "prepared"
    assert backfill_plan["base_chapter_trace_digest"] is None
    assert backfill_plan["ledger_entry"]["records"][0]["record_type"] == "entity"
    assert "+ entity:" in backfill_plan["canon_diff"]

    wrong_backfill_code, wrong_backfill = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        "trace-backfill",
        "approve",
        "--backfill-id",
        backfill_plan["backfill_id"],
        "--approval-digest",
        "sha256:" + "0" * 64,
    )
    assert wrong_backfill_code == EXIT_CONFLICT
    assert wrong_backfill["error"]["code"] == "approval_mismatch"
    _project_call(
        capsys,
        catalog,
        root,
        "trace-backfill",
        "approve",
        "--backfill-id",
        backfill_plan["backfill_id"],
        "--approval-digest",
        backfill_plan["approval_digest"],
    )

    monkeypatch.setattr(SQLiteProjectionStore, "replace", fail_projection)
    failed_backfill_code, failed_backfill = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        "trace-backfill",
        "apply",
        "--backfill-id",
        backfill_plan["backfill_id"],
    )
    assert failed_backfill_code == EXIT_STORAGE
    assert failed_backfill["error"]["code"] == "trace_backfill_recovery_required"
    monkeypatch.setattr(SQLiteProjectionStore, "replace", original_replace)

    backfill_unhealthy = _project_call(capsys, catalog, root, "doctor")
    assert backfill_unhealthy["healthy"] is False
    assert "unfinished Trace Backfill transaction" in backfill_unhealthy["issues"][0]
    applied_backfill = _project_call(
        capsys,
        catalog,
        root,
        "trace-backfill",
        "recover",
        "--backfill-id",
        backfill_plan["backfill_id"],
    )
    assert applied_backfill["status"] == "completed"
    refreshed_source = _project_call(
        capsys,
        catalog,
        root,
        "trace-backfill",
        "source",
        "--volume-id",
        first_session["target_volume_id"],
        "--chapter-id",
        first_session["target_chapter_id"],
    )
    assert refreshed_source["current_trace"] is not None
    assert refreshed_source["current_trace_stale"] is False
    old_letter_id = backfill_plan["ledger_entry"]["records"][0]["value"]["entity_id"]
    backfill_entity_line = _project_call(
        capsys,
        catalog,
        root,
        "trace-backfill",
        "entity-line",
        "--entity-id",
        protagonist_id,
    )
    assert len(backfill_entity_line["occurrences"]) == 2

    heading_letter_start = backfill_text.index("旧信")
    correction_trace = ChapterTraceDraft(
        mentions=(
            EntityMentionDraft(
                mention_ordinal=1,
                start_offset=heading_letter_start,
                end_offset=heading_letter_start + len("旧信"),
                surface_text="旧信",
                mention_form=EntityMentionForm.NAME,
                resolution_status=EntityResolutionStatus.IGNORED,
                considered_entity_ids=(UUID(old_letter_id),),
                resolution_reason="这是 Volume 标题文字，不是叙事中的 Entity Mention。",
            ),
            EntityMentionDraft(
                mention_ordinal=2,
                start_offset=protagonist_start,
                end_offset=protagonist_start + len("林澜"),
                surface_text="林澜",
                mention_form=EntityMentionForm.NAME,
                resolution_status=EntityResolutionStatus.RESOLVED_EXISTING,
                considered_entity_ids=(UUID(protagonist_id),),
                resolved_entity_id=UUID(protagonist_id),
                resolution_reason="精确候选与行动主体一致。",
            ),
            EntityMentionDraft(
                mention_ordinal=3,
                start_offset=letter_start,
                end_offset=letter_start + len("那封信"),
                surface_text="那封信",
                mention_form=EntityMentionForm.DESCRIPTION,
                resolution_status=EntityResolutionStatus.RESOLVED_EXISTING,
                considered_entity_ids=(UUID(old_letter_id),),
                resolved_entity_id=UUID(old_letter_id),
                resolution_reason="前一回填已建立稳定旧信 Entity，本次修正改为复用。",
            ),
        ),
        entity_occurrences=(
            ChapterEntityOccurrenceDraft(
                resolved_entity_id=UUID(protagonist_id),
                presence_kind=EntityPresenceKind.PRESENT,
                prominence=EntityProminence.FOCUS,
                mention_ordinals=(2,),
            ),
            ChapterEntityOccurrenceDraft(
                resolved_entity_id=UUID(old_letter_id),
                presence_kind=EntityPresenceKind.PRESENT,
                prominence=EntityProminence.SUPPORTING,
                mention_ordinals=(3,),
            ),
        ),
        scan_notes=("修正历史 Trace，复用已批准 Entity 身份。",),
    )
    correction_path = tmp_path / "first-chapter-corrected-trace.json"
    correction_path.write_text(
        correction_trace.model_dump_json(indent=2),
        encoding="utf-8",
    )
    correction = _project_call(
        capsys,
        catalog,
        root,
        "trace-backfill",
        "prepare",
        "--volume-id",
        first_session["target_volume_id"],
        "--chapter-id",
        first_session["target_chapter_id"],
        "--source-revision",
        refreshed_source["source_revision"],
        "--chapter-trace",
        str(correction_path),
    )
    correction_plan = correction["plan"]
    assert correction_plan["base_chapter_trace_digest"] == refreshed_source["current_trace_digest"]
    assert correction_plan["ledger_entry"] is None
    assert correction_plan["canon_diff"] == ""
    _project_call(
        capsys,
        catalog,
        root,
        "trace-backfill",
        "approve",
        "--backfill-id",
        correction_plan["backfill_id"],
        "--approval-digest",
        correction_plan["approval_digest"],
    )
    corrected = _project_call(
        capsys,
        catalog,
        root,
        "trace-backfill",
        "apply",
        "--backfill-id",
        correction_plan["backfill_id"],
    )
    assert corrected["status"] == "completed"
    assert (
        len((root / "canon" / "ledger" / "canon.jsonl").read_text(encoding="utf-8").splitlines())
        == 4
    )

    connection = sqlite3.connect(root / ".novel" / "project.sqlite")
    try:
        assert connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM chapter_traces").fetchone()[0] == 2
        assert (
            connection.execute("SELECT COUNT(*) FROM chapter_entity_occurrences").fetchone()[0] == 4
        )
    finally:
        connection.close()

    story_time_3 = tmp_path / "story-time-3.json"
    _write_story_time(story_time_3, 3)
    third_session = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "start",
        "--author-goal",
        "继续追查潮汐地图",
        "--story-time",
        str(story_time_3),
        "--volume-id",
        first_session["target_volume_id"],
        "--new-chapter-number",
        "3",
        "--new-chapter-title",
        "海图",
        "--before-chapter-id",
        second_session["target_chapter_id"],
    )
    third_context = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "context",
        "--session-id",
        third_session["writing_session_id"],
    )
    assert third_context["continuity_volume_id"] == first_session["target_volume_id"]
    assert third_context["continuity_chapter_ids"] == [second_session["target_chapter_id"]]
    protagonist_line = _project_call(
        capsys,
        catalog,
        root,
        "memory",
        "entity-line",
        "--session-id",
        third_session["writing_session_id"],
        "--entity-id",
        protagonist_id,
    )
    assert len(protagonist_line["occurrences"]) == 2
    assert all(not item["stale"] for item in protagonist_line["occurrences"])
    old_letter = _project_call(
        capsys,
        catalog,
        root,
        "resolve",
        "entity",
        "旧信",
        "--session-id",
        third_session["writing_session_id"],
    )
    assert old_letter["matches"][0]["entity_id"] == old_letter_id
    third_draft_file = tmp_path / "third-chapter.md"
    third_draft_file.write_text(
        "# 第三章　海图\n\n林澜沿着潮线标出的旧路走向县志馆。\n",
        encoding="utf-8",
    )
    blocked_code, blocked = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        "draft",
        "save",
        "--session-id",
        third_session["writing_session_id"],
        "--file",
        str(third_draft_file),
    )
    assert blocked_code == EXIT_CONFLICT
    assert blocked["error"]["code"] == "invalid_workflow_state"
    assert second_session["target_chapter_id"] in blocked["error"]["message"]

    _project_call(
        capsys,
        catalog,
        root,
        "memory",
        "read-chapter",
        "--session-id",
        third_session["writing_session_id"],
        "--volume-id",
        first_session["target_volume_id"],
        "--chapter-id",
        second_session["target_chapter_id"],
    )
    complete_continuity = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "continuity-status",
        "--session-id",
        third_session["writing_session_id"],
    )
    assert complete_continuity["satisfied"] is True
    assert complete_continuity["missing_chapter_ids"] == []
    _project_call(
        capsys,
        catalog,
        root,
        "draft",
        "save",
        "--session-id",
        third_session["writing_session_id"],
        "--file",
        str(third_draft_file),
    )

    other_root = tmp_path / "other-novel"
    other_code, _other = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "create",
        str(other_root),
        "--title",
        "另一部小说",
    )
    assert other_code == EXIT_OK
    cross_code, cross = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(other_root),
        "session",
        "show",
        "--session-id",
        second_session["writing_session_id"],
    )
    assert cross_code == EXIT_PROJECT
    assert cross["error"]["code"] == "workflow_not_found"
    assert not (other_root / "runs").exists()

    revision_session = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "start",
        "--author-goal",
        "压缩第二章并保留林澜的行动结果",
        "--revise-chapter-id",
        second_session["target_chapter_id"],
    )
    assert revision_session["mode"] == "revise"
    assert revision_session["target_chapter_id"] == second_session["target_chapter_id"]
    assert revision_session["target_document_id"] == second_session["target_document_id"]
    assert revision_session["base_document_revision"] == second_plan["manuscript_digest"]
    revision_context = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "context",
        "--session-id",
        revision_session["writing_session_id"],
    )
    assert revision_context["mode"] == "revise"
    assert revision_context["continuity_chapter_ids"] == [first_session["target_chapter_id"]]
    assert revision_context["revision_source_chapter_id"] == second_session["target_chapter_id"]
    assert revision_context["required_chapter_heading"] == "# 第二章　盐渍"

    revised_file = tmp_path / "second-chapter-revised.md"
    revised_file.write_text(
        "# 第二章　盐渍\n\n林澜把潮盐抹上地图，旧路只剩一道向县志馆去的白痕。\n",
        encoding="utf-8",
    )
    blocked_revision_code, blocked_revision = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        "draft",
        "save",
        "--session-id",
        revision_session["writing_session_id"],
        "--file",
        str(revised_file),
    )
    assert blocked_revision_code == EXIT_CONFLICT
    assert "revision source Chapter" in blocked_revision["error"]["message"]

    revision_source = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "revision-source",
        "--session-id",
        revision_session["writing_session_id"],
    )
    assert revision_source["chapter_id"] == second_session["target_chapter_id"]
    assert revision_source["document_id"] == second_session["target_document_id"]
    assert revision_source["document_revision"] == second_plan["manuscript_digest"]
    _project_call(
        capsys,
        catalog,
        root,
        "memory",
        "read-chapter",
        "--session-id",
        revision_session["writing_session_id"],
        "--volume-id",
        first_session["target_volume_id"],
        "--chapter-id",
        first_session["target_chapter_id"],
    )
    revision_continuity = _project_call(
        capsys,
        catalog,
        root,
        "session",
        "continuity-status",
        "--session-id",
        revision_session["writing_session_id"],
    )
    assert revision_continuity["satisfied"] is True
    assert revision_continuity["revision_source_satisfied"] is True

    revised_draft = _project_call(
        capsys,
        catalog,
        root,
        "draft",
        "save",
        "--session-id",
        revision_session["writing_session_id"],
        "--file",
        str(revised_file),
    )
    revised_diff = _project_call(
        capsys,
        catalog,
        root,
        "draft",
        "diff",
        "--session-id",
        revision_session["writing_session_id"],
        "--draft-revision",
        revised_draft["draft_revision"],
    )
    assert second_plan["manuscript_digest"] in revised_diff["diff"].splitlines()[0]
    revised_review = _project_call(
        capsys,
        catalog,
        root,
        "review",
        "save",
        "--session-id",
        revision_session["writing_session_id"],
        "--draft-revision",
        revised_draft["draft_revision"],
        "--recommendation",
        "ready",
        "--conclusion",
        "压缩后因果与人物视角仍然成立。",
    )
    revised_chapter_summary, revised_volume_summary = _write_summaries(
        tmp_path / "revised-summaries",
        chapter_number=2,
    )
    revised_trace = _write_chapter_trace(
        tmp_path / "second-chapter-revised-trace.json",
        revised_file.read_text(encoding="utf-8"),
        protagonist_id=protagonist_id,
    )
    revised_publication = _project_call(
        capsys,
        catalog,
        root,
        "publish",
        "prepare",
        "--session-id",
        revision_session["writing_session_id"],
        "--draft-revision",
        revised_draft["draft_revision"],
        "--chapter-summary",
        str(revised_chapter_summary),
        "--volume-summary",
        str(revised_volume_summary),
        "--chapter-trace",
        str(revised_trace),
        "--review-id",
        revised_review["review_id"],
    )
    revised_plan = revised_publication["plan"]
    assert revised_plan["mode"] == "revise"
    assert revised_plan["base_document_revision"] == second_plan["manuscript_digest"]
    assert revised_plan["base_chapter_summary_digest"] is not None
    assert revised_plan["base_volume_summary_digest"] is not None
    assert revised_plan["base_chapter_trace_digest"] is not None
    assert not revised_plan["manuscript_diff"].startswith("--- /dev/null")
    assert revised_plan["chapter_change"]["chapter_id"] == second_session["target_chapter_id"]
    assert revised_plan["target_document"]["document_id"] == second_session["target_document_id"]
    assert revised_plan["volume_change"]["chapter_ids"] == [
        first_session["target_chapter_id"],
        second_session["target_chapter_id"],
    ]
    _project_call(
        capsys,
        catalog,
        root,
        "publish",
        "approve",
        "--publication-id",
        revised_plan["publication_id"],
        "--approval-digest",
        revised_plan["approval_digest"],
    )
    original_manuscript_replace = FilesystemManuscriptStore.replace_document

    def replace_manuscript_then_fail(store, relative_path, *, expected_revision, content):
        original_manuscript_replace(
            store,
            relative_path,
            expected_revision=expected_revision,
            content=content,
        )
        raise OSError("injected post-replacement failure")

    monkeypatch.setattr(
        FilesystemManuscriptStore,
        "replace_document",
        replace_manuscript_then_fail,
    )
    revision_failed_code, revision_failed = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        "publish",
        "apply",
        "--publication-id",
        revised_plan["publication_id"],
    )
    assert revision_failed_code == EXIT_STORAGE
    assert revision_failed["error"]["code"] == "publication_recovery_required"
    assert (root / second_session["target_document_path"]).read_bytes() == revised_file.read_bytes()
    applying_revision = _project_call(
        capsys,
        catalog,
        root,
        "publish",
        "inspect",
        "--publication-id",
        revised_plan["publication_id"],
    )
    assert applying_revision["status"] == "applying"
    monkeypatch.setattr(
        FilesystemManuscriptStore,
        "replace_document",
        original_manuscript_replace,
    )

    monkeypatch.setattr(SQLiteProjectionStore, "replace", fail_projection)
    projection_failed_code, projection_failed = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project",
        str(root),
        "publish",
        "recover",
        "--publication-id",
        revised_plan["publication_id"],
    )
    assert projection_failed_code == EXIT_STORAGE
    assert projection_failed["error"]["code"] == "publication_recovery_required"
    monkeypatch.setattr(SQLiteProjectionStore, "replace", original_replace)
    revision_unhealthy = _project_call(capsys, catalog, root, "doctor")
    assert revision_unhealthy["healthy"] is False
    assert any(revised_plan["publication_id"] in issue for issue in revision_unhealthy["issues"])
    revision_applied = _project_call(
        capsys,
        catalog,
        root,
        "publish",
        "recover",
        "--publication-id",
        revised_plan["publication_id"],
    )
    assert revision_applied["status"] == "completed"
    assert (root / second_session["target_document_path"]).read_bytes() == revised_file.read_bytes()

    revised_source = _project_call(
        capsys,
        catalog,
        root,
        "trace-backfill",
        "source",
        "--volume-id",
        first_session["target_volume_id"],
        "--chapter-id",
        second_session["target_chapter_id"],
    )
    assert revised_source["text"] == revised_file.read_text(encoding="utf-8")
    assert revised_source["source_revision"] == revised_draft["draft_revision"]
    assert revised_source["current_trace_stale"] is False
