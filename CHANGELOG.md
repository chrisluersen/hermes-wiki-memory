# Changelog

All notable changes to **hermes-wiki-memory** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

---

[Unreleased]: https://github.com/chrisluersen/hermes-wiki-memory/compare/v0.3.2...HEAD
[0.3.2]: https://github.com/chrisluersen/hermes-wiki-memory/releases/tag/v0.3.2
[0.3.1]: https://github.com/chrisluersen/hermes-wiki-memory/releases/tag/v0.3.1
[0.3.0]: https://github.com/chrisluersen/hermes-wiki-memory/releases/tag/v0.3.0
