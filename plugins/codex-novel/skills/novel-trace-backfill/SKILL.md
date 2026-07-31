---
name: novel-trace-backfill
description: Prepare, inspect, explicitly approve, apply, and recover revision-bound Entity Chapter Trace backfills for approved historical Novel Chapters. Use when an author asks to add a missing historical Trace, repair a stale or incorrect Trace, or build old Entity occurrence lines without republishing or changing manuscript prose.
---

# Novel Trace Backfill

Use the installed `novel` CLI as the only business-data interface. A Backfill is an approved
maintenance transaction over existing prose, not a Writing Session or automatic extraction job.

## Project contract

Resolve the exact project root, then read `<root>/AGENTS.md` when present and follow it in the
current task, even when the Codex workspace or current directory is a parent of `<root>`. Apply it
only to operations bound to that project's Manifest and Project ID. Do not ask the author to
switch workspaces or start a new thread only to activate the project contract.

Use `<root>` as the working directory for every project-bound command. Put the Codex-authored
Chapter Trace Draft only under
`<root>/candidates/trace-backfill/<chapter-id>/`. This is non-authoritative staging. Do not place it
in the parent workspace, project top level, `memory/`, `canon/`, `runs/`, or `.novel/`.

## Select the source

1. Run `novel version --json`, `novel protocol-version --json`, and
   `novel --project <root> doctor --json`. Stop on an unhealthy project or incompatible protocol.
2. Use `memory volumes` and `memory chapters --volume-id <id>` to discover stable IDs. Process
   missing historical Traces one Chapter at a time in Narrative Order unless the author selected a
   specific correction.
3. Read the exact target:

   ```text
   novel --project <root> trace-backfill source \
     --volume-id <id> --chapter-id <id> --json
   ```

   Use only the returned approved UTF-8 `text`, `source_revision`, current Trace, current Entity
   Registry, and exact candidates. Review same-type Registry entries before proposing a new
   re-identifiable Entity. Never read manuscript or SQLite directly.
4. For every uncertain existing candidate, inspect its approved occurrence line:

   ```text
   novel --project <root> trace-backfill entity-line \
     --entity-id <id> --json
   ```

   Read relevant exact Chapters with `trace-backfill source`. Occurrences and summaries locate
   evidence; they do not decide identity.

## Resolve the Trace

Scan the exact target text for names, aliases, titles, pronouns, descriptions, present Entities,
offstage mentions, and recalled Entities. Record exact character offsets. Cover every mechanically
returned exact candidate and include every candidate ID in `considered_entity_ids`.

Resolve each Mention as `resolved_existing`, `resolved_new`, `anonymous`, `ignored`, or
`ambiguous`. Never choose the first, unique, nearest, most recent, or fuzzy string hit
automatically. Keep an Entity anonymous when the prose does not establish a reusable identity.
Do not prepare while any Mention is `ambiguous`.

Create the versioned Chapter Trace Draft in the project-local candidate directory. If the source
revision changes, discard it and repeat source reading and resolution.

## Prepare and inspect

Call:

```text
novel --project <root> trace-backfill prepare \
  --volume-id <id> --chapter-id <id> \
  --source-revision <revision> --chapter-trace <json-file> --json
```

Then call `trace-backfill inspect --backfill-id <id> --json`. Present:

- exact Volume, Chapter, Document, and source revision;
- old and candidate Trace Diff;
- every Mention resolution and occurrence;
- optional new Entity IDs and Canon Diff;
- exact `backfill_id` and `approval_digest`.

Ask the author to approve that exact pair, then stop. Ordinary “continue”, approval of another
operation, or agreement with the identity analysis is not Backfill approval.

## Approve, apply, and recover

Only after exact approval, call `trace-backfill approve` with the shown ID and Digest, then
`trace-backfill apply`.

If apply returns `trace_backfill_recovery_required`, do not prepare a replacement. Call
`trace-backfill recover --backfill-id <id>` for the same immutable plan.

Never directly edit manuscript, Volume/Chapter structure, Summary, Chapter Trace, Intent, Ledger,
run state, or SQLite. Backfill must not be used from an ordinary Writing Session to bypass its
Narrative Order history boundary. Keep final Mention extraction and identity resolution in the
primary agent; a partial-context sub-agent report cannot substitute for exact source review.

## Diagnostics

Preserve the `diagnostic_id` returned by every CLI JSON envelope. On failure, report the stable
error code and diagnostic ID, then run
`novel diagnostics show --diagnostic-id <id> --json` before retrying. Diagnostic records are
operational evidence, not approval or narrative history.
