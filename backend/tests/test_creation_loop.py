from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from novel_adapters.sqlite import SQLiteProjectionStore
from novel_cli.main import EXIT_CONFLICT, EXIT_OK, EXIT_PROJECT, EXIT_STORAGE, main
from novel_core import (
    BootstrapEntityDraft,
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
    scene_number: int,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    scene_path = directory / f"scene-{scene_number}.md"
    chapter_path = directory / f"chapter-{scene_number}.md"
    scene_path.write_text(
        f"第 {scene_number} 场推进了主角的选择。\n",
        encoding="utf-8",
    )
    chapter_path.write_text(
        f"本章已有 {scene_number} 个正式场景。\n",
        encoding="utf-8",
    )
    return scene_path, chapter_path


def test_full_approved_creation_loop_publishes_two_queryable_scenes(
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
    assert saved["content"]["entity_resolutions"][0]["entity"]["entity_id"]
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
        "写出林澜打开旧信的场景",
        "--story-time",
        str(story_time),
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
    assert context["previous_scene_text_available"] is False

    first_draft_file = tmp_path / "first-scene.md"
    first_draft_file.write_text("# 旧信\n\n潮声退去时，林澜拆开了那封信。\n", encoding="utf-8")
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
    first_scene_path, first_chapter_path = _write_summaries(
        tmp_path / "summaries",
        scene_number=1,
    )
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
        "--scene-summary",
        str(first_scene_path),
        "--chapter-summary",
        str(first_chapter_path),
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
        "写出林澜追查寄信人的场景",
        "--story-time",
        str(story_time_2),
        "--chapter-id",
        first_session["target_chapter_id"],
        "--before-scene-id",
        first_session["target_scene_id"],
    )
    historical = _project_call(
        capsys,
        catalog,
        root,
        "memory",
        "read-scene",
        "--session-id",
        second_session["writing_session_id"],
        "--chapter-id",
        first_session["target_chapter_id"],
        "--scene-id",
        first_session["target_scene_id"],
    )
    assert "林澜拆开了那封信" in historical["text"]
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

    second_draft_file = tmp_path / "second-scene.md"
    second_draft_file.write_text(
        "# 盐渍\n\n林澜把信纸举向灯下，看见潮汐留下的地图。\n",
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
    second_scene_path, second_chapter_path = _write_summaries(
        tmp_path / "summaries",
        scene_number=2,
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
        "--scene-summary",
        str(second_scene_path),
        "--chapter-summary",
        str(second_chapter_path),
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

    ledger_lines = (
        (root / "canon" / "ledger" / "canon.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(ledger_lines) == 3
    connection = sqlite3.connect(root / ".novel" / "project.sqlite")
    try:
        assert connection.execute("SELECT COUNT(*) FROM scenes").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 1
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
