from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from novel_adapters.filesystem import (
    FilesystemCanonLedgerStore,
    FilesystemManuscriptStore,
    FilesystemNavigationStore,
    FilesystemProjectStore,
    FilesystemProjectWriteLock,
)
from novel_adapters.sqlite import SQLiteProjectionQueries, SQLiteProjectionStore
from novel_application import (
    CanonQueryService,
    ManuscriptReadError,
    NavigationMemoryService,
    NavigationMemoryWriter,
    ProjectService,
    SceneHistoryAccessError,
)
from novel_cli.main import EXIT_OK, main
from novel_core import (
    EMPTY_CANON_REVISION,
    CanonLedgerEntry,
    Chapter,
    ChapterSummary,
    Document,
    DocumentKind,
    DocumentLedgerRecord,
    Entity,
    EntityLedgerRecord,
    EntityStatus,
    ProjectManifest,
    Scene,
    SceneLedgerRecord,
    SceneStatus,
    SceneSummary,
    SceneSummaryDependency,
    SourceRef,
    SourceRefLedgerRecord,
    StoryTime,
    StoryTimeKind,
    manuscript_revision,
    scene_summary_digest,
)

CHARACTER_ID = UUID("71000000-0000-4000-8000-000000000001")
CHAPTER_ONE = UUID("72000000-0000-4000-8000-000000000001")
CHAPTER_TWO = UUID("72000000-0000-4000-8000-000000000002")
CHAPTER_THREE = UUID("72000000-0000-4000-8000-000000000003")
SCENE_ONE = UUID("73000000-0000-4000-8000-000000000001")
SCENE_TWO = UUID("73000000-0000-4000-8000-000000000002")
SCENE_THREE = UUID("73000000-0000-4000-8000-000000000003")
DOCUMENT_ONE = UUID("74000000-0000-4000-8000-000000000001")
DOCUMENT_TWO = UUID("74000000-0000-4000-8000-000000000002")
DOCUMENT_THREE = UUID("74000000-0000-4000-8000-000000000003")


@pytest.fixture
def memory_case(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "中文 小说"
    projects = _project_service(root)
    projects.initialize(
        ProjectManifest(
            project_id=UUID("75000000-0000-4000-8000-000000000001"),
            title="银戒旧事",
            language="zh-CN",
            minimum_core_version="0.1.0",
        )
    )

    contents = (
        "# 第一章：霜夜\n\n顾宁在北塔发现银戒秘密，也记下隐藏原文词。\n".encode(),
        "# 第二章：旧誓\n\n她把银戒收进木匣，没有解释缘由。\n".encode(),
        "# 第三章：黎明\n\n目标小节从这里开始，不能作为普通历史读取。\n".encode(),
    )
    paths = (
        "manuscript/卷一/第一章-霜夜.md",
        "manuscript/卷一/第二章-旧誓.md",
        "manuscript/卷一/第三章-黎明.md",
    )
    document_ids = (DOCUMENT_ONE, DOCUMENT_TWO, DOCUMENT_THREE)
    scene_ids = (SCENE_ONE, SCENE_TWO, SCENE_THREE)
    chapter_ids = (None, CHAPTER_TWO, CHAPTER_THREE)

    documents: list[Document] = []
    scenes: list[Scene] = []
    for order, (content, relative_path, document_id, scene_id, chapter_id) in enumerate(
        zip(contents, paths, document_ids, scene_ids, chapter_ids, strict=True),
        start=1,
    ):
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        revision = manuscript_revision(content)
        document = Document(
            document_id=document_id,
            relative_path=relative_path,
            document_kind=DocumentKind.MANUSCRIPT,
            revision=revision,
        )
        scene = Scene(
            scene_id=scene_id,
            chapter_id=chapter_id,
            narrative_order=order,
            story_time=StoryTime(
                timeline_id="main",
                kind=StoryTimeKind.ORDINAL,
                story_time_start=order * 10,
                display_time=f"旧历第 {order * 10} 日",
            ),
            pov_entity_id=CHARACTER_ID,
            status=SceneStatus.APPROVED,
            source_document_id=document_id,
            revision=revision,
        )
        documents.append(document)
        scenes.append(scene)

    chapters = (
        Chapter(
            chapter_id=CHAPTER_ONE,
            chapter_number=1,
            title="霜夜",
            scene_ids=(SCENE_ONE,),
        ),
        Chapter(
            chapter_id=CHAPTER_TWO,
            chapter_number=2,
            title="旧誓",
            scene_ids=(SCENE_TWO,),
        ),
        Chapter(
            chapter_id=CHAPTER_THREE,
            chapter_number=3,
            title="黎明",
            scene_ids=(SCENE_THREE,),
        ),
    )
    scene_one_summary = SceneSummary(
        scene_id=SCENE_ONE,
        chapter_id=CHAPTER_ONE,
        scene_number_in_chapter=1,
        source_document_id=DOCUMENT_ONE,
        source_revision=documents[0].revision,
        summary="顾宁在北塔发现银戒秘密。",
        main_entity_ids=(CHARACTER_ID,),
        key_changes=("发现银戒",),
        open_questions=("银戒来自何处？",),
    )
    scene_three_summary = SceneSummary(
        scene_id=SCENE_THREE,
        chapter_id=CHAPTER_THREE,
        scene_number_in_chapter=1,
        source_document_id=DOCUMENT_THREE,
        source_revision=documents[2].revision,
        summary="顾宁将在黎明追查银戒来源。",
        main_entity_ids=(CHARACTER_ID,),
    )
    chapter_one_summary = ChapterSummary(
        chapter_id=CHAPTER_ONE,
        chapter_number=1,
        title="霜夜",
        scene_ids=(SCENE_ONE,),
        scene_summary_dependencies=(
            SceneSummaryDependency(
                scene_id=SCENE_ONE,
                source_revision=scene_one_summary.source_revision,
                summary_digest=scene_summary_digest(scene_one_summary),
            ),
        ),
        summary="顾宁在霜夜获得银戒线索。",
        main_entity_ids=(CHARACTER_ID,),
    )
    character = Entity(
        entity_id=CHARACTER_ID,
        entity_type="character",
        display_name="顾宁",
        status=EntityStatus.ACTIVE,
        created_revision=EMPTY_CANON_REVISION,
    )
    excerpt = contents[0].decode("utf-8").strip()
    source_ref = SourceRef(
        source_ref_id=UUID("77000000-0000-4000-8000-000000000001"),
        document_id=DOCUMENT_ONE,
        scene_id=SCENE_ONE,
        document_revision=documents[0].revision,
        fragment_ordinal=1,
        quote_hash=sha256(excerpt.encode("utf-8")).hexdigest(),
        excerpt=excerpt,
    )
    projects.append(
        CanonLedgerEntry(
            ledger_sequence=1,
            ledger_entry_id=UUID("76000000-0000-4000-8000-000000000001"),
            base_revision=EMPTY_CANON_REVISION,
            approved_at=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
            records=(
                EntityLedgerRecord(value=character),
                *(DocumentLedgerRecord(value=document) for document in documents),
                *(SceneLedgerRecord(value=scene) for scene in scenes),
                SourceRefLedgerRecord(value=source_ref),
            ),
        )
    )
    navigation = FilesystemNavigationStore(root)
    projection = SQLiteProjectionQueries(root)
    canon = CanonQueryService(projection)
    writer = NavigationMemoryWriter(
        sources=navigation,
        navigation=projection,
        canon=canon,
        projects=FilesystemProjectStore(root),
        ledger=FilesystemCanonLedgerStore(root),
        projection=SQLiteProjectionStore(root),
        write_lock=FilesystemProjectWriteLock(root),
    )
    for chapter in chapters:
        writer.save_chapter(chapter)
    writer.save_scene_summary(scene_one_summary)
    writer.save_scene_summary(scene_three_summary)
    writer.save_chapter_summary(chapter_one_summary)
    memory = NavigationMemoryService(
        navigation=projection,
        canon=canon,
        manuscripts=FilesystemManuscriptStore(root),
    )
    return {
        "root": root,
        "projects": projects,
        "navigation": navigation,
        "writer": writer,
        "memory": memory,
        "documents": tuple(documents),
        "contents": contents,
        "scene_one_summary": scene_one_summary,
    }


def test_chapter_and_summary_contracts_are_strict_frozen_and_round_trip() -> None:
    chapter = Chapter(
        chapter_id=CHAPTER_ONE,
        chapter_number=1,
        title="霜夜",
        scene_ids=(SCENE_ONE,),
    )
    summary = SceneSummary(
        scene_id=SCENE_ONE,
        chapter_id=CHAPTER_ONE,
        scene_number_in_chapter=1,
        source_document_id=DOCUMENT_ONE,
        source_revision=f"sha256:{sha256(b'scene').hexdigest()}",
        summary="顾宁发现银戒。",
    )
    dependency = SceneSummaryDependency(
        scene_id=SCENE_ONE,
        source_revision=summary.source_revision,
        summary_digest=scene_summary_digest(summary),
    )
    chapter_summary = ChapterSummary(
        chapter_id=CHAPTER_ONE,
        chapter_number=1,
        title="霜夜",
        scene_ids=(SCENE_ONE,),
        scene_summary_dependencies=(dependency,),
        summary="银戒之谜开始。",
    )

    for model in (chapter, summary, dependency, chapter_summary):
        restored = type(model).from_json(model.to_canonical_json())
        assert restored == model
        assert restored.to_canonical_json() == model.to_canonical_json()

    with pytest.raises(ValidationError, match="frozen"):
        chapter.title = "被修改"
    with pytest.raises(ValidationError):
        Chapter(
            chapter_id=CHAPTER_ONE,
            chapter_number=0,
            title="非法",
            scene_ids=(SCENE_ONE,),
        )
    with pytest.raises(ValidationError, match="unique"):
        Chapter(
            chapter_id=CHAPTER_ONE,
            chapter_number=1,
            title="重复",
            scene_ids=(SCENE_ONE, SCENE_ONE),
        )
    with pytest.raises(ValidationError, match="same order"):
        ChapterSummary(
            chapter_id=CHAPTER_ONE,
            chapter_number=1,
            title="霜夜",
            scene_ids=(SCENE_ONE,),
            scene_summary_dependencies=(
                SceneSummaryDependency(
                    scene_id=SCENE_TWO,
                    source_revision=summary.source_revision,
                    summary_digest=scene_summary_digest(summary),
                ),
            ),
            summary="依赖错误。",
        )


def test_explicit_chapter_binding_lists_summaries_without_guessing_paths(
    memory_case: dict[str, object],
) -> None:
    memory = memory_case["memory"]
    chapters = memory.chapters()
    scenes = memory.scenes(CHAPTER_ONE)
    missing = memory.scenes(CHAPTER_TWO)

    assert [item.chapter.title for item in chapters] == ["霜夜", "旧誓", "黎明"]
    assert chapters[0].summary is not None
    assert chapters[1].summary is None
    assert scenes[0].scene.chapter_id is None
    assert scenes[0].scene_number_in_chapter == 1
    assert scenes[0].summary is not None
    assert missing[0].summary is None
    assert missing[0].stale is None


def test_stale_scene_revision_propagates_to_chapter_summary(
    memory_case: dict[str, object],
) -> None:
    navigation = memory_case["navigation"]
    current = memory_case["scene_one_summary"]
    stale = current.model_copy(
        update={"source_revision": f"sha256:{sha256(b'old revision').hexdigest()}"}
    )
    with pytest.raises(SceneHistoryAccessError, match="current approved"):
        memory_case["writer"].save_scene_summary(stale)
    navigation.save_scene_summary(stale)
    memory_case["projects"].ensure_projection_current()

    projection = SQLiteProjectionQueries(memory_case["root"])
    memory = NavigationMemoryService(
        navigation=projection,
        canon=CanonQueryService(projection),
        manuscripts=FilesystemManuscriptStore(memory_case["root"]),
    )
    chapter = memory.chapters()[0]
    scene = memory.scenes(CHAPTER_ONE)[0]

    assert scene.stale is True
    assert chapter.stale is True
    assert scene.summary.source_revision != memory_case["documents"][0].revision


def test_changed_scene_summary_digest_stales_only_dependent_chapter(
    memory_case: dict[str, object],
) -> None:
    current = memory_case["scene_one_summary"]
    memory_case["writer"].save_scene_summary(
        current.model_copy(update={"summary": "顾宁确认银戒刻有陌生铭文。"})
    )

    projection = SQLiteProjectionQueries(memory_case["root"])
    memory = NavigationMemoryService(
        navigation=projection,
        canon=CanonQueryService(projection),
        manuscripts=FilesystemManuscriptStore(memory_case["root"]),
    )

    assert memory.scenes(CHAPTER_ONE)[0].stale is False
    assert memory.chapters()[0].stale is True


def test_exact_read_ignores_missing_summary_and_blocks_wrong_or_future_scene(
    memory_case: dict[str, object],
) -> None:
    memory = memory_case["memory"]
    exact = memory.read_scene(
        chapter_id=CHAPTER_TWO,
        scene_id=SCENE_TWO,
        before_scene_id=SCENE_THREE,
    )

    assert exact.text == memory_case["contents"][1].decode("utf-8")
    assert exact.document.revision == manuscript_revision(memory_case["contents"][1])
    assert exact.scene.story_time.story_time_start == 20
    assert exact.scene.narrative_order == 2
    assert exact.scene.pov_entity_id == CHARACTER_ID

    with pytest.raises(SceneHistoryAccessError, match="does not belong"):
        memory.read_scene(
            chapter_id=CHAPTER_TWO,
            scene_id=SCENE_ONE,
            before_scene_id=SCENE_THREE,
        )
    with pytest.raises(SceneHistoryAccessError, match="before"):
        memory.read_scene(
            chapter_id=CHAPTER_THREE,
            scene_id=SCENE_THREE,
            before_scene_id=SCENE_THREE,
        )


def test_exact_read_rejects_disk_bytes_that_drift_from_approved_revision(
    memory_case: dict[str, object],
) -> None:
    root = memory_case["root"]
    document = memory_case["documents"][1]
    (root / document.relative_path).write_text("未批准的磁盘修改", encoding="utf-8")

    with pytest.raises(ManuscriptReadError, match="revision mismatch"):
        memory_case["memory"].read_scene(
            chapter_id=CHAPTER_TWO,
            scene_id=SCENE_TWO,
            before_scene_id=SCENE_THREE,
        )


def test_summary_search_returns_only_historical_navigation_candidates(
    memory_case: dict[str, object],
) -> None:
    memory = memory_case["memory"]
    hits = memory.search_summaries(
        query="银戒秘密",
        entity_id=CHARACTER_ID,
        before_scene_id=SCENE_THREE,
    )

    assert len(hits) == 1
    assert isinstance(hits[0].summary, SceneSummary)
    assert hits[0].summary.scene_id == SCENE_ONE
    assert hits[0].retrieval_method.value == "fts5_trigram"
    assert "main_entity_ids contains" in hits[0].match_reason
    assert not hasattr(hits[0], "canon_status")

    assert (
        memory.search_summaries(
            query="隐藏原文词",
            entity_id=None,
            before_scene_id=SCENE_THREE,
        )
        == ()
    )
    future = memory.search_summaries(
        query="黎明追查",
        entity_id=None,
        before_scene_id=SCENE_THREE,
    )
    assert future == ()


def test_deleted_sqlite_rebuilds_navigation_projection_from_files(
    memory_case: dict[str, object],
) -> None:
    root = memory_case["root"]
    before = [
        (
            item.chapter,
            item.summary,
            item.stale,
        )
        for item in memory_case["memory"].chapters()
    ]
    database = root / ".novel" / "project.sqlite"
    database.unlink()
    Path(f"{database}-wal").unlink(missing_ok=True)
    Path(f"{database}-shm").unlink(missing_ok=True)

    memory_case["projects"].rebuild_projection()
    projection = SQLiteProjectionQueries(root)
    rebuilt = NavigationMemoryService(
        navigation=projection,
        canon=CanonQueryService(projection),
        manuscripts=FilesystemManuscriptStore(root),
    )
    after = [(item.chapter, item.summary, item.stale) for item in rebuilt.chapters()]

    assert after == before
    assert (root / "structure" / "chapters" / f"{CHAPTER_ONE}.json").is_file()
    assert (root / "memory" / "scenes" / f"{SCENE_ONE}.json").is_file()


def test_memory_cli_vertical_slice_uses_one_versioned_json_envelope(
    memory_case: dict[str, object],
    capsys,
) -> None:
    root = memory_case["root"]

    assert main(["--project", str(root), "memory", "chapters", "--json"]) == EXIT_OK
    chapters = json.loads(capsys.readouterr().out)
    assert chapters["ok"] is True
    assert chapters["data"]["schema_version"] == "1.0.0"
    assert chapters["data"]["chapters"][0]["chapter"]["title"] == "霜夜"

    assert (
        main(
            [
                "--project",
                str(root),
                "memory",
                "scenes",
                "--chapter-id",
                str(CHAPTER_TWO),
                "--json",
            ]
        )
        == EXIT_OK
    )
    scenes = json.loads(capsys.readouterr().out)
    assert scenes["data"]["scenes"][0]["summary"] is None

    assert (
        main(
            [
                "--project",
                str(root),
                "memory",
                "search-summaries",
                "--query",
                "银戒秘密",
                "--entity",
                str(CHARACTER_ID),
                "--before-scene",
                str(SCENE_THREE),
                "--json",
            ]
        )
        == EXIT_OK
    )
    search = json.loads(capsys.readouterr().out)
    assert search["data"]["hits"][0]["summary_kind"] == "scene"
    assert search["data"]["hits"][0]["retrieval_method"] == "fts5_trigram"

    assert (
        main(
            [
                "--project",
                str(root),
                "memory",
                "read-scene",
                "--chapter-id",
                str(CHAPTER_ONE),
                "--scene-id",
                str(SCENE_ONE),
                "--before-scene",
                str(SCENE_THREE),
                "--json",
            ]
        )
        == EXIT_OK
    )
    exact = json.loads(capsys.readouterr().out)
    assert exact["data"]["text"] == memory_case["contents"][0].decode("utf-8")
    assert exact["data"]["chapter_id"] == str(CHAPTER_ONE)
    assert exact["data"]["scene_id"] == str(SCENE_ONE)
    assert exact["data"]["document_revision"] == memory_case["documents"][0].revision


def _project_service(root: Path) -> ProjectService:
    return ProjectService(
        projects=FilesystemProjectStore(root),
        ledger=FilesystemCanonLedgerStore(root),
        projection=SQLiteProjectionStore(root),
        write_lock=FilesystemProjectWriteLock(root),
    )
