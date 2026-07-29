from __future__ import annotations

import json
from pathlib import Path

from novel_core import SCHEMA_VERSION
from novel_core.schemas import schema_documents, schema_json

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = REPOSITORY_ROOT / "schemas"
EXPECTED_SCHEMA_FILES = {
    "approval.schema.json",
    "assertion.schema.json",
    "bootstrap-content.schema.json",
    "bootstrap-draft.schema.json",
    "bootstrap-entity-draft.schema.json",
    "bootstrap-entity-resolution.schema.json",
    "bootstrap-run.schema.json",
    "canon-change-set.schema.json",
    "canon-ledger-entry.schema.json",
    "chapter-summary.schema.json",
    "chapter.schema.json",
    "character-state.schema.json",
    "change-set-operation.schema.json",
    "continuity-scene-status.schema.json",
    "continuity-status.schema.json",
    "creation-context.schema.json",
    "document.schema.json",
    "draft-revision.schema.json",
    "draft-entity-candidates.schema.json",
    "draft-entity-match-candidate.schema.json",
    "entity-alias.schema.json",
    "entity-mention-draft.schema.json",
    "entity-mention.schema.json",
    "entity.schema.json",
    "event-edge.schema.json",
    "event.schema.json",
    "event-chain.schema.json",
    "intent-content.schema.json",
    "intent-revision.schema.json",
    "proposition.schema.json",
    "project.schema.json",
    "project-catalog-entry.schema.json",
    "project-catalog.schema.json",
    "publication-plan.schema.json",
    "publication.schema.json",
    "retrieved-source.schema.json",
    "review.schema.json",
    "scene.schema.json",
    "scene-entity-occurrence-draft.schema.json",
    "scene-entity-occurrence.schema.json",
    "scene-summary.schema.json",
    "scene-trace-draft.schema.json",
    "scene-trace-backfill-plan.schema.json",
    "scene-trace-backfill.schema.json",
    "scene-trace-entity-draft.schema.json",
    "scene-trace.schema.json",
    "source-ref.schema.json",
    "story-time.schema.json",
    "writing-session.schema.json",
}


def test_checked_in_schemas_are_current_and_explicitly_versioned() -> None:
    documents = tuple(schema_documents())
    assert {filename for filename, _ in documents} == EXPECTED_SCHEMA_FILES
    assert {path.name for path in SCHEMA_ROOT.glob("*.schema.json")} == EXPECTED_SCHEMA_FILES

    for filename, schema in documents:
        checked_in = SCHEMA_ROOT / filename
        assert checked_in.read_text(encoding="utf-8") == schema_json(schema)
        assert schema["x-schema-version"] == SCHEMA_VERSION
        assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
        assert schema["properties"]["schema_version"]["default"] == SCHEMA_VERSION


def test_schema_files_are_deterministic_json() -> None:
    for path in sorted(SCHEMA_ROOT.glob("*.schema.json")):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        canonical_pretty = (
            json.dumps(
                loaded,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        assert path.read_text(encoding="utf-8") == canonical_pretty
