---
name: novel-memory
description: Navigate a local Novel project with Chapter and Scene summaries, search navigation memory, and read exact approved historical Scene prose through stable IDs. Use when Codex needs to recover historical context for AI-first writing or review.
---

# Novel Memory

Use the installed `novel` CLI as the only application interface. Treat summaries as incomplete,
non-Canon navigation hints and approved manuscript text as the authority.

## Workflow

1. Locate the project root containing `novel.yaml`.
2. Run `novel version --json`, `novel protocol-version --json`, and
   `novel --project <root> doctor --json`. Stop on an unhealthy project or incompatible protocol.
3. If a Writing Session exists, use its stable ID on every navigation call. List Chapter
   navigation memory:

   ```text
   novel --project <root> memory chapters --session-id <session-id> --json
   ```

4. Expand promising Chapters with stable IDs:

   ```text
   novel --project <root> memory scenes --chapter-id <chapter-id> \
     --session-id <session-id> --json
   ```

5. When the location is unclear, search summaries before the target Scene:

   ```text
   novel --project <root> memory search-summaries \
     --query <text> \
     --entity <entity-id> \
     --session-id <session-id> \
     --json
   ```

   Supply a query, an Entity ID, or both. Treat every hit as a candidate location only.
6. Read selected approved prose with the exact Chapter/Scene pair:

   ```text
   novel --project <root> memory read-scene \
     --chapter-id <chapter-id> \
     --scene-id <scene-id> \
     --session-id <session-id> \
     --json
   ```

7. Interpret the returned exact UTF-8 text. Repeat summary search, Chapter expansion, and Scene
   reads until you judge the history sufficient for the current writing or review task.

## Boundaries

- Use stable Chapter, Scene, Document, and Entity IDs; chapter and scene numbers are display data.
- Never infer that missing or stale summaries mean an event did not happen.
- Never use FTS rank, hit count, or a summary to declare a fact or semantic sufficiency.
- Never request the target Scene or a later Scene through ordinary historical reading.
- Never replace the saved Session boundary with an ad hoc `--before-scene`.
- Report revision mismatch or invalid Chapter/Scene membership; do not bypass it by reading files
  directly.
- Never query SQLite, edit `memory/`, append the Canon Ledger, approve changes, call a model API,
  create Embeddings, or start a service.
