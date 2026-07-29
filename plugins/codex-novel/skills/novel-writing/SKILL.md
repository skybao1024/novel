---
name: novel-writing
description: Run a project-bound Writing Session, recover approved history within its Narrative Order boundary, save immutable Draft Revisions, resolve Entity mentions into a Scene Trace, record an AI Review, and immediately surface exact publication approval for a ready Scene. Use when an author asks Codex to write, continue, insert, revise, or review a Scene in a bootstrapped local Novel project.
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

## Project workspace

Use `<root>` as the working directory for every project-bound filesystem and CLI call, even when
the Codex workspace remains a parent directory. Put Codex-authored StoryTime, prose, Review input,
and publication input files only under `<root>/candidates/`, grouped by Writing Session ID as soon
as it exists or by a unique pending-session directory beforehand. `candidates/` is
non-authoritative staging, not Novel business data. Never scatter these files in the parent
workspace, directly in the project top level, or inside formal `manuscript/`, `runs/`, or
`.novel/`.

## Session

1. Verify `novel --project <root> doctor --json` is healthy.
2. Prepare a versioned StoryTime JSON file under a unique
   `<root>/candidates/writing/pending-<operation>/` directory. Start a Session with the author goal
   and either an existing `--chapter-id` or a new Chapter number/title. Use `--before-scene-id` and
   `--after-scene-id` to state the exact insertion boundary.
3. Run `session context --session-id <id>`. Do not invent a manuscript Document for the
   unpublished target Scene. If `required_chapter_heading` is non-null, copy that exact value as
   the Draft's first line. Do not translate, restyle, renumber, or replace its spacing.

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

Before drafting prose or saving the first Draft Revision in each Writing Session:

1. Read `continuity_chapter_id` and every ordered `continuity_scene_ids` value from
   `session context`. These IDs identify all approved Scenes in the Chapter containing
   `before_scene_id` that precede the target's Narrative Order. If the list is non-empty, call
   `memory read-scene` for every listed Scene, even when the same prose was read earlier in this
   Codex task or in another Writing Session.
2. Call `session continuity-status --session-id <id>` and require `satisfied: true` before drafting
   or saving. A Scene Summary, `previous_scene_text_available`, remembered model context, another
   Session's `retrieved_sources`, or a sub-agent report cannot satisfy the current Session's exact
   read requirement. Missing or stale summaries do not waive it.
3. When the target opens a new Chapter, also inspect the preceding Chapter Summary when available.
   The required exact-read window already covers that preceding Chapter's approved Scenes before
   the target boundary.
4. For history earlier than the continuity Chapter, navigate Chapter Summary → Scene Summary →
   stable IDs → exact approved prose. Continue reading when an action, dialogue exchange, emotional
   beat, clue, or other dependency reaches farther back; do not load the whole manuscript by
   default.
5. Skip the exact-read window only when `continuity_scene_ids` is empty, which is normally the
   first Scene in Narrative Order.

Do not delegate the required exact reads, target prose drafting, or continuity Review to a
sub-agent that may receive partial conversation context. A sub-agent may help locate older
candidate clues, but the primary writing agent must perform the required reads in the current
Session and make the final continuity judgment.

The Application mechanically gates `draft save` only on this bounded exact-read window. It does
not treat any broader query count, summary completeness, or semantic judgment as sufficient or
required. Continue broader history and Canon queries until you judge the semantic context
sufficient.

## Entity resolution and Scene Trace

For every exact Draft revision that may be published:

1. Call `draft entity-candidates`:

   ```text
   novel --project <root> draft entity-candidates \
     --session-id <id> --draft-revision <revision> --json
   ```

   Treat every returned display-name or Alias match as a candidate, never an identity decision.
2. Scan the same exact Draft for additional name, alias, pronoun, title, and descriptive Mentions.
   Use `resolve entity --session-id <id>` to discover exact existing candidates and
   `memory entity-line --session-id <id> --entity-id <id>` to inspect each candidate's prior
   Scene/Chapter occurrences. Read exact historical Scene prose when candidates remain ambiguous.
3. Save a versioned Scene Trace Draft under
   `<root>/candidates/writing/<session-id>/publication/`. Give every Mention exact character
   offsets, surface text, considered Entity IDs, resolution reason, and one status:
   `resolved_existing`, `resolved_new`, `anonymous`, `ignored`, or `ambiguous`.
4. Link every resolved Mention to exactly one Entity occurrence with presence and prominence.
   Declare re-identifiable new people or places in `new_entities`; keep genuinely anonymous extras
   anonymous instead of inventing reusable identities.
5. Resolve every `ambiguous` Mention before publication. The Application validates exact text
   spans, requires every mechanically returned candidate to be covered, rejects future Entity IDs,
   and allocates all new Entity, Trace, Mention, and occurrence UUIDs. Never choose the first,
   unique, nearest, or fuzzy string hit as an automatic identity.

If the Draft changes, discard the candidate scan and Scene Trace Draft and repeat this section for
the new exact revision. Keep final Mention extraction, identity resolution, and Scene Trace Review
in the primary writing agent; a partial-context sub-agent report cannot substitute for them.

Do not use historical `trace-backfill` source or Entity-line commands to bypass the current
Writing Session boundary. `$novel-trace-backfill` is only for an explicit maintenance task over
already approved prose.

## Draft and Review

1. For a new Chapter's first Scene, verify the candidate begins with the exact
   `required_chapter_heading` returned by `session context`. Existing-Chapter Scenes receive
   `null` and do not repeat a Chapter heading.
2. Save non-empty UTF-8 prose from `<root>/candidates/writing/<session-id>/` with
   `draft save --session-id <id> --file <file>`. The Application rejects a missing or different
   required heading. Save another revision instead of overwriting.
3. Run the Entity resolution and Scene Trace workflow for the exact Draft revision.
4. Review the exact returned Draft revision and its Scene Trace Draft as a distinct Reviewer role.
   Continue Session-bound history queries when needed.
5. Save the Review with `review save`, its exact `--draft-revision`, recommendation, conclusion,
   findings, uncertainties, and any returned retrieved-source IDs.
6. Revise and repeat as needed. Keep old Drafts and Reviews unchanged.

## Publication handoff

After saving a Review:

1. If its recommendation is not `ready`, revise or report the blocker without preparing a
   Publication.
2. If it is `ready` and the author explicitly requested draft-only or review-only work, report the
   stable Draft and Review IDs and stop without preparing a Publication.
3. Otherwise continue in the same Codex turn with `$novel-publish`. Use the exact Session, Draft,
   and Review; prepare Scene and Chapter Summary inputs under
   `<root>/candidates/writing/<session-id>/publication/`; include the exact Scene Trace Draft; call
   `publish prepare`, then `publish inspect`.
4. Present the protected manuscript, structure, Summary, Scene Trace, Mention resolution, new
   Entity, optional Intent and Canon Diffs, unresolved questions, exact `publication_id`, and exact
   `approval_digest`. End by asking the author to approve that exact pair.

Do not end a normal Scene-writing turn with only “Review ready” or “not yet published”, and do not
wait for a later “continue writing” request to surface the pending approval. Before opening the next
Writing Session, surface any existing ready Review that has not completed this handoff unless the
author explicitly left it draft-only. Never call `publish approve` or `publish apply` without the
author's exact approval.

Do not write formal manuscript, summary, Intent, Ledger, or SQLite files directly. Let
`$novel-publish` own Publication commands and approval boundaries.

## Diagnostics

Preserve the `diagnostic_id` returned by every CLI JSON envelope. When a call fails, report its
stable error code and diagnostic ID, then run
`novel diagnostics show --diagnostic-id <id> --json` before retrying. Diagnostic records are
operational evidence, not Draft, Review, retrieved-source history, or publication approval.
