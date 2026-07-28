from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "codex-novel"
MEMORY_SKILL_ROOT = PLUGIN_ROOT / "skills" / "novel-memory"
BOOTSTRAP_SKILL_ROOT = PLUGIN_ROOT / "skills" / "novel-bootstrap"
CREATION_SKILLS = {
    "novel-bootstrap": (
        "project create",
        "install_project_agents.py",
        "bootstrap start",
        "bootstrap approve",
        "intent prepare",
        "Intent Canon",
    ),
    "novel-writing": (
        "session context",
        "draft save",
        "review save",
        "--session-id",
    ),
    "novel-publish": (
        "publish prepare",
        "publish approve",
        "publish recover",
        "approval_digest",
    ),
}
PROJECT_CONTRACT_PHRASES = (
    "<root>/AGENTS.md",
    "current task",
    "Codex workspace",
    "current directory is a parent",
    "only to operations bound to that project's",
    "switch workspaces or start a new thread",
)
DIAGNOSTIC_PHRASES = (
    "diagnostic_id",
    "diagnostics show --diagnostic-id",
    "operational evidence",
)


def test_plugin_manifest_and_repo_marketplace_are_installable_contracts() -> None:
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    marketplace = json.loads(
        (REPOSITORY_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
    )
    long_description = manifest["interface"]["longDescription"]
    default_prompt = manifest["interface"]["defaultPrompt"][0]

    assert manifest["name"] == "codex-novel"
    assert manifest["version"].split("+", maxsplit=1)[0] == "0.4.0"
    assert manifest["skills"] == "./skills/"
    assert "loads the selected project's Codex boundaries in place" in long_description
    assert "publishes immutable Draft revisions" in long_description
    assert "compatib" not in long_description.lower()
    assert "load the selected project contract in place" in default_prompt
    assert "explicit project and digest boundaries" in default_prompt
    assert "mcpServers" not in manifest
    assert "apps" not in manifest
    assert "hooks" not in manifest

    entry = marketplace["plugins"][0]
    assert entry["name"] == manifest["name"]
    assert entry["source"] == {
        "source": "local",
        "path": "./plugins/codex-novel",
    }
    assert entry["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }


def test_plugin_exposes_creation_loop_and_ai_first_memory_skills() -> None:
    skill_directories = {path.name for path in (PLUGIN_ROOT / "skills").iterdir() if path.is_dir()}
    assert skill_directories == {"novel-memory", *CREATION_SKILLS}

    content = (MEMORY_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    frontmatter, body = _frontmatter(content)
    normalized_body = " ".join(body.split())

    assert frontmatter["name"] == "novel-memory"
    assert "AI-first" in frontmatter["description"]
    assert "legacy" not in content.lower()
    assert "[TODO:" not in content
    assert "memory chapters" in body
    assert "memory scenes --chapter-id" in body
    assert "memory search-summaries" in body
    assert "memory read-scene" in body
    assert "candidate location only" in body
    assert "Never query SQLite" in body
    assert "Never infer that missing or stale summaries" in body
    for phrase in PROJECT_CONTRACT_PHRASES:
        assert phrase in normalized_body
    for phrase in DIAGNOSTIC_PHRASES:
        assert phrase in normalized_body

    assert {path.name for path in MEMORY_SKILL_ROOT.iterdir()} == {
        "SKILL.md",
        "agents",
    }
    metadata = (MEMORY_SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert 'display_name: "Novel Memory"' in metadata
    assert "allow_implicit_invocation: true" in metadata
    assert "$novel-memory" in metadata

    for skill_name, required_phrases in CREATION_SKILLS.items():
        skill_root = PLUGIN_ROOT / "skills" / skill_name
        content = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        frontmatter, body = _frontmatter(content)
        normalized_body = " ".join(body.split())
        assert frontmatter["name"] == skill_name
        assert "Use when" in frontmatter["description"]
        assert "[TODO:" not in content
        assert "directly" in body
        for phrase in required_phrases:
            assert phrase in body
        for phrase in PROJECT_CONTRACT_PHRASES:
            assert phrase in normalized_body
        for phrase in DIAGNOSTIC_PHRASES:
            assert phrase in normalized_body
        expected_entries = {"SKILL.md", "agents"}
        if skill_name == "novel-bootstrap":
            expected_entries.update({"assets", "scripts"})
        assert {path.name for path in skill_root.iterdir()} == expected_entries
        metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        assert f"${skill_name}" in metadata


def test_bootstrap_does_not_require_a_restart_to_activate_project_guidance() -> None:
    content = (BOOTSTRAP_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "Immediately read the created file" in content
    assert "guidance applies to future Codex runs" not in content


def test_writing_skill_requires_exact_adjacent_prose_before_drafting() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "novel-writing"
    content = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    normalized_content = " ".join(content.split())
    metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "### Continuity floor" in content
    assert "Before drafting prose or saving the first Draft Revision" in normalized_content
    assert "If `before_scene_id` exists, always" in normalized_content
    assert "immediately preceding approved Scene" in normalized_content
    assert "Neither its Scene Summary" in normalized_content
    assert "Do not draft until this required exact read succeeds" in normalized_content
    assert "When the target opens a new Chapter" in normalized_content
    assert "preceding Chapter Summary" in normalized_content
    assert "final approved Scene in full" in normalized_content
    assert "action, dialogue exchange, emotional beat" in normalized_content
    assert "first Scene in Narrative Order" in normalized_content
    assert "Plugin writing rule, not an Application query-count gate" in normalized_content
    assert "recover adjacent approved prose" in metadata


def test_bootstrap_project_guidance_captures_codex_boundaries() -> None:
    guidance = (BOOTSTRAP_SKILL_ROOT / "assets" / "project-AGENTS.md").read_text(encoding="utf-8")

    assert guidance.startswith("# Novel Project Guidance\n")
    assert "Read and verify `novel.yaml`" in guidance
    assert "Use `novel` as the only business-data interface." in guidance
    assert "Never directly edit formal `intent/`" in guidance
    assert "exact operation ID and approval digest" in guidance
    assert "missing structured Canon does not prove" in guidance
    assert "approved manuscript prose as the primary source" in guidance


def test_project_guidance_installer_is_idempotent_and_never_overwrites(
    tmp_path: Path,
) -> None:
    project = tmp_path / "story"
    project.mkdir()
    (project / "novel.yaml").write_text("schema_version: 1.0.0\n", encoding="utf-8")

    created = _install_project_guidance(project)
    destination = project / "AGENTS.md"
    template = BOOTSTRAP_SKILL_ROOT / "assets" / "project-AGENTS.md"
    assert created.returncode == 0
    assert created.stdout.startswith("created:")
    assert destination.read_bytes() == template.read_bytes()

    unchanged = _install_project_guidance(project)
    assert unchanged.returncode == 0
    assert unchanged.stdout.startswith("unchanged:")

    destination.write_text("# Author guidance\n", encoding="utf-8")
    refused = _install_project_guidance(project)
    assert refused.returncode == 3
    assert "refusing to overwrite existing guidance" in refused.stderr
    assert destination.read_text(encoding="utf-8") == "# Author guidance\n"


def test_project_guidance_installer_requires_a_novel_manifest(tmp_path: Path) -> None:
    project = tmp_path / "not-a-novel"
    project.mkdir()

    result = _install_project_guidance(project)

    assert result.returncode == 2
    assert "cannot find Novel manifest" in result.stderr
    assert not (project / "AGENTS.md").exists()


def _install_project_guidance(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(BOOTSTRAP_SKILL_ROOT / "scripts" / "install_project_agents.py"),
            "--project",
            str(project),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _frontmatter(content: str) -> tuple[dict[str, str], str]:
    assert content.startswith("---\n")
    metadata_text, body = content[4:].split("\n---\n", maxsplit=1)
    metadata: dict[str, str] = {}
    for line in metadata_text.splitlines():
        key, value = line.split(":", maxsplit=1)
        metadata[key.strip()] = value.strip()
    assert set(metadata) == {"name", "description"}
    return metadata, body
