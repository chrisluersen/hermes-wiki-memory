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

### P0.3 Use one GBrain owner

- Replace one-`gbrain serve`-per-provider-process behavior with a shared-owner
  connection strategy.
- Never remove a lock held by a live owner.
- Degrade to lexical recall when attachment is unavailable.

Acceptance:

- Two provider processes against one PGLite brain do not start competing owners.
- Both can recall, or the non-owner reports `degraded` and uses lexical fallback.
- Owner restart reconnects without data loss.

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

## P1 — Durable behavior

### P1.1 Capture, do not auto-promote

- Route inferred session/delegation insights to the configured capture folder.
- Record session provenance, extraction method, timestamp, and captured status.
- Keep explicit memory-write behavior separately configurable.

Acceptance:

- Session extraction never edits an existing topic or project page directly.
- Captures can be traced to their source session.
- Duplicate end-of-session delivery is idempotent.

### P1.2 Add real lexical fallback

- Implement bounded Markdown lexical search independent of GBrain.
- Exclude archives/generated paths according to configuration.
- Return the same bounded recall-block contract as semantic search.

Acceptance:

- Expected pages are found with GBrain stopped.
- Recall stays within configured context size.
- Recalled context is fenced so it is not recursively captured as new memory.

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

### P1.4 Add truthful health

- Report `available`, `degraded`, or `unavailable` plus component facts.
- Keep dashboard read-only.
- Avoid lock-taking health commands on request paths.

Acceptance:

- Tests cover healthy GBrain, missing GBrain, stale embeddings, read-only Wiki,
  missing Wiki, and dashboard failure.
- No health result claims semantic recall when only lexical recall works.

### P1.5 Fix backup and uninstall

- Make `backup_paths()` initialization-free.
- Discover configured GBrain state rather than assuming `~/.gbrain`.
- Add a disposable representative restore check.
- Document and test data-preserving uninstall.

Acceptance:

- Backup includes canonical external paths or explicitly records rebuild policy.
- Restored fixture passes Git integrity, page read, lexical query, and a semantic
  query when embeddings are configured.
- Uninstall twice leaves Wiki and session bytes unchanged.

## P2 — Quality and release

### P2.1 Establish a recall evaluation set

Track expected page, rank, latency, retrieval path, and context size for a small
set of stable questions. Keep the fixture synthetic for public CI.

### P2.2 Make extraction claims honest

Either rename heuristic extraction accordingly or add a bounded structured
extractor. Do not describe regex extraction as LLM extraction.

### P2.3 Expand CI to behavioral tests

CI must run the provider lifecycle, path/config, concurrency, outage fallback,
backup/restore, uninstall, and dashboard API tests—not only compilation and
manifest parsing.

### P2.4 Publish a hardening release

After P0 and P1 pass:

- update README and setup guide;
- document known limitations;
- publish a changelog entry;
- tag the next compatible release.

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

Keep the implementation near:

- 6–8 focused Python modules;
- 20–30 meaningful behavioral tests;
- one provider, one Wiki configuration model, and one shared GBrain connection
  strategy;
- no new persistent database.
