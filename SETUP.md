# Setup — the full Hermes Wiki-Memory stack

This repo is more than a plugin. It's a self-contained **local-first replacement for
the cloud memory providers** (Honcho, Hindsight, Mem0, etc.). Four pieces work
together; install all of them or the recall layer is incomplete:

| # | Piece | Where | What it does |
|---|---|---|---|
| 1 | **Memory provider** | `__init__.py` + `wiki_client.py` | per-turn semantic recall + session persistence |
| 2 | **gbrain** | `skills/gbrain-integration.SKILL.md` | installs gbrain, builds the PGLite knowledge graph, wires gbrain MCP tools |
| 3 | **The wiki** | `skills/llm-wiki.SKILL.md` | Karpathy-pattern interlinked markdown KB (your actual knowledge base) |
| 4 | **Maintenance** | `skills/wiki-maintenance.SKILL.md` | cron-driven health pipeline: sync, embed, extract, doctor |

Why this beats the stock providers: the knowledge base is a **human-curated,
git-versioned markdown wiki you own** — with provenance and cross-links — instead
of opaque cloud memories. And it's **shared across every profile/bot** (the wiki
lives at the Hermes root, so `light`, `heavy`, and `default` all read/write the
same brain).

---

## 0. Prerequisites

- [Hermes Agent](https://hermes-agent.nousresearch.com) (any platform)
- [Bun](https://bun.sh) (required by gbrain)
- An embeddings backend. The default here uses `ZEROENTROPY_API_KEY`; a local
  model via Ollama works too (see `gbrain-integration` skill).

## 1. Install the plugin

```bash
hermes plugins install github:chrisluersen/hermes-wiki-memory --enable
hermes config set memory.provider wiki
hermes config set memory.wiki.wiki_context_cap 1200   # optional recall budget
hermes gateway restart
hermes memory status     # Provider: wiki / Plugin: installed / Status: available
```

## 2. Install gbrain + build the brain

```bash
bun install -g github:garrytan/gbrain
# gbrain installs its skills to ~/.bun/install/global/node_modules/gbrain/skills
# Follow the gbrain-integration skill for the PGLite brain + MCP tool wiring
```

The `gbrain-integration` skill (ships in `skills/`) covers the full Windows setup:
install gbrain, create the PGLite brain from your wiki, and expose gbrain's
`search`/`think` as MCP tools in Hermes.

## 3. Scaffold the wiki

Follow `skills/llm-wiki.SKILL.md` (Karpathy pattern): a plain markdown dir
(no DB) of interlinked pages. Canonical structure when the wiki is used with the
tracking system:

```
wiki/
  index.md
  governance/SCHEMA.md        # structure authority
  knowledge/
    concepts/  entities/  comparisons/  queries/  references/
  work/  personal/  sessions/  plans/
```

Set `WIKI_PATH` in `$HERMES_HOME/.env` so tooling finds it (default `~/wiki`;
this provider uses `<HERMES_HOME>/wiki` at the **root**, shared across profiles).

## 4. Set up maintenance

Schedule the health pipeline from `skills/wiki-maintenance.SKILL.md` — sync →
embed → extract → doctor. Typical cron:

```bash
hermes cron add "0 3 * * *" "wiki maintenance: sync, embed stale, extract sessions, doctor" \
  --skill wiki-maintenance
```

And back the store up weekly — `scripts/hermes-store-backup.py` in the Hermes
config repo, or `hermes backup` (the wiki + `~/.gbrain` are both included).

## 5. Verify

```bash
hermes memory status                     # provider available
gbrain doctor                            # health score
# Open a session, talk about something already in the wiki, confirm recall.
```

---

## Profiles / bots

Because the wiki resolves to the Hermes **root**, every profile and Bot Mode bot
queries and writes the **same** brain — no per-bot memory fragmentation. A `light`
worker and a `heavy` worker share one knowledge base, each with its own model and
token budget.

> **Note for profile installs:** a `hermes profile create --clone` does NOT copy
> plugins. After cloning a profile, copy the plugin files into the profile's
> plugin dir (or `hermes plugins install` per profile) or `memory status` reports
> "NOT installed ✗".

## Files

```
plugin.yaml                          # plugin manifest
__init__.py                          # WikiMemoryProvider (MemoryProvider ABC)
wiki_client.py                       # GBrainClient (serve/JSON-RPC) + file ops
skills/
  gbrain-integration.SKILL.md        # gbrain install + PGLite + MCP wiring
  llm-wiki.SKILL.md                  # Karpathy-pattern wiki methodology
  wiki-maintenance.SKILL.md          # cron health pipeline
SETUP.md                             # this file
```

## License

MIT. See [LICENSE](LICENSE).
