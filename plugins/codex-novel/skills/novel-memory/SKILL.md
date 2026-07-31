---
name: novel-memory
description: Navigate a local Novel project with Volume and Chapter summaries, Entity occurrence lines, search navigation memory, and read exact approved historical Chapter prose through stable IDs. Use when Codex needs to recover historical context or disambiguate an Entity for AI-first writing or review.
---

# Novel Memory

Use the installed `novel` CLI as the only application interface. Treat summaries as incomplete,
non-Canon navigation hints and approved manuscript text as the authority.

## Workflow

1. Locate the project root containing `novel.yaml`.
2. Read `<root>/AGENTS.md` when present and follow it as the selected project's contract in the
   current task, even when the Codex workspace or current directory is a parent of `<root>`.
   Apply it only to operations bound to that project's Manifest and Project ID. Do not ask the
   author to switch workspaces or start a new thread only to activate the project contract. Use
   `<root>` as the working directory for every project-bound tool call.
3. Run `novel version --json`, `novel protocol-version --json`, and
   `novel --project <root> doctor --json`. Stop on an unhealthy project or incompatible protocol.
4. If a Writing Session exists, use its stable ID on every navigation call. List Volume
   navigation memory:

   ```text
   novel --project <root> memory volumes --session-id <session-id> --json
   ```

5. Expand promising Volumes with stable IDs:

   ```text
   novel --project <root> memory chapters --volume-id <volume-id> \
     --session-id <session-id> --json
   ```

6. When the location is unclear, search summaries before the target Chapter:

   ```text
   novel --project <root> memory search-summaries \
     --query <text> \
     --entity <entity-id> \
     --session-id <session-id> \
     --json
   ```

   Supply a query, an Entity ID, or both. Treat every hit as a candidate location only.
7. Read selected approved prose with the exact Volume/Chapter pair:

   ```text
   novel --project <root> memory read-chapter \
     --volume-id <volume-id> \
     --chapter-id <chapter-id> \
     --session-id <session-id> \
     --json
   ```

8. When resolving a known Entity candidate, inspect its revision-bound occurrence line:

   ```text
   novel --project <root> memory entity-line \
     --entity-id <entity-id> --session-id <session-id> --json
   ```

   Treat Chapter Trace Mentions and occurrences as candidate locations, not proof of identity or
   narrative fact. Read the referenced exact Chapter prose when the distinction matters.
9. Interpret the returned exact UTF-8 text. Repeat summary search, Entity occurrence navigation,
   Volume expansion, and Chapter reads until you judge the history sufficient for the task.

## Boundaries

- Use stable Volume, Chapter, Document, and Entity IDs; volume and chapter numbers are display data.
- Never infer that missing or stale summaries mean an event did not happen.
- Never infer that a missing or stale Chapter Trace means an Entity did not appear.
- Never use a unique, exact, fuzzy, or recent name match as an automatic Entity identity.
- Never use FTS rank, hit count, or a summary to declare a fact or semantic sufficiency.
- Never request the target Chapter or a later Chapter through ordinary historical reading.
- Never call `trace-backfill source` or `trace-backfill entity-line` during ordinary Writing
  Session navigation. Those full-history maintenance reads belong only to an explicit
  `$novel-trace-backfill` task.
- Never replace the saved Session boundary with an ad hoc `--before-chapter`.
- Report revision mismatch or invalid Volume/Chapter membership; do not bypass it by reading files
  directly.
- Never query SQLite, edit `memory/`, append the Canon Ledger, approve changes, call a model API,
  create Embeddings, or start a service.

## Diagnostics

Preserve the `diagnostic_id` returned by every CLI JSON envelope. When a call fails, report its
stable error code and diagnostic ID, then run
`novel diagnostics show --diagnostic-id <id> --json` before retrying. Diagnostic records are
operational evidence, not approved narrative history or Canon.
