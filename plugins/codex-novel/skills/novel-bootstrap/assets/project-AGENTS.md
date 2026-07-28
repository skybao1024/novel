# Novel Project Guidance

## Project identity

- Treat this directory as one independent Novel project.
- Read and verify `novel.yaml` before starting project work.
- Bind every write to the exact Project ID and normalized project root.
- Never select a write target from a title, recent directory, or fuzzy path.

## Workflow routing

- Use `novel` as the only business-data interface.
- Use `$novel-bootstrap` for project Bootstrap and later Intent revisions.
- Use `$novel-writing` for Scene writing, revision, and AI Review.
- Use `$novel-memory` to navigate summaries and read exact approved history.
- Use `$novel-publish` to prepare, inspect, approve, apply, or recover publication.

## Data boundaries

- Never directly edit formal `intent/`, `structure/`, `manuscript/`, `memory/`,
  `canon/ledger/`, `runs/`, or `.novel/`.
- Keep discussion and comparison artifacts outside formal Intent and label them as candidates.
- Do not describe a Draft, Review, summary, or comparison artifact as approved Canon.
- Do not delete Draft, Review, Bootstrap, Intent Revision, or Publication assets as cache.

## Phase and approval boundaries

- When the author asks only to discuss or compare, do not write a formal Scene or publish.
- Before writing, create or resume the exact Writing Session and load its Creation Context.
- Treat ordinary feedback, “continue”, and approval of another revision as non-approval.
- Approve or apply Bootstrap, Intent, or Publication only when the author explicitly approves the
  exact operation ID and approval digest shown by its inspect command.

## Creative sources

- Treat approved manuscript prose as the primary source for complete narrative history.
- Treat approved Intent as the primary source for creative direction.
- Use Chapter and Scene summaries only to locate relevant approved prose.
- Treat the Canon Ledger as sparse long-term memory; missing structured Canon does not prove that
  an event or detail is absent from the manuscript.
- Recover relevant summaries, stable IDs, and exact Scene prose before making continuity claims.

## Collaboration

- Communicate in the author's requested language.
- Clearly distinguish discussion candidates, Drafts, Reviews, approved Intent, and published prose.
- Make minimal reversible assumptions for small undefined details.
- Stop for author direction before changing the premise, major character fate, ending, or another
  locked creative direction.
