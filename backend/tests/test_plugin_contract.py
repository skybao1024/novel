from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "codex-novel"
MEMORY_SKILL_ROOT = PLUGIN_ROOT / "skills" / "novel-memory"
CREATION_SKILLS = {
    "novel-bootstrap": (
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


def test_plugin_manifest_and_repo_marketplace_are_installable_contracts() -> None:
    manifest = json.loads(
        (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    marketplace = json.loads(
        (REPOSITORY_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
    )

    assert manifest["name"] == "codex-novel"
    assert manifest["version"] == "0.4.0"
    assert manifest["skills"] == "./skills/"
    assert "publishes immutable Draft revisions" in manifest["interface"]["longDescription"]
    assert "compatib" not in manifest["interface"]["longDescription"].lower()
    assert "explicit project and digest boundaries" in manifest["interface"]["defaultPrompt"][0]
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
        assert frontmatter["name"] == skill_name
        assert "Use when" in frontmatter["description"]
        assert "[TODO:" not in content
        assert "directly" in body
        for phrase in required_phrases:
            assert phrase in body
        assert {path.name for path in skill_root.iterdir()} == {"SKILL.md", "agents"}
        metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        assert f"${skill_name}" in metadata


def _frontmatter(content: str) -> tuple[dict[str, str], str]:
    assert content.startswith("---\n")
    metadata_text, body = content[4:].split("\n---\n", maxsplit=1)
    metadata: dict[str, str] = {}
    for line in metadata_text.splitlines():
        key, value = line.split(":", maxsplit=1)
        metadata[key.strip()] = value.strip()
    assert set(metadata) == {"name", "description"}
    return metadata, body
