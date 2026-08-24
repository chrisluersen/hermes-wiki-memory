# Hermes Wiki Memory Provider

A pluggable **memory provider for [Hermes Agent](https://hermes-agent.nousresearch.com)** that gives the agent semantic recall + session persistence backed by a **git wiki + [gbrain](https://github.com/garrytan/gbrain)** knowledge graph.

Think of it as Hindsight's auto-generated "knowledge pages" — except the knowledge base is a **human-curated, git-versioned markdown wiki** you own, with provenance and cross-links, rather than opaque auto-generated memories.

> **Status: experimental; hardening in progress.** Release `0.3.2` is not yet a
> safe drop-in replacement for the stock memory providers. Its provider contract,
> path/config handling, GBrain ownership, concurrent writes, fallback, and backup
> behavior remain roadmap work. Do not enable it against canonical data until the
> P0/P1 acceptance tests in the [reliability roadmap](docs/RELIABILITY-ROADMAP.md)
> pass.

## Why

The stock Hermes memory providers (Honcho, Hindsight, Mem0, etc.) are single cloud-backed providers. This one is **local-first and wiki-native**:

- **Per-turn semantic recall** — gbrain hybrid search injects the most relevant wiki context into each prompt.
- **Prototype session capture** — current hooks attempt heuristic extraction and
  dated-page writes; capture-before-promotion, idempotency, and safe-path tests
  remain roadmap work.
- **Prototype memory/delegation mirroring** — current hooks append dated entries
  to hardcoded legacy paths. Configurable roles and atomic concurrent writes are
  not implemented in release `0.3.2`.
- **Dashboard status tab** — a read-only Hermes dashboard pane (`/wiki`) showing
  brain health, page counts by category, and recent commits. No `gbrain doctor`
  call — it probes availability without the advisory-lock hang.
- **Designed for shared use across profiles/bots** — the target architecture uses
  one configured Wiki and one shared GBrain owner. Release `0.3.2` does not yet
  satisfy the shared-owner acceptance tests.
- **Backup integration planned** — the hardened provider will discover the actual
  configured Wiki/GBrain paths and verify representative restore. Release `0.3.2`
  still assumes `~/.gbrain` and does not prove complete backup coverage.

## Requirements

- Hermes Agent (any platform)
- [gbrain](https://github.com/garrytan/gbrain) CLI — `bun install -g github:garrytan/gbrain`
- A disposable development Wiki at `<HERMES_ROOT>/wiki` for release `0.3.2`;
  custom-root support is not reliable until roadmap item P0.2 lands
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
| `memory.wiki.wiki_context_cap` | `1200` | max chars of wiki recall injected per turn |
| `HERMES_WIKI_CONTEXT_MAX_CHARS` | (unset) | env override for the same cap |
| `WIKI_PATH` | `<HERMES_ROOT>/wiki` | intended compatibility override; release `0.3.2` does not consistently honor it during provider initialization |

Per-model context caps live in `wiki_client.py` (`MODEL_CONTEXT_CAP_CHARS`) — tight windows for `:free` tiers, default 3000 chars otherwise.

## How it works

- `WikiClient` wraps a **persistent `gbrain serve` child** over JSON-RPC/stdio — pays the ~6.5s DB init once per process, then answers warm (`search` ~5.6s, `think` ~0.2s). Falls back to one-shot CLI calls if the server dies.
- The prototype exposes methods shaped like the Hermes memory-provider lifecycle,
  but release `0.3.2` does not subclass the current `MemoryProvider` ABC. Direct
  provider-contract compatibility is roadmap item P0.1.
- gbrain tools (`search`, `think`) are exposed to the agent via the native gbrain MCP server, not this plugin.

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
After roadmap item P0.2 lands, the planned new-Wiki default is:

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

## License

MIT. See [LICENSE](LICENSE).
