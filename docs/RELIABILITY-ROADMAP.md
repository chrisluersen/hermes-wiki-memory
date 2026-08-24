# Reliability Roadmap

This roadmap applies the retained principles in
[`SENESCHAL-DESIGN-NOTES.md`](SENESCHAL-DESIGN-NOTES.md) without expanding
Hermes Wiki Memory into a governance platform.

## Product identity

- Repository: `chrisluersen/hermes-wiki-memory`
- Display name: **Hermes Wiki Memory**
- Provider ID: `wiki`
- Config namespace: `memory.wiki.*`
- Positioning: local-first Hermes memory backed by a canonical Markdown Wiki and
  a shared, rebuildable GBrain index

The repository and provider names remain unchanged.

## P0 — Correctness blockers

### P0.1 Implement the Hermes provider contract directly

- Make `WikiMemoryProvider` subclass Hermes `MemoryProvider`.
- Implement the minimal configuration schema required by `hermes memory setup`.
- Preserve provider ID `wiki`.

Acceptance:

- Hermes discovers and loads the provider through the documented plugin API.
- Memory-manager lifecycle tests cover initialize, prefetch, session switch,
  session end, memory-write hook, delegation hook, and shutdown.

Status: provider subclassing, setup, initialization, prefetch, pre-compression,
session switching/end, memory/delegation hooks, degraded prompt text, and
shutdown have behavioral coverage. The exact merged commit also passed a
disposable installed-package lexical-only activation and reload test.

### P0.2 Resolve one Wiki configuration everywhere

- Introduce one immutable resolved configuration object.
- Use it in the provider, file client, dashboard, backup declaration, and tests.
- Honor `WIKI_PATH` as a compatibility override while preferring
  `memory.wiki.root` for normal setup.
- Support semantic-role folder mapping instead of hardcoded
  `knowledge/...`/`work/...` paths.
- Provide an `adopt-existing` layout that maps existing folders without moving
  content. The new-Wiki default is `Inbox/`, `Projects/`, `Knowledge/`,
  `Sources/Originals/`, `Sources/Notes/`, `Archive/`, and `_meta/`.
- Treat `Clippings/` as a compatible existing name for `Sources/Originals/`
  and `Topics/`/`Ideas/` as compatible existing names for `Knowledge/`.
- Keep page subtype, lifecycle, provenance, and stable identity in frontmatter
  and links rather than multiplying folders.

Acceptance:

- A custom Wiki root controls every read, write, dashboard count, and backup path.
- No code path silently falls back to `<HERMES_ROOT>/wiki` after configuration.
- Existing six-folder and generic Wiki fixtures require no migration.
- A new-Wiki fixture uses the small role-based layout without requiring
  `entities/`, `concepts/`, `comparisons/`, `queries/`, `work/`, `personal/`,
  `sessions/`, or `plans/` directories.

Status: matching root precedence, semantic roles, multiple knowledge paths,
exact-case validation, dashboard counts, setup persistence, and
`adopt-existing` are implemented without migration. The provider and isolated
dashboard still use equivalent read-only resolvers rather than one importable
cross-loader configuration object.

### P0.3 Use one GBrain owner

- Replace one-`gbrain serve`-per-provider-process behavior with a shared-owner
  connection strategy.
- Never remove a lock held by a live owner.
- Degrade to lexical recall when attachment is unavailable.

Acceptance:

- Two provider processes against one PGLite brain do not start competing owners.
- Both can recall, or the non-owner reports `degraded` and uses lexical fallback.
- Owner restart reconnects without data loss.

Status: the provider owns no GBrain process and dispatches the shared Hermes MCP
`recall` tool only after exact source/timeout/toolset attestation. Missing or
failed attachment degrades to lexical recall. A live configured-owner restart
test remains approval-gated.

### P0.4 Make Wiki writes safe

- Add contained relative-path resolution.
- Add cross-process locking and prior-fingerprint conflict detection.
- Use temporary-file, flush, and atomic-replace writes.
- Preserve concurrent append operations.

Acceptance:

- Parallel append test has no lost update.
- Injected interruption leaves the prior file intact.
- Absolute, traversal, reserved-name, and out-of-root paths fail safely.
- No temporary or lock file leaks remain after success or failure.

Status: containment, reserved-name/ADS rejection, immutable capture creation,
atomic replace, concurrent append, prior-fingerprint replacement conflicts,
case aliases, transient Windows lock-file initialization/repair, and
cross-process stress are implemented. Explicit Windows reparse-point coverage
remains open. The supported model is cooperative writers with under-lock
resolved-containment revalidation; adversarial post-check junction swaps require
native handle-relative I/O and remain explicitly out of scope.

## P1 — Durable behavior

### P1.1 Capture, do not auto-promote

- Route inferred session/delegation insights to the configured capture folder.
- Record session provenance, extraction method, timestamp, and captured status.
- Keep explicit memory-write behavior separately configurable.

Acceptance:

- Session extraction never edits an existing topic or project page directly.
- Captures can be traced to their source session.
- Duplicate end-of-session delivery is idempotent.

Status: implemented for session insights, delegation results, and explicit
memory add/replace/remove events. Captures use forced Hermes redaction, stable
event IDs, immutable pages, source provenance, replay byte-idempotency, and
collision refusal. Capture requires an existing configured capture directory.

### P1.2 Add real lexical fallback

- Implement bounded Markdown lexical search independent of GBrain.
- Exclude archives/generated paths according to configuration.
- Return the same bounded recall-block contract as semantic search.

Acceptance:

- Expected pages are found with GBrain stopped.
- Recall stays within configured context size.
- Recalled context is fenced so it is not recursively captured as new memory.

Status: implemented with file/byte/time/result/context ceilings and synthetic
evaluation coverage. The provider's capture heuristics scan original session
messages, not injected prefetch blocks.

### P1.3 Apply explicit Wiki retrieval policy

- Hard-exclude runtime, generated, cache, session-export, and quarantine paths.
- Demote preserved originals and Archive content by default.
- Prefer durable Knowledge and active project outcomes for ordinary recall.
- Keep full Hermes sessions in Hermes state; if transcript derivatives are
  indexed, isolate them as a separate derived source.

Acceptance:

- A fixture query does not return `_meta/`, `.hermes/`, session exports, or
  generated artifacts as ordinary Wiki knowledge.
- Existing `Clippings/` and new `Sources/Originals/` receive equivalent policy.
- Archive retrieval is available explicitly without polluting ordinary recall.

Status: ordinary recall excludes runtime/generated/cache/session paths, prefers
knowledge/projects, and demotes originals/archive. An explicit archive-only
query mode is still optional future work.

### P1.4 Add truthful health

- Report `available`, `degraded`, or `unavailable` plus component facts.
- Keep dashboard read-only.
- Avoid lock-taking health commands on request paths.

Acceptance:

- Tests cover healthy GBrain, missing GBrain, stale embeddings, read-only Wiki,
  missing Wiki, and dashboard failure.
- No health result claims semantic recall when only lexical recall works.

Status: implemented for Wiki readability/writability, lexical recall, attested
semantic registration, and capture readiness. Embedding coverage is reported as
unknown unless proven; a live stale-embedding probe remains approval-gated.

### P1.5 Fix backup and uninstall

- Make `backup_paths()` initialization-free.
- Treat GBrain state as derived and record rebuild inputs rather than copying a
  live PGLite directory as required canonical backup.
- Add a disposable representative restore check.
- Document and test data-preserving uninstall.

Acceptance:

- Backup includes canonical external paths or explicitly records rebuild policy.
- Restored fixture passes Git integrity, page read, lexical query, and a semantic
  query when embeddings are configured.
- Uninstall twice leaves Wiki and session bytes unchanged.

Status: initialization-free canonical Wiki discovery, secret-free rebuild
manifest, temporary tree/Git/lexical restore verification, and idempotent
plugin-code removal are implemented. Hermes sessions remain outside plugin
ownership. A representative private-Wiki restore is approval-gated before
canonical activation; a separate isolated semantic canary is approval-gated
before semantic activation. Neither blocks an explicitly experimental lexical-
capable release.

## P2 — Quality and release

### P2.1 Establish a recall evaluation set

Track expected page, rank, latency, retrieval path, and context size for a small
set of stable questions. Keep the fixture synthetic for public CI.

Status: a deterministic synthetic lexical fixture records route, expected page,
latency, injected size, and exclusion violations. A keyed semantic canary is
deferred until embedding settings and cost are approved.

### P2.2 Make extraction claims honest

Either rename heuristic extraction accordingly or add a bounded structured
extractor. Do not describe regex extraction as LLM extraction.

Status: capture metadata and documentation identify current extraction as
heuristic rather than LLM-based.

### P2.3 Expand CI to behavioral tests

CI must run the provider lifecycle, path/config, concurrency, outage fallback,
backup/restore, uninstall, and dashboard API tests—not only compilation and
manifest parsing.

Status: implemented on Ubuntu and Windows using the standalone test runner.

### P2.4 Publish a hardening release

After P0 and P1 pass:

- update README and setup guide;
- document known limitations;
- publish a changelog entry;
- tag the next compatible release.

Status: version `0.4.0` is merged to `master`; PR publication and disposable
installed-package validation are complete. Release-documentation publication,
tag creation, and GitHub Release publication remain separate approval-gated
effects. Live recovery and semantic evidence remain activation gates rather
than experimental-release gates.

## Non-goals

This roadmap does not include:

- an estate manager;
- a task or project system;
- approval or policy engines;
- a second canonical database;
- multi-provider routing;
- cross-organization federation;
- automatic canonicalization of inferred knowledge;
- broad autonomy or destructive self-repair.

## Scope ceiling

Keep one provider, one Wiki configuration model, and one shared GBrain
connection strategy. Do not add a persistent database, daemon, migration
engine, governance framework, or duplicated GBrain implementation. Add tests
for behavior and regressions rather than targeting an arbitrary test count.
