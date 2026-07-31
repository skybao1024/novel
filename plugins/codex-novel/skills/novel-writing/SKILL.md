---
name: novel-writing
description: Run a project-bound Writing Session, recover approved history and authorial voice within its Narrative Order boundary, develop and confirm an author-visible causal Chapter plan, route material outline changes through Intent Revision, draft and review causally coherent and first-read-clear prose, present the exact ready Draft for author confirmation before any derived Entity or story-clue work, then resolve mentions and surface exact publication approval. Use when an author asks Codex to write, continue, insert, materially revise, or review a Chapter in a bootstrapped local Novel project.
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
2. For a new Chapter, prepare a versioned StoryTime JSON file under a unique
   `<root>/candidates/writing/pending-<operation>/` directory. Start a Session with the author goal
   and explicit `--new-chapter-number` plus `--new-chapter-title`. Select either an existing
   `--volume-id` or a new `--new-volume-number` plus `--new-volume-title`. Use
   `--before-chapter-id` and `--after-chapter-id` to state the exact insertion boundary. These
   option names describe where the neighboring approved Chapter sits relative to the new target
   Chapter, not the direction named in the author's request:

   - To append after the last approved Chapter, pass
     `--before-chapter-id <previous-chapter-id>` and omit `--after-chapter-id`.
   - To insert before the first approved Chapter, pass
     `--after-chapter-id <next-chapter-id>` and omit `--before-chapter-id`.
   - To insert between adjacent approved Chapters A and B, pass
     `--before-chapter-id <chapter-a-id> --after-chapter-id <chapter-b-id>`.

   Never translate “write after Chapter A” into `--after-chapter-id <chapter-a-id>`: Chapter A is
   the target's previous Chapter, so it belongs in `--before-chapter-id`.
   For an author-requested rewrite of one approved Chapter, start with its stable
   `--revise-chapter-id` instead. Do not pass StoryTime, Volume, insertion-boundary, POV, or location
   overrides: revision preserves the approved Chapter, Document, Volume, Narrative Order, and
   structural metadata.
3. Run `session context --session-id <id>`. Do not invent a manuscript Document for the
   unpublished target Chapter. Before any history read or drafting, verify that the returned
   `before_chapter_id` and `after_chapter_id` are the intended neighboring Chapters. For an append
   after Chapter A, Context must return `before_chapter_id` as Chapter A and `after_chapter_id` as
   null. Do not proceed with a Session whose saved boundary differs from the intended position.
   Copy `required_chapter_heading` exactly as the Draft's first line. Do not translate, restyle,
   renumber, or replace its spacing.
4. When `mode` is `revise`, immediately call
   `session revision-source --session-id <id>` and read the exact approved target prose. Verify its
   Chapter ID, Document ID, and `document_revision` against the Context. This dedicated read
   authorizes only the locked revision source; ordinary history commands still cannot read the
   target or later prose.

## History recovery

Call all navigation commands with `--session-id`:

```text
novel --project <root> memory volumes --session-id <id> --json
novel --project <root> memory chapters --session-id <id> --volume-id <id> --json
novel --project <root> memory search-summaries --session-id <id> --query <text> --json
novel --project <root> memory read-chapter --session-id <id> \
  --volume-id <id> --chapter-id <id> --json
```

Use `--session-id` on Entity and Canon queries too. Treat summaries as candidate locations and
approved Chapter text as narrative authority. Query until semantic context is sufficient; do not use
hit count or structured-record completeness as a writing gate.

### Continuity floor

Before drafting prose or saving the first Draft Revision in each Writing Session:

1. Read `continuity_volume_id` and `continuity_chapter_ids` from `session context`. For a new
   Chapter or a revision with a predecessor, the list contains the single immediately preceding
   approved Chapter. Read that Chapter exactly with `memory read-chapter`, even when the same prose
   was read earlier in this Codex task or in another Writing Session.
2. Call `session continuity-status --session-id <id>` and require `satisfied: true` before drafting
   or saving. A Chapter Summary, `previous_chapter_text_available`, remembered model context, another
   Session's `retrieved_sources`, or a sub-agent report cannot satisfy the current Session's exact
   read requirement. Missing or stale summaries do not waive it.
3. When the target opens a new Volume, also inspect the preceding Volume Summary when available.
4. For history earlier than the immediate predecessor, navigate Volume Summary → Chapter Summary →
   stable IDs → exact approved prose. Continue reading when an action, dialogue exchange, emotional
   beat, clue, or other dependency reaches farther back; do not load the whole manuscript by
   default.
5. Skip the predecessor read only when `continuity_chapter_ids` is empty, normally for the first
   Chapter in Narrative Order.

For a revision Session, `satisfied: true` also requires the exact `revision-source` read. The old
target prose is protected source material, not an instruction to paraphrase sentence by sentence.
Identify its necessary facts, implications, voice evidence, and structural defects, then rebuild
the candidate from the approved Intent and requested Chapter function.

Do not delegate the required exact reads, target prose drafting, or continuity Review to a
sub-agent that may receive partial conversation context. A sub-agent may help locate older
candidate clues, but the primary writing agent must perform the required reads in the current
Session and make the final continuity judgment.

The Application mechanically gates `draft save` only on this bounded exact-read window. It does
not treat any broader query count, summary completeness, or semantic judgment as sufficient or
required. Continue broader history and Canon queries until you judge the semantic context
sufficient.

## Chapter plan and author confirmation

Before creating or materially revising reader-facing prose, turn the recovered Context into a
versioned Chapter plan under `<root>/candidates/writing/<session-id>/planning/`. The plan is a
discussion artifact, not manuscript, approved Intent, Canon, Review, or publication approval. A
review-only request that does not change prose may skip this planning gate.

Keep the plan concise and author-visible. Do not create hidden subchapter or Scene cards, prescribe
a fixed number of beats, or disguise a prose draft as planning. Include only:

- the Chapter's function, approved-outline alignment, entry state, exit state, and mainline change;
- each material character's immediate aim, relevant knowledge, mistaken assumption, and pressure;
- the causal chain of material turns as observed fact → interpretation or choice → result → next
  condition;
- the decisive choice, concrete cost, and forward condition created for the next Chapter;
- whether the plan only refines Current Outline or changes approved Chapter or later-arc outcomes.

Show the exact plan revision to the author and invite correction, rejection, combination, or
replacement. Continue revising the plan until its events, character behavior, information flow,
and exit state are accepted. Do not draft prose merely because the author asked to “continue” or
commented on one part of an unconfirmed plan.

If the plan changes an approved Chapter turn, sequence, decisive choice, exit state, later Chapter
dependency, or other material Current Outline commitment, pause the Writing workflow and use
`$novel-bootstrap` to prepare, inspect, approve, and apply an Intent Revision. Reacquire Creation
Context after apply and make sure the active Writing Session reflects the approved Intent; replace
the Session when necessary. Then present the final aligned plan revision for author confirmation.
If the change reaches Creative Brief or Story Bible, include those exact Intent files in the same
explicit revision boundary rather than hiding the change in a Chapter plan.

Only the author's explicit confirmation of the exact aligned plan revision opens prose drafting.
This creative confirmation does not approve an Intent Revision or Publication. If drafting reveals
that a material turn, character choice, cost, or exit state must change, stop, revise the plan,
route any resulting Intent change, and reconfirm before continuing. Local wording, blocking, and
transitions that preserve the confirmed causal chain do not require another confirmation.

## Governing writing standard

### Highest creative gate: narrative intelligibility

After explicit author instructions, approved Intent, factual continuity, and structural identity,
causal coherence and first-pass narrative clarity are the highest creative gate. A target reader
must normally understand on one continuous read:

1. what is happening now;
2. why each character, limited to what that character knows and wants, responds this way;
3. how that response, choice, or result creates the next material condition.

If prose needs rereading, authorial explanation, abnormal character behavior, convenient
coincidence, or an unsupported conclusion to connect those answers, repair the causality or
description before improving voice, atmosphere, imagery, rhythm, novelty, elegance, length, or
speed. Style cannot compensate for an unclear event or a broken transition.

Deliberate uncertainty may conceal an answer, but it must leave the live question, observed facts,
available interpretations, and present stakes clear. Do not confuse mystery with missing causal
information.

### Project-specific voice

Within that intelligibility gate, make the prose belong to the approved novel. Derive a compact
Chapter voice brief from Writing Rules, Creative Brief, exact approved prose, Chapter position,
viewpoint attention, relationship pressure, and lived knowledge. Decide what the viewpoint notices,
ignores, misunderstands, or refuses to explain; how each speaker pursues an immediate aim; and where
the approved voice permits silence, roughness, repetition, humor, or incompleteness.

Do not fall back to generic “good literary prose” or generalized “human style”. A material paragraph
must depend on this viewpoint, relationship, knowledge, pressure, selection, or consequence.
Polish, local objects, period vocabulary, and banned-phrase avoidance do not establish authorial
voice by themselves.

When no earlier approved manuscript prose exists, recover an author-approved Voice Contract from
Writing Rules. It must establish the target reader and first-read baseline, narrative distance and
viewpoint limits, familiar diction and justified exceptions, relationship-specific dialogue,
permitted roughness, and positive and negative voice anchors. If it is missing, use
`$novel-bootstrap` to calibrate and approve it before recommending the opening Chapter as `ready`.
Infer choices from anchors without copying their sentences.

### Draft from confirmed causality

Generate prose from the confirmed plan's causal chain rather than decorating an event summary.
Every material detail must help the viewpoint perceive, decide, act, misread, relate, or suffer a
consequence. Do not add atmosphere, micro-actions, sensory inventory, explanation, or closure
merely because a literary paragraph appears to need them.

When revising generic or unclear prose:

1. preserve required facts, implications, and the confirmed exit state;
2. identify the broken causal, behavioral, or reader-facing function;
3. reduce the passage to necessary action, perception, dialogue, and consequence;
4. rebuild it from viewpoint knowledge, immediate pressure, and relationship;
5. restore only project-grounded rhythm or imagery;
6. verify that the structure, not merely the vocabulary, changed.

Prefer familiar, precise wording when it carries the meaning. Use archaic, technical, dialectal, or
world-specific terms only when the approved voice or setting needs them, and make their meaning
recoverable from nearby action or consequence. Keep actors, actions, objects, referents, and causal
turns legible. Give each paragraph one dominant reader-facing job and allocate space by narrative
importance: slow down for a material conflict, discovery, choice, or consequence; compress support,
scenery, terminology, and already-known procedure.

For Chinese prose, avoid stacked abstract nouns, decorative four-character formulations, parallel
mini-essays, and thesis → elaboration → thematic-summary scaffolding when direct action,
perception, or dialogue carries the meaning. Do not restate an emotion or implication already clear
from action or dialogue. Do not impose a universal sentence-length limit or flatten every approved
voice into colloquial minimalism.

### Compact diagnostic tests

Use these as ordered literary judgments, not equal-weight mechanical scores:

- **Causal link:** If two material turns can swap places or one can disappear without changing the
  next action, rebuild the chain.
- **Knowledge and behavior:** If a character's conclusion, speech, or action exceeds current
  knowledge, role, relationship, fear, or interest, restore a plausible basis.
- **First read:** If a reader cannot tell who did what, what changed, why it changed, or what matters
  most without rereading, reconstruct the smallest affected passage.
- **POV and dialogue:** If another viewpoint could observe the paragraph identically or speakers
  could exchange lines without damage, restore their distinct knowledge, aims, tactics, and history.
- **Rhetorical substitution:** If imagery, fragments, sensory detail, a polished explanation, or an
  aphoristic close masks rather than repairs a structural problem, remove it.

Never optimize against an AI-detector score or add random errors, awkward synonyms, forced
fragments, arbitrary variation, slang, or factual noise to simulate human authorship.

## Chapter scope

One Writing Session, Draft, Review, and Publication represents one complete reader-facing Chapter.
There is no formal subchapter narrative unit. Do not split one Session into separately reviewed
narrative fragments.

Read the approved Writing Rules and Current Outline before deciding length or pace. Recover the
selected project's Chapter budget and counting convention; never install a universal word-count
target in this Skill. When Intent specifies non-whitespace characters, count the exact Draft that
way rather than estimating from tokens. When approved Intent has no numeric budget, do not invent
one.

Keep one continuous action unit and one explainable exit change. A short Chapter still needs a
complete causal movement; a longer Chapter must earn its space through indivisible escalation, not
scenery, procedural repetition, connective explanation, or thematic summary. Repeat an
investigation, verification, or rhetorical move only when its result, failure mode, relationship,
or consequence materially changes. Compression must preserve action, perception, interruption,
choice, and consequence rather than turn the Chapter into synopsis or telegraphic beats.

Chapter length and movement remain author and AI literary judgments recorded in Review, not
Application gates.

## Draft and Review

1. Verify that the author confirmed the exact aligned Chapter plan revision and that any required
   Intent Revision has been applied.
2. Verify every candidate begins with the exact `required_chapter_heading` returned by
   `session context`. A revision receives the same heading and must preserve it.
3. Save non-empty UTF-8 prose from `<root>/candidates/writing/<session-id>/` with
   `draft save --session-id <id> --file <file>`. The Application rejects a missing or different
   required heading. Save another revision instead of overwriting.
4. Review the exact returned Draft revision as a distinct Reviewer role. Do not scan Entity
   candidates, extract people, plot, place, or clue records, generate a Chapter Trace or Summary,
   propose Canon, or prepare a Publication during this prose Review. Continue Session-bound history
   queries when needed and follow the ordered review below.
5. Save the Review with `review save`, its exact `--draft-revision`, recommendation, conclusion,
   findings, uncertainties, and any returned retrieved-source IDs.
6. If revision is required, rebuild the affected prose, save a new immutable Draft Revision, and
   review that exact revision from the beginning. Keep old Drafts and Reviews unchanged.

For `mode=revise`, inspect the first `draft diff` against the exact approved base manuscript. It
must show old formal prose → candidate prose, never `/dev/null` → candidate. Before recommending
`ready`, verify that Chapter/Document/Volume IDs and Narrative Order remain unchanged and that any
changed facts are reconciled through the optional sparse Canon proposal rather than silently
leaving contradictory long-term records.

### Ordered narrative review

Review in this order. A later strength cannot compensate for an earlier failure:

1. **Plan and continuity:** The Draft preserves the confirmed plan, approved Intent, exact history,
   structural identity, and required exit state.
2. **Causal coherence:** Each material turn follows from observed facts, character knowledge,
   immediate aims, pressure, choice, or consequence. Another instance of the same anomaly,
   procedure, argument, or image counts only when it changes the working explanation, risk,
   relationship, resource, or available action.
3. **First-pass narrative clarity:** A cold reader using only the Draft can tell what happened, who
   acted, why the reaction is plausible, how the result creates the next condition, what a referent
   points to, and which detail matters most without syntactic rereading.
4. **Human behavior and viewpoint:** Conclusions stay within character knowledge; speech and action
   fit role, relationship, fear, habit, and current interest; the viewpoint selects rather than
   inventories details.
5. **Project-specific voice:** Diction, dialogue, omission, roughness, and rhythm follow approved
   evidence instead of generic literary completion.
6. **AI-pattern regression:** A revision repairs the structural cause instead of exchanging one
   conspicuous pattern for another.

Do not recommend `ready` when the mainline change is only thematic, opposition stays passive, a
central choice has no concrete cost, the ending can move unchanged to another Chapter, the
confirmed plan was materially bypassed, or causal coherence or first-pass clarity fails.

For each material failure, cite the shortest exact excerpt, state the probable reader
misunderstanding, identify the causal, behavioral, focal, or voice cause, name protected material,
and give the smallest reconstruction goal. Prefer diagnosis over replacement prose. Provide
example prose only when the author explicitly asks or the repair would otherwise remain ambiguous;
mark it as a non-authoritative candidate.

State all of the following in the Review conclusion:

- `confirmed chapter plan: <revision>`;
- `causal-coherence check: passed` or `causal-coherence check: failed`;
- `first-pass narrative-clarity check: passed` or
  `first-pass narrative-clarity check: failed`;
- `human-behavior plausibility check: passed` or
  `human-behavior plausibility check: failed`;
- `focal-hierarchy check: passed` or `focal-hierarchy check: failed`;
- `lexical-accessibility check: passed` or `lexical-accessibility check: failed`;
- `authorial-prose integrity check: passed` or
  `authorial-prose integrity check: failed`;
- `AI-like prose regression check: passed` or
  `AI-like prose regression check: failed`.

For a failed clarity check, preserve intended uncertainty but identify what the reader should have
understood without rereading. For a failed causal or behavior check, do not patch the gap with
explanatory narration; return to the Chapter plan when the confirmed chain itself is defective.

### Reviewer restraint and AI-pattern review

Act primarily as a diagnostic role, not a second prose generator. Preserve project-grounded
silence, ambiguity, bluntness, unevenness, and character-limited expression. Do not automatically
add atmosphere, sensory detail, polished metaphor, balanced clauses, fashionable fragments,
explicit emotion, thematic summary, aphoristic closure, or more articulate dialogue.

After every revision, review the exact new Draft. Check whether the causal or clarity defect was
repaired, a generic pattern was merely exchanged for another, unsupported decoration appeared, or
effective authorial irregularity was normalized. Judge AI-like prose by causality, viewpoint,
relationship, selection, and consequence, not by a phrase blacklist.

For a first Chapter with no earlier approved manuscript prose, state
`opening voice basis: established` or `opening voice basis: missing` in the Review conclusion.
`established` requires the approved Voice Contract and its author-approved anchors; genre
convention, Writer rationale, local period detail, and polished specificity do not substitute.

Do not recommend `ready` while a material generic completion, rhetorical substitution,
Reviewer-induced style regression, or missing opening voice basis remains. Treat an AI-detector
result only as a noisy external observation, never as the writing objective, Application gate, or
substitute for literary judgment.

## Exact Draft author confirmation

When a Review first reaches `ready`:

1. Call `draft show --session-id <id> --draft-revision <revision>` and verify the returned bytes and
   revision are the exact reviewed Draft.
2. Present the exact Draft revision, complete prose, and a compact Review conclusion directly to
   the author. Ask the author to confirm that exact Draft, request changes, or leave it as
   draft-only.
3. Stop and wait for the author's response. Before this confirmation, do not call
   `draft entity-candidates`, generate a Chapter Trace, extract people, plot, places, or clues,
   generate Chapter or Volume Summaries, propose Canon, or call `publish prepare` or
   `publish inspect`.

Treat only an explicit response accepting the displayed exact Draft revision as confirmation.
Ordinary feedback, approval of the Chapter plan, `Review ready`, “continue”, or approval of an
earlier Draft is not enough. If the author requests any prose change, save a new immutable Draft
revision, repeat the prose Review, show the new exact Draft, and request confirmation again. A new
Draft revision always invalidates the earlier creative confirmation.

This confirmation is a Plugin-managed creative checkpoint, not an Application approval artifact.
It does not approve Intent, a Publication, Summary, Chapter Trace, Entity resolution, or Canon. If
the exact confirmation is not available in the current task context, show the Draft again and
reconfirm instead of inferring approval.

## Entity resolution and Chapter Trace

Only after the author confirms the exact Review-`ready` Draft revision:

1. Call `draft entity-candidates`:

   ```text
   novel --project <root> draft entity-candidates \
     --session-id <id> --draft-revision <revision> --json
   ```

   Treat every returned display-name or Alias match as a candidate, never an identity decision.
2. Scan the same exact Draft for additional name, alias, pronoun, title, and descriptive Mentions.
   Use `resolve entity --session-id <id>` to discover exact existing candidates and
   `memory entity-line --session-id <id> --entity-id <id>` to inspect each candidate's prior
   Chapter/Volume occurrences. Read exact historical Chapter prose when candidates remain ambiguous.
3. Save a versioned Chapter Trace Draft under
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

If the Draft changes, discard the candidate scan and Chapter Trace Draft and return to prose Review
and exact Draft author confirmation for the new revision before repeating this section. Keep final
Mention extraction, identity resolution, and Chapter Trace Review in the primary writing agent; a
partial-context sub-agent report cannot substitute for them.

Do not use historical `trace-backfill` source or Entity-line commands to bypass the current
Writing Session boundary. `$novel-trace-backfill` is only for an explicit maintenance task over
already approved prose.

## Publication handoff

After the author confirms the exact Review-`ready` Draft:

1. Verify the confirmation, ready Review, and all downstream work bind the same exact Draft
   revision. If the author explicitly requested draft-only or review-only work, report the stable
   Draft and Review IDs and stop without preparing a Publication.
2. Run the Entity resolution and Chapter Trace workflow for that confirmed revision.
3. Continue in the same Codex turn with `$novel-publish`. Use the exact Session, Draft, and Review;
   prepare Chapter and Volume Summary inputs under
   `<root>/candidates/writing/<session-id>/publication/`; include the exact Chapter Trace Draft; call
   `publish prepare`, then `publish inspect`.
4. Present the protected manuscript, structure, Summary, Chapter Trace, Mention resolution, new
   Entity, optional Intent and Canon Diffs, unresolved questions, exact `publication_id`, and exact
   `approval_digest`. End by asking the author to approve that exact pair.

Do not begin this handoff merely because a Review is `ready`; the exact Draft confirmation is the
required creative boundary. Once the author confirms that revision and has not requested
draft-only work, complete the derived work and surface Publication approval; do not wait for a
later “continue writing” request. Never call `publish approve` or `publish apply` without the
author's separate exact Publication approval.

Do not write formal manuscript, summary, Intent, Ledger, or SQLite files directly. Let
`$novel-publish` own Publication commands and approval boundaries.

## Diagnostics

Preserve the `diagnostic_id` returned by every CLI JSON envelope. When a call fails, report its
stable error code and diagnostic ID, then run
`novel diagnostics show --diagnostic-id <id> --json` before retrying. Diagnostic records are
operational evidence, not Draft, Review, retrieved-source history, or publication approval.
