# Setup — the full Hermes Wiki-Memory stack

This repository describes a local-first alternative to cloud memory providers
(Honcho, Hindsight, Mem0, etc.). Release `0.3.2` is experimental and must not be
treated as a production-ready replacement: the reliability roadmap's P0/P1
acceptance tests are not yet complete.

Four pieces are intended to work together:

| # | Piece | Where | What it does |
|---|---|---|---|
| 1 | **Memory provider** | `__init__.py` + `wiki_client.py` | per-turn semantic recall + session persistence |
| 2 | **GBrain** | upstream GBrain install/onboarding | builds the derived knowledge graph and exposes retrieval tools |
| 3 | **The wiki** | Hermes skill `llm-wiki` | Karpathy-pattern interlinked markdown KB (your actual knowledge base) |
| 4 | **Maintenance** | GBrain CLI plus future plugin automation | sync, embed, extract, doctor, backup and restore checks |

Hermes Agent currently ships `llm-wiki`. GBrain has its own install/onboarding
and skill bundle. This repository does not assume Hermes catalog entries named
`gbrain-integration` or `wiki-maintenance`.

The design advantage is a **human-curated, git-versioned Markdown Wiki you
own**—with provenance and cross-links—instead of opaque cloud memories. The
target architecture shares one configured Wiki and one GBrain owner across
profiles/bots; release `0.3.2` does not yet satisfy that ownership contract.

---

## 0. Prerequisites

- [Hermes Agent](https://hermes-agent.nousresearch.com) (any platform)
- [Bun](https://bun.sh) (required by gbrain)
- An embeddings backend supported by the installed GBrain version, if semantic
  retrieval is required. Lexical fallback remains roadmap work in this plugin.

## 1. Install the plugin (experimental only)

Do not enable release `0.3.2` against canonical data. The commands below are
retained for development/test environments while the hardening roadmap is in
progress.

```bash
hermes plugins install chrisluersen/hermes-wiki-memory --enable
hermes config set memory.provider wiki
hermes config set memory.wiki.root C:/path/to/wiki       # optional
hermes config set memory.wiki.wiki_context_cap 1200   # optional recall budget
hermes gateway restart
hermes memory status     # Provider: wiki / Plugin: installed / Status: available
```

> Use the `owner/repo` shorthand, not a `github:` prefix — the prefix mangles
> the URL (`github.com/github:chrisluersen/...`) and breaks install.

## 2. Install gbrain + build the brain

```bash
bun install -g github:garrytan/gbrain
```

Follow the documentation shipped with the installed GBrain version to create a
brain/source and expose its supported retrieval surface to Hermes. Do not infer
commands from this experimental plugin; GBrain's interface changes independently.

## 3. Adopt or scaffold the wiki

Follow the `llm-wiki` skill (Karpathy pattern): a plain Markdown directory
(no canonical database) of interlinked pages. The hardened plugin will not
require one physical taxonomy. In the target design, folders represent coarse
operational roles; page type, status, provenance, and identity belong in
frontmatter and links. Release `0.3.2` still writes to hardcoded legacy paths.

After roadmap item P0.2 is implemented, the planned new-Wiki default is this
deliberately small layout:

```text
wiki/
  AGENTS.md                    # workspace context, if used
  SCHEMA.md                    # structure authority
  index.md                     # human navigation
  log.md                       # append-only operation history
  Inbox/                       # unclassified capture
  Projects/                    # active finite outcomes
  Knowledge/                   # durable concepts, decisions, runbooks, syntheses
  Sources/
    Originals/                 # preserved external source material
    Notes/                     # processed single-source records
  Archive/                     # inactive or superseded material
  _meta/                       # generated/control artifacts
```

For an existing Wiki, the roadmap target is `layout: adopt-existing`: map its
current folders to these roles and do not perform a big-bang move. A common
compatibility map is `Clippings/` → Sources/Originals, `Notes/` → Sources/Notes,
and `Topics/` + `Ideas/` → Knowledge. The physical folders can retain their old
names until stable IDs, redirects, link rewriting, backups, and retrieval tests
make a move worthwhile. The current release documents this target; it does not
yet implement every mapping option. Configuration must preserve each path's
exact on-disk spelling and case. See the
[Wiki folder mapping contract](docs/WIKI-FOLDER-MAPPING.md) for compatibility,
retrieval, and no-big-bang migration rules.

Release `0.3.2` effectively initializes the provider at
`<HERMES_ROOT>/wiki`. Current unreleased hardening centralizes path resolution
with `memory.wiki.root` → `WIKI_PATH` → default precedence; do not treat it as
released behavior until a subsequent tagged release passes the remaining gates.

## 4. Set up maintenance

Do not schedule maintenance from a `wiki-maintenance` Hermes skill; no such
bundled catalog entry currently exists. Before production use, the hardened
plugin must document and test an idempotent maintenance path for the pinned
GBrain version, including sync, stale embedding/extraction work, health, backup,
and representative restore.

Back up canonical data with a separately verified procedure. Do not assume
release `0.3.2` discovers the actual GBrain store: its `backup_paths()` assumes
`~/.gbrain`. Current unreleased hardening adds pre-init Wiki discovery and
`GBRAIN_HOME/.gbrain` support, but representative restore remains required
before backup coverage is claimed. Hermes archives external provider paths only
when they are under the user home; configure and verify a separate backup for
roots on other drives or outside that boundary.

## 5. Verify

In an isolated development fixture, run `hermes memory status` and `gbrain
doctor`, then verify a capture and recall round-trip. Do not treat a reported
`available` status as proof that shared ownership, fallback, backup, or restore
acceptance tests pass.

---

## Profiles / bots

The target architecture lets every approved profile and Bot Mode bot use one
configured Wiki through one shared GBrain owner. Release `0.3.2` still starts a
process-local `gbrain serve`, so concurrent profiles can contend for PGLite
ownership instead of safely sharing it. Do not enable multi-profile use until
P0.3 passes.

> **Note for profile installs:** a `hermes profile create --clone` does NOT copy
> plugins. After cloning a profile, copy the plugin files into the profile's
> plugin dir (or `hermes plugins install` per profile) or `memory status` reports
> "NOT installed ✗".

## Files

```
plugin.yaml                          # plugin manifest
__init__.py                          # WikiMemoryProvider prototype lifecycle hooks
wiki_client.py                       # GBrainClient (serve/JSON-RPC) + file ops
SETUP.md                             # this file
```

Hermes Agent currently supplies `llm-wiki`; GBrain setup and maintenance remain
owned by GBrain and the future hardened integration.

## License

MIT. See [LICENSE](LICENSE).
