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
    ChapterHistoryAccessError,
    ManuscriptReadError,
    NavigationMemoryService,
    NavigationMemoryWriter,
    ProjectService,
)
from novel_cli.main import EXIT_OK, main
from novel_core import (
    EMPTY_CANON_REVISION,
    CanonLedgerEntry,
    Chapter,
    ChapterLedgerRecord,
    ChapterStatus,
    ChapterSummary,
    ChapterSummaryDependency,
    Document,
    DocumentKind,
    DocumentLedgerRecord,
    Entity,
    EntityLedgerRecord,
    EntityStatus,
    ProjectManifest,
    SourceRef,
    SourceRefLedgerRecord,
    StoryTime,
    StoryTimeKind,
    Volume,
    VolumeSummary,
    chapter_summary_digest,
    manuscript_revision,
)

CHARACTER_ID = UUID("71000000-0000-4000-8000-000000000001")
CHAPTER_ONE = UUID("72000000-0000-4000-8000-000000000001")
CHAPTER_TWO = UUID("72000000-0000-4000-8000-000000000002")
CHAPTER_THREE = UUID("72000000-0000-4000-8000-000000000003")
CHAPTER_ID_ONE = UUID("73000000-0000-4000-8000-000000000001")
CHAPTER_ID_TWO = UUID("73000000-0000-4000-8000-000000000002")
CHAPTER_ID_THREE = UUID("73000000-0000-4000-8000-000000000003")
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
    chapter_ids = (CHAPTER_ID_ONE, CHAPTER_ID_TWO, CHAPTER_ID_THREE)
    volume_ids = (None, CHAPTER_TWO, CHAPTER_THREE)

    documents: list[Document] = []
    chapters: list[Chapter] = []
    for order, (content, relative_path, document_id, chapter_id, volume_id) in enumerate(
        zip(contents, paths, document_ids, chapter_ids, volume_ids, strict=True),
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
        chapter = Chapter(
            chapter_id=chapter_id,
            volume_id=volume_id,
            chapter_number=order,
            title=f"第 {order} 章",
            narrative_order=order,
            story_time=StoryTime(
                timeline_id="main",
                kind=StoryTimeKind.ORDINAL,
                story_time_start=order * 10,
                display_time=f"旧历第 {order * 10} 日",
            ),
            pov_entity_id=CHARACTER_ID,
            status=ChapterStatus.APPROVED,
            source_document_id=document_id,
            revision=revision,
        )
        documents.append(document)
        chapters.append(chapter)

    volumes = (
        Volume(
            volume_id=CHAPTER_ONE,
            volume_number=1,
            title="霜夜",
            chapter_ids=(CHAPTER_ID_ONE,),
        ),
        Volume(
            volume_id=CHAPTER_TWO,
            volume_number=2,
            title="旧誓",
            chapter_ids=(CHAPTER_ID_TWO,),
        ),
        Volume(
            volume_id=CHAPTER_THREE,
            volume_number=3,
            title="黎明",
            chapter_ids=(CHAPTER_ID_THREE,),
        ),
    )
    chapter_one_summary = ChapterSummary(
        chapter_id=CHAPTER_ID_ONE,
        volume_id=CHAPTER_ONE,
        chapter_number_in_volume=1,
        source_document_id=DOCUMENT_ONE,
        source_revision=documents[0].revision,
        summary="顾宁在北塔发现银戒秘密。",
        main_entity_ids=(CHARACTER_ID,),
        key_changes=("发现银戒",),
        open_questions=("银戒来自何处？",),
    )
    chapter_three_summary = ChapterSummary(
        chapter_id=CHAPTER_ID_THREE,
        volume_id=CHAPTER_THREE,
        chapter_number_in_volume=1,
        source_document_id=DOCUMENT_THREE,
        source_revision=documents[2].revision,
        summary="顾宁将在黎明追查银戒来源。",
        main_entity_ids=(CHARACTER_ID,),
    )
    volume_one_summary = VolumeSummary(
        volume_id=CHAPTER_ONE,
        volume_number=1,
        title="霜夜",
        chapter_ids=(CHAPTER_ID_ONE,),
        chapter_summary_dependencies=(
            ChapterSummaryDependency(
                chapter_id=CHAPTER_ID_ONE,
                source_revision=chapter_one_summary.source_revision,
                summary_digest=chapter_summary_digest(chapter_one_summary),
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
        chapter_id=CHAPTER_ID_ONE,
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
                *(ChapterLedgerRecord(value=chapter) for chapter in chapters),
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
    for volume in volumes:
        writer.save_volume(volume)
    writer.save_chapter_summary(chapter_one_summary)
    writer.save_chapter_summary(chapter_three_summary)
    writer.save_volume_summary(volume_one_summary)
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
        "chapter_one_summary": chapter_one_summary,
    }


def test_volume_and_summary_contracts_are_strict_frozen_and_round_trip() -> None:
    volume = Volume(
        volume_id=CHAPTER_ONE,
        volume_number=1,
        title="霜夜",
        chapter_ids=(CHAPTER_ID_ONE,),
    )
    summary = ChapterSummary(
        chapter_id=CHAPTER_ID_ONE,
        volume_id=CHAPTER_ONE,
        chapter_number_in_volume=1,
        source_document_id=DOCUMENT_ONE,
        source_revision=f"sha256:{sha256(b'chapter').hexdigest()}",
        summary="顾宁发现银戒。",
    )
    dependency = ChapterSummaryDependency(
        chapter_id=CHAPTER_ID_ONE,
        source_revision=summary.source_revision,
        summary_digest=chapter_summary_digest(summary),
    )
    volume_summary = VolumeSummary(
        volume_id=CHAPTER_ONE,
        volume_number=1,
        title="霜夜",
        chapter_ids=(CHAPTER_ID_ONE,),
        chapter_summary_dependencies=(dependency,),
        summary="银戒之谜开始。",
    )

    for model in (volume, summary, dependency, volume_summary):
        restored = type(model).from_json(model.to_canonical_json())
        assert restored == model
        assert restored.to_canonical_json() == model.to_canonical_json()

    with pytest.raises(ValidationError, match="frozen"):
        volume.title = "被修改"
    with pytest.raises(ValidationError):
        Volume(
            volume_id=CHAPTER_ONE,
            volume_number=0,
            title="非法",
            chapter_ids=(CHAPTER_ID_ONE,),
        )
    with pytest.raises(ValidationError, match="unique"):
        Volume(
            volume_id=CHAPTER_ONE,
            volume_number=1,
            title="重复",
            chapter_ids=(CHAPTER_ID_ONE, CHAPTER_ID_ONE),
        )
    with pytest.raises(ValidationError, match="same order"):
        VolumeSummary(
            volume_id=CHAPTER_ONE,
            volume_number=1,
            title="霜夜",
            chapter_ids=(CHAPTER_ID_ONE,),
            chapter_summary_dependencies=(
                ChapterSummaryDependency(
                    chapter_id=CHAPTER_ID_TWO,
                    source_revision=summary.source_revision,
                    summary_digest=chapter_summary_digest(summary),
                ),
            ),
            summary="依赖错误。",
        )


def test_explicit_volume_binding_lists_summaries_without_guessing_paths(
    memory_case: dict[str, object],
) -> None:
    memory = memory_case["memory"]
    volumes = memory.volumes()
    chapters = memory.chapters(CHAPTER_ONE)
    missing = memory.chapters(CHAPTER_TWO)

    assert [item.volume.title for item in volumes] == ["霜夜", "旧誓", "黎明"]
    assert volumes[0].summary is not None
    assert volumes[1].summary is None
    assert chapters[0].chapter.volume_id is None
    assert chapters[0].chapter_number_in_volume == 1
    assert chapters[0].summary is not None
    assert missing[0].summary is None
    assert missing[0].stale is None


def test_stale_chapter_revision_propagates_to_volume_summary(
    memory_case: dict[str, object],
) -> None:
    navigation = memory_case["navigation"]
    current = memory_case["chapter_one_summary"]
    stale = current.model_copy(
        update={"source_revision": f"sha256:{sha256(b'old revision').hexdigest()}"}
    )
    with pytest.raises(ChapterHistoryAccessError, match="current approved"):
        memory_case["writer"].save_chapter_summary(stale)
    navigation.save_chapter_summary(stale)
    memory_case["projects"].ensure_projection_current()

    projection = SQLiteProjectionQueries(memory_case["root"])
    memory = NavigationMemoryService(
        navigation=projection,
        canon=CanonQueryService(projection),
        manuscripts=FilesystemManuscriptStore(memory_case["root"]),
    )
    volume = memory.volumes()[0]
    chapter = memory.chapters(CHAPTER_ONE)[0]

    assert chapter.stale is True
    assert volume.stale is True
    assert chapter.summary.source_revision != memory_case["documents"][0].revision


def test_changed_chapter_summary_digest_stales_only_dependent_volume(
    memory_case: dict[str, object],
) -> None:
    current = memory_case["chapter_one_summary"]
    memory_case["writer"].save_chapter_summary(
        current.model_copy(update={"summary": "顾宁确认银戒刻有陌生铭文。"})
    )

    projection = SQLiteProjectionQueries(memory_case["root"])
    memory = NavigationMemoryService(
        navigation=projection,
        canon=CanonQueryService(projection),
        manuscripts=FilesystemManuscriptStore(memory_case["root"]),
    )

    assert memory.chapters(CHAPTER_ONE)[0].stale is False
    assert memory.volumes()[0].stale is True


def test_exact_read_ignores_missing_summary_and_blocks_wrong_or_future_chapter(
    memory_case: dict[str, object],
) -> None:
    memory = memory_case["memory"]
    exact = memory.read_chapter(
        volume_id=CHAPTER_TWO,
        chapter_id=CHAPTER_ID_TWO,
        before_chapter_id=CHAPTER_ID_THREE,
    )

    assert exact.text == memory_case["contents"][1].decode("utf-8")
    assert exact.document.revision == manuscript_revision(memory_case["contents"][1])
    assert exact.chapter.story_time.story_time_start == 20
    assert exact.chapter.narrative_order == 2
    assert exact.chapter.pov_entity_id == CHARACTER_ID

    with pytest.raises(ChapterHistoryAccessError, match="does not belong"):
        memory.read_chapter(
            volume_id=CHAPTER_TWO,
            chapter_id=CHAPTER_ID_ONE,
            before_chapter_id=CHAPTER_ID_THREE,
        )
    with pytest.raises(ChapterHistoryAccessError, match="before"):
        memory.read_chapter(
            volume_id=CHAPTER_THREE,
            chapter_id=CHAPTER_ID_THREE,
            before_chapter_id=CHAPTER_ID_THREE,
        )


def test_exact_read_rejects_disk_bytes_that_drift_from_approved_revision(
    memory_case: dict[str, object],
) -> None:
    root = memory_case["root"]
    document = memory_case["documents"][1]
    (root / document.relative_path).write_text("未批准的磁盘修改", encoding="utf-8")

    with pytest.raises(ManuscriptReadError, match="revision mismatch"):
        memory_case["memory"].read_chapter(
            volume_id=CHAPTER_TWO,
            chapter_id=CHAPTER_ID_TWO,
            before_chapter_id=CHAPTER_ID_THREE,
        )


def test_summary_search_returns_only_historical_navigation_candidates(
    memory_case: dict[str, object],
) -> None:
    memory = memory_case["memory"]
    hits = memory.search_summaries(
        query="银戒秘密",
        entity_id=CHARACTER_ID,
        before_chapter_id=CHAPTER_ID_THREE,
    )

    assert len(hits) == 1
    assert isinstance(hits[0].summary, ChapterSummary)
    assert hits[0].summary.chapter_id == CHAPTER_ID_ONE
    assert hits[0].retrieval_method.value == "fts5_trigram"
    assert "main_entity_ids contains" in hits[0].match_reason
    assert not hasattr(hits[0], "canon_status")

    assert (
        memory.search_summaries(
            query="隐藏原文词",
            entity_id=None,
            before_chapter_id=CHAPTER_ID_THREE,
        )
        == ()
    )
    future = memory.search_summaries(
        query="黎明追查",
        entity_id=None,
        before_chapter_id=CHAPTER_ID_THREE,
    )
    assert future == ()


def test_deleted_sqlite_rebuilds_navigation_projection_from_files(
    memory_case: dict[str, object],
) -> None:
    root = memory_case["root"]
    before = [
        (
            item.volume,
            item.summary,
            item.stale,
        )
        for item in memory_case["memory"].volumes()
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
    after = [(item.volume, item.summary, item.stale) for item in rebuilt.volumes()]

    assert after == before
    assert (root / "structure" / "volumes" / f"{CHAPTER_ONE}.json").is_file()
    assert (root / "memory" / "chapters" / f"{CHAPTER_ID_ONE}.json").is_file()


def test_memory_cli_vertical_slice_uses_one_versioned_json_envelope(
    memory_case: dict[str, object],
    capsys,
) -> None:
    root = memory_case["root"]

    assert main(["--project", str(root), "memory", "volumes", "--json"]) == EXIT_OK
    volumes = json.loads(capsys.readouterr().out)
    assert volumes["ok"] is True
    assert volumes["data"]["schema_version"] == "1.0.0"
    assert volumes["data"]["volumes"][0]["volume"]["title"] == "霜夜"

    assert (
        main(
            [
                "--project",
                str(root),
                "memory",
                "chapters",
                "--volume-id",
                str(CHAPTER_TWO),
                "--json",
            ]
        )
        == EXIT_OK
    )
    chapters = json.loads(capsys.readouterr().out)
    assert chapters["data"]["chapters"][0]["summary"] is None

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
                "--before-chapter",
                str(CHAPTER_ID_THREE),
                "--json",
            ]
        )
        == EXIT_OK
    )
    search = json.loads(capsys.readouterr().out)
    assert search["data"]["hits"][0]["summary_kind"] == "chapter"
    assert search["data"]["hits"][0]["retrieval_method"] == "fts5_trigram"

    assert (
        main(
            [
                "--project",
                str(root),
                "memory",
                "read-chapter",
                "--volume-id",
                str(CHAPTER_ONE),
                "--chapter-id",
                str(CHAPTER_ID_ONE),
                "--before-chapter",
                str(CHAPTER_ID_THREE),
                "--json",
            ]
        )
        == EXIT_OK
    )
    exact = json.loads(capsys.readouterr().out)
    assert exact["data"]["text"] == memory_case["contents"][0].decode("utf-8")
    assert exact["data"]["volume_id"] == str(CHAPTER_ONE)
    assert exact["data"]["chapter_id"] == str(CHAPTER_ID_ONE)
    assert exact["data"]["document_revision"] == memory_case["documents"][0].revision


def _project_service(root: Path) -> ProjectService:
    return ProjectService(
        projects=FilesystemProjectStore(root),
        ledger=FilesystemCanonLedgerStore(root),
        projection=SQLiteProjectionStore(root),
        write_lock=FilesystemProjectWriteLock(root),
    )
