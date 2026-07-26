---
name: novel-bootstrap
description: Initialize an empty local Novel project or prepare a later Intent Revision through the formal CLI approval boundary. Use when an author wants to turn a discussed premise, Story Bible, writing rules, or outline into approved Intent Canon, or explicitly revise those files later.
---

# Novel Bootstrap

Use `novel` as the only business-data interface. Keep candidate files outside formal `intent/`;
the Application installs them as Intent Canon only after approval.

## New project

1. Resolve one explicit project and run `novel --project <root> doctor --json`.
2. Run `novel --project <root> bootstrap start --json`.
3. Discuss the novel with the author. Prepare four non-empty UTF-8 files: Creative Brief,
   Story Bible, Writing Rules, and Current Outline. Optionally prepare a versioned JSON array of
   Bootstrap Entity drafts containing only temporary name, type, and display name; the
   Application allocates their stable IDs before approval.
4. Save the candidate:

   ```text
   novel --project <root> bootstrap save \
     --bootstrap-id <id> \
     --creative-brief <file> --story-bible <file> \
     --writing-rules <file> --current-outline <file> \
     --initial-goal <goal> --json
   ```

5. Run `bootstrap inspect`. Show the exact Diff, stable IDs, unresolved questions, and approval
   digest. Stop and wait for the author.
6. Only after the author explicitly approves that exact digest, call `bootstrap approve` with
   `--bootstrap-id` and `--approval-digest`, then call `bootstrap apply`.

Do not treat “continue”, ordinary feedback, or approval of another revision as authorization.

## Later Intent Revision

1. Run `novel --project <root> intent show --json`.
2. Prepare one or more replacement UTF-8 files and call `intent prepare` with only the changed
   file options.
3. Run `intent inspect`; show its Diff and digest, then wait.
4. After exact author approval, call `intent approve`. Use `intent apply` for a standalone change,
   or leave it approved for inclusion by ID in a Publish Plan.

Never edit formal Intent files, the Ledger, or SQLite directly.
