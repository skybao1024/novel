from __future__ import annotations

import json
from pathlib import Path

from novel_cli.main import EXIT_OK, EXIT_PROJECT, PROTOCOL_VERSION, main


def test_cli_exposes_only_current_project_canon_and_memory_commands(capsys) -> None:
    assert main(["--help"]) == EXIT_OK
    help_text = capsys.readouterr().out

    for command in (
        "version",
        "doctor",
        "project",
        "bootstrap",
        "intent",
        "session",
        "resolve",
        "query",
        "memory",
        "draft",
        "review",
        "publish",
        "rebuild",
    ):
        assert command in help_text
    for removed in (
        "init",
        "ingest",
        "changeset",
        "scene-card",
        "evidence",
        "check",
    ):
        assert removed not in help_text


def test_version_and_schema_commands_have_one_json_document(capsys) -> None:
    assert main(["version", "--json"]) == EXIT_OK
    version_payload = json.loads(capsys.readouterr().out)
    assert version_payload == {
        "command": "version",
        "data": {
            "core_schema_version": "1.0.0",
            "protocol_version": PROTOCOL_VERSION,
            "version": "0.1.0",
        },
        "ok": True,
        "protocol_version": PROTOCOL_VERSION,
        "warnings": [],
    }

    assert main(["schema", "show", "scene-summary", "--json"]) == EXIT_OK
    schema_payload = json.loads(capsys.readouterr().out)
    assert schema_payload["ok"] is True
    assert schema_payload["data"]["x-schema-version"] == "1.0.0"
    assert schema_payload["data"]["title"] == "SceneSummary"


def test_project_create_doctor_and_project_discovery(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = tmp_path / "中文 小说"
    catalog = tmp_path / "catalog"
    assert (
        main(
            [
                "--catalog-dir",
                str(catalog),
                "project",
                "create",
                str(root),
                "--title",
                "长跑测试",
                "--language",
                "zh-CN",
                "--json",
            ]
        )
        == EXIT_OK
    )
    initialized = json.loads(capsys.readouterr().out)
    assert initialized["ok"] is True
    assert Path(initialized["data"]["project_path"]) == root
    assert initialized["data"]["status"] == "not_bootstrapped"

    nested = root / "manuscript" / "volume-001"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert main(["--catalog-dir", str(catalog), "doctor", "--json"]) == EXIT_OK
    doctor = json.loads(capsys.readouterr().out)
    assert doctor["data"]["healthy"] is True
    assert doctor["data"]["last_ledger_sequence"] == 0


def test_machine_errors_use_stable_envelope_and_exit_code(
    tmp_path: Path,
    capsys,
) -> None:
    missing = tmp_path / "missing"
    result = main(["--project", str(missing), "doctor", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == EXIT_PROJECT
    assert captured.err == ""
    assert payload["ok"] is False
    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert payload["error"]["code"] == "project_not_found"


def test_removed_init_command_is_not_a_compatibility_alias(capsys) -> None:
    assert main(["init"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "invalid_input" in captured.err
    assert "invalid choice: 'init'" in captured.err

    assert main(["init", "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["command"] == "init"
    assert payload["error"]["code"] == "invalid_input"
