from __future__ import annotations

import ast
import tomllib
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = BACKEND_ROOT / "src" / "novel_core"
APPLICATION_ROOT = BACKEND_ROOT / "src" / "novel_application"
ADAPTER_ROOT = BACKEND_ROOT / "src" / "novel_adapters"

FORBIDDEN_IMPORT_ROOTS = {
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "codex",
    "openai",
    "sqlite3",
    "tauri",
    "tkinter",
    "typer",
    "yaml",
}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    return roots


def test_novel_core_has_no_storage_agent_cli_or_desktop_imports() -> None:
    offenders = {
        path.relative_to(CORE_ROOT): imported_roots(path) & FORBIDDEN_IMPORT_ROOTS
        for path in CORE_ROOT.rglob("*.py")
        if imported_roots(path) & FORBIDDEN_IMPORT_ROOTS
    }
    assert offenders == {}


def test_application_does_not_import_adapters_or_sqlite() -> None:
    forbidden = {"novel_adapters", "sqlite3"}
    offenders = {
        path.relative_to(APPLICATION_ROOT): imported_roots(path) & forbidden
        for path in APPLICATION_ROOT.rglob("*.py")
        if imported_roots(path) & forbidden
    }
    assert offenders == {}


def test_runtime_dependency_surface_is_domain_only() -> None:
    pyproject = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["dependencies"] == ["pydantic>=2.12,<3"]


def test_removed_experimental_workflows_have_no_runtime_packages() -> None:
    assert {
        path.name
        for path in CORE_ROOT.iterdir()
        if path.name in {"ingest", "context", "retrieval", "writing"}
    } == set()
    assert {
        path.name
        for path in APPLICATION_ROOT.glob("*.py")
        if path.stem in {"ingest", "context", "writing"}
    } == set()
    assert not (ADAPTER_ROOT / "sqlite" / "candidates.py").exists()
