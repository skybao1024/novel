from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from novel_adapters.filesystem import FilesystemDiagnosticLog
from novel_cli.main import EXIT_OK, EXIT_PROJECT, PROTOCOL_VERSION, main


def test_cli_exposes_only_current_project_canon_and_memory_commands(capsys) -> None:
    assert main(["--help"]) == EXIT_OK
    help_text = capsys.readouterr().out

    for command in (
        "version",
        "doctor",
        "diagnostics",
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


def test_version_and_schema_commands_have_one_json_document(
    tmp_path: Path,
    capsys,
) -> None:
    catalog = tmp_path / "application-data"
    assert main(["--catalog-dir", str(catalog), "version", "--json"]) == EXIT_OK
    version_payload = json.loads(capsys.readouterr().out)
    UUID(version_payload.pop("diagnostic_id"))
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

    assert (
        main(
            [
                "--catalog-dir",
                str(catalog),
                "schema",
                "show",
                "scene-summary",
                "--json",
            ]
        )
        == EXIT_OK
    )
    schema_payload = json.loads(capsys.readouterr().out)
    UUID(schema_payload["diagnostic_id"])
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
    diagnostic, warnings = FilesystemDiagnosticLog(catalog).show(UUID(doctor["diagnostic_id"]))
    assert warnings == ()
    assert diagnostic.project_id == UUID(initialized["data"]["project_id"])


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
    UUID(payload["diagnostic_id"])


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
    UUID(payload["diagnostic_id"])


def test_diagnostics_list_and_show_correlate_exact_cli_call(
    tmp_path: Path,
    capsys,
) -> None:
    catalog = tmp_path / "application-data"
    assert main(["--catalog-dir", str(catalog), "version", "--json"]) == EXIT_OK
    invoked = json.loads(capsys.readouterr().out)
    diagnostic_id = UUID(invoked["diagnostic_id"])

    assert (
        main(
            [
                "--catalog-dir",
                str(catalog),
                "diagnostics",
                "list",
                "--outcome",
                "success",
                "--json",
            ]
        )
        == EXIT_OK
    )
    listed = json.loads(capsys.readouterr().out)
    records = listed["data"]["records"]
    assert [record["diagnostic_id"] for record in records] == [str(diagnostic_id)]
    assert records[0]["command"] == "version"
    assert records[0]["phase"] == "completed"
    assert "traceback" not in records[0]

    assert (
        main(
            [
                "--catalog-dir",
                str(catalog),
                "diagnostics",
                "show",
                "--diagnostic-id",
                str(diagnostic_id),
                "--json",
            ]
        )
        == EXIT_OK
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["data"]["diagnostic_id"] == str(diagnostic_id)
    assert shown["data"]["outcome"] == "success"
    assert shown["data"]["exit_code"] == EXIT_OK


def test_internal_error_has_persisted_traceback(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    catalog = tmp_path / "application-data"

    def fail_dispatch(*_args, **_kwargs):
        message = "synthetic diagnostic failure"
        raise RuntimeError(message)

    monkeypatch.setattr("novel_cli.main._dispatch", fail_dispatch)
    assert main(["--catalog-dir", str(catalog), "version", "--json"]) == 10
    failed = json.loads(capsys.readouterr().out)

    record, warnings = FilesystemDiagnosticLog(catalog).show(UUID(failed["diagnostic_id"]))
    assert warnings == ()
    assert record.error_code == "internal_error"
    assert record.error_type == "RuntimeError"
    assert "fail_dispatch" in (record.traceback or "")
    assert "RuntimeError" in (record.traceback or "")
    assert "synthetic diagnostic failure" not in (record.traceback or "")


def test_diagnostic_log_does_not_store_full_cli_arguments(
    tmp_path: Path,
    capsys,
) -> None:
    catalog = tmp_path / "application-data"
    secret = "这是一段不应进入诊断日志的正文"
    assert (
        main(
            [
                "--catalog-dir",
                str(catalog),
                "review",
                "save",
                "--conclusion",
                secret,
                "--json",
            ]
        )
        == 2
    )
    capsys.readouterr()
    logged = b"".join(path.read_bytes() for path in (catalog / "diagnostics").glob("*.jsonl"))
    assert secret.encode("utf-8") not in logged


def test_diagnostic_write_failure_does_not_change_successful_business_result(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    catalog = tmp_path / "application-data"

    def fail_append(*_args, **_kwargs):
        raise OSError("synthetic log write failure")

    monkeypatch.setattr(FilesystemDiagnosticLog, "append", fail_append)
    assert main(["--catalog-dir", str(catalog), "version", "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert "diagnostic_id" not in payload
    assert payload["warnings"] == ["diagnostic log could not be written"]

    assert main(["--catalog-dir", str(catalog), "init", "--json"]) == 2
    failed = json.loads(capsys.readouterr().out)
    assert failed["error"]["code"] == "invalid_input"
    assert "diagnostic_id" not in failed
    assert failed["warnings"] == ["diagnostic log could not be written"]
