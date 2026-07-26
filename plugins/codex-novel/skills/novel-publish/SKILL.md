---
name: novel-publish
description: Prepare, inspect, explicitly approve, apply, and recover an exact Novel Scene publication. Use when a Writing Session has a stable Draft Revision and Review and Codex must generate navigation summaries and optional Intent or sparse Canon changes without bypassing the author's digest approval.
---

# Novel Publish

Use `novel` as the only business-data interface. Publishing is a protected transaction, not an
implicit consequence of drafting or review.

## Prepare

1. Confirm the exact open Session, Draft revision, and one or more Reviews.
2. Generate a UTF-8 Scene Summary that describes only the candidate Scene and a UTF-8 Chapter
   Summary that aggregates the Chapter. Optionally prepare an approved Intent Revision ID and a
   versioned JSON array of sparse Canon Ledger records.
3. Call:

   ```text
   novel --project <root> publish prepare \
     --session-id <id> --draft-revision <revision> \
     --scene-summary <text-file> --chapter-summary <text-file> \
     --review-id <id> --json
   ```

   Add main Entity IDs, key changes, open questions, `--intent-revision-id`, or
   `--canon-records` only when they are accurate. The Application derives Summary bindings,
   Document/Scene IDs, revisions, and dependency digests.
4. Run `publish inspect --publication-id <id>`. Present the manuscript, structure, Summary,
   optional Intent, Canon Diffs, Review conclusions, unresolved questions, and approval digest.
   Stop and wait.

## Approve and apply

Call `publish approve` only after the author explicitly approves the exact
`publication_id + approval_digest`. Then call `publish apply`.

If apply returns `publication_recovery_required`, do not create or approve a replacement plan.
Report the stored Publication ID, then call `publish recover --publication-id <id>` to continue
the already approved steps. Repeat recovery only for the same immutable plan.

Never interpret “continue writing”, ordinary Draft feedback, or Review recommendation as publish
approval. Never edit manuscript, navigation memory, Intent, Ledger, transaction state, or SQLite
directly.
