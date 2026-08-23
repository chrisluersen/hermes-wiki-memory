---
name: wiki-maintenance
title: "Wiki Maintenance Pipeline"
description: "Automated wiki health pipeline: sync, embed, extract, doctor verification"
category: hermes
version: "1.2.0"
metadata:
  hermes:
    tags: [hermes, agent, fleet, config, wiki-maintenance]
---

# Wiki Maintenance Pipeline

Automated maintenance for the agent wiki + gbrain brain. Runs as a skill that can be invoked manually or via cron.

## Pipeline Steps

1. **Import** - `gbrain import --no-embed` (imports new/changed markdown)
2. **Embed** - `gbrain embed --stale` (embeds only stale chunks)
3. **Extract** - `gbrain extract --stale` (extracts entities/relations from stale)
4. **Sync brain** - `mcp__gbrain__sync_brain()` (imports new/changed markdown)
5. **Lint** - `mcp__gbrain__find_orphans()` (checks for broken wikilinks, orphans, stale frontmatter)
6. **Doctor** - `gbrain doctor --json` (health check, alerts if score < 50)

## Phase 2: Content Health (batch frontmatter fixes)

> **2026-08-05 (t_782fc626):** easy frontmatter issues are now auto-healed weekly by
> `scripts/wiki/heal-frontmatter.py` (cron `frontmatter-auto-heal`, Sun 08:45) — legacy
> field typos, missing created/updated dates (rename-aware git dates), `sources: []` on
> structural types, invalid types. Hard cases (no frontmatter, content pages missing
> sources, sources without/with-old extracted_at) surface in its weekly report — do NOT
> bulk-add synthetic `sources:` to content pages to clear the metric; that fabricates
> provenance. The `fix-sources.py` pattern below is the legacy approach for appending
> `extracted_at` to already-populated sources.

After lint identifies stale frontmatter (pages with `sources:` that lack provenance), use the batch fix script:

```
python3 .hermes/scripts/fix-sources.py
```

Run from `C:/Users/<user>/polaris/wiki`. Fixes three page categories (`concepts/`, `entities/`, `comparisons/`):

- **Has `source_query` with value + empty `sources:`** → creates `sources: [{description: '<query>', extracted_at: YYYY-MM-DD}]`
- **Has no `source_query` + empty `sources:`** → creates `sources: [{extracted_at: YYYY-MM-DD}]`
- **Already has populated sources with `extracted_at:`** → skipped
- **Already has populated sources WITHOUT `extracted_at:`** → appends `extracted_at:` to each entry

The linter (`wiki_utils.py::lint_stale_frontmatter`) checks:
1. File starts with `---`
2. Has `sources:` key in first 2000 chars
3. Has `extracted_at: YYYY-MM-DD` within 90 days in first 5000 chars

So entries **must** have `extracted_at:` — bare URLs or description-only entries count as stale.

**Always verify:** after script, run `mcp__gbrain__sync_brain()` then `mcp__gbrain__find_orphans()`. Stale-frontmatter count should drop. Spot-check 3 files (had source_query, no source_query, already populated — last should be untouched).

## Pitfalls

### extract_tags leaked relates_to/sources items into tags (fixed 2026-08-05)

`wiki_utils.py::extract_tags` previously appended **every** `- item` line in
frontmatter after seeing `tags:`, so `relates_to:` targets and `sources:`
entries were misread as tags. Result: `lint_tags` reported ~1500 false-positive
"tag drift" entries (values like `target: x`, `file: raw/...`, `url: ...`,
`extracted_at: ...`) when the real taxonomy violation count was **0**.

**Fix applied:** track `in_tags_list` state — only collect `- ` lines inside
the `tags:` block and break at the next top-level key (no leading whitespace).

**Verification:** run `run-wiki-audit.py` and confirm `tag_drift_count` drops
to ~0. If a large tag_drift count reappears, check `extract_tags` wasn't
regressed. Do NOT bulk-edit wiki files to "fix" phantom drift.

### Linter returns stale results
`mcp__gbrain__find_orphans()` can return **stale/cached data** that persists across sessions — it may report broken wikilinks that were already fixed in a prior session. Known case: `[[tracking/cron]]` etc. in `log.md` were patched in an earlier session (documented in log.md lines 310-314) but the linter still reports them.

**Always verify** with `grep` or `search_files` on the actual file before concluding a link is still broken. Do not trust the linter's word alone when the log shows earlier fixes.

### `lint_broken_links` had a silent always-false bug (fixed 2026-08-13)

`wiki_utils.py::lint_broken_links` (def ~line 409) previously had
`if t_stem not in page_stems and t_stem != target.lower():` — for a plain
lowercase target, `Path(target).stem.lower() == target.lower()` is always
true, so the second condition was always false and **real broken links were
never flagged**. It reported 0 while 57+ genuinely broken targets existed.

**Fix:** rewritten to resolve Obsidian-style (full path, leaf basename, leaf
stem case-insensitive) PLUS `id:` frontmatter (the SCHEMA-canonical link
target is the page `id:`, not filename). Resolution set built from **all**
`.md` on disk including `_archive/` and `raw/` (archived pages are navigable);
excludes only system dirs `.git .obsidian .llmwiki __pycache__ .trash`.
Exempts `governance/templates/` and `*_template.md` (copy-source templates
with doc placeholders). Fragment/URL/whitespace targets are not broken.

**Canonical link target = `id:` frontmatter.** Repoint renamed pages to their
canonical `id:`; unlink (bare display text) skill/tool names, doc-example
tokens, and plan/overhaul refs with no page.

**Verification:** `python scripts/wiki/wiki-link-audit.py --dry-run` must print
`OK: 0 broken links — gate PASS`. Do NOT trust a single pass — re-run after any
file edit; live memory-mirror pages (`knowledge/entities/memory-entries/*`)
are rewritten by background writers and can resurrect unlinked `[[slug]]`
prose tokens, re-breaking the gate.

### Reindex before lint

`mcp__gbrain__sync_brain()` imports new/changed markdown into the brain index. If you patch files, sync first, then lint.

### Linter `extracted_at` date comparison fails on YAML-quoted dates

`yaml.safe_dump` outputs date-like strings with quotes (`extracted_at: '2026-07-07'`).
The linter's regex `r"extracted_at:\\s*(\\S+)"` captures the quotes as part of the value,
and the lexicographic compare `'2026-07-07' >= 2026-04-08` fails because `'` (ASCII 39)
sorts before `2` (ASCII 50). Every page with a YAML-dumped sources block appears stale.

**Fix applied to `wiki_utils.py`:** strip surrounding quotes from the captured date:
```python
ts = em.group(1).strip("'\"")
```

Also, in fix scripts that emit `extracted_at:` values, use YAML-safe formatting that
avoids quoting. For date strings, build the line directly rather than relying on
`yaml.safe_dump` to format date-like values:
```python
# Good — no yaml.dump for the extracted_at line
new_sources_block = f'sources:\\n  - extracted_at: {TODAY}'
```

**Verification:** after running the fix script, sync then lint. If the stale count
doesn't drop, check that `wiki_utils.py` has the quote-strip fix at line ~279-280.
Spot-check one fixed page in the DB:
```bash
gbrain get concepts/active-questions.md | grep -A2 extracted_at:
```

### Batch frontmatter: use YAML parsing, not regex on `sources: []`

Several files have **populated sources as YAML lists** (e.g., `sources:\n  - https://github.com/...`) not empty `[]`. A regex targeting `sources: \[\s*\]` will **miss these** or **mangle them**. Known case: `concepts/ai-terminal-stack.md` has 15 GitHub URLs under `sources:` — should never be touched.

Always use `yaml.safe_load` to check if sources are populated before deciding to fix.

### Regex `\s*` on CRLF files leaks into next line

When the wiki uses CRLF line endings, `\s*` in a `source_query:` regex
```python
re.search(r'^source_query:\s*(.+)$', fm_text, re.MULTILINE)
```
matches `\r\n` (both are whitespace) and captures `sources:` from the next line as the _value_. This destroys populated sources blocks. Use `[ \t]*` instead of `\s*` for same-line capture across CRLF content:

```python
re.search(r'^source_query:[ \t]*(.+)$', fm_text, re.MULTILINE)  # OK
```

This applies to any regex that captures a scalar value on the same line. YAML parsing avoids this entirely.

### Verify after batch fixes

After `fix-sources.py`, always: 1) `mcp__gbrain__sync_brain()` to import fixes, 2) `mcp__gbrain__find_orphans()` — stale frontmatter should clear, 3) spot-check 3 files (had source_query, no source_query, already populated — last should be untouched).

### Doctor score does not auto-refresh
`gbrain doctor` runs against the last embedded state. Run steps 1-4 before step 6 if you want a current score.

### Full rebuild when embedding model changes
When switching gbrain embedding models (e.g., local ollama instead of zeroentropy), you need a full rebuild — see the `gbrain-integration` skill's "Full Rebuild: Changing the Embedding Model" section for the exact sequence.

### `gbrain import .` vs `--no-embed`
- `gbrain import /path --no-embed` — faster, imports without vectors. Then `gbrain embed --stale`.
- `gbrain import .` — imports WITH embedding in one pass (slower but simpler). Use on a fresh brain with no prior chunks.
- `gbrain init --pglite --embedding-model <model>` — sets the embedding model at brain creation time. Required when switching models.

## Usage

### Run full pipeline
```bash
hermes skill wiki-maintenance
```

### Run individual steps
```bash
hermes skill wiki-maintenance --step import
hermes skill wiki-maintenance --step embed
hermes skill wiki-maintenance --step extract
hermes skill wiki-maintenance --step reindex   # now runs gbrain sync (native)
hermes skill wiki-maintenance --step doctor
```

Cron-friendly: exit code 0 on success, non-zero on health degradation.

## Cron Setup

The actual cron delivering this pipeline is **`wiki-maintenance`** — agent job, Sun 09:00 (`0 9 * * 0`), pinned model `deepseek/deepseek-v4-flash` (nous), delivers to Discord. Its pipeline steps (2026-08-12, A6 t_14aa6e85 added step 1.5):

**1.5 HUB REGEN (A6, deterministic):**
```
python C:/Users/chris/AppData/Local/hermes/scripts/wiki/build-concepts-moc.py
```
Regenerates `knowledge/concepts/_index.md` (Concepts MOC) + `_hermes-platform.md` + `_infra.md` + `concepts/README.md` from the LIVE page map (rebuilds the map fresh, recomputes inbound counts excluding hub self-links, re-applies the 6-theme classifier). Commits ONLY those 4 files when changed, push warn-only. Idempotent: "no changes — hubs already live" = clean run. NEVER hand-edit the hub files — run the generator instead. Decision (A6.1): generated hubs via cron, NOT Obsidian Dataview (`.obsidian/community-plugins.json` absent; headless, survives outside Obsidian, no plugin maintenance).

**LINT step is the A5 deterministic gate** (2026-08-12, t_42adc275):

```
python C:/Users/chris/AppData/Local/hermes/scripts/wiki/wiki-link-audit.py
```

- **Gate:** exit 0 = 0 broken links (PASS); exit 1 = broken links found (FAIL — agent must report loudly, never claim clean).
- **Count refresh:** recomputes live page counts and rewrites README.md + governance/SCHEMA.md numbers (excludes `_archive`; `knowledge/` = sum of its 5 content subdirs). Commits ONLY those two files, then pushes (warn-only on push failure).
- **Audit:** appends one record to `governance/tracking/audit/log.jsonl` (success = broken == 0) via `audit_log.py`.
- **Idempotent:** re-running with no changes reports "counts unchanged", exits 0.
- Run standalone: `python scripts/wiki/wiki-link-audit.py [--dry-run] [--no-commit]`.

Legacy (historical, do not recreate): `wiki-brain-health` cron was the earlier name; `frontmatter-auto-heal` (Sun 08:45, no_agent) still runs separately for frontmatter fixes.

## Structural Consolidation

After merging, moving, or removing wiki directories, follow this checklist:

1. **Update SCHEMA.md** — replace the canonical directory tree to match `ls -d */`. Remove stale dirs (`_archive`, `_private`, `audit/`, `personal/`, `queries/`, bare `tracking/`), add new ones (`governance/`, `raw/inbox/`, `scripts/`, `tests/`, `work/`)
2. **Update Subdirectory Rules** — remove rules for deleted dirs (`_archive/`, `raw/assets/`), add rules for new ones (`raw/inbox/`, `governance/audit/`)
3. **Fix WIKI.instructions.md** — update structure table if stale paths referenced
4. **Reindex** — `mcp__gbrain__sync_brain()`
5. **Lint** — `mcp__gbrain__find_orphans()` to verify no new broken links
6. **Verify structural changes:**
   ```bash
   ls -d */                      # dirs match SCHEMA.md tree
   git status --short            # check for unintended side effects
   ```
7. **Commit + push:** `git add -A && git commit -m "W<N>: <summary>" && git push origin main`

## Environment

- Wiki at `C:/Users/<user>/polaris/wiki` (or `HERMES_WIKI_VAULT` env var)
- gbrain CLI in PATH (`~/.bun/bin`)