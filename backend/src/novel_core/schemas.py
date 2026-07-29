"""Deterministic JSON Schema documents for public Narrative Core models."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from novel_core._base import SCHEMA_VERSION, VersionedDomainModel
from novel_core.canon import (
    Assertion,
    CanonChangeSet,
    CanonLedgerEntry,
    ChangeSetOperation,
    CharacterState,
    EventChain,
    Proposition,
    SourceRef,
)
from novel_core.chronology import StoryTime
from novel_core.creation import (
    Approval,
    BootstrapContent,
    BootstrapDraft,
    BootstrapEntityDraft,
    BootstrapEntityResolution,
    BootstrapRun,
    ContinuitySceneStatus,
    ContinuityStatus,
    CreationContext,
    DraftEntityCandidates,
    DraftEntityMatchCandidate,
    DraftRevision,
    EntityMentionDraft,
    IntentContent,
    IntentRevision,
    Publication,
    PublicationPlan,
    RetrievedSource,
    Review,
    SceneEntityOccurrenceDraft,
    SceneTraceBackfill,
    SceneTraceBackfillPlan,
    SceneTraceDraft,
    SceneTraceEntityDraft,
    WritingSession,
)
from novel_core.events import Event, EventEdge
from novel_core.identity import Entity, EntityAlias
from novel_core.navigation import (
    Chapter,
    ChapterSummary,
    EntityMention,
    SceneEntityOccurrence,
    SceneSummary,
    SceneTrace,
)
from novel_core.projects import (
    Document,
    ProjectCatalog,
    ProjectCatalogEntry,
    ProjectManifest,
    Scene,
)

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_BASE_ID = "https://novel.local/schemas"

SCHEMA_MODELS: tuple[tuple[str, type[VersionedDomainModel]], ...] = (
    ("entity.schema.json", Entity),
    ("entity-alias.schema.json", EntityAlias),
    ("project.schema.json", ProjectManifest),
    ("project-catalog-entry.schema.json", ProjectCatalogEntry),
    ("project-catalog.schema.json", ProjectCatalog),
    ("intent-content.schema.json", IntentContent),
    ("approval.schema.json", Approval),
    ("bootstrap-content.schema.json", BootstrapContent),
    ("bootstrap-draft.schema.json", BootstrapDraft),
    ("bootstrap-entity-draft.schema.json", BootstrapEntityDraft),
    ("bootstrap-entity-resolution.schema.json", BootstrapEntityResolution),
    ("bootstrap-run.schema.json", BootstrapRun),
    ("intent-revision.schema.json", IntentRevision),
    ("writing-session.schema.json", WritingSession),
    ("retrieved-source.schema.json", RetrievedSource),
    ("continuity-scene-status.schema.json", ContinuitySceneStatus),
    ("continuity-status.schema.json", ContinuityStatus),
    ("creation-context.schema.json", CreationContext),
    ("draft-revision.schema.json", DraftRevision),
    ("draft-entity-candidates.schema.json", DraftEntityCandidates),
    ("draft-entity-match-candidate.schema.json", DraftEntityMatchCandidate),
    ("entity-mention-draft.schema.json", EntityMentionDraft),
    ("scene-trace-entity-draft.schema.json", SceneTraceEntityDraft),
    ("scene-entity-occurrence-draft.schema.json", SceneEntityOccurrenceDraft),
    ("scene-trace-draft.schema.json", SceneTraceDraft),
    ("scene-trace-backfill-plan.schema.json", SceneTraceBackfillPlan),
    ("scene-trace-backfill.schema.json", SceneTraceBackfill),
    ("review.schema.json", Review),
    ("publication-plan.schema.json", PublicationPlan),
    ("publication.schema.json", Publication),
    ("document.schema.json", Document),
    ("scene.schema.json", Scene),
    ("chapter.schema.json", Chapter),
    ("scene-summary.schema.json", SceneSummary),
    ("entity-mention.schema.json", EntityMention),
    ("scene-entity-occurrence.schema.json", SceneEntityOccurrence),
    ("scene-trace.schema.json", SceneTrace),
    ("chapter-summary.schema.json", ChapterSummary),
    ("story-time.schema.json", StoryTime),
    ("source-ref.schema.json", SourceRef),
    ("proposition.schema.json", Proposition),
    ("assertion.schema.json", Assertion),
    ("event.schema.json", Event),
    ("event-edge.schema.json", EventEdge),
    ("change-set-operation.schema.json", ChangeSetOperation),
    ("canon-change-set.schema.json", CanonChangeSet),
    ("canon-ledger-entry.schema.json", CanonLedgerEntry),
    ("character-state.schema.json", CharacterState),
    ("event-chain.schema.json", EventChain),
)


def schema_document(filename: str, model: type[VersionedDomainModel]) -> dict[str, Any]:
    """Build one versioned public schema without filesystem side effects."""

    schema = model.model_json_schema(mode="validation")
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": f"{SCHEMA_BASE_ID}/{filename}",
        "x-schema-version": SCHEMA_VERSION,
        **schema,
    }


def schema_documents() -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield public schemas in a stable order."""

    for filename, model in SCHEMA_MODELS:
        yield filename, schema_document(filename, model)


def schema_json(schema: dict[str, Any]) -> str:
    """Render a schema deterministically."""

    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
