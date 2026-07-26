from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import UUID

from novel_adapters.filesystem import (
    FilesystemCanonLedgerStore,
    FilesystemProjectStore,
    FilesystemProjectWriteLock,
    default_app_data_directory,
)
from novel_adapters.sqlite import SQLiteProjectionStore
from novel_application import ProjectService
from novel_cli.main import (
    EXIT_BUSY,
    EXIT_CONFLICT,
    EXIT_INVALID_INPUT,
    EXIT_OK,
    EXIT_PROJECT,
    EXIT_STORAGE,
    main,
)
from novel_core import ProjectManifest


def _invoke_json(capsys, *arguments: str) -> tuple[int, dict]:
    exit_code = main([*arguments, "--json"])
    captured = capsys.readouterr()
    assert captured.err == ""
    return exit_code, json.loads(captured.out)


def _create(
    capsys,
    *,
    catalog: Path,
    root: Path,
    title: str,
) -> dict:
    exit_code, payload = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "create",
        str(root),
        "--title",
        title,
        "--language",
        "zh-CN",
    )
    assert exit_code == EXIT_OK
    assert payload["ok"] is True
    return payload["data"]


def _standalone_project(root: Path, project_id: UUID, title: str) -> None:
    service = ProjectService(
        projects=FilesystemProjectStore(root),
        ledger=FilesystemCanonLedgerStore(root),
        projection=SQLiteProjectionStore(root),
        write_lock=FilesystemProjectWriteLock(root),
    )
    service.initialize(
        ProjectManifest(
            project_id=project_id,
            title=title,
            language="zh-CN",
            minimum_core_version="0.1.0",
        )
    )


def _asset_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in {"project.sqlite-shm", "project.sqlite-wal"}
    }


def test_default_catalog_directory_is_cross_platform_and_overridable(
    tmp_path: Path,
) -> None:
    override = tmp_path / "isolated-app-data"
    assert (
        default_app_data_directory(
            environment={"NOVEL_APP_DATA_DIR": str(override)},
            platform="darwin",
            home=tmp_path / "home",
        )
        == override.resolve()
    )
    assert (
        default_app_data_directory(
            environment={},
            platform="darwin",
            home=tmp_path / "home",
        )
        == (tmp_path / "home" / "Library" / "Application Support" / "Novel").resolve()
    )
    assert (
        default_app_data_directory(
            environment={},
            platform="linux",
            home=tmp_path / "home",
        )
        == (tmp_path / "home" / ".local" / "share" / "novel").resolve()
    )


def test_two_projects_have_distinct_identity_storage_and_catalog_entries(
    tmp_path: Path,
    capsys,
) -> None:
    catalog = tmp_path / "app-data"
    first_root = tmp_path / "第一部"
    second_root = tmp_path / "第二部"
    first = _create(capsys, catalog=catalog, root=first_root, title="第一部")
    second = _create(capsys, catalog=catalog, root=second_root, title="第二部")

    assert first["project_id"] != second["project_id"]
    assert Path(first["project_path"]) == first_root.resolve()
    assert Path(second["project_path"]) == second_root.resolve()
    for root in (first_root, second_root):
        assert (root / "novel.yaml").is_file()
        assert (root / "intent").is_dir()
        assert (root / "canon" / "ledger" / "canon.jsonl").read_bytes() == b""
        assert (root / ".novel" / "project.sqlite").is_file()
        assert not (root / "runs").exists()

    exit_code, listed = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "list",
    )
    assert exit_code == EXIT_OK
    assert {
        (item["project_id"], item["title"], Path(item["project_path"]), item["status"])
        for item in listed["data"]["projects"]
    } == {
        (first["project_id"], "第一部", first_root.resolve(), "not_bootstrapped"),
        (second["project_id"], "第二部", second_root.resolve(), "not_bootstrapped"),
    }
    assert all(item["path_exists"] for item in listed["data"]["projects"])

    catalog_payload = json.loads((catalog / "projects.json").read_text(encoding="utf-8"))
    assert set(catalog_payload) == {"catalog_format_version", "projects", "schema_version"}
    assert all(
        set(entry)
        == {
            "project_id",
            "project_path",
            "schema_version",
            "status",
            "title",
        }
        for entry in catalog_payload["projects"]
    )
    assert not list(catalog.glob(".projects-*.tmp"))


def test_show_and_existing_commands_share_exact_project_selection(
    tmp_path: Path,
    capsys,
) -> None:
    catalog = tmp_path / "app-data"
    first = _create(
        capsys,
        catalog=catalog,
        root=tmp_path / "one",
        title="One",
    )
    second = _create(
        capsys,
        catalog=catalog,
        root=tmp_path / "two",
        title="Two",
    )

    exit_code, by_id = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project-id",
        first["project_id"],
        "project",
        "show",
    )
    assert exit_code == EXIT_OK
    assert by_id["data"]["project_id"] == first["project_id"]
    assert by_id["data"]["catalog"]["registered"] is True
    assert by_id["data"]["catalog"]["path_matches"] is True
    assert by_id["data"]["health"]["storage_healthy"] is True

    exit_code, by_path = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "show",
        "--project",
        second["project_path"],
    )
    assert exit_code == EXIT_OK
    assert by_path["data"]["project_id"] == second["project_id"]

    exit_code, exact_pair = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project-id",
        first["project_id"],
        "--project",
        first["project_path"],
        "doctor",
    )
    assert exit_code == EXIT_OK
    assert exact_pair["data"]["project_id"] == first["project_id"]

    exit_code, mismatch = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project-id",
        first["project_id"],
        "--project",
        second["project_path"],
        "doctor",
    )
    assert exit_code == EXIT_CONFLICT
    assert mismatch["error"]["code"] == "project_selection_mismatch"

    exit_code, doctor = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project-id",
        second["project_id"],
        "doctor",
    )
    assert exit_code == EXIT_OK
    assert doctor["data"]["project_id"] == second["project_id"]
    assert Path(doctor["data"]["project"]) == Path(second["project_path"])

    second_assets = _asset_bytes(Path(second["project_path"]))
    exit_code, rebuilt = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "--project-id",
        first["project_id"],
        "rebuild",
    )
    assert exit_code == EXIT_OK
    assert rebuilt["data"]["project_id"] == first["project_id"]
    assert _asset_bytes(Path(second["project_path"])) == second_assets


def test_add_is_read_only_and_moved_project_updates_the_same_identity(
    tmp_path: Path,
    capsys,
) -> None:
    catalog = tmp_path / "app-data"
    original = tmp_path / "original"
    moved = tmp_path / "moved"
    project_id = UUID("b0000000-0000-4000-8000-000000000042")
    _standalone_project(original, project_id, "Existing")
    marker = original / "manuscript" / "author-note.md"
    marker.write_text("不得修改\n", encoding="utf-8")
    before = _asset_bytes(original)

    exit_code, added = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "add",
        str(original),
    )
    assert exit_code == EXIT_OK
    assert added["data"]["catalog_action"] == "registered"
    assert _asset_bytes(original) == before

    original.rename(moved)
    moved_before = _asset_bytes(moved)
    _, stale_list = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "list",
    )
    assert stale_list["data"]["projects"][0]["path_exists"] is False

    exit_code, updated = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "add",
        str(moved),
    )
    assert exit_code == EXIT_OK
    assert updated["data"]["project_id"] == str(project_id)
    assert updated["data"]["catalog_action"] == "path_updated"
    assert Path(updated["data"]["project_path"]) == moved.resolve()
    assert _asset_bytes(moved) == moved_before

    _, listed = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "list",
    )
    assert [item["project_path"] for item in listed["data"]["projects"]] == [str(moved.resolve())]


def test_add_rejects_invalid_manifest_duplicate_path_and_live_identity_clone(
    tmp_path: Path,
    capsys,
) -> None:
    catalog = tmp_path / "app-data"
    original = tmp_path / "original"
    clone = tmp_path / "clone"
    project_id = UUID("b0000000-0000-4000-8000-000000000043")
    _standalone_project(original, project_id, "Existing")

    exit_code, _ = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "add",
        str(original),
    )
    assert exit_code == EXIT_OK

    exit_code, duplicate = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "add",
        str(original),
    )
    assert exit_code == EXIT_CONFLICT
    assert duplicate["error"]["code"] == "catalog_path_conflict"

    shutil.copytree(original, clone)
    exit_code, identity_conflict = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "add",
        str(clone),
    )
    assert exit_code == EXIT_CONFLICT
    assert identity_conflict["error"]["code"] == "project_identity_conflict"

    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "novel.yaml").write_text("{}\n", encoding="utf-8")
    exit_code, invalid_manifest = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "add",
        str(invalid),
    )
    assert exit_code == EXIT_PROJECT
    assert invalid_manifest["error"]["code"] == "invalid_project_manifest"


def test_remove_forgets_only_catalog_reference_and_missing_reference_is_stable(
    tmp_path: Path,
    capsys,
) -> None:
    catalog = tmp_path / "app-data"
    root = tmp_path / "novel"
    created = _create(capsys, catalog=catalog, root=root, title="Keep Assets")
    marker = root / "manuscript" / "keep.md"
    marker.write_text("保留正文\n", encoding="utf-8")
    before = _asset_bytes(root)

    exit_code, removed = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "remove",
        "--project-id",
        created["project_id"],
    )
    assert exit_code == EXIT_OK
    assert removed["data"] == {
        "project_id": created["project_id"],
        "project_path": str(root.resolve()),
        "removed": True,
    }
    assert root.is_dir()
    assert marker.read_text(encoding="utf-8") == "保留正文\n"
    assert _asset_bytes(root) == before

    exit_code, shown = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "show",
        "--project",
        str(root),
    )
    assert exit_code == EXIT_OK
    assert shown["data"]["project_id"] == created["project_id"]
    assert shown["data"]["catalog"]["registered"] is False

    exit_code, missing = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "remove",
        "--project-id",
        created["project_id"],
    )
    assert exit_code == EXIT_PROJECT
    assert missing["error"]["code"] == "catalog_entry_not_found"


def test_catalog_lock_and_create_conflict_have_distinct_protocol_errors(
    tmp_path: Path,
    capsys,
) -> None:
    catalog = tmp_path / "app-data"
    catalog.mkdir()
    (catalog / "projects.lock").write_text(
        json.dumps({"pid": 1, "token": "held"}),
        encoding="utf-8",
    )
    exit_code, busy = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "create",
        str(tmp_path / "one"),
        "--title",
        "One",
    )
    assert exit_code == EXIT_BUSY
    assert busy["error"]["code"] == "catalog_busy"

    (catalog / "projects.lock").unlink()
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("user data", encoding="utf-8")
    exit_code, conflict = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "create",
        str(occupied),
        "--title",
        "Occupied",
    )
    assert exit_code == EXIT_CONFLICT
    assert conflict["error"]["code"] == "project_already_exists"
    assert (occupied / "keep.txt").read_text(encoding="utf-8") == "user data"

    exit_code, invalid_path = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "add",
        "\x00",
    )
    assert exit_code == EXIT_INVALID_INPUT
    assert invalid_path["error"]["code"] == "invalid_project_path"

    (catalog / "projects.json").write_text("{broken", encoding="utf-8")
    exit_code, broken_catalog = _invoke_json(
        capsys,
        "--catalog-dir",
        str(catalog),
        "project",
        "list",
    )
    assert exit_code == EXIT_STORAGE
    assert broken_catalog["error"]["code"] == "catalog_read_error"
