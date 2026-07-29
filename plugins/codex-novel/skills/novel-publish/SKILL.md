---
name: novel-publish
description: Prepare, inspect, explicitly approve, apply, and recover an exact Novel Scene publication including its resolved Scene Trace. Use when a Writing Session has a stable Draft Revision, Entity resolution, and Review and Codex must generate navigation summaries and optional Intent or sparse Canon changes without bypassing the author's digest approval.
---

# Novel Publish

Use `novel` as the only business-data interface. Publishing is a protected transaction, not an
implicit consequence of drafting or review.

## Project contract

Resolve the exact project root for the Writing Session, then read `<root>/AGENTS.md` when present
and follow it as the selected project's contract in the current task. Do this even when the Codex
workspace or current directory is a parent of `<root>`. Apply it only to operations bound to that
project's Manifest and Project ID. Do not ask the author to switch workspaces or start a new thread
only to activate the project contract.

## Project workspace

Use `<root>` as the working directory for every project-bound filesystem and CLI call, even when
the Codex workspace remains a parent directory. Put Codex-authored Summary and optional Canon input
files only under `<root>/candidates/writing/<session-id>/publication/`. `candidates/` is
non-authoritative staging, not Novel business data. Never scatter these inputs in the parent
workspace, directly in the project top level, or inside formal `memory/`, `canon/`, `runs/`, or
`.novel/`.

## Prepare

1. Confirm the exact open Session, Draft revision, and one or more Reviews.
2. Generate a UTF-8 Scene Summary that describes only the candidate Scene, a UTF-8 Chapter
   Summary that aggregates the Chapter, and a versioned Scene Trace Draft for the exact Draft
   revision. The Trace must cover every `draft entity-candidates` hit, include AI-found pronoun,
   title, and description Mentions, contain no `ambiguous` resolution, and link every resolved
   Mention to one Entity occurrence. Optionally prepare an approved Intent Revision ID and a
   versioned JSON array of sparse Canon Ledger records. Store all generated input files in the
   project-local publication candidate directory.
3. Call:

   ```text
   novel --project <root> publish prepare \
     --session-id <id> --draft-revision <revision> \
     --scene-summary <text-file> --chapter-summary <text-file> \
     --scene-trace <json-file> \
     --review-id <id> --json
   ```

   Add main Entity IDs, key changes, open questions, `--intent-revision-id`, or
   `--canon-records` only when they are accurate. The Application derives Summary bindings,
   Document/Scene IDs, revisions, and dependency digests.
4. Run `publish inspect --publication-id <id>`. Present the manuscript, structure, Summary, Scene
   Trace, Mention resolutions, new Entity assignments, optional Intent, Canon Diffs, Review
   conclusions, unresolved questions, exact Publication ID, and approval digest. Ask the author to
   approve that exact pair, then stop and wait.

When `$novel-writing` hands off a `ready` Review, complete Prepare and Inspect in that same Codex
turn. Do not stop after merely reporting that the Scene is ready or unpublished, and do not defer
the approval request until the author later asks to continue writing.

## Approve and apply

Call `publish approve` only after the author explicitly approves the exact
`publication_id + approval_digest`. Then call `publish apply`.

If apply returns `publication_recovery_required`, do not create or approve a replacement plan.
Report the stored Publication ID, then call `publish recover --publication-id <id>` to continue
the already approved steps. Repeat recovery only for the same immutable plan.

Never interpret “continue writing”, ordinary Draft feedback, or Review recommendation as publish
approval. Never edit manuscript, navigation memory, Intent, Ledger, transaction state, or SQLite
directly.

Do not republish an approved historical Scene only to add or correct its Scene Trace. Route that
explicit maintenance request to `$novel-trace-backfill`.

## Diagnostics

Preserve the `diagnostic_id` returned by every CLI JSON envelope. When a call fails, report its
stable error code and diagnostic ID, then run
`novel diagnostics show --diagnostic-id <id> --json` before retrying or choosing
`publish recover`. Diagnostic records are operational evidence; they do not authorize publication
and are not recovery state.
