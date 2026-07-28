---
name: novel-bootstrap
description: Create or initialize a local Novel project with project-scoped Codex guidance, or prepare a later Intent Revision through the formal CLI approval boundary. Use when an author wants to create a new novel, turn a discussed premise, Story Bible, writing rules, or outline into approved Intent Canon, or explicitly revise those files later.
---

# Novel Bootstrap

Use `novel` as the only business-data interface. Keep candidate files outside formal `intent/`;
the Application installs them as Intent Canon only after approval.

## Project contract

After resolving or creating the exact project root, read `<root>/AGENTS.md` when present and follow
it as the selected project's contract in the current task. Do this even when the Codex workspace or
current directory is a parent of `<root>`. Apply it only to operations bound to that project's
Manifest and Project ID. Do not ask the author to switch workspaces or start a new thread only to
activate the project contract.

## Project workspace

After resolving or creating `<root>`, use it as the working directory for every project-bound
filesystem and CLI call, even when the Codex workspace remains a parent directory. Put
Codex-authored CLI input files only under `<root>/candidates/`, grouped by the stable operation ID
as soon as one exists or by a unique pending-operation directory beforehand. `candidates/` is
non-authoritative staging, not Novel business data. Never scatter candidate files in the parent
workspace, directly in the project top level, or inside formal `intent/`, `runs/`, or `.novel/`.

## New project

1. If the project does not exist, choose one explicit root with the author and run:

   ```text
   novel project create <root> --title <title> [--language <tag>] --json
   ```

2. After `project create` succeeds, install this Skill's project guidance:

   ```text
   python3 <this-skill-directory>/scripts/install_project_agents.py --project <root>
   ```

   This helper only creates root `AGENTS.md`; it does not write Novel business data. It is
   idempotent for the bundled template and refuses to overwrite different existing guidance.
   If the project already exists with status `not_bootstrapped` and has no root `AGENTS.md`, run
   the same helper before starting Bootstrap. Report a conflicting existing file instead of
   replacing it. Immediately read the created file and follow it in the current task.
3. Resolve that exact project and run `novel --project <root> doctor --json`.
4. Run `novel --project <root> bootstrap start --json`.
5. Discuss the novel with the author. Prepare four non-empty UTF-8 files: Creative Brief,
   Story Bible, Writing Rules, and Current Outline. Optionally prepare a versioned JSON array of
   Bootstrap Entity drafts containing only temporary name, type, and display name; the
   Application allocates their stable IDs before approval. Store these inputs under
   `<root>/candidates/bootstrap/<bootstrap-id>/`.
6. Save the candidate:

   ```text
   novel --project <root> bootstrap save \
     --bootstrap-id <id> \
     --creative-brief <file> --story-bible <file> \
     --writing-rules <file> --current-outline <file> \
     --initial-goal <goal> --json
   ```

7. Run `bootstrap inspect`. Show the exact Diff, stable IDs, unresolved questions, and approval
   digest. Stop and wait for the author.
8. Only after the author explicitly approves that exact digest, call `bootstrap approve` with
   `--bootstrap-id` and `--approval-digest`, then call `bootstrap apply`.

Do not treat “continue”, ordinary feedback, or approval of another revision as authorization.

## Later Intent Revision

1. Run `novel --project <root> intent show --json`.
2. Prepare one or more replacement UTF-8 files under a unique
   `<root>/candidates/intent/<operation>/` directory and call `intent prepare` with only the
   changed file options.
3. Run `intent inspect`; show its Diff and digest, then wait.
4. After exact author approval, call `intent approve`. Use `intent apply` for a standalone change,
   or leave it approved for inclusion by ID in a Publish Plan.

Never edit formal Intent files, the Ledger, or SQLite directly.

## Diagnostics

Preserve the `diagnostic_id` returned by every CLI JSON envelope. When a call fails, report its
stable error code and diagnostic ID, then run
`novel diagnostics show --diagnostic-id <id> --json` before retrying or proposing recovery.
Diagnostic records are operational evidence, not Novel business data or author approval.
