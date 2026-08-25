# Canonical Personal Wiki Workbench Migration Implementation Plan

> **For Hermes:** Implement this plan task-by-task using test-driven development and independent review. This plan is non-authorizing: it does not authorize a real Wiki migration, Git commit/push/PR/merge, release mutation, credential use, semantic activation, cleanup, or deletion.

**Goal:** Extend `hermes-wiki-memory` with a safe, explicit, one-time migration path from an existing Personal Wiki into one canonical power-user workbench layout, while keeping normal plugin startup non-destructive and retaining `adopt-existing` for users who prefer it.

**Architecture:** Add a small repository-owned migration surface with four explicit phases: plan, apply, verify, and rollback. Planning is deterministic and read-only; apply is bound to an approved plan hash, source-tree digest, verified external backup, and successful isolated rehearsal; verification proves one-layout completion and lexical behavior; rollback is backup-first. Do not build a daemon, generalized schema engine, database, dual-layout synchronization layer, or automatic semantic activation.

**Tech stack:** Python 3.11 standard library where practical; existing repository containment/recovery/locking helpers; pytest synthetic fixtures; Hermes plugin doctor; Ubuntu and Windows CI.

> **Repository implementation status: complete.** Merged commit:
> `f4a408c3a84bb44ae0adc202dd395587b61087b7` (PR #10). Local and
> post-merge Ubuntu/Windows verification passed. Remaining work is
> Personal-Hermes-only: exact Wiki root/mode selection, backup creation,
> isolated restore, inventory/decisions, rehearsal, plan approval, apply,
> verification, lexical-only activation, optional semantics, and cleanup—each
> under its separately stated HITL gate.
>
> **Repository handoff status: complete.** The executable Personal-Hermes
> backup/install/setup handoff was merged at
> `0adba55c4ad9756ecec54217190f8aaef566ba96` (PR #11), and post-merge
> Ubuntu/Windows CI passed. Current Hermes's install scanner can false-positive
> on this instruction-bearing repository; `SETUP.md` contains the verified,
> reversible profile-local scanner exception and exact installed-SHA readback.

---

## Desired end state

After one approved migration, the Personal Wiki has one canonical structure:

```text
Inbox/
Projects/
Knowledge/
Sources/
  Originals/
  Notes/
Archive/
_meta/
```

The final provider configuration is:

```yaml
memory:
  provider: wiki
  wiki:
    layout: workbench
    paths:
      capture: Inbox
      projects: Projects
      knowledge: Knowledge
      sources:
        originals: Sources/Originals
        processed: Sources/Notes
      archive: Archive
```

There is no permanent legacy/canonical dual-layout layer after migration. `adopt-existing` remains supported, but Personal Hermes may explicitly choose a one-time migration to `workbench`.

## Authority and hard boundaries

- Work only in the public `hermes-wiki-memory` repository during implementation.
- Use synthetic fixtures only; do not inspect or publish a real Personal Wiki during repository development.
- Do not modify the Work Wiki, Work Hermes profile, live Work GBrain/MCP/gateway, backups, restores, or retained evidence.
- Normal provider startup must remain non-destructive.
- Planning must write no Wiki/config content.
- Real Personal Wiki inventory, classification, backup, rehearsal, apply, activation, semantic rebuild, and cleanup remain separate Personal-Hermes HITLs.
- Do not change `v0.4.0` or its GitHub Release unless a separate new-release proposal is justified and approved.

## Explicit non-goals

Do not build:

- a migration daemon;
- continuous synchronization between legacy and canonical layouts;
- a generalized workflow or schema engine;
- a new database;
- a second canonical layer;
- automatic semantic activation;
- automatic archival based only on age;
- Clippings OCR or source-content rewriting;
- generalized ontology conversion;
- a benchmark platform;
- a governance framework;
- background cleanup.

---

### Task 1: Re-establish exact repository baseline and implementation seams

**Objective:** Confirm current remote state and identify the smallest stable interfaces before writing code.

**Files:**
- Read: `AGENTS.md`
- Read: `README.md`
- Read: `SETUP.md`
- Read: `docs/WIKI-FOLDER-MAPPING.md`
- Read: `docs/RELIABILITY-ROADMAP.md`
- Read: `__init__.py`
- Read: `wiki_client.py`
- Read: `recovery.py`
- Read: `tests/test_capture_mapping.py`
- Read: `tests/test_recovery.py`
- Read: `tests/test_documentation.py`
- Likely create later: `migration.py`
- Likely create later: `migration_cli.py`
- Likely create later: `tests/test_migration.py`

**Steps:**

1. Fetch `origin` and require clean local `master == origin/master`.
2. Record the exact full base SHA and current `v0.4.0` peeled commit.
3. Trace role resolution, path containment, rebuild manifests, tree hashing, lexical retrieval, capture readiness, and lock conventions to their definitions/usages.
4. Inspect current CLI/plugin packaging conventions. Decide the smallest executable surface:
   - preferred: `python migration_cli.py <plan|apply|verify|rollback> ...` from a reviewed checkout;
   - use another surface only if current repository conventions make it materially safer/smaller.
5. Write a short implementation-seam note in the plan execution log; do not add a design framework.
6. Run the current full suite and plugin doctor as the untouched baseline.

**Verification:**

```bash
python -m pip install fastapi pyyaml pytest
python tests/run.py
python -m py_compile __init__.py wiki_client.py recovery.py dashboard/plugin_api.py
node --check dashboard/dist/index.js
hermes plugins doctor --ci .
git diff --check
```

Expected: current suite green; no working-tree changes.

---

### Task 2: Define frozen migration-plan and result contracts

**Objective:** Define small versioned JSON contracts that bind inventory, operations, rewrites, preconditions, rollback, and results without creating a generalized engine.

**Files:**
- Create: `migration.py`
- Create: `tests/test_migration.py`
- Possibly create: `docs/MIGRATION-CONTRACT.md` only if the JSON contract cannot be explained concisely in `SETUP.md`; avoid duplicate prose.

**Contract requirements:**

The plan must include at least:

- schema version;
- canonical source root identity without publishing machine-specific paths;
- source-tree digest;
- generated timestamp excluded from the canonical plan hash or otherwise normalized deterministically;
- exact ordered inventory entries with relative path, object type, byte size, SHA-256, and relevant metadata;
- proposed source/destination operations;
- operation class: retain, mkdir, move, rewrite, review-required, exclude, unsupported;
- expected source preimage hash;
- collision and ambiguity status;
- exact planned link/embed/attachment rewrites and expected postimage hash;
- rollback operation or backup-restore requirement;
- exclusions and unresolved blockers;
- final proposed `layout: workbench` config;
- canonical plan SHA-256 over normalized content.

The result contract must include:

- plan SHA-256;
- source-tree digest;
- final-tree digest;
- applied operation count;
- verified operation count;
- failures/unresolved items;
- link/attachment verification totals;
- lexical/capture verification facts;
- semantic state (must remain inactive unless separately approved);
- rollback readiness.

**TDD steps:**

1. Write failing tests for deterministic canonical JSON and stable plan SHA.
2. Write failing tests that timestamps/order differences do not alter a logically identical canonical plan.
3. Write failing tests that any operation/path/hash change alters the plan SHA.
4. Implement minimal dataclasses/serialization/hash functions.
5. Reject unknown schema versions and duplicate source/destination entries.
6. Run focused tests.

**Verification:**

```bash
python tests/run.py tests/test_migration.py -q
```

Expected: contract tests pass.

---

### Task 3: Implement read-only recursive inventory

**Objective:** Inventory every canonical Wiki object without mutating it or following unsafe boundaries.

**Files:**
- Modify: `migration.py`
- Modify: `tests/test_migration.py`

**Required behavior:**

- Recursively inventory files, directories, hidden paths, attachments, and existing `.obsidian` configuration.
- Record symlinks, Windows junctions/reparse points, and unsupported/special objects without traversing them.
- Reject or mark review-required any resolved escape outside the Wiki root.
- Preserve exact spelling, case, Unicode, bytes, and relative paths.
- Detect Windows reserved names, ADS-like names, case-fold collisions, Unicode-normalization collisions, duplicate destinations, and malformed paths.
- Exclude runtime/generated paths from target recall, but still account for every source object in the migration manifest.
- Produce a deterministic source-tree digest.
- Perform zero source-tree writes, directory creation, config changes, or timestamp modifications.

**Synthetic fixtures:**

- legacy root with `Inbox`, `Projects`, `Topics`, `Ideas`, `Clippings`, `Notes`;
- hidden files and `.obsidian`;
- nested attachments;
- Unicode names;
- reserved/ADS-like names;
- case-only collision candidates;
- symlink/junction escape where platform permissions permit;
- unknown root folders;
- missing optional roles.

**TDD steps:**

1. Write a snapshot-before/snapshot-after zero-write test.
2. Write recursive inventory and digest tests.
3. Write collision/special-object tests.
4. Implement minimal safe inventory.
5. Re-run focused tests on Windows-compatible and POSIX-compatible fixtures.

---

### Task 4: Implement canonical role classification and move planning

**Objective:** Propose one canonical layout while failing closed on ambiguity and preserving useful relative structure.

**Files:**
- Modify: `migration.py`
- Modify: `tests/test_migration.py`

**Default mappings:**

- `Inbox/**` → `Inbox/**`
- `Projects/**` → `Projects/**`
- `Topics/**` → `Knowledge/Topics/**`
- `Ideas/**` → `Knowledge/Ideas/**`
- `Clippings/**` → `Sources/Originals/**`
- `Notes/**` → `Sources/Notes/**`
- existing `Knowledge/**`, `Sources/Originals/**`, `Sources/Notes/**`, `Archive/**`, `_meta/**` retain canonical roles
- `.obsidian/**` and attachment folders retain their existing paths unless a separately justified exact move is planned
- completed/superseded/inactive content becomes `review-required` for Archive; never archive solely from age or filename
- unknown roots become explicit operator-classification questions; never guess

**Rules:**

- Preserve relative organization below each mapped root.
- Do not flatten `Topics` and `Ideas` into one directory when duplicate names could collide; retaining `Knowledge/Topics` and `Knowledge/Ideas` is acceptable inside the single `Knowledge` role.
- Never overwrite destinations.
- A source already at the exact destination is retained, not moved.
- The plan is blocked while any collision or unknown-root decision is unresolved.

**TDD steps:**

1. Write expected-operation tests for every default mapping.
2. Write duplicate-name tests across Topics/Ideas and source trees.
3. Write unknown-root and archive-review tests.
4. Implement the minimal classifier/planner.
5. Verify deterministic operation order and stable plan SHA.

---

### Task 5: Parse and plan link/embed/attachment rewrites

**Objective:** Identify only references that must change because of planned moves.

**Files:**
- Modify: `migration.py`
- Modify: `tests/test_migration.py`

**Supported references:**

- path-qualified Obsidian wikilinks: `[[path/to/page]]`;
- Obsidian embeds: `![[path/to/file.ext]]`;
- Markdown links/images with relative paths;
- attachment references affected by planned moves.

**Rules:**

- Do not rewrite ordinary title-only wikilinks unless a collision or explicit path change makes it necessary and deterministic.
- Preserve aliases, headings, block IDs, query strings, fragments, display text, and surrounding bytes.
- Do not rewrite code fences or inline code.
- Every rewrite records source preimage hash, exact replacement range/value, and expected postimage hash.
- Ambiguous links block the plan and become operator decisions.

**TDD steps:**

1. Add fixtures for wikilinks, embeds, Markdown links, images, aliases, fragments, headings, code blocks, and Unicode paths.
2. Write exact-byte expected rewrite tests.
3. Write ambiguity and no-op tests.
4. Implement the smallest parser/rewrite planner necessary for these formats; do not build a general Markdown parser unless current dependencies already provide one and it materially reduces risk.
5. Verify unchanged files remain byte-identical.

---

### Task 6: Emit human-readable and machine-readable plans

**Objective:** Make the migration understandable and approvable by Personal Hermes and the user.

**Files:**
- Create: `migration_cli.py`
- Modify: `migration.py`
- Modify: `tests/test_migration.py`

**CLI shape (preferred):**

```bash
python migration_cli.py plan \
  --wiki <path> \
  --json-out <external-plan.json> \
  --report-out <external-plan.md>
```

**Behavior:**

- Planning is read-only.
- Output locations must be outside the canonical Wiki unless explicitly placed under an existing `_meta` only after separate approval; default to external paths.
- Human report summarizes counts, mappings, collisions, unknown roots, rewrites, exclusions, rollback requirements, final config, and exact plan SHA.
- CLI exits nonzero when unresolved decisions block apply, while still writing a reviewable blocked plan/report.
- No external credentials or semantic calls.

**Tests:**

- zero Wiki writes;
- deterministic JSON/report for the same tree;
- blocked-plan exit code;
- exact plan-hash display;
- safe output-path containment and refusal to overwrite unless explicitly allowed.

---

### Task 7: Bind apply to backup, rehearsal, plan hash, and unchanged source tree

**Objective:** Ensure apply cannot run from intent alone.

**Files:**
- Modify: `migration.py`
- Modify: `migration_cli.py`
- Modify: `tests/test_migration.py`
- Reuse: `recovery.py`

**Required apply inputs:**

- canonical Wiki path;
- exact plan JSON path and approved SHA-256;
- exact expected source-tree digest;
- verified external backup archive + manifest/reference;
- successful isolated rehearsal result bound to the same plan/source digest;
- explicit `--apply` or equivalent confirmation flag;
- external migration-lock and journal locations.

**Preconditions:**

- plan schema/version valid;
- supplied hash matches canonical plan hash;
- current source tree equals planned digest;
- backup and rehearsal evidence are readable and match the same source/plan;
- no unresolved operations/collisions/questions;
- destination paths still absent or exactly retained as planned;
- exclusive external migration lock acquired.

**TDD steps:**

1. Write failure tests for every missing/mismatched precondition.
2. Write changed-tree-after-plan and destination-created-after-plan tests.
3. Implement preflight only; verify it performs no Wiki mutation.
4. Add explicit apply confirmation check last.

---

### Task 8: Implement journaled apply with interruption safety

**Objective:** Apply only the approved operations and support deterministic resume or rollback.

**Files:**
- Modify: `migration.py`
- Modify: `migration_cli.py`
- Modify: `tests/test_migration.py`

**Behavior:**

- Journal lives outside canonical content and is append-only.
- Each operation records pending/start/completed/verified states with plan hash and pre/post hashes.
- Never overwrite a destination.
- Create canonical directories only when declared in the approved plan.
- Use same-volume atomic renames where safe; otherwise copy-to-temp, fsync/close, verify hash, atomic destination replace only when destination is absent, then retain source until operation verification permits removal.
- Rewrite only files/ranges declared in the plan, using atomic replacement and postimage verification.
- Preserve timestamps where feasible; record unavoidable metadata changes.
- Interruption leaves enough journal state to resume or roll back deterministically.
- Resume revalidates every completed operation and all remaining preconditions.
- Never delete backup, rehearsal, plan, report, journal, or failed tree.

**Tests:**

- exact successful apply;
- injected interruption after each operation class;
- deterministic resume;
- corrupted journal refusal;
- destination race refusal;
- no unplanned write/delete;
- external lock contention.

---

### Task 9: Implement independent post-migration verification

**Objective:** Prove canonical completeness and behavior without trusting the apply journal alone.

**Files:**
- Modify: `migration.py`
- Modify: `migration_cli.py`
- Modify: `tests/test_migration.py`
- Reuse: `wiki_client.py`

**Verification requirements:**

- every pre-migration object accounted for exactly once;
- no unexpected destination object;
- hashes unchanged except declared rewrites;
- every rewrite matches expected postimage;
- canonical directories exist with exact case;
- no active duplicate legacy taxonomy remains;
- unknown/unresolved content absent from a claimed successful result;
- wikilinks, Markdown links, embeds, and attachments resolve according to supported semantics;
- runtime/generated paths remain excluded;
- lexical retrieval works for representative `Knowledge`, `Projects`, and `Sources/Notes` facts;
- `Sources/Originals` and `Archive` remain demoted;
- `_meta` excluded from ordinary recall;
- a synthetic capture succeeds only in a disposable verification copy or explicit temporary verification context, never by silently writing a production page;
- final proposed config uses `layout: workbench` and canonical paths;
- semantic source remains empty unless separately approved;
- machine-readable result binds plan SHA and final-tree digest.

**CLI shape:**

```bash
python migration_cli.py verify \
  --wiki <migrated-path> \
  --plan <plan.json> \
  --result-out <verification.json> \
  --report-out <verification.md>
```

---

### Task 10: Implement backup-first rollback procedure

**Objective:** Recover canonical bytes from verified backup without pretending reverse renames are sufficient.

**Files:**
- Modify: `migration.py`
- Modify: `migration_cli.py`
- Modify: `tests/test_migration.py`
- Modify: `SETUP.md`

**Behavior:**

- Require verified backup manifest and pre-migration tree digest.
- Restore into a separate target first.
- Verify every restored byte/object against the pre-migration manifest.
- Keep the migrated/failed tree separately until restore verification passes.
- Provide an exact final swap procedure, separately destructive/HITL-gated.
- Never operate against active GBrain/PGLite state.
- After canonical recovery, GBrain remains derived and must be rebuilt separately.
- Cleanup/deletion of failed or superseded trees remains a separate data-loss gate.

**Tests:**

- exact backup restore;
- incomplete/corrupt backup refusal;
- wrong-source manifest refusal;
- retained failed tree;
- no active-store deletion;
- restored final digest equals pre-migration digest.

---

### Task 11: Update Personal Hermes onboarding and documentation

**Objective:** Make one-time canonical migration a first-class, explicit onboarding option without implying destructive startup behavior.

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `SETUP.md`
- Modify: `docs/WIKI-FOLDER-MAPPING.md`
- Modify: `docs/RELIABILITY-ROADMAP.md` only if implementation changes roadmap status
- Modify: `CHANGELOG.md`
- Modify: `tests/test_documentation.py`
- Create: `docs/PERSONAL-HERMES-MIGRATION-PROMPT.md` only if a short copyable prompt cannot fit cleanly in SETUP; otherwise keep it in SETUP to avoid duplicate docs.

**Required documentation changes:**

- Present two onboarding choices:
  - adopt existing layout;
  - one-time migration to canonical workbench.
- Recommend one-time migration for the user's Personal Hermes preference while preserving safe choice/approval.
- Clearly state normal startup never migrates.
- Document plan/apply/verify/rollback commands and evidence gates.
- Include the final canonical config.
- Include a copyable Personal Hermes prompt:

> Clone this repository and switch this session into its root. Read `AGENTS.md`. I explicitly prefer a one-time migration to the canonical power-user workbench layout rather than permanent `adopt-existing` mapping. Inventory my Personal Wiki read-only, classify every existing path, create and verify an external backup and isolated rehearsal restore, then produce an exact hash-bound migration/link-rewrite/rollback plan. Stop for my approval before changing the canonical Wiki. After approval, migrate once, verify bytes, links, attachments, capture, and lexical retrieval, set `layout: workbench`, and leave semantic activation and cleanup separately gated. Do not build a daemon, dual-layout synchronization layer, or generalized migration framework.

- Explain that Personal-Wiki-specific path/classification/collision decisions cannot be known in the public repository.
- Keep release status honest; do not imply `v0.4.0` contains migration unless a new release is separately made.

**Documentation tests:**

- root AGENTS routing and onboarding choice;
- normal startup remains non-destructive;
- plan/apply/verify/rollback all documented;
- backup/rehearsal/plan-hash/apply gates appear before mutation;
- workbench config exact;
- semantics and cleanup separately gated;
- no private paths, content, or credential values.

---

### Task 12: Run full cross-platform and privacy verification

**Objective:** Prove the implementation and docs are release-ready before any publication request.

**Commands:**

```bash
python tests/run.py tests/test_migration.py -q
python tests/run.py
python -m py_compile __init__.py wiki_client.py recovery.py migration.py migration_cli.py dashboard/plugin_api.py
node --check dashboard/dist/index.js
hermes plugins doctor --ci .
git diff --check
git fsck --strict
```

**Additional verification:**

- Run synthetic migration walkthrough on Windows.
- Ensure CI exercises migration tests on Ubuntu and Windows.
- Scan added lines/files for credentials, personal paths, private Wiki names/content, employer details, and private source IDs.
- Verify exact changed-file allow-list.
- Verify no live Wiki, Work Hermes, GBrain, MCP, gateway, backups, restores, or evidence changed.
- Run an independent spec-compliance review and code-quality review on the exact bytes.
- If bytes change after review, rerun review.

---

### Task 13: Prepare exact GitHub publication gates

**Objective:** Finish safe local development, then stop for separate publication decisions.

**Before asking:**

- Fetch authoritative remote and ensure base has not moved; rebase/reapply cleanly if needed.
- Bind exact base SHA, changed-file list, payload SHA-256, test results, synthetic walkthrough evidence, privacy scan, and independent-review verdict.
- Draft PR title/body without creating external state.

**Separate required approvals:**

1. local commit;
2. branch push and PR creation;
3. squash merge only after exact-head readback and green Ubuntu/Windows CI.

Do not infer approval between gates. Do not alter `v0.4.0` or publish a new release without a separate proposal and approval.

---

## Real Personal Wiki execution remains separately gated

Repository implementation does not authorize the actual migration. When Personal Hermes later inventories the real Wiki, it must separately obtain decisions for:

- exact Personal Wiki root;
- external backup destination;
- classification of unknown roots;
- archive candidates;
- filename/case/Unicode collisions;
- ambiguous link rewrites;
- exact plan SHA approval;
- canonical apply;
- final `layout: workbench` config activation;
- optional GBrain rebuild/semantic activation;
- cleanup/deletion of legacy, failed, rehearsal, or backup artifacts.

## Completion criteria

The repository work is complete only when:

- plan/apply/verify/rollback are implemented and synthetically proven;
- normal provider startup remains non-destructive;
- one-layout workbench completion is verified;
- docs and AGENTS guide a cold Personal Hermes correctly;
- full local and Ubuntu/Windows CI are green;
- privacy review passes;
- exact PR is merged under separate approval;
- remote files and post-merge CI are read back;
- no real Wiki was migrated during repository development.
