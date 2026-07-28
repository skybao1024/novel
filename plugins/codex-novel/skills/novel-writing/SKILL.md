---
name: novel-writing
description: Run a project-bound Writing Session, recover approved history within its Narrative Order boundary, save immutable Draft Revisions, and record an AI Review. Use when an author asks Codex to write, continue, insert, revise, or review a Scene in a bootstrapped local Novel project.
---

# Novel Writing

Use one explicit Project and one open Writing Session. The Application owns IDs, boundaries,
revisions, and retrieved-source records; Codex owns writing and literary judgment.

## Project contract

Resolve the exact project root containing `novel.yaml`, then read `<root>/AGENTS.md` when present
and follow it as the selected project's contract in the current task. Do this even when the Codex
workspace or current directory is a parent of `<root>`. Apply it only to operations bound to that
project's Manifest and Project ID. Do not ask the author to switch workspaces or start a new thread
only to activate the project contract.

## Session

1. Verify `novel --project <root> doctor --json` is healthy.
2. Prepare a versioned StoryTime JSON file. Start a Session with the author goal and either an
   existing `--chapter-id` or a new Chapter number/title. Use `--before-scene-id` and
   `--after-scene-id` to state the exact insertion boundary.
3. Run `session context --session-id <id>`. Do not invent a manuscript Document for the
   unpublished target Scene.

## History recovery

Call all navigation commands with `--session-id`:

```text
novel --project <root> memory chapters --session-id <id> --json
novel --project <root> memory scenes --session-id <id> --chapter-id <id> --json
novel --project <root> memory search-summaries --session-id <id> --query <text> --json
novel --project <root> memory read-scene --session-id <id> \
  --chapter-id <id> --scene-id <id> --json
```

Use `--session-id` on Entity and Canon queries too. Treat summaries as candidate locations and
approved Scene text as narrative authority. Query until semantic context is sufficient; do not use
hit count or structured-record completeness as a writing gate.

### Continuity floor

Before drafting prose or saving the first Draft Revision in the current Codex run:

1. If `before_scene_id` exists, always resolve its Chapter and call `memory read-scene` for that
   immediately preceding approved Scene. Neither its Scene Summary nor
   `previous_scene_text_available` substitutes for the exact prose. Do not draft until this required
   exact read succeeds; a missing or stale summary does not waive it.
2. When the target opens a new Chapter, inspect the preceding Chapter Summary when available and
   read that Chapter's final approved Scene in full. One exact read may satisfy both this step and
   the immediately preceding Scene requirement.
3. If the exact prose leaves an action, dialogue exchange, emotional beat, or other direct handoff
   unresolved, use summaries to locate and read the additional approved Scenes needed to understand
   the handoff. Read all relevant Scenes from the preceding Chapter when continuity spans them; do
   not load the whole manuscript by default.
4. Skip the required predecessor read only when the target is the first Scene in Narrative Order.
   When resuming a Session in a new Codex run, perform these reads again so the exact prose is
   present in the current context.

This is a Plugin writing rule, not an Application query-count gate. Continue broader history and
Canon queries until you judge the semantic context sufficient.

## Draft and Review

1. Save non-empty UTF-8 prose with `draft save --session-id <id> --file <file>`. Save another
   revision instead of overwriting.
2. Review the exact returned Draft revision as a distinct Reviewer role. Continue Session-bound
   history queries when needed.
3. Save the Review with `review save`, its exact `--draft-revision`, recommendation, conclusion,
   findings, uncertainties, and any returned retrieved-source IDs.
4. Revise and repeat as needed. Keep old Drafts and Reviews unchanged.

Do not write formal manuscript, summary, Intent, Ledger, or SQLite files directly. Do not publish
from this skill; hand the stable Draft and Review IDs to `$novel-publish`.

## Diagnostics

Preserve the `diagnostic_id` returned by every CLI JSON envelope. When a call fails, report its
stable error code and diagnostic ID, then run
`novel diagnostics show --diagnostic-id <id> --json` before retrying. Diagnostic records are
operational evidence, not Draft, Review, retrieved-source history, or publication approval.
