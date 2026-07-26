---
name: novel-writing
description: Run a project-bound Writing Session, recover approved history within its Narrative Order boundary, save immutable Draft Revisions, and record an AI Review. Use when an author asks Codex to write, continue, insert, revise, or review a Scene in a bootstrapped local Novel project.
---

# Novel Writing

Use one explicit Project and one open Writing Session. The Application owns IDs, boundaries,
revisions, and retrieved-source records; Codex owns writing and literary judgment.

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
