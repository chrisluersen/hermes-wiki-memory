# Hermes Wiki Memory Provider

A pluggable **memory provider for [Hermes Agent](https://hermes-agent.nousresearch.com)** that gives the agent semantic recall + session persistence backed by a **git wiki + [gbrain](https://github.com/garrytan/gbrain)** knowledge graph.

Think of it as Hindsight's auto-generated "knowledge pages" — except the knowledge base is a **human-curated, git-versioned markdown wiki** you own, with provenance and cross-links, rather than opaque auto-generated memories.

> This is the **complete** local-first replacement for the stock cloud memory
> providers (Honcho, Hindsight, Mem0). Pair this plugin with the `gbrain-integration`,
> `llm-wiki`, and `wiki-maintenance` skills (ships with Hermes Agent) and the
> [full setup guide](SETUP.md).

## Why

The stock Hermes memory providers (Honcho, Hindsight, Mem0, etc.) are single cloud-backed providers. This one is **local-first and wiki-native**:

- **Per-turn semantic recall** — gbrain hybrid search injects the most relevant wiki context into each prompt.
- **Session insights persisted** — decisions, learnings, and open questions are extracted and written back to the wiki as dated pages.
- **Memory writes mirrored** — every `memory` tool write is appended to a dated wiki entry page.
- **Delegation captured** — subagent outcomes logged to the wiki.
- **Shared across profiles/bots** — the wiki lives at the Hermes *root*, so every profile and Bot Mode bot queries and writes the **same** knowledge base (no per-bot memory fragmentation).
- **Backup-friendly** — `hermes backup` includes the wiki + `~/.gbrain`.

## Requirements

- Hermes Agent (any platform)
- [gbrain](https://github.com/garrytan/gbrain) CLI — `bun install -g github:garrytan/gbrain`
- A git wiki repo at `<HERMES_ROOT>/wiki` by default (the Hermes **root**, not a profile dir) — override with `WIKI_PATH` env
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

The provider is a standard Hermes memory plugin. Key knobs:

| Setting | Default | Purpose |
|---|---|---|
| `memory.provider` | — | must be `wiki` |
| `memory.wiki.wiki_context_cap` | `1200` | max chars of wiki recall injected per turn |
| `HERMES_WIKI_CONTEXT_MAX_CHARS` | (unset) | env override for the same cap |
| `WIKI_PATH` | `<HERMES_ROOT>/wiki` | env override for the wiki location (read at load) |

Per-model context caps live in `wiki_client.py` (`MODEL_CONTEXT_CAP_CHARS`) — tight windows for `:free` tiers, default 3000 chars otherwise.

## How it works

- `WikiClient` wraps a **persistent `gbrain serve` child** over JSON-RPC/stdio — pays the ~6.5s DB init once per process, then answers warm (`search` ~5.6s, `think` ~0.2s). Falls back to one-shot CLI calls if the server dies.
- The `wiki` memory provider implements the Hermes `MemoryProvider` ABC: `initialize`, `prefetch`, `system_prompt_block`, `on_session_end`, `on_pre_compress`, `on_memory_write`, `on_delegation`, `backup_paths`.
- gbrain tools (`search`, `think`) are exposed to the agent via the native gbrain MCP server, not this plugin.

## Files

```
plugin.yaml        # plugin manifest (name, requires, provides, config)
__init__.py        # WikiMemoryProvider — the MemoryProvider implementation
wiki_client.py     # GBrainClient (serve/JSON-RPC) + WikiFileClient (file ops)
SETUP.md           # full-stack install guide (plugin + wiki + gbrain + maintenance)
```

Companion skills (`gbrain-integration`, `llm-wiki`, `wiki-maintenance`) ship
with Hermes Agent.

## License

MIT. See [LICENSE](LICENSE).
