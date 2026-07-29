# Novel Project Guidance

## Project identity

- Treat this directory as one independent Novel project.
- Read and verify `novel.yaml` before starting project work.
- Bind every write to the exact Project ID and normalized project root.
- Never select a write target from a title, recent directory, or fuzzy path.
- Use this project root as the working directory for project-bound tools even when the Codex
  workspace is a parent directory.

## Workflow routing

- Use `novel` as the only business-data interface.
- Use `$novel-bootstrap` for project Bootstrap and later Intent revisions.
- Use `$novel-writing` for Scene writing, revision, and AI Review.
- Use `$novel-memory` to navigate summaries and read exact approved history.
- Use `$novel-publish` to prepare, inspect, approve, apply, or recover publication.
- Use `$novel-trace-backfill` only when the author explicitly asks to add or correct a historical
  Scene Trace.

## Data boundaries

- Never directly edit formal `intent/`, `structure/`, `manuscript/`, `memory/`,
  `canon/ledger/`, `runs/`, or `.novel/`.
- Put Codex-authored CLI input only under project-local `candidates/`, grouped by operation ID when
  available. Never scatter it in a parent workspace or directly in the project top level.
- Treat `candidates/` as non-authoritative staging; it cannot replace immutable assets in `runs/`.
- Keep discussion and comparison artifacts outside formal Intent and label them as candidates.
- Do not describe a Draft, Review, summary, or comparison artifact as approved Canon.
- Do not delete Draft, Review, Bootstrap, Intent Revision, Publication, or Trace Backfill assets
  as cache.

## Phase and approval boundaries

- When the author asks only to discuss or compare, do not write a formal Scene or publish.
- Before writing, create or resume the exact Writing Session and load its Creation Context.
- When `session context` returns `required_chapter_heading`, use that exact text as the first Draft
  line; do not improvise Chapter numbering, title text, punctuation, or spacing.
- For every publishable Draft revision, run `draft entity-candidates`, inspect uncertain candidates
  with `memory entity-line`, and submit a revision-bound Scene Trace with no unresolved
  `ambiguous` Mention.
- Treat exact, unique, fuzzy, recent, or same-name matches only as candidates. Do not automatically
  merge Entity identities. Let the Application allocate stable IDs for new re-identifiable
  Entities and keep genuinely anonymous extras anonymous.
- When a Scene Review becomes `ready`, immediately prepare and inspect its Publication in the same
  turn unless the author explicitly requested draft-only work. Show the Scene Trace and Entity
  resolution Diff, exact Publication ID, and approval digest before ending the turn.
- Treat ordinary feedback, “continue”, and approval of another revision as non-approval.
- Approve or apply Bootstrap, Intent, Publication, or Trace Backfill only when the author
  explicitly approves the exact operation ID and approval digest shown by its inspect command.
- Never use Trace Backfill full-history source reads during an ordinary Writing Session. Backfill
  approved Scenes one at a time, prefer Narrative Order, and never treat exact or unique matches
  as identity decisions.

## Creative sources

- Treat approved manuscript prose as the primary source for complete narrative history.
- Treat approved Intent as the primary source for creative direction.
- Use Chapter and Scene summaries only to locate relevant approved prose.
- Use Scene Trace occurrence lines only to locate candidate history; read exact approved prose
  before treating an identity or narrative detail as established.
- Treat the Canon Ledger as sparse long-term memory; missing structured Canon does not prove that
  an event or detail is absent from the manuscript.
- In every Writing Session, Exact Scene Read every `continuity_scene_ids` entry from
  `session context` and confirm `session continuity-status` is satisfied before drafting or saving.
  Earlier Codex context, another Session, or a sub-agent report does not substitute.
- Use summaries and stable IDs to locate any still-earlier approved prose needed for continuity.
- Keep required exact reads, target prose drafting, and continuity Review in the primary writing
  agent; use sub-agents only to help locate older candidate clues.

## Collaboration

- Communicate in the author's requested language.
- Clearly distinguish discussion candidates, Drafts, Reviews, approved Intent, and published prose.
- Make minimal reversible assumptions for small undefined details.
- Stop for author direction before changing the premise, major character fate, ending, or another
  locked creative direction.
