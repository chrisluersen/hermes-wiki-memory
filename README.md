# Hermes Wiki Memory Provider

A local-first [`MemoryProvider`](https://hermes-agent.nousresearch.com) for a canonical Markdown Wiki, with bounded lexical recall and optional semantic retrieval through a shared [GBrain](https://github.com/garrytan/gbrain) MCP owner.

## What this is — and is not

Hermes Wiki Memory connects three systems with distinct responsibilities:

1. **Hermes owns agent memory lifecycle** — sessions, turns, provider hooks, configuration, backup discovery, and activation.
2. **Markdown owns durable knowledge** — the Wiki is the human-readable canonical store. Git may version it, but this plugin does not stage or commit changes.
3. **GBrain is optional derived retrieval** — Hermes owns the shared MCP connection; this provider never starts, kills, or falls back to a private GBrain process.

This is **not a rewrite or fork of Hermes memory**. It implements Hermes's existing provider contract. It is also **more than a thin GBrain wrapper**: it owns Wiki configuration, bounded lexical fallback, retrieval policy, contained atomic writes, immutable capture events, backup declarations, recovery evidence, and dashboard health.

> **Status: experimental `0.4.0` prerelease; tagged and published.** The exact
> released commit passed disposable lexical-only activation, a representative canonical-Wiki
> backup/restore drill, and canonical-profile lexical-only activation. An
> isolated keyed semantic canary also passed. A later bounded Notes evaluation
> improved retrieval but missed its predeclared production threshold, so the
> validated production posture remains lexical-only and semantic activation is
> still a separate, unperformed operation.

## Current behavior

- **Lexical recall works without GBrain.** Markdown search is bounded by file count, per-file bytes, aggregate bytes, elapsed time, result count, and context size.
- **Explicit retrieval policy.** Runtime/generated/session/cache paths are excluded; durable knowledge and active projects rank above originals and archives.
- **One shared semantic owner.** Optional semantic recall dispatches GBrain's `recall` verb through Hermes's public tool registry. The provider owns no subprocess.
- **Fail-closed semantic admission.** Semantic recall is enabled only when:
  - `memory.wiki.gbrain_source` exactly matches the configured MCP server's `GBRAIN_SOURCE`;
  - the MCP timeout is positive and no more than seven seconds; and
  - the expected `mcp__<server>__recall` tool is registered under the matching toolset.
  Otherwise recall degrades to lexical Markdown search.
- **Semantic role mapping.** `layout: adopt-existing` maps existing folders without creating, moving, or renaming them. Multiple knowledge folders are supported.
- **Safe capture.** Session insights, delegation results, and explicit memory events go only to the configured capture role. Captures are immutable candidates, not automatic promotion into established knowledge.
- **Stable and redacted events.** Event IDs are derived after forced Hermes secret redaction; replay preserves exact bytes; collisions fail closed.
- **Contained atomic writes.** Page writes reject traversal, absolute paths, ADS/device names, unsafe extensions, and resolved escapes; per-page thread/process locking prevents lost cooperative updates.
- **Truthful health.** The provider/dashboard report `available`, `degraded`, or `unavailable` with Wiki, lexical, semantic, and capture facts.
- **Canonical backup contract.** `backup_paths()` returns the Markdown Wiki only. GBrain storage is derived and described by a secret-free rebuild manifest rather than copied live as a required backup.

## Data flow

```text
Hermes turn/session hook
        │
        ├── recall ──> shared GBrain MCP recall (when attested and healthy)
        │                    │
        │                    └── failure/unavailable ──> bounded Markdown lexical recall
        │
        └── capture ─> forced redaction ─> stable event ID ─> immutable Inbox page

Canonical: Markdown Wiki (+ optional Git history)
Derived:   GBrain index, caches, dashboard projections
Canonical sessions: Hermes state.db/session store
```

## Requirements

- Current Hermes Agent with the `MemoryProvider` and public tool-registry interfaces.
- An existing Markdown Wiki. The provider does not scaffold or migrate one during startup.
- Optional: one Hermes-managed GBrain MCP server exposing the `verbs` surface and `recall` tool.
- Optional semantic embeddings backend configured in GBrain, not in this plugin.

## Configuration

```yaml
memory:
  provider: wiki
  wiki:
    root: C:/path/to/wiki
    wiki_context_cap: 1200
    layout: adopt-existing
    paths:
      capture: Inbox
      projects: Projects
      knowledge: [Topics, Ideas]
      sources:
        originals: Clippings
        processed: Notes
      archive: Archive
    gbrain_server: gbrain-local
    gbrain_source: hermes-wiki

mcp_servers:
  gbrain-local:
    # Exact command/args belong to the installed GBrain version.
    timeout: 6
    env:
      GBRAIN_SOURCE: hermes-wiki
```

Root precedence is:

```text
memory.wiki.root → WIKI_PATH → <HERMES_ROOT>/wiki
```

The setup UI exposes comma-separated knowledge paths because Hermes's current setup schema fields are scalar. Configuration is persisted as a list.

### Semantic activation safety

The provider does **not** trust ambient source resolution, a sole source, a brain default, or an unbounded MCP timeout. If exact source/timeout attestation is absent, health is `degraded` and lexical recall remains available.

Existing installations that lack either exact setting remain safely lexical-only until their MCP configuration is separately reviewed and changed.

## Adopt existing, do not migrate

For an existing Wiki, map roles using exact on-disk spelling and case. A compatible example is:

```yaml
layout: adopt-existing
paths:
  capture: Inbox
  projects: Projects
  knowledge: [Topics, Ideas]
  sources:
    originals: Clippings
    processed: Notes
```

No folder is created by role resolution. Automatic capture also refuses to create a missing capture directory. Create/scaffold operations and live migrations are separate, explicit actions.

For a new Wiki created by a separately approved scaffold, the recommended workbench is:

```text
Inbox/
Projects/
Knowledge/
Sources/Originals/
Sources/Notes/
Archive/
_meta/
```

## Health states

| State | Meaning |
|---|---|
| `available` | Wiki readable/writable, lexical recall available, capture role ready, and attested semantic recall registered |
| `degraded` | Wiki/lexical recall works, but semantic recall or capture readiness is unavailable |
| `unavailable` | Wiki is missing/unreadable and no safe recall path exists |

Embedding coverage remains `unknown` unless the shared GBrain owner proves it. The dashboard never runs lock-taking `gbrain doctor` calls.

## Backup, restore, and uninstall

- **Required backup:** canonical Markdown Wiki, including Git metadata when the Wiki is archived as a directory.
- **Derived rebuild:** GBrain state is rebuilt from Markdown; live PGLite bytes are not claimed as a consistent required backup.
- **Rebuild manifest:** records Wiki tree digest, Git head, source ID, and verification requirements without credentials.
- **Temporary restore verification:** tests compare bytes/tree digest, run `git fsck --strict`, and prove lexical recall/exclusion behavior.
- **Data-preserving removal:** plugin-code removal is idempotent and retains Wiki/data paths. Hermes full uninstall remains a separate destructive action requiring verified backup.

The representative canonical-Wiki restore and isolated keyed GBrain canary have
been completed for the released commit. They prove recoverability and the
optional semantic attachment path; they do not by themselves justify production
semantic activation. A bounded derived-Notes evaluation improved retrieval but
did not meet its predeclared acceptance threshold, so lexical-only remains the
validated production posture.

## Verification on merged `master`

The repository includes:

- provider/config/lifecycle tests;
- Windows/POSIX path and locking tests;
- repeated cross-process cooperative-writer tests;
- shared-MCP and error-envelope tests;
- lexical fallback and retrieval-policy tests;
- capture redaction/idempotency/collision tests;
- adopt-existing mapping tests;
- dashboard health/count tests;
- temporary restore/Git/uninstall tests; and
- a deterministic synthetic lexical recall benchmark.

CI runs on Ubuntu and Windows. Some Windows symlink tests skip when the process lacks symlink privileges; containment code is still exercised through non-privileged path tests.

The write model protects cooperative writers and revalidates resolved containment
after acquiring the page lock. It does not claim to defeat a malicious external
process that races a Windows junction/reparse-point swap after revalidation;
native handle-relative I/O would be required for that stronger adversarial model.

## Files

```text
plugin.yaml             provider manifest
__init__.py             Hermes MemoryProvider lifecycle and hooks
wiki_client.py          shared MCP adapter, lexical recall, roles, capture, safe file operations
recovery.py             rebuild manifest and temporary restore/removal verification
dashboard/              read-only health/count/activity UI
SETUP.md                development and activation procedure
docs/                   mapping, design boundaries, and reliability roadmap
tests/                  behavioral, concurrency, recovery, and evaluation tests
.github/                CI, dependency updates, PR and issue templates
SECURITY.md             private-reporting and security-boundary guidance
CONTRIBUTING.md         product invariants and development workflow
```

## Operational setup and remaining gates

`v0.4.0` is published, and representative lexical-only activation is complete.
For another Hermes installation, follow [SETUP.md](SETUP.md): install the exact
published tag's peeled 40-character commit (or another reviewed full SHA)
disabled, map the existing Wiki without moving content, verify a recoverable
backup/restore, then enable lexical-only and inspect detailed health. Do not copy
another installation's absolute paths, secrets, profile state, derived GBrain
store, or source IDs.

Before optional semantic activation:

1. Build a fresh isolated GBrain canary with approved model, dimensions, and
   credential reference.
2. Verify semantic recall on synthetic or explicitly approved non-sensitive
   Markdown.
3. Separately approve the exact live MCP source binding and ≤7-second timeout.
4. Define and pass a local retrieval acceptance set. A canary proves plumbing,
   not production usefulness; if the acceptance set fails, remain lexical-only.

Explicit Windows reparse-point coverage remains desirable where the CI runner
permits it, but the documented threat model does not claim adversarial
post-check junction-race protection. Live Wiki migration, embedding-schema
changes, active-store reinitialization/deletion, and full Hermes uninstall are
not authorized by release publication.

## License

MIT. See [LICENSE](LICENSE).
