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
        "session revision-source",
        "--revise-chapter-id",
        "draft save",
        "draft entity-candidates",
        "review save",
        "--session-id",
    ),
    "novel-publish": (
        "publish prepare",
        "--chapter-trace",
        "publish approve",
        "publish recover",
        "approval_digest",
    ),
    "novel-trace-backfill": (
        "trace-backfill source",
        "trace-backfill entity-line",
        "trace-backfill prepare",
        "trace-backfill approve",
        "trace-backfill recover",
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
PROJECT_WORKSPACE_PHRASES = (
    "working directory for every project-bound",
    "<root>/candidates/",
    "parent workspace",
    "project top level",
    "non-authoritative staging",
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
    assert "keeps staging inputs contained inside that project" in long_description
    assert "surfaces exact publication approval" in long_description
    assert "backfills missing historical Traces" in long_description
    assert "compatib" not in long_description.lower()
    assert "concise plan" in default_prompt
    assert "emotionally alive viewpoint prose" in default_prompt
    assert "exact approval boundaries" in default_prompt
    assert len(default_prompt) <= 128
    assert "causal-and-emotional plan" in long_description
    assert "emotional truth, lived viewpoint, meaningful setting" in long_description
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
    assert "memory volumes" in body
    assert "memory chapters --volume-id" in body
    assert "memory search-summaries" in body
    assert "memory read-chapter" in body
    assert "memory entity-line" in body
    assert "candidate location only" in body
    assert "Never query SQLite" in body
    assert "Never infer that missing or stale summaries" in body
    assert "Never use a unique, exact, fuzzy, or recent name match" in body
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
        for phrase in PROJECT_WORKSPACE_PHRASES:
            assert phrase in normalized_body
        expected_entries = {"SKILL.md", "agents"}
        if skill_name == "novel-bootstrap":
            expected_entries.update({"assets", "scripts"})
        if skill_name == "novel-writing":
            expected_entries.add("references")
        assert {path.name for path in skill_root.iterdir()} == expected_entries
        metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        assert f"${skill_name}" in metadata


def test_bootstrap_does_not_require_a_restart_to_activate_project_guidance() -> None:
    content = (BOOTSTRAP_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "Immediately read the created file" in content
    assert "guidance applies to future Codex runs" not in content


def test_bootstrap_requires_author_approved_opening_voice_calibration() -> None:
    content = (BOOTSTRAP_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    normalized_content = " ".join(content.split())
    metadata = (BOOTSTRAP_SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "author-approved Voice Contract" in normalized_content
    assert "what must remain clear on one continuous first read" in normalized_content
    assert "familiar, precise diction as the baseline" in normalized_content
    assert "paragraph focal hierarchy" in normalized_content
    assert "focal character's allowed direct interiority" in normalized_content
    assert "bodily response, private thought, memory, contradiction" in normalized_content
    assert "setting, sensory detail, material life, and social atmosphere" in normalized_content
    assert "positive voice anchors and sparing negative anchors" in normalized_content
    assert "Make positive anchors the primary calibration evidence" in normalized_content
    assert "lived setting, focal interiority, and relationship subtext" in normalized_content
    assert "voice-calibration/" in normalized_content
    assert "select, revise, combine, or reject them" in normalized_content
    assert "discussion artifact, not manuscript or approved Intent" in normalized_content
    assert "genre convention, generalized “human style,” or imitation of a named author" in (
        normalized_content
    )
    assert "do not leave placeholder voice rules" in normalized_content
    assert "Do not select only efficient action-and-dialogue samples" in normalized_content
    assert "rare wording, tangled syntax, compressed logic, or unclear emphasis" in (
        normalized_content
    )
    assert "$novel-bootstrap" in metadata
    assert "calibrate an author-approved Voice Contract" in metadata
    assert "lived viewpoint, emotional movement, meaningful setting" in metadata
    assert "positive prose anchors" in metadata
    assert "prepare its exact Intent Diff for approval" in metadata


def test_writing_skill_requires_exact_predecessor_chapter_before_drafting() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "novel-writing"
    content = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    normalized_content = " ".join(content.split())
    metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "### Continuity floor" in content
    assert "Before drafting prose or saving the first Draft Revision in each Writing Session" in (
        normalized_content
    )
    assert "`continuity_volume_id` and `continuity_chapter_ids`" in normalized_content
    assert "single immediately preceding approved Chapter" in normalized_content
    assert "Read that Chapter exactly with `memory read-chapter`" in normalized_content
    assert "even when the same prose was read earlier in this Codex task" in normalized_content
    assert "`session continuity-status --session-id <id>`" in normalized_content
    assert "require `satisfied: true`" in normalized_content
    assert "remembered model context" in normalized_content
    assert "another Session's `retrieved_sources`" in normalized_content
    assert "When the target opens a new Volume" in normalized_content
    assert "preceding Volume Summary" in normalized_content
    assert "action, dialogue exchange, emotional beat" in normalized_content
    assert "Volume Summary → Chapter Summary → stable IDs → exact approved prose" in (
        normalized_content
    )
    assert "Do not delegate the required exact reads" in normalized_content
    assert "sub-agent that may receive partial conversation context" in normalized_content
    assert "Application mechanically gates `draft save`" in normalized_content
    assert "broader query count" in normalized_content
    assert "`required_chapter_heading` exactly as the Draft's first line" in normalized_content
    assert "Do not translate, restyle, renumber, or replace its spacing" in normalized_content
    assert "rejects a missing or different required heading" in normalized_content
    assert "## Entity resolution and Chapter Trace" in content
    assert "`draft entity-candidates`" in normalized_content
    assert "`memory entity-line --session-id <id> --entity-id <id>`" in normalized_content
    assert "candidate, never an identity decision" in normalized_content
    assert "`resolved_existing`, `resolved_new`, `anonymous`, `ignored`, or `ambiguous`" in (
        normalized_content
    )
    assert "requires every mechanically returned candidate to be covered" in normalized_content
    assert "Never choose the first, unique, nearest, or fuzzy string hit" in normalized_content
    assert "partial-context sub-agent report cannot substitute" in normalized_content
    assert "recover exact history" in metadata
    assert "recover exact history" in metadata
    assert "concise causal-and-emotional Chapter plan" in metadata
    assert "emotionally alive viewpoint prose with meaningful setting" in metadata
    assert "separate confirmation and publication boundaries" in metadata


def test_writing_skill_disambiguates_chapter_insertion_boundaries() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "novel-writing"
    content = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    normalized_content = " ".join(content.split())

    assert "`--before-chapter-id <previous-chapter-id>`" in normalized_content
    assert "append after the last approved Chapter" in normalized_content
    assert "`--after-chapter-id <next-chapter-id>`" in normalized_content
    assert "insert before the first approved Chapter" in normalized_content
    assert (
        "`--before-chapter-id <chapter-a-id> --after-chapter-id <chapter-b-id>`"
        in normalized_content
    )
    assert "Never translate “write after Chapter A” into" in normalized_content
    assert "Chapter A is the target's previous Chapter" in normalized_content
    assert "verify that the returned `before_chapter_id` and `after_chapter_id`" in (
        normalized_content
    )
    assert "Do not proceed with a Session whose saved boundary differs" in normalized_content


def test_writing_skill_balances_clarity_with_lived_emotional_prose() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "novel-writing"
    content = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    normalized_content = " ".join(content.split())
    metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "## Governing writing standard" in content
    assert "### Co-equal creative foundations" in content
    assert "causal coherence, first-pass narrative clarity, emotional truth" in normalized_content
    assert "lived viewpoint are co-equal creative foundations" in normalized_content
    assert "what is happening now" in normalized_content
    assert (
        "why each character, limited to what that character knows and wants" in normalized_content
    )
    assert "creates the next material condition" in normalized_content
    assert "emotionally inert, set in an interchangeable void" in normalized_content
    assert "plot efficiency cannot compensate for absent lived experience" in normalized_content
    assert "mystery with missing causal information" in normalized_content

    assert "### Project-specific voice" in content
    assert "Writing Rules, Creative Brief, exact approved prose" in normalized_content
    assert "generic “good literary prose” or generalized “human style”" in normalized_content
    assert "author-approved Voice Contract from Writing Rules" in normalized_content
    assert "$novel-bootstrap" in normalized_content

    assert "### Draft from causality and lived experience" in content
    assert "confirmed plan's causal and emotional spine" in normalized_content
    assert "without converting the plan into a checklist" in normalized_content
    assert "Atmosphere, silence, sensory detail, bodily response, and interior thought" in (
        normalized_content
    )
    assert "Remove only detachable decoration" in normalized_content
    assert "structure, not merely the vocabulary, changed" in normalized_content
    assert "Prefer familiar, precise wording when it carries the meaning" in normalized_content
    assert "Give each paragraph a clear focal center" in normalized_content
    assert "allowing action, perception, memory, and emotion to coexist" in normalized_content
    assert "slow down for material conflict" in normalized_content
    assert "thesis → elaboration → thematic-summary scaffolding" in normalized_content
    assert "Do not impose a universal sentence-length limit" in normalized_content

    assert "### Compact diagnostic tests" in content
    for test_name in (
        "**Causal link:**",
        "**Knowledge and behavior:**",
        "**First read:**",
        "**POV and dialogue:**",
        "**Lived interiority:**",
        "**Place and atmosphere:**",
        "**Emotional movement:**",
        "**Rhetorical substitution:**",
    ):
        assert test_name in content

    assert "### Ordered narrative review" in content
    assert "do not treat later literary dimensions as optional polish" in normalized_content
    for review_name in (
        "**Plan and continuity:**",
        "**Causal coherence:**",
        "**First-pass narrative clarity:**",
        "**Human behavior and lived viewpoint:**",
        "**Emotional and relationship movement:**",
        "**Place and atmosphere:**",
        "**Project-specific voice:**",
        "**AI-pattern regression:**",
    ):
        assert review_name in content
    assert "Keep the Review conclusion compact" in normalized_content
    assert "Do not emit a ceremonial battery of `passed` labels" in normalized_content
    assert "let checklist completion substitute for literary judgment" in normalized_content

    assert "### Reviewer restraint and AI-pattern review" in content
    assert "diagnostic role, not a second prose generator" in normalized_content
    assert "Absence is also a material failure" in normalized_content
    assert "focal character has no inner life" in normalized_content
    assert "setting is an interchangeable void" in normalized_content
    assert "viewpoint-grounded body, thought, memory, environment" in normalized_content
    assert "a generic pattern was merely exchanged for another" in normalized_content
    assert "Judge AI-like prose by causality, viewpoint" in normalized_content
    assert "`opening voice basis: established`" in normalized_content
    assert "`opening voice basis: missing`" in normalized_content
    assert "noisy external observation" in normalized_content
    assert "never as the writing objective" in normalized_content

    assert "concise causal-and-emotional Chapter plan" in metadata
    assert "clear and emotionally alive viewpoint prose" in metadata
    assert "meaningful setting" in metadata


def test_writing_skill_prefers_scene_evidence_over_rhetorical_expansion() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "novel-writing"
    content = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    normalized_content = " ".join(content.split())
    calibration_path = skill_root / "references" / "scene-evidence-calibration.md"
    calibration = calibration_path.read_text(encoding="utf-8")
    normalized_calibration = " ".join(calibration.split())

    assert "[Scene-evidence calibration](references/scene-evidence-calibration.md)" in content
    assert "Before drafting or reviewing Chinese prose in the current task" in normalized_content
    assert "Use all three labeled examples as a contrast set" in normalized_content
    assert "learn structure without copying wording" in normalized_content

    assert "## Example 1 — reject: confirmed AI" in calibration
    assert "足足有七百多个日夜" in calibration
    assert "balanced “long/not long, short/not short” exposition" in normalized_calibration
    assert "## Example 2 — reject or rebuild: suspected AI" in calibration
    assert "幼时我骑在他的肩头" in calibration
    assert "generic childhood montage" in normalized_calibration
    assert "## Example 3 — positive calibration: human-authored" in calibration
    assert "他用两手攀着上面，两脚再向上缩" in calibration
    assert "exact spatial problem and a visible action sequence" in normalized_calibration
    assert "Read all three examples before drafting" in normalized_calibration
    assert "not detector ground truth" in normalized_calibration
    assert "Do not copy the father, railway, oranges" in normalized_calibration

    assert "symmetrical exposition" in normalized_calibration
    assert "counted-time amplification" in normalized_calibration
    assert "stock weather" in normalized_calibration.lower()
    assert "approved history or a present trigger makes it specific" in normalized_calibration
    assert "functional repetition" in normalized_calibration
    assert "**Scene evidence and restraint:**" in content
    assert "remove only the redundant explanation" in normalized_content
    assert "stock sentimental memory" in normalized_content


def test_writing_skill_enforces_author_prohibited_chinese_constructions() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "novel-writing"
    content = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    normalized_content = " ".join(content.split())
    constraints_path = skill_root / "references" / "chinese-prose-prohibited-constructions.md"
    constraints = constraints_path.read_text(encoding="utf-8")
    normalized_constraints = " ".join(constraints.split())

    assert (
        "[Chinese prose prohibited constructions]"
        "(references/chinese-prose-prohibited-constructions.md)" in content
    )
    assert "Apply every author-maintained prohibited construction" in normalized_content
    assert "**Prohibited Chinese constructions:**" in content
    assert "author-maintained prohibited-construction list exactly" in normalized_content
    assert "Do not recommend `ready` while newly drafted or revised prose contains" in (
        normalized_content
    )

    assert "## 1. Sentence-opening `……的时候，……`" in constraints
    assert "太阳落山的时候，他们来到了山脚下" in constraints
    assert "他们在太阳落山的时候来到了山脚下" in constraints
    assert "Begin with the actor, action, change" in normalized_constraints
    assert "## 2. Paired `没有……只……` contrast" in constraints
    assert "`没有 A，只/只是/只有 B`" in constraints
    assert "`只/只是/只有 B，没有 A`" in constraints
    assert "屋里没有灯，只有窗外的月光" in constraints
    assert "他只是低头赶路，没有回头" in constraints
    assert "standalone `只`, `只是`, `只有`, or `没有` is not automatically" in (
        normalized_constraints
    )
    assert "swapping the two halves" in normalized_constraints
    assert "splitting them into adjacent sentences" in normalized_constraints


def test_writing_skill_confirms_plans_and_controls_chapter_scope() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "novel-writing"
    content = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    normalized_content = " ".join(content.split())
    metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
    manifest = (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")

    assert "## Chapter plan and author confirmation" in content
    assert "author-visible" in normalized_content
    assert "discussion artifact, not manuscript, approved Intent, Canon" in normalized_content
    assert "materially shorter than the prose it enables" in normalized_content
    assert "Do not create hidden subchapter or Scene cards" in normalized_content
    assert "build exhaustive role tables" in normalized_content
    assert "disguise a prose implementation specification as planning" in normalized_content
    assert "causal and emotional spine" in normalized_content
    assert "Leave room for the Writer to discover local blocking" in normalized_content
    assert "sensory emphasis, interior response, and relationship subtext" in normalized_content
    assert "Show the exact plan revision to the author" in normalized_content
    assert "changes an approved Chapter turn, sequence, decisive choice" in normalized_content
    assert "use `$novel-bootstrap` to prepare, inspect, approve, and apply an Intent Revision" in (
        normalized_content
    )
    assert "Reacquire Creation Context after apply" in normalized_content
    assert "explicit confirmation of the exact aligned plan revision opens prose drafting" in (
        normalized_content
    )
    assert "does not approve an Intent Revision or Publication" in normalized_content
    assert "stop, revise the plan" in normalized_content

    assert "## Chapter scope" in content
    assert "one complete reader-facing Chapter" in normalized_content
    assert "no formal subchapter" in normalized_content
    assert "approved Writing Rules and Current Outline" in normalized_content
    assert "never install a universal word-count target" in normalized_content
    assert "selected project's Chapter budget and counting convention" in normalized_content
    assert "count the exact Draft" in normalized_content
    assert "one continuous action unit and one explainable exit change" in normalized_content
    assert "ending can move unchanged to another Chapter" in normalized_content
    assert "Compression must preserve action, perception" in normalized_content
    assert "not Application gates" in normalized_content

    assert "concise causal-and-emotional Chapter plan" in metadata
    assert "separate confirmation and publication boundaries" in metadata
    assert "emotionally alive Chapters" in manifest
    assert "causal-and-emotional plan" in manifest
    assert "emotional truth, lived viewpoint, meaningful setting" in manifest


def test_writing_and_publish_skills_control_approved_chapter_revisions() -> None:
    writing_root = PLUGIN_ROOT / "skills" / "novel-writing"
    writing = " ".join((writing_root / "SKILL.md").read_text(encoding="utf-8").split())
    writing_metadata = (writing_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
    publish_root = PLUGIN_ROOT / "skills" / "novel-publish"
    publishing = " ".join((publish_root / "SKILL.md").read_text(encoding="utf-8").split())
    publishing_metadata = (publish_root / "agents" / "openai.yaml").read_text(encoding="utf-8")

    assert "`--revise-chapter-id`" in writing
    assert "Do not pass StoryTime, Volume, insertion-boundary, POV, or location overrides" in (
        writing
    )
    assert "`session revision-source --session-id <id>`" in writing
    assert "ordinary history commands still cannot read the target or later prose" in writing
    assert "`satisfied: true` also requires the exact `revision-source` read" in writing
    assert "old formal prose → candidate prose, never `/dev/null` → candidate" in writing
    assert "Chapter/Document/Volume IDs and Narrative Order remain unchanged" in writing
    assert "recover exact history" in writing_metadata
    assert "review the exact Draft" in writing_metadata

    assert "`base_document_revision`" in publishing
    assert "`mode=revise`" in publishing
    assert "old formal manuscript → candidate manuscript Diff" in publishing
    assert "Chapter Summary, Volume Summary, and Chapter Trace Diffs" in publishing
    assert "Any third revision is a conflict" in publishing
    assert "same-identity revised Chapter publication" in publishing_metadata


def test_ready_review_confirms_exact_draft_before_derived_publication_work() -> None:
    writing_root = PLUGIN_ROOT / "skills" / "novel-writing"
    writing = " ".join((writing_root / "SKILL.md").read_text(encoding="utf-8").split())
    writing_metadata = (writing_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
    publishing = " ".join(
        (PLUGIN_ROOT / "skills" / "novel-publish" / "SKILL.md").read_text(encoding="utf-8").split()
    )

    assert "## Exact Draft author confirmation" in writing
    assert "`draft show --session-id <id> --draft-revision <revision>`" in writing
    assert "Present the exact Draft revision, complete prose" in writing
    assert "Stop and wait for the author's response" in writing
    assert "Before this confirmation, do not call `draft entity-candidates`" in writing
    assert "extract people, plot, places, or clues" in writing
    assert "generate Chapter or Volume Summaries" in writing
    assert "A new Draft revision always invalidates" in writing
    assert "not an Application approval artifact" in writing
    assert "Only after the author confirms the exact Review-`ready` Draft revision" in writing
    assert writing.index("## Exact Draft author confirmation") < writing.index(
        "## Entity resolution and Chapter Trace"
    )
    assert "After the author confirms the exact Review-`ready` Draft" in writing
    assert "same Codex turn with `$novel-publish`" in writing
    assert "call `publish prepare`, then `publish inspect`" in writing
    assert "exact `publication_id`, and exact `approval_digest`" in writing
    assert "do not wait for a later “continue writing” request" in writing
    assert "Never call `publish approve` or `publish apply`" in writing
    assert "show the exact ready revision and wait for author confirmation" in writing_metadata
    assert "prepare publication digest approval" in writing_metadata

    assert "author's explicit confirmation of that same exact Review-`ready` Draft revision" in (
        publishing
    )
    assert "Review `ready` alone does not authorize Entity resolution" in publishing
    assert "complete deferred Entity resolution, Prepare, and Inspect in that same Codex turn" in (
        publishing
    )
    assert "do not defer the approval request" in publishing
    assert "cover every `draft entity-candidates` hit" in publishing
    assert "--chapter-trace <json-file>" in publishing
    assert "Mention resolutions, new Entity assignments" in publishing


def test_bootstrap_project_guidance_captures_codex_boundaries() -> None:
    guidance = (BOOTSTRAP_SKILL_ROOT / "assets" / "project-AGENTS.md").read_text(encoding="utf-8")
    normalized_guidance = " ".join(guidance.split())

    assert guidance.startswith("# Novel Project Guidance\n")
    assert "Read and verify `novel.yaml`" in guidance
    assert "Use `novel` as the only business-data interface." in guidance
    assert "Never directly edit formal `intent/`" in guidance
    assert "exact operation ID and approval digest" in guidance
    assert "missing structured Canon does not prove" in guidance
    assert "approved manuscript prose as the primary source" in guidance
    assert "project root as the working directory" in guidance
    assert "project-local `candidates/`" in guidance
    assert "first show the exact Draft revision and complete prose" in normalized_guidance
    assert "Before confirmation, do not run `draft entity-candidates`" in normalized_guidance
    assert "Any prose change creates a new Draft" in normalized_guidance
    assert "Only for an author-confirmed exact Draft revision" in normalized_guidance
    assert "After the author confirms the exact ready Draft" in normalized_guidance
    assert "prepare and inspect its Publication in the same turn" in normalized_guidance
    assert "Exact Chapter Read every `continuity_chapter_ids`" in normalized_guidance
    assert "`session continuity-status` is satisfied" in normalized_guidance
    assert "Earlier Codex context, another Session, or a sub-agent report" in normalized_guidance
    assert "continuity Review in the primary writing agent" in normalized_guidance
    assert "exact `required_chapter_heading` returned by `session context`" in normalized_guidance
    assert "as every Draft's first line" in normalized_guidance
    assert "`draft entity-candidates`" in normalized_guidance
    assert "`memory entity-line`" in normalized_guidance
    assert "no unresolved `ambiguous` Mention" in normalized_guidance
    assert "`session revision-source`" in normalized_guidance
    assert "normal continuity window must both be satisfied" in normalized_guidance
    assert (
        "keep its Chapter, Document, Volume, and Narrative Order identities" in normalized_guidance
    )
    assert "never create a duplicate Chapter" in normalized_guidance
    assert "Do not automatically merge Entity identities" in normalized_guidance
    assert "Chapter Trace and Entity resolution Diff" in normalized_guidance
    assert "`$novel-trace-backfill`" in normalized_guidance
    assert "Backfill approved Chapters one at a time" in normalized_guidance


def test_trace_backfill_skill_keeps_maintenance_outside_writing_sessions() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "novel-trace-backfill"
    content = " ".join((skill_root / "SKILL.md").read_text(encoding="utf-8").split())
    metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
    memory = " ".join((MEMORY_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").split())
    writing = " ".join(
        (PLUGIN_ROOT / "skills" / "novel-writing" / "SKILL.md").read_text(encoding="utf-8").split()
    )

    assert "one Chapter at a time in Narrative Order" in content
    assert "Never choose the first, unique, nearest, most recent, or fuzzy string hit" in content
    assert "Do not prepare while any Mention is `ambiguous`" in content
    assert "exact `backfill_id` and `approval_digest`" in content
    assert "not a Writing Session or automatic extraction job" in content
    assert "must not be used from an ordinary Writing Session" in content
    assert "allow_implicit_invocation: true" in metadata
    assert "$novel-trace-backfill" in metadata
    assert "full-history maintenance reads" in memory
    assert "explicit maintenance task" in writing


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
