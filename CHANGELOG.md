# Changelog

All notable changes to **hermes-wiki-memory** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.4.0] - 2026-08-24

### Added
- Shared-owner GBrain integration through Hermes's public tool registry and
  GBrain's `recall` verb. The provider no longer starts, respawns, kills, or
  falls back to private GBrain processes.
- Fail-closed semantic admission requiring exact MCP `GBRAIN_SOURCE` binding,
  a timeout of at most seven seconds, and the matching registered MCP toolset.
- Bounded Markdown lexical fallback with explicit ranking/exclusion policy,
  resolved containment, and file/byte/time/context ceilings.
- Semantic role mapping, `adopt-existing`, exact-case validation, and multiple
  knowledge paths without folder creation or migration.
- Immutable capture events for session insights, delegations, and explicit
  memory add/replace/remove hooks, with stable IDs, forced Hermes redaction,
  replay byte-idempotency, provenance, and collision refusal.
- Truthful `available`/`degraded`/`unavailable` health facts and a role-aware,
  read-only dashboard.
- Canonical-Wiki rebuild manifest, temporary restore/Git verification,
  data-preserving code-removal checks, and a synthetic lexical recall benchmark.
- Ubuntu/Windows behavioral CI with immutable Node-24 action pins.
- Security/contribution guidance, PR and issue templates, and monthly GitHub
  Actions dependency updates.

### Fixed
- `WikiMemoryProvider` now subclasses Hermes's current `MemoryProvider` ABC.
- Matching call-time Wiki-root resolution now applies
  `memory.wiki.root` → `WIKI_PATH` → `<HERMES_ROOT>/wiki` precedence during
  provider initialization, dashboard status, and backup discovery.
- `hermes memory setup` and the dashboard can now discover and persist the
  supported Wiki root and recall-budget settings.
- `backup_paths()` works before initialization and now returns canonical
  Markdown only; live GBrain/PGLite state is explicitly derived/rebuildable.
- Provider shutdown clears only local adapter references and never stops the
  shared Hermes MCP owner.
- Wiki reads/writes reject absolute, traversal, reserved-device, alternate-data-
  stream, non-Markdown, and resolved parent-link escapes.
- Wiki writes now use per-page locking, same-directory temporary files,
  flush/fsync, and atomic replacement; concurrent appends re-read under lock.
- Lock identities are lexical, case-normalized, and independent of target
  existence; Windows extended-path aliases and existing on-disk casing are
  normalized under lock, transient lock-file initialization and replace sharing
  violations are retried, interrupted zero-length lock sentinels are repaired,
  and lock artifacts live outside the Wiki.
- Plugin manifest now declares the exclusive memory-provider kind.

### Remaining limitations
- The operator's live GBrain MCP entry has not been changed; semantic prefetch
  stays disabled until exact source binding and a safe timeout are approved.
- A representative private-Wiki restore remains required before canonical-
  profile activation. An isolated keyed GBrain canary remains required before
  semantic activation. A full private-Wiki semantic rebuild is not a release prerequisite.
- Explicit Windows reparse-point coverage remains open; replacement writes now
  support prior-fingerprint conflict detection under the page lock.
- Hermes backup archives external provider paths only when they are under the
  user home; other configured roots require a separate verified backup.

### Validation
- PR #5 was squash-merged as commit
  `1027f727a36f2a71c60fc7398a29c397bc1243a5`; Ubuntu and Windows CI passed.
- The disposable lexical-only activation passed against the exact merged
  commit in an isolated Hermes profile and synthetic Wiki, including bounded
  recall, exclusions, redacted byte-idempotent capture, dashboard health,
  backup declaration, rebuild manifest, reload, and cleanup.
- Canonical-profile activation, live GBrain configuration, semantic indexing,
  tag creation, and GitHub Release publication were not performed by that test.

## [0.3.2] - 2026-08-23

### Added
- Dashboard status + activity tab (`provides_dashboard: true`). A read-only
  pane showing brain health (wiki location, git branch/head, gbrain
  availability, last commit), page counts by knowledge category and entities
  subdir, and recent commits to the knowledge base. Served by the plugin's own
  `dashboard/plugin_api.py` (mounted at `/api/plugins/wiki/`) and a plain-IIFE
  frontend bundle — no build step.
- gbrain availability is probed WITHOUT running `gbrain doctor` (doctor takes a
  schema advisory lock during embed/sync and can hang a dashboard request up to
  600s). The dashboard checks the binary is on PATH and `config.json` resolves.

## [0.3.1] - 2026-08-23

### Added
- `WIKI_PATH` env override (read at load) so the wiki can live outside
  `<HERMES_ROOT>/wiki`. Matches the `SETUP.md` documentation, which previously
  claimed the override without the code backing it.

### Known limitation
- Release `0.3.1` added `WIKI_PATH` resolution to `wiki_client.py`, but provider
  initialization still reconstructs `<HERMES_ROOT>/wiki` and bypasses the
  override. Custom-root support remains incomplete pending roadmap item P0.2.

### Fixed
- `SETUP.md` install command used a `github:` prefix that mangles the URL
  (`github.com/github:chrisluersen/...`) and breaks install. Corrected to the
  `owner/repo` shorthand and documented why.

## [0.3.0] - 2026-08-23

### Added
- Core plugin: `wiki` memory provider — per-turn semantic recall via gbrain,
  on-session-end insight extraction, on-memory-write mirror to the wiki,
  on-delegation capture, per-turn prefetch recall.
- Ship full self-contained stack: memory provider (`__init__.py` +
  `wiki_client.py`) + reference to the companion skills (`gbrain-integration`,
  `llm-wiki`, `wiki-maintenance`) that ship with Hermes Agent.
- `SETUP.md` end-to-end guide (prerequisites, gbrain, wiki scaffold,
  maintenance cron, verification, profiles/bots notes).

### Fixed
- Removed bundled `skills/` — the install-time scanner treated env-secret/curl/
  git-clone patterns in `.md` prose as injection signals and returned a
  `dangerous` verdict that blocks install (`--force` cannot override).
  Prose now lives in the docs; skills are referenced by catalog name instead.
- Install command corrected to `owner/repo` shorthand in `README.md`.

### Documentation correction
- The `0.3.0` notes above recorded the release's original claim. Current Hermes
  ships `llm-wiki`, but does not provide catalog entries named
  `gbrain-integration` or `wiki-maintenance`. GBrain onboarding and maintenance
  must use GBrain's own documented surfaces until the hardened plugin provides
  tested automation.

---

[Unreleased]: https://github.com/chrisluersen/hermes-wiki-memory/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/chrisluersen/hermes-wiki-memory/releases/tag/v0.4.0
[0.3.2]: https://github.com/chrisluersen/hermes-wiki-memory/releases/tag/v0.3.2
[0.3.1]: https://github.com/chrisluersen/hermes-wiki-memory/releases/tag/v0.3.1
[0.3.0]: https://github.com/chrisluersen/hermes-wiki-memory/releases/tag/v0.3.0
