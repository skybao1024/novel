---
name: novel-publish
description: Prepare, inspect, explicitly approve, apply, and recover an exact Novel Chapter publication including its resolved Chapter Trace. Use when the author has confirmed an exact Review-ready Draft Revision and Codex must perform deferred Entity resolution, generate navigation summaries and optional Intent or sparse Canon changes, and request a separate publication digest approval.
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

1. Confirm the exact open Session, Draft revision, one or more Reviews, and the author's explicit
   confirmation of that same exact Review-`ready` Draft revision. If the confirmation is not
   available in the current task context, return to `$novel-writing`, show the Draft, and wait;
   Review `ready` alone does not authorize Entity resolution or publication preparation.
   If the Session `mode` is `revise`, confirm its `base_document_revision`, exact revision-source
   retrieval, and unchanged Chapter, Document, Volume, and Narrative Order identities.
2. Call `draft entity-candidates` for that exact confirmed Draft revision, resolve every returned
   match and AI-found name, pronoun, title, or description Mention under the Writing Session
   boundary, and inspect uncertain existing identities with `memory entity-line`. Do not continue
   while any Mention remains `ambiguous`.
3. Generate a UTF-8 Chapter Summary that describes only the candidate Chapter, a UTF-8 Volume
   Summary that aggregates the Volume, and a versioned Chapter Trace Draft for the exact Draft
   revision. The Trace must cover every `draft entity-candidates` hit, include AI-found pronoun,
   title, and description Mentions, contain no `ambiguous` resolution, and link every resolved
   Mention to one Entity occurrence. Optionally prepare an approved Intent Revision ID and a
   versioned JSON array of sparse Canon Ledger records. Store all generated input files in the
   project-local publication candidate directory.
4. Call:

   ```text
   novel --project <root> publish prepare \
     --session-id <id> --draft-revision <revision> \
     --chapter-summary <text-file> --volume-summary <text-file> \
     --chapter-trace <json-file> \
     --review-id <id> --json
   ```

   Add main Entity IDs, key changes, open questions, `--intent-revision-id`, or
   `--canon-records` only when they are accurate. The Application derives Summary bindings,
   Document/Chapter IDs, revisions, and dependency digests.
5. Run `publish inspect --publication-id <id>`. Present the manuscript, structure, Summary, Chapter
   Trace, Mention resolutions, new Entity assignments, optional Intent, Canon Diffs, Review
   conclusions, unresolved questions, exact Publication ID, and approval digest. Ask the author to
   approve that exact pair, then stop and wait.

For a revision Publication, require the inspect result to show:

- `mode=revise` and the exact old `base_document_revision`;
- old formal manuscript → candidate manuscript Diff, not `/dev/null` → candidate;
- unchanged Chapter, Document, Volume, and Narrative Order identities;
- old → new Chapter Summary, Volume Summary, and Chapter Trace Diffs with their protected base
  digests;
- any sparse Canon corrections needed because the rewrite changed a previously structured fact.

When `$novel-writing` hands off an author-confirmed exact `ready` Draft, complete deferred Entity
resolution, Prepare, and Inspect in that same Codex turn. Do not infer Draft confirmation from the
Review, and do not defer the approval request until the author later asks to continue writing.

## Approve and apply

Call `publish approve` only after the author explicitly approves the exact
`publication_id + approval_digest`. Then call `publish apply`.

If apply returns `publication_recovery_required`, do not create or approve a replacement plan.
Report the stored Publication ID, then call `publish recover --publication-id <id>` to continue
the already approved steps. Repeat recovery only for the same immutable plan.

A revision recovery may observe either the exact approved old manuscript bytes or the already
installed approved new bytes. Any third revision is a conflict; never directly restore, overwrite,
or edit it.

Never interpret “continue writing”, ordinary Draft feedback, or Review recommendation as publish
approval. Never edit manuscript, navigation memory, Intent, Ledger, transaction state, or SQLite
directly.

Do not republish an approved historical Chapter only to add or correct its Chapter Trace. Route that
explicit maintenance request to `$novel-trace-backfill`.

## Diagnostics

Preserve the `diagnostic_id` returned by every CLI JSON envelope. When a call fails, report its
stable error code and diagnostic ID, then run
`novel diagnostics show --diagnostic-id <id> --json` before retrying or choosing
`publish recover`. Diagnostic records are operational evidence; they do not authorize publication
and are not recovery state.
