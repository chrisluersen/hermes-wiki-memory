# Hermes Wiki Memory Provider

A pluggable **memory provider for [Hermes Agent](https://hermes-agent.nousresearch.com)** that gives the agent semantic recall + session persistence backed by a **git wiki + [gbrain](https://github.com/garrytan/gbrain)** knowledge graph.

Think of it as Hindsight's auto-generated "knowledge pages" — except the knowledge base is a **human-curated, git-versioned markdown wiki** you own, with provenance and cross-links, rather than opaque auto-generated memories.

## What this is — and is not

Hermes Wiki Memory is a **Hermes `MemoryProvider` adapter** for a canonical
Markdown Wiki. It connects three systems with different responsibilities:

1. **Hermes owns the agent lifecycle** — sessions, turns, memory hooks,
   delegation hooks, configuration, backup discovery, and provider activation.
2. **Markdown + Git own durable knowledge** — the Wiki is the human-readable
   system of record. It remains usable without this plugin or GBrain.
3. **GBrain currently provides semantic retrieval** — the plugin starts and
   queries GBrain, then injects bounded recall into Hermes.

So this is **not a rewrite or fork of Hermes's memory system**. It implements
Hermes's existing provider interface. It is also **more than a thin GBrain
wrapper** because it owns safe Wiki writes, Hermes lifecycle capture,
configuration, backup declarations, and dashboard status. However, the current
retrieval path is GBrain-specific and too tightly coupled: one shared GBrain
owner and a GBrain-independent lexical fallback remain required before the
architecture is complete.

> **Status: experimental; hardening in progress.** Release `0.3.2` is not yet a
> safe drop-in replacement for the stock memory providers. Semantic role mapping,
> GBrain ownership, fallback, capture safety, and restore
> behavior remain roadmap work. Do not enable it against canonical data until the
> P0/P1 acceptance tests in the [reliability roadmap](docs/RELIABILITY-ROADMAP.md)
> pass.

## Why

The stock Hermes memory providers (Honcho, Hindsight, Mem0, etc.) are single cloud-backed providers. This one is **local-first and wiki-native**:

- **Per-turn semantic recall** — gbrain hybrid search injects the most relevant wiki context into each prompt.
- **Prototype session capture** — current hooks attempt heuristic extraction and
  dated-page writes. Paths and writes are now contained, locked, atomic, and
  concurrency-tested; capture-before-promotion, idempotency, and redaction remain
  roadmap work.
- **Prototype memory/delegation mirroring** — current hooks append dated entries
  to hardcoded legacy paths. Configurable roles are not implemented; safe atomic
  concurrent writes are present on current `master` but were not part of tagged
  release `0.3.2`.
- **Dashboard status tab** — a read-only Hermes dashboard pane (`/wiki`) showing
  brain health, page counts by category, and recent commits. No `gbrain doctor`
  call — it probes availability without the advisory-lock hang.
- **Designed for shared use across profiles/bots** — the target architecture uses
  one configured Wiki and one shared GBrain owner. Release `0.3.2` does not yet
  satisfy the shared-owner acceptance tests.
- **Backup integration in progress** — current unreleased hardening discovers the
  configured Wiki and `GBRAIN_HOME/.gbrain` paths before initialization. A
  representative restore is still required before complete backup coverage is
  claimed, and Hermes skips external provider paths outside the user home.

## Requirements

- Hermes Agent (any platform)
- [gbrain](https://github.com/garrytan/gbrain) CLI — `bun install -g github:garrytan/gbrain`
- A disposable development Wiki. Release `0.3.2` defaults to
  `<HERMES_ROOT>/wiki`; current unreleased hardening supports `memory.wiki.root`
  while semantic role mapping in roadmap item P0.2 remains open.
- gbrain embeddings backend (e.g. `ZEROENTROPY_API_KEY`, or a local model)

## Install

```bash
hermes plugins install chrisluersen/hermes-wiki-memory --enable
hermes config set memory.provider wiki
hermes config set memory.wiki.wiki_context_cap 1200   # optional: per-turn recall budget
```

Restart the gateway (`hermes gateway restart`) for hooks to load, then verify:

```bash
hermes memory status    # Provider: wiki / Plugin: installed / Status: available
```

## Configure

The prototype is packaged as a Hermes memory plugin. Current and planned knobs:

| Setting | Default | Purpose |
|---|---|---|
| `memory.provider` | — | must be `wiki` |
| `memory.wiki.root` | `<HERMES_ROOT>/wiki` | canonical Wiki root |
| `memory.wiki.wiki_context_cap` | `1200` | max chars of wiki recall injected per turn |
| `HERMES_WIKI_CONTEXT_MAX_CHARS` | (unset) | env override for the same cap |
| `WIKI_PATH` | `<HERMES_ROOT>/wiki` | compatibility override; `memory.wiki.root` takes precedence |

Per-model context caps live in `wiki_client.py` (`MODEL_CONTEXT_CAP_CHARS`) — tight windows for `:free` tiers, default 3000 chars otherwise.

## How it works

- `WikiClient` wraps a **persistent `gbrain serve` child** over JSON-RPC/stdio — pays the ~6.5s DB init once per process, then answers warm (`search` ~5.6s, `think` ~0.2s). Falls back to one-shot CLI calls if the server dies.
- `WikiMemoryProvider` subclasses the current Hermes `MemoryProvider` ABC.
- `WikiFileClient` confines paths to the Wiki root and uses locked atomic writes.
- The provider and dashboard use matching precedence: `memory.wiki.root`, then
  `WIKI_PATH`, then the shared Hermes root.
- gbrain tools (`search`, `think`) are exposed to the agent via the native gbrain MCP server, not this plugin.

### Current data flow

```text
Hermes turn/session hook
        │
        ├── recall ──> WikiMemoryProvider ──> GBrain search ──> bounded context
        │
        └── capture ─> WikiFileClient ──────> Markdown files
```

GBrain is a **derived index**, not the memory system of record. If its database
is lost, the intended recovery path is to rebuild it from the Markdown Wiki.
Full sessions remain canonically owned by Hermes rather than being duplicated
as canonical Wiki pages. Git can version the Wiki, but this plugin does not
stage or commit changes; Git history depends on a separate user or automation
workflow.

## Files

```
plugin.yaml        # plugin manifest (name, requires, provides, config)
__init__.py        # WikiMemoryProvider prototype lifecycle hooks
wiki_client.py     # GBrainClient (serve/JSON-RPC) + WikiFileClient (file ops)
dashboard/         # optional read-only dashboard tab (manifest + API + IIFE bundle)
SETUP.md           # full-stack install guide (plugin + wiki + gbrain + maintenance)
```

Hermes Agent currently ships the `llm-wiki` skill. Install and configure GBrain
through its own documented onboarding; this project does not assume nonexistent
`gbrain-integration` or `wiki-maintenance` Hermes catalog entries.

## Design and roadmap

- [Reliability roadmap](docs/RELIABILITY-ROADMAP.md)
- [Design principles extracted from Seneschal](docs/SENESCHAL-DESIGN-NOTES.md)
- [Wiki folder mapping](docs/WIKI-FOLDER-MAPPING.md)

## Wiki layout

The target configuration uses semantic roles, not one mandatory directory tree.
Root-path configuration from P0.2 is implemented; semantic-role mapping is not.
After that remaining mapping work lands, the planned new-Wiki default is:

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

The roadmap target for an existing Wiki is `layout: adopt-existing`: map
equivalent roles without moving content. For example, the existing
`Clippings/` folder can remain the originals role and `Notes/` can remain
processed source notes. `Topics/` and `Ideas/` may map to one durable
`Knowledge` role. This is a target contract, not yet a claim that the current
plugin implements every mapping option. Path matching must use the exact
on-disk spelling and case. See the [full mapping decision](docs/WIKI-FOLDER-MAPPING.md).

## Next steps

Do **not** enable the provider against a canonical Wiki yet. The recommended
implementation order is:

1. **P0.3 — one GBrain owner:** stop starting one private `gbrain serve` per
   Hermes process and attach profiles to one supervised owner. Explicit source
   binding and normalized MCP error handling are additional integration
   hardening needed during that work.
2. **P1.2/P1.3 — lexical fallback and retrieval policy:** recall useful Markdown
   when GBrain is unavailable while excluding generated/runtime content and
   demoting originals/archive material.
3. **P1.1 — safe capture semantics:** send inferred insights to Inbox, preserve
   provenance, and make replay idempotent. Stable event IDs are one practical
   implementation mechanism; secret redaction is additional capture hardening.
4. **Finish P0.2 — role mapping:** implement `adopt-existing` and configurable
   capture/project/knowledge/source/archive paths without moving live content.
5. **P1.4/P1.5 — truthful health and recovery:** report
   available/degraded/unavailable states and prove representative backup,
   restore, rebuild, and data-preserving uninstall.
6. **P2 — evaluate and release:** add a synthetic recall benchmark, complete
   lifecycle integration tests, then publish the next tagged hardening release.

For a practical next milestone, complete steps 1–2 before installing this on a
real Wiki. Folder migration should come later, after stable identity, retrieval
comparison, backup, and rollback are proven.

## License

MIT. See [LICENSE](LICENSE).
