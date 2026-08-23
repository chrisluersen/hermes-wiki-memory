---
name: gbrain-integration
description: "Install gbrain, set up a PGLite brain from the wiki, and integrate gbrain tools as MCP tools in Hermes Agent on Windows."
version: 1.7.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [gbrain, knowledge-brain, MCP, windows, PGLite, vector-search]
    related_skills: [native-mcp, wiki-operations, multi-agent-orchestration-design, gbrain-native-operations]
created_from_user_sessions: true
---

# gbrain Integration with Hermes Agent

gbrain is a local knowledge brain — it indexes a markdown wiki, generates vector embeddings, and provides semantic search, knowledge graph traversal, and multi-hop synthesis. This skill covers installing gbrain, creating a brain from the Hermes wiki, and exposing gbrain capabilities as MCP tools in Hermes on Windows.

## When to Use

Use this when:
- The user asks to set up gbrain
- The user wants semantic / vector search over the wiki
- The user asks to "connect gbrain to Hermes" or "make gbrain a tool"
- You need to recover from a broken brain / connect to Supabase — see `gbrain-native-operations` (rebuild + sync are the primary recovery paths)

## Prerequisites

- **Bun** — gbrain is installed via `bun install -g github:garrytan/gbrain`
- **Embedding model** — current setup uses `ollama:nomic-embed-text` (local, no API key). If using a hosted provider, a `ze_...` ZeroEntropy key or equivalent is needed for vector embeddings. Free tier available.
- **A markdown wiki** — gbrain indexes `.md` files. Chris's is at `~/AppData/Local/hermes/wiki` (registered as gbrain source `wiki`)

## Installation

### 1. Install gbrain

```bash
bun install -g github:garrytan/gbrain
```

If global install fails, use the deterministic path:

```bash
git clone https://github.com/garrytan/gbrain.git ~/gbrain-source
cd ~/gbrain-source && bun install && bun link
```

### 2. Verify

```bash
PATH="$HOME/.bun/bin:$PATH" gbrain --version
# Should show: gbrain <version>
```

### 3. Create the brain

```bash
export ZEROENTROPY_API_KEY="ze_..."
gbrain init
```

This creates a PGLite brain at `~/.gbrain/brain.pglite` — zero-config, no server needed.

### 4. Configure search mode

`gbrain init` defaults to **conservative** mode (cheapest, least payload). Ask the user before changing. Recommended modes:

| Mode | Budget | Chunks | Use Case |
|------|--------|--------|----------|
| conservative | 4K | 10 | Minimal, cheapest |
| balanced | 12K | 25 | Sweet spot for most usage |
| tokenmax | unlimited | 50 | Full retrieval, richest context |

```bash
gbrain config set search.mode <mode>
```

### 5. Import the wiki

```bash
gbrain import /path/to/wiki/ --no-embed
```

`--no-embed` imports without generating vectors (faster). Then run embeddings separately:

```bash
gbrain embed --stale
```

### 6. Extract knowledge graph links

```bash
# Normal incremental — use after a few edits
gbrain extract --stale

# Full re-extraction — use after batch edits of 10+ files, or when the link score seems stuck
gbrain extract all
```

This extracts frontmatter `relates_to` edges and inline `[[wikilinks]]` into the graph.

**This is NOT a one-time setup step.** It must be re-run after every batch of frontmatter edits. gbrain's auto-detection of stale pages is gradual — `--stale` only catches pages gbrain already knows are dirty. If you just reindexed or patched `relates_to`, the doctor will show a flat link score (`links 10/25`) no matter how many edges you added — until you run `gbrain extract all`. This has no visible error; the graph just never reflects the new edges.

**Extract is separate from reindex.** `mcp__gbrain__sync_brain` only rebuilds the FTS5 keyword index — it does NOT update gbrain's graph. You must run `gbrain extract all` (or `--stale`) separately to pick up frontmatter `relates_to` changes.

**Typical workflow after adding edges:**
1. Add `relates_to` edges via `patch` to the target files
2. `mcp__gbrain__sync_brain` — updates keyword search
3. `gbrain extract all` — updates the graph layer
4. `gbrain doctor` — confirm link score improved

## MCP Integration

For general MCP client setup, transport types, security, and troubleshooting, see the `native-mcp` skill. This section covers gbrain-specific MCP patterns only.

On Windows, the gbrain native binary (`gbrain.exe` — PE32+ Windows executable) has two serve modes:

- **`gbrain serve --http`** — starts an HTTP server. On Windows, this **enforces OAuth 2.1 authentication** and requires DCR (Dynamic Client Registration) to use — not practical for local-only setups. Avoid this path unless you're setting up a multi-user or remote deployment.
- **`gbrain serve` (stdio)** — starts an stdio JSON-RPC server. This is the **canonical MCP integration** (see `Native serve MCP entry` below). It works directly from git-bash/MSYS2 with **stock settings** — no `GBRAIN_NO_RETRY_CONNECT` needed (that env override was removed 2026-08-04; native serve holds the lock and registers ~92 tools with defaults). Verified 2026-08-04: `hermes mcp test gbrain` connects instantly from zero state. Do NOT use the Python FastMCP wrappers (`gbrain-mcp-server.py` / `wiki-mcp-server.py`) — those are archived at `archive/fleet-scripts/` and are NOT in the live config.

### Native serve MCP entry — current config

```yaml
mcp_servers:
  gbrain:
    command: ${USERPROFILE}/.bun/bin/gbrain.EXE
    args: ["serve"]
    env: {GBRAIN_SOURCE: wiki}
    enabled: true
    connect_timeout: 60
```

This is the **canonical integration** (Phase 2, re-established 2026-08-03) — the native `gbrain serve` MCP exposes the full **92-tool** surface (`mcp__gbrain__*`: search, think, graph traversal, page CRUD, jobs, schema, takes, sync, doctor). It supersedes the FTS5-only `wiki-server.py`, which is retired from the MCP config.

**Engine note (2026-08-04):** the brain now runs on **Supabase Postgres** (multi-writer, zero locks) — migrated from PGLite. The old PGLite single-writer lock class is gone: `gbrain serve`, CLI commands, and `sync` all coexist. The `scripts/gbrain-watchdog.py` cron was **removed** (no lock to wedge; cron `6b206f683953`, script archived to `archive/scripts-20260804/`). `scripts/gbrain-maintenance.py` is now a plain sync → embed → extract cycle (no gateway stop/start toggle — Postgres tolerates serve+sync concurrency), run by the Windows scheduled task `Hermes_Gbrain_Maintenance` daily 04:00. For recovery, see `gbrain-native-operations` — **rebuild (`reinit-pglite` / `sync --full` + `extract all`) + sync are the primary paths, never lock surgery.**

The wiki memory provider (`plugins/wiki`) is a **memory provider** (not an MCP server) — it shells out to the `gbrain` CLI for per-turn recall and persists session insights to the wiki.

### Python FastMCP wrappers — ARCHIVED, do not use

The Python FastMCP wrappers (`gbrain-mcp-server.py`, `wiki-mcp-server.py`) are **archived** at `archive/fleet-scripts/` and are NOT in the live config. The native `gbrain serve` entry above is the single canonical integration — it exposes the full 92-tool surface directly. Do not re-introduce the wrappers; the two-server pattern caused PGLite lock conflicts (see Pitfalls below).

### `.llmwiki/` Resolution — legacy note

The old `.llmwiki/` workspace-database pattern is legacy. The current brain is Supabase Postgres (project `vyrfnbzgitxprpypteju`, migrated 2026-08-04), pinned to the `wiki` source via the `.gbrain-source` marker / `GBRAIN_SOURCE: wiki` env. There is no `.llmwiki/` directory in the wiki root.

### Tools exposed by native serve

| Tool | gbrain command | Purpose |
|------|---------------|---------|
| `mcp__gbrain__query` | `gbrain query <q>` | Semantic search, ranked results |
| `mcp__gbrain__think` | `gbrain think <q>` | Multi-hop synthesis with citations |
| `mcp__gbrain__doctor` | `gbrain doctor` | Brain health score, warnings |
| `mcp__gbrain__brain_stats` | `gbrain stats` | Page count, chunk count, coverage |

`gbrain think` requires `ANTHROPIC_API_KEY` for LLM synthesis. Without it, it returns gathered evidence pages only.

## Platform-specific Environment Variables

### ZeroEntropy API Key

The `ZEROENTROPY_API_KEY` is needed for vector embeddings and search. On Windows:

- If set at `gbrain init` time, it IS stored in the PGLite DB and **read-only** CLI calls (`gbrain query`, `gbrain doctor`, `gbrain stats`) work without it in the environment.
- **BUT `gbrain embed --stale` still requires `ZEROENTROPY_API_KEY` in the environment**, even if the key is already in the DB. Embedding re-validates credentials rather than trusting the DB-stored config. Run it with the key exported.
- Hermes MCP subprocesses get a **filtered** environment (see `native-mcp` skill — only safe baselines are passed). If gbrain's embedding model needs the key at serve time, pass it via the `env:` key in config.yaml:

```yaml
mcp_servers:
  gbrain:
    command: ${USERPROFILE}/.bun/bin/gbrain.EXE
    args: ["serve"]
    env:
      GBRAIN_SOURCE: wiki
      ZEROENTROPY_API_KEY: "ze_..."
```

**But this is fragile** — API keys in config.yaml are plaintext. Current setup uses `ollama:nomic-embed-text` (local embeddings, no API key needed) — see `gbrain config` output.

## Recovery: rebuild + sync (native — see `gbrain-native-operations`)

**The brain is on Supabase since 2026-08-04 — the PGLite lock class is gone.** Recovery from a broken/corrupt brain is **rebuild + sync**, never lock surgery:

```bash
# Derived-state rebuild (any engine) — the system-of-record recovery:
gbrain sync --full
gbrain extract all
# PGLite-only wipe-and-reinit (embedding change / legacy PGLite brain):
gbrain reinit-pglite --embedding-model ollama:nomic-embed-text --embedding-dimensions 768 --yes
```

- `gbrain rebuild --confirm-destructive` does **NOT exist** in 0.42.73.0 (phantom command; `reinit-pglite` + `sync --full` are the verified native surface).
- Supabase pooler gotchas (aws-0 vs aws-N trap, transaction pooler 6543, URL-encode password, `GBRAIN_MAX_CONNECTIONS`) — all in `gbrain-native-operations`.

> **Historical (PGLite, pre-2026-08-04):** the old `Timed out waiting for PGLite lock` symptom (every CLI command hanging at the 30s acquire) came from PGLite's single-writer design + gbrain's Windows parent-death watchdog being disabled (`ps` unavailable). The fix then was killing hung `gbrain.exe` and removing `~/.gbrain/brain.pglite/postmaster.pid` + `.gbrain-lock/` — runtime artifacts only, DB files untouched. That whole class is retired; see `gbrain-native-operations` → `references/2026-08-04-wedged-holder-diagnosis.md` for the worked example. If you ever hit a legacy PGLite brain again, the native path is `reinit-pglite` + `sync`, not lock surgery.

**Known-normal doctor warnings (not actionable):**

After recovering, `gbrain doctor` may report these — all are non-issues:

| Warning | Why it's fine |
|---------|---------------|
| `Could not check JSONB integrity` | PGLite limitation — no JSONB support in in-process PostgreSQL |
| `Could not check pgvector extension` | PGLite limitation — vector ops work differently in PGLite |
| `serve IPC socket not present` | Expected in stdio-only context — no daemon socket needed |
| `soft_block=2, warn=8` audit events | Normal operational noise; inspect with `gbrain audit events` if curious |
| `1 page(s) flagged (markup-heavy or oversize)` | Still searchable, agent gets a warning on retrieval. Check with `gbrain quarantine list --include-flagged` |

## Skillpack Scaffolding

gbrain ships with 38 bundled skillpacks (agent-facing skills for Claude Code / OpenClaw). To scaffold them:

```bash
# The global install doesn't have a git repo — scaffold needs one
git clone --depth 1 https://github.com/garrytan/gbrain.git ~/gbrain-source

# Run scaffold from the source directory
cd ~/gbrain-source
gbrain skillpack scaffold --all --workspace <target-dir>
```

The `skillpack list` command also requires the source repo to find bundled skills.

## Pitfalls

- **Strip `GBRAIN_*` / `SUPABASE_*` env vars when invoking gbrain from scripts or terminal** — leftover env from other contexts (cron, MCP, previous sessions) can point gbrain at the wrong source/credentials and produce confusing cross-wiring. Start gbrain runs from a clean env (or `env -u GBRAIN_* -u SUPABASE_* ...`), and never let those vars leak into subprocess invocations.
- **Multiple gbrain processes now coexist on Supabase.** The old "PGLite is single-writer — one serve at a time" rule died with the migration. Postgres tolerates concurrent connections; N serves + CLI + sync run simultaneously. If something wedges anyway, recovery is rebuild + sync (see `gbrain-native-operations`), not lock clearing.
- **`gbrain.exe` works as a stdio MCP server directly.** Despite being a PE32+ Windows binary, native `gbrain serve` is the canonical integration — verified working from git-bash/MSYS2 with stock settings (2026-08-04). Do NOT wrap it via Python FastMCP; the wrappers are archived.
- **Config file corruption via sed.** `sed -i` with `d` (delete) can corrupt the file if the line ranges are wrong. Prefer `patch` tool where possible. For Hermes config.yaml, the `patch` tool is blocked — use careful `sed -i` with `a` (append) rather than `d` (delete).
- **Backup config before editing.** Always `cp config.yaml config.yaml.bak` before running sed on Hermes config.
- **The shell env is NOT the MCP subprocess env** — see `native-mcp` skill for the mechanism. Pass env vars via the `env:` config key or hardcode in the Python wrapper.
- **`ZEROENTROPY_API_KEY` stored in DB — query works, embed doesn't.** If the key was set during `gbrain init`, read-only CLI commands (`query`, `doctor`, `stats`) work without re-exporting. But `gbrain embed --stale` still requires the env var — it re-validates credentials rather than trusting the DB config. Keep the key available or set it in `_GBRAIN_ENV` in the Python wrapper when running embed operations.
- **Frontmatter edges are invisible until `gbrain extract`.** Adding `relates_to` to a page's frontmatter does NOT immediately update gbrain's graph. The link score (`links 10/25`) stays flat no matter how many edges you add — until you run `gbrain extract all`. This has no visible error; the doctor just never reflects the new edges. After any batch of frontmatter edits: `gbrain extract all`.
- **`gbrain serve --http` enforces OAuth 2.1 on Windows.** The HTTP server requires DCR (Dynamic Client Registration) to accept connections — not usable for local-only setups without setting up a full OAuth provider. Stdio mode has no such requirement. If you need HTTP access, investigate DCR setup; for local use, prefer stdio or embedded subprocess.
- **One gbrain MCP entry is still right — but not for lock reasons.** The archived Python wrappers (`wiki-mcp-server.py` / `gbrain-mcp-server.py`) are retired; the native `gbrain serve` entry is canonical. If tools hang, recovery is rebuild + sync (see `gbrain-native-operations`).

### Verification

After setup, run:

```bash
# CLI test
PATH="$HOME/.bun/bin:$PATH" gbrain query "asteroid fleet" --json

# Health check (plain output - --json may return empty on this version)
gbrain doctor

# Stats
gbrain stats
```

Expected: ranked results, health score > 30/100 (improves over time), page/chunk counts.

**`gbrain extract all` returning "0 links, 0 timeline entries"** is normal when nothing changed on disk since the last extraction. It means the graph is already current — not an error. Only expect non-zero results after editing wiki pages or adding `relates_to` edges.

**`gbrain embed --stale` returning "0 stale found"** means all embedded chunks are current. The onboard's stale count refers to sync staleness (external sources), not embedding staleness.

## Adding Timeline Data to Pages

gbrain's `extract timeline` command scans pages for **level-3 markdown headings starting with an ISO date** (`### YYYY-MM-DD`). This is the ONLY format gbrain recognizes for auto-timeline extraction — frontmatter fields like `date:`, `created:`, and `updated:` are NOT picked up.

**To add a timeline entry to a page:**

```markdown
## Timeline

### 2026-06-17 — Event description
```

After adding entries, run:
```bash
gbrain extract timeline
```

The `## Timeline` section heading is optional but recommended for readability. Each page with at least one `### YYYY-MM-DD` heading counts toward entity timeline coverage.

**Pitfall:** Adding a `## Timeline` section right after the body's first heading can orphan that heading. gbrain lint catches this as `empty-section`. Fix by removing the orphaned heading.

## Full Rebuild: Changing the Embedding Model

When switching gbrain's embedding model (e.g., zeroentropy 1280d → ollama 768d), old embeddings are incompatible — a full rebuild is required. Do NOT attempt `gbrain embed --stale` or incremental operations; they will fail because the existing chunk embeddings have different dimensions than the new model produces.

**Full rebuild sequence (native — verified in gbrain 0.42.73.0):**

```bash
# PGLite: canonical wipe-and-reinit (backs up to <path>.bak, inits, syncs)
gbrain reinit-pglite --embedding-model ollama:nomic-embed-text --embedding-dimensions 768 --yes

# Supabase (current engine): embedding model changes are an in-place ALTER —
# see gbrain docs/embedding-migrations.md; derived-state rebuild is:
gbrain sync --full
gbrain extract all
```

**Expected outcome:**
- `brain_score`: Starts at ~75-80/100 (embed 35/35, links 25/25, timeline 1/15, orphans 9/15, dead-links 10/10)
- The timeline score is low until pages get `### YYYY-MM-DD` heading entries — expected
- Orphans 9/15 is normal — many pages intentionally have no inbound links (braindumps, config/pages, DNT files)
- A flagged page (typically `raw/articles/hermes-agent-full-documentation` at ~2.9MB) is a non-blocking retrieval warning — still searchable

**When to rebuild vs incremental:**

| Situation | Approach |
|-----------|----------|
| Changed a few pages' content | `gbrain embed --stale` (incremental) |
| Added `relates_to` edges | `gbrain extract all` (graph-only, no re-embed needed) |
| **Changed embedding model** | **`gbrain reinit-pglite`** (PGLite) or in-place ALTER (Supabase) — old embeddings incompatible |
| Moved vault path | Re-init + import from new path |
| Old brain corrupted / locked | **Rebuild + sync** (`reinit-pglite` / `sync --full` + `extract all`) — see `gbrain-native-operations` |
| Fresh checkout of wiki repo | `gbrain init --pglite` → `gbrain import .` |

**New brain vs old brain interface:** After rebuilding with `ollama:nomic-embed-text` (768d) instead of `zeroentropyai:zembed-1` (1280d), the MCP tool signatures remain identical — only the underlying vector dimension shifts. No semantic change to search results.

**Old brain fallback (PGLite only):**
```bash
rm -rf ~/.gbrain
mv ~/.gbrain.bak.20260707_* ~/.gbrain
```
The old brain retains the prior embedding model and all prior embeddings.

## API Key Management in Shell

gbrain reads `ZEROENTROPY_API_KEY` and `OPENAI_API_KEY` from the environment. On Windows git-bash, these must be in `.bashrc` to persist across shell sessions:

```bash
export ZEROENTROPY_API_KEY="ze_..."
export OPENAI_API_KEY="sk-..."
```

**Which commands need the key in the shell:**

| Command | Needs ZEROENTROPY_API_KEY in shell? | Notes |
|---------|--------------------------------------|-------|
| `gbrain query` / `gbrain doctor` / `gbrain stats` | No | Reads key from engine DB (stored at init time) |
| `gbrain extract all` | Partially | Works without key for link/timeline extraction; needs it for embedding |
| `gbrain embed --stale` | **Yes** | Re-validates credentials rather than trusting DB config |
| `gbrain sync` | **Yes** | Needs it for embedding during sync |

**Why:** `gbrain init` stores the embedding config + API key in the engine database. Read-only CLI calls (`query`, `doctor`, `stats`) use the DB-stored config. But `embed --stale` and `sync` re-validate credentials at runtime — they need the env var present.

The `extract` command (link/timeline extraction) works without the shell key because it operates on markdown filesystem content, not embedding. If a future version changes this, the doctor's `ze_embedding_health` check will report it.

**MCP subprocess gotcha:** Env vars set in `.bashrc` are NOT inherited by Hermes MCP subprocesses. If gbrain is called from a FastMCP server via `subprocess.run()`, pass the key explicitly in the env dict:

```python
ENV = os.environ.copy()
if "ZEROENTROPY_API_KEY" not in ENV:
    ENV["ZEROENTROPY_API_KEY"] = "ze_..."
```

## Periodic Maintenance: gbrain Upgrade

Beyond initial setup, run `gbrain upgrade` periodically to apply database migrations:

```bash
gbrain upgrade
```

This auto-applies migrations (jsonb fix, auto-link wire-up, frontmatter relationship indexing) that can significantly increase your graph link count. In one test run, a single upgrade added +287 links and +20 timeline entries.

After upgrade, check for additional steps:
```bash
gbrain onboard --check --explain
```

The onboard list may offer:
- `extract` and `sync` — **auto-eligible**, materialize edges from fresh pages. Execute separately via `gbrain extract all` and `gbrain embed --stale` (`gbrain sync` requires a configured source — see "Running onboard recommendations" below)
- `unify-types` — manual, collapses redundant page types after a pack upgrade (free)
### Running onboard recommendations

`gbrain onboard` is preview-only (--check is the default). There is no `run` subcommand — to apply auto-eligible items, execute them directly:
  - `gbrain extract all` — full knowledge graph re-extraction
  - `gbrain embed --stale` — re-embed pages that changed on disk

**`gbrain sync` IS for wiki content — scoped to a source.** `gbrain sync --source wiki` (the maintenance script's step 1) incrementally imports the wiki repo's changed markdown into the engine. The onboard's "42 stale pages" message refers to sync staleness for a source whose `local_path` is absent. To re-embed wiki content after changes, use `gbrain embed --stale`; to refresh the graph, use `gbrain extract all`.

**Windows note:** The `crontab` install during `gbrain upgrade` will fail — expected on Windows, non-impacting. All DB migrations apply correctly.

## Memory Provider Integration (Hermes Plugin Architecture)

**Critical gap discovered:** Hermes has a pluggable `MemoryProvider` architecture (`plugins/memory/`) but **no wiki-aware memory provider exists**. The wiki is only accessible via MCP tools (`gbrain_query`, `gbrain_think`, etc.) and never enters the agent's persistent memory system.

### Why This Matters

| Current Limitation | Memory Provider Fix |
|-------------------|---------------------|
| Wiki knowledge doesn't persist across sessions | `prefetch()` → semantic recall every turn |
| Can't ask "what did we decide about X last week?" | `gbrain_think` exposed as provider tool |
| Subagent research vanishes after delegation | `on_delegation()` → capture outcomes to wiki |
| Context compression loses wiki references | `on_pre_compress()` → preserve wiki context |
| Manual `memory` tool writes don't reach wiki | `on_memory_write()` → mirror to wiki |
| Session insights evaporate | `on_session_end()` → extract → wiki pages |

### MemoryProvider Interface (from `hermes-agent/agent/memory_provider.py`)

```python
class MemoryProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...  # e.g. "wiki"

    @abstractmethod
    def is_available(self) -> bool: ...  # config + deps check

    @abstractmethod
    def initialize(self, session_id: str, **kwargs) -> None: ...
        # kwargs: hermes_home, platform, agent_context, agent_identity,
        #         agent_workspace, parent_session_id, user_id, user_id_alt

    def system_prompt_block(self) -> str: ...  # static provider info

    def prefetch(self, query: str, *, session_id: str = "") -> str: ...
        # Called BEFORE each API call - return context to inject

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None: ...
        # Called AFTER each turn - bg recall for NEXT turn

    def sync_turn(self, user_content: str, assistant_content: str, *,
                  session_id: str = "", messages: List[Dict] = None) -> None: ...
        # Persist turn to backend (async, non-blocking)

    @abstractmethod
    def get_tool_schemas(self) -> List[Dict]: ...
        # Tool schemas exposed to model (OpenAI function format)

    def handle_tool_call(self, tool_name: str, args: Dict, **kwargs) -> str: ...
        # Dispatch tool call, return JSON string result

    # Optional hooks (override to opt in):
    def on_turn_start(self, turn_number: int, message: str, **kwargs): ...
    def on_session_end(self, messages: List[Dict]): ...
    def on_session_switch(self, new_session_id: str, *, parent_session_id: str = "",
                          reset: bool = False, rewound: bool = False, **kwargs): ...
    def on_pre_compress(self, messages: List[Dict]) -> str: ...
    def on_delegation(self, task: str, result: str, *, child_session_id: str = "", **kwargs): ...
    def on_memory_write(self, action: str, target: str, content: str,
                        metadata: Dict = None): ...
    def backup_paths(self) -> List[str]: ...  # extra paths for `hermes backup`
    def get_config_schema(self) -> List[Dict]: ...  # for `hermes memory setup`
    def save_config(self, values: Dict, hermes_home: str): ...
```

### Wiki Memory Provider Design

**Location:** `~/.hermes/plugins/memory/wiki-memory/`

```python
# wiki_memory_provider.py
class WikiMemoryProvider(MemoryProvider):
    name = "wiki"

    def is_available(self) -> bool:
        return Path(vault_path).exists() and gbrain_available()

    def initialize(self, session_id: str, **kwargs):
        self.vault = kwargs.get('vault_path', 'C:/agent-wiki')
        self.gbrain = GBrainClient(self.vault)
        self.session_id = session_id

    def prefetch(self, query: str, session_id: str = "") -> str:
        results = self.gbrain.query(query, limit=5)
        return format_as_memory_context(results)

    def get_tool_schemas(self) -> List[Dict]:
        return [GBRAIN_QUERY_SCHEMA, GBRAIN_THINK_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: Dict) -> str:
        if tool_name == "gbrain_query":
            return self.gbrain.query(args["query"], args.get("limit", 10))
        if tool_name == "gbrain_think":
            return self.gbrain.think(args["question"])

    def on_session_end(self, messages: List[Dict]):
        insights = extract_session_insights(messages)
        for insight in insights:
            self.wiki.upsert_page(insight)

    def on_pre_compress(self, messages: List[Dict]) -> str:
        return extract_wiki_context(messages)

    def on_delegation(self, task: str, result: str, **kwargs):
        self.wiki.record_delegation(task, result, kwargs.get("child_session_id"))

    def on_memory_write(self, action: str, target: str, content: str, metadata: Dict = None):
        # Mirror built-in memory writes to wiki
        self.wiki.mirror_memory_write(action, target, content, metadata)

    def backup_paths(self) -> List[str]:
        return [self.vault, str(Path.home() / ".gbrain")]
```

### Activation

```yaml
# config.yaml
memory:
  provider: "wiki"  # ← ACTIVATE
```

### Benefits Over MCP-Only Access

| Aspect | MCP Tools Only | Memory Provider |
|--------|---------------|-----------------|
| Per-turn semantic recall | Manual `gbrain_query` call | Automatic `prefetch()` every turn |
| Session knowledge persistence | Lost on session end | `on_session_end()` → wiki |
| Subagent capture | Manual | `on_delegation()` auto-captures |
| Context compression | Loses wiki refs | `on_pre_compress()` preserves |
| Built-in `memory` tool | MEMORY.md only | Mirrored to wiki via hook |
| Tool exposure | MCP tools list | `get_tool_schemas()` → model tools |

### Related: Context Engine Plugin

Hermes also has a `ContextEngine` plugin architecture (`plugins/context_engine/`) for wiki-aware compression. See `references/wiki-context-engine-plugin.md`.

---

## Post-Install Optimization: Link Resolution

### Global basename links (strongly recommended)

Enable global wikilink resolution so `[[profiles]]` finds pages across all subdirectories, not just the current one:

```bash
gbrain config set link_resolution.global_basename true
```

**Before:** `[[profiles]]` only matches pages in the same directory. ~37% of bare wikilinks don't resolve.

**After:** `[[profiles]]` finds `entities/profiles.md`, `concepts/profiles.md`, or any page named `profiles.md` anywhere in the wiki. This resolves hundreds of previously-dead wikilinks instantly.

To verify:
```bash
gbrain config get link_resolution.global_basename
# Returns: true
```

No re-indexing needed — resolution happens at query time.

**Reading config values**

Use **full dotted-path** to read specific config keys:

```bash
gbrain config get link_resolution.global_basename  # true/false
gbrain config get search.mode                        # conservative/balanced/tokenmax
gbrain config get embedding_model                    # e.g. zeroentropyai:zembed-1
```

**Pitfall: partial paths fail silently.** `gbrain config get link_resolution` (without `.global_basename`) returns "Config key not found" even though `link_resolution.global_basename` IS set to `true`. Always use the full dotted path to the leaf key.

## gbrain Integrations

gbrain ships with several integrations that add data inputs and automated reflexes. Manage them with the `integrations` subcommand.

### List available integrations

```bash
gbrain integrations list
```

Groups by type:
- **INFRASTRUCTURE** — `credential-gateway`, `ngrok-tunnel`
- **SENSES** (data inputs) — `calendar-to-brain`, `email-to-brain`, `meeting-sync`, `x-to-brain`
- **REFLEXES** (automated responses) — `restart-sweep`, `retrieval-reflex`

### Show integration details

```bash
gbrain integrations show <id>
```

Shows setup time, cost, secrets needed, and the full recipe body.

### Install an integration

```bash
gbrain integrations install <id> --target <path-to-host-repo>
```

The `<target>` is the root of the host repo (where SKILL.md / AGENTS.md lives). For Hermes wiki integration, use the vault root:
```bash
gbrain integrations install retrieval-reflex --target /c/Users/chris/AppData/Local/hermes/wiki
```

This copies a policy skill into `<target>/skills/<id>/SKILL.md`. The policy teaches the agent WHEN to look something up and WHAT to pull — without it, the agent can discuss an entity for several messages without ever opening its brain page.

**Cost:** $0 for zero-LLM integrations like `retrieval-reflex`.

### Retrieval-reflex specifically

The reflex has two halves:

1. **Deterministic pointer layer** (automatic, on by default) — scans each turn's user message for salient entities and injects a compact pointer (name → slug → one-line summary). Zero-LLM, fail-open.
2. **Policy skill** (installed via `integrations install`) — a SKILL.md fragment that encodes the trigger policy and retrieval spec.

The `gbrain doctor` check `retrieval_reflex_health` reports:
- `ok` — both halves working
- `policy skill not installed` — deterministic layer is on, but the policy fragment is missing. Run `integrations install`.
- `IPC socket not present` — the deterministic layer needs `gbrain serve` as a daemon for live IPC. Without it, only the policy skill carries the behavior. The skill is still useful standalone.

### Other useful health checks from gbrain doctor

```bash
gbrain doctor
```

Key checks to watch:
| Check | Meaning |
|-------|---------|
| `retrieval_reflex_health` | Whether retrieval-reflex is fully operational |
| `flagged_pages` | Pages too large to embed (oversize / markup-heavy) — still searchable but agent warned on retrieval |
| `eval_drift` | Whether retrieval-affecting files changed in working tree |
| `brain_score` | Overall health score (improves over time as graph fills)

## Reference Files

| File | What It Covers |
|------|---------------|
| **`gbrain-native-operations` skill** | **CURRENT recovery/ops: rebuild (`reinit-pglite` / `sync --full` + `extract all`), sync, Supabase pooler gotchas. Supersedes the retired `gbrain-pglite-operations`.** |
| `references/embedded-gbrain-tools-wiki-mcp.md` | HISTORICAL (archived 2026-08-04): embedding gbrain tools in wiki-mcp-server.py — superseded by native `gbrain serve` |
| `references/standalone-gbrain-mcp-attempt.md` | June 2026 session detail: OAuth 2.1 HTTP discovery, two-MCP config attempt, full timeline |
| `references/wiki-memory-provider-plugin.md` | Full implementation skeleton for WikiMemoryProvider plugin (MemoryProvider architecture) |
| `references/wiki-context-engine-plugin.md` | Design for ContextEngine plugin enabling wiki-aware context compression |
| `references/wiki-memory-implementation-plan.md` | Validated implementation plan with priority order, risk mitigation, and session validation notes |
