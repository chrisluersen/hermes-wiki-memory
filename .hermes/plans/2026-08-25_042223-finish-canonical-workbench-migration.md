# Finish Canonical Workbench Migration — Bounded Execution Plan

> **For Hermes:** Repository implementation and handoff publication are
> complete. Use this addendum as historical implementation evidence and follow
> `AGENTS.md` plus `SETUP.md` for a new Personal installation. The original
> architecture and safety boundaries remain binding. No real Personal Wiki
> inventory, migration, configuration activation, credential use, semantic
> activation, cleanup, or deletion is authorized by repository completion.

**Goal:** Finish and verify the existing one-time Personal Wiki migration implementation without expanding it into a generalized migration system.

**Authoritative base:** `26b0caf8ead290529c900487df30cf68563a169f` on local `master` and `origin/master` when this addendum was written.

**Architecture to preserve:** One repository-owned `plan → apply → verify → rollback` workflow. Normal plugin startup remains non-destructive. Markdown remains canonical. GBrain remains separate, derived, and inactive. `adopt-existing` remains compatibility behavior, not the intended Personal Hermes end state.

> **Repository implementation status: complete.** Merged commit:
> `f4a408c3a84bb44ae0adc202dd395587b61087b7` (PR #10). Local and
> post-merge Ubuntu/Windows verification passed. Remaining work is
> Personal-Hermes-only and begins with a separately approved read-only inventory
> and operator choice between mapping in place and the preferred one-time
> migration. No live Personal Wiki effect is authorized by this closeout.
>
> **Repository handoff status: complete.** PR #11 merged the executable
> cold-start handoff at `0adba55c4ad9756ecec54217190f8aaef566ba96`; post-merge
> Ubuntu/Windows CI and a fresh-clone bootstrap passed. Current Hermes can
> false-positive on instruction-bearing repositories during plugin scanning;
> `SETUP.md` records the verified profile-local disable/install/restore sequence
> plus exact installed-SHA and clean-tree checks.

---

## Scope-control rule

Fix only a proven correctness, data-loss, portability, or cold-start blocker. If current code already satisfies a requirement, prove it instead of rewriting it.

Do **not** add:

- a startup choice menu or interactive setup wizard;
- plugin-startup migration behavior;
- a daemon, database, queue, or background worker;
- a generalized workflow, schema, ontology, or approval engine;
- continuous legacy/canonical synchronization;
- automatic archival or title-only wikilink inference;
- a general Markdown parser;
- semantic/GBrain activation or indexing;
- automatic config activation;
- new packaging/executable surfaces;
- metadata/timestamp perfection work;
- additional migration documents unless a verified cold-start gap requires one;
- broad refactors or multi-agent simplification sweeps.

Defer non-blocking improvements explicitly rather than implementing them.

---

## Gate 1 — Re-establish current state

1. Read `AGENTS.md`, this addendum, and the original migration plan.
2. Verify this addendum's SHA-256 if the invoking prompt supplies one.
3. Fetch `origin`; require `HEAD == origin/master == 26b0caf8ead290529c900487df30cf68563a169f`, or stop and report drift before mutation.
4. Inspect all tracked and untracked changes. Preserve the existing uncommitted migration implementation; do not restart it or overwrite concurrent work.
5. Confirm no provider startup/runtime files changed unless already required by the approved plan.
6. Run the tight interrupted test first to determine current state:

```bash
python tests/run.py tests/test_migration.py::test_resume_reconciles_exact_post_operation_pre_journal_crash -q
```

The prior invocation was interrupted; do not assume pass or fail.

---

## Gate 2 — Close only material blockers with strict TDD

### 2.1 Reviewed unknown-root decisions

Add the smallest explicit mechanism that lets an operator resolve plan blockers for unknown roots and archive candidates, then regenerate a deterministic plan.

Requirements:

- use a small reviewed JSON decision file or equally small explicit CLI input;
- bind decisions into the canonical plan hash;
- support only needed actions such as retain, map to an exact safe relative destination, or mark review-required;
- validate paths with existing plan containment rules;
- reject unknown decision keys/actions, duplicate destinations, and traversal;
- never mutate the Wiki during decision application/planning;
- do not create a workflow framework or interactive questionnaire engine.

### 2.2 Windows reparse points

Inventory Windows junctions/reparse points as unsupported source objects without descending into them.

Requirements:

- inspect `st_file_attributes`/`FILE_ATTRIBUTE_REPARSE_POINT` where available;
- preserve existing symlink non-traversal behavior;
- add a platform-neutral unit seam for reparse classification plus a real junction test only where runner permissions permit;
- lack of junction privileges may skip the real-object test, but classification logic must remain covered.

### 2.3 Crash-window resume reconciliation

Complete exact reconciliation for a crash after a filesystem operation succeeds but before `operation-complete` reaches the journal.

Requirements:

- reconcile only when the destination's exact expected hash exists and the source state exactly matches the operation class;
- append an explicit reconciliation event before continuing;
- refuse ambiguous, partial, mismatched, or unexpected states;
- preserve current drift refusal and completed-operation validation;
- run the existing crash-window regression red/green.

### 2.4 Bounded large-file handling

Replace whole-file hashing/copying on potentially large source files with bounded streaming.

Requirements:

- stream SHA-256 in fixed-size chunks;
- stream move/copy content to same-directory temporary files with flush/fsync and post-copy hash verification;
- avoid storing binary file bytes in memory;
- Markdown files may be decoded for exact planned rewrites, but impose a documented/reviewed size limit and block oversized rewrite candidates rather than loading unbounded content;
- add a synthetic large-file test proving bounded reads or streaming behavior;
- do not build a chunking framework.

### 2.5 Independent backup/rehearsal proof and pre-apply safety

Finish and verify the recently added evidence hardening.

Requirements:

- independently stream-hash the external backup artifact and compare it with its declared SHA-256;
- independently inventory the isolated rehearsal restore and require its source-tree digest to match the plan;
- bind rehearsal evidence to the exact source-tree and plan hashes;
- run the forged-backup and tampered-restore regressions;
- exercise apply against the isolated rehearsal copy through final verification before treating rehearsal as successful;
- ensure the canonical apply path never trusts a bare `verified: true` declaration;
- do not implement archive creation inside this migration CLI; backup creation remains a separately approved effect.

### Gate 2 verification

Run focused migration and documentation tests after every material fix. Do not add optional work because a reviewer suggests style or extensibility improvements.

---

## Gate 3 — One canonical verification pass

After Gate 2 bytes stop changing, run exactly one complete local verification cycle:

```bash
python tests/run.py tests/test_migration.py tests/test_migration_lifecycle.py tests/test_migration_cli.py tests/test_documentation.py -q
python tests/run.py
python -m py_compile __init__.py wiki_client.py recovery.py migration.py migration_cli.py dashboard/plugin_api.py
node --check dashboard/dist/index.js
hermes plugins doctor --ci .
git diff --check
git fsck --strict
```

Warnings and privilege-based skips must be reported honestly. A passing focused test is not a substitute for the full suite.

---

## Gate 4 — One complete synthetic cold walkthrough

Use a newly created disposable synthetic Wiki and external evidence directory. Do not use or inspect a real Work or Personal Wiki.

The fixture must include:

- `Inbox`, `Projects`, `Topics`, `Ideas`, `Clippings`, and `Notes`;
- standard retained root governance files;
- `.obsidian` and an attachment folder;
- nested Markdown and binary attachments;
- Unicode paths;
- path-qualified wikilinks, embeds, and relative Markdown links;
- one reviewed unknown-root decision;
- a sufficiently large synthetic binary to exercise streaming;
- no secrets or private content.

Walk through the public CLI only:

1. `plan` — prove source tree unchanged; inspect plan/report/hash.
2. Create synthetic external backup/rehearsal evidence in the disposable area.
3. `apply` — use exact approved hash, external journal, and lock.
4. `verify` — require verified status, exact accounting/hashes, resolved links, lexical role checks, capture readiness, semantic inactivity, and no legacy roots.
5. `rollback` — restore exact pre-migration digest and retain migrated tree.
6. Confirm no artifacts escaped the disposable area.

Record exact commands, exit codes, plan/source/final/restored hashes, operation counts, and verification status in a temporary local report. Do not commit disposable evidence.

---

## Gate 5 — Privacy, scope, and no-live-state checks

Verify:

- exact changed-file allowlist;
- no credential values, private Wiki text, employer details, local user paths, private source IDs, or retained evidence are present in repository additions;
- no live Wiki, Hermes profile/config, GBrain, MCP, gateway, backup, restore, release, or GitHub state changed;
- normal provider startup still imports/calls no migration code;
- `v0.4.0` files/history were not rewritten;
- no setup menu, daemon, generalized engine, second canonical layer, semantic activation, or cleanup behavior was added.

Use targeted scans. Do not read `.env` or print secrets.

---

## Gate 6 — One bounded final independent review

After all implementation bytes and docs are stable, obtain one independent review covering both:

- compliance with this addendum and the original plan's still-binding architecture/safety constraints; and
- filesystem/data-loss security, including containment, reparse points, large files, evidence proof, journal reconciliation, verification, and rollback.

Review the exact final diff plus untracked source/test files. Fix only findings that are correctness, data-loss, portability, privacy, or cold-start blockers. Defer style, abstraction, flexibility, or future-feature suggestions.

If bytes change, rerun affected focused tests, the canonical full verification, the synthetic walkthrough if behavior changed, and one final review of the changed bytes. Do not begin repeated review loops for non-blocking suggestions.

---

## Gate 7 — Bind payload and stop for local commit HITL

Before asking the user:

1. Fetch authoritative remote and verify the base has not moved.
2. Record:
   - base SHA;
   - exact changed/untracked file list;
   - deterministic payload SHA-256 over relative paths and file bytes;
   - full and focused test results;
   - compilation/plugin-doctor/Git checks;
   - synthetic walkthrough hashes/results;
   - privacy/no-live-state result;
   - independent review verdict and deferred non-blockers.
3. Draft a concise commit message and PR title/body locally without creating external state.
4. Use the Hermes questionnaire feature for an exact **local commit only** HITL.

Do not infer approval for branch creation, push, PR, merge, tag, release, real Wiki inventory/migration, config activation, semantic work, or cleanup.

---

## Completion boundary

This addendum and repository publication are complete. Remaining work starts in
the intended Personal Hermes profile and consists only of separately approved
installation-specific effects: root/mode selection, backup/restore, inventory,
rehearsal, exact plan approval, apply/verify, lexical-only activation, optional
semantics, and cleanup. Repository completion never authorizes those effects.
