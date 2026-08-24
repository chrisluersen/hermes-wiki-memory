# Design Principles Extracted from Seneschal

## Status

This document records the small set of reliability principles retained from the
experimental `chrisluersen/seneschal` project before that repository is archived.
It is a design input, not a dependency, governance layer, or authorization
system.

> **Implementation status:** Everything under “Retained principles” is a
> normative target for the hardened product unless explicitly labeled as
> current behavior. Release `0.3.2` does not yet satisfy these guarantees; see
> the reliability roadmap and README limitations.

- Seneschal source reviewed at commit:
  `da083149399a6e840b5c74f0c33f499a720b0def`
- Hermes Wiki Memory baseline when this record was created:
  `d1db1a5ae692662757af9fbcd4bfd7d2c799b9d8`
- No Seneschal source code was copied.
- General principles are reimplemented independently under this repository's MIT
  license.

## Product boundary

Hermes Wiki Memory is intended to remain a small, plug-and-play Hermes memory
provider after direct `MemoryProvider` compatibility and the P0/P1 acceptance
tests are implemented.
It is not an agent-estate manager, policy engine, workflow system, task store,
secrets manager, or replacement for native Hermes and Git state.

The hardened product will have three responsibilities:

1. recall relevant Wiki knowledge for Hermes;
2. safely capture candidate knowledge into the Wiki;
3. report and maintain the health of its own memory integration.

## Retained principles

### 1. Markdown is canonical; retrieval is derived

The configured Markdown Wiki and its Git history will contain durable knowledge.
GBrain embeddings, graph edges, indexes, dashboard counts, and recall caches will
remain derived and rebuildable. No user-authored fact may exist only in derived
state.

### 2. Adopt the existing Wiki

The hardened plugin will map semantic roles onto an existing layout rather than
force a new folder tree or create a parallel taxonomy. The simple new-Wiki
target is `Inbox/`, `Projects/`, `Knowledge/`, `Sources/Originals/`,
`Sources/Notes/`, `Archive/`, and `_meta/`; the roadmap's `adopt-existing`
mapping will let an existing `Clippings/`/`Notes/`/`Topics/`/`Ideas/` layout
remain physically unchanged. Release `0.3.2` does not implement this mapping.

### 3. Capture before promotion

Automatically inferred session insights and delegation summaries will land in the
configured capture area with source-session provenance and `status: captured`.
They will not silently rewrite canonical topic or project pages. Explicit memory
tool writes will remain explicit user/agent actions and may follow their configured
canonical path.

### 4. One GBrain owner per PGLite brain

All approved Hermes profiles and bots will use one shared GBrain owner for a
PGLite brain. The hardened plugin will never compete for ownership, kill another
owner, or delete a live owner's lock. If it cannot attach, recall will degrade to
lexical search while Wiki capture remains available.

### 5. Writes are contained, concurrent-safe, and crash-safe

Every plugin-generated path will remain below the configured Wiki root. Page
updates will use a cross-process lock, recheck the prior fingerprint after
acquiring the lock, write a sibling temporary file, flush it, and atomically
replace the target. A conflicting writer will produce an explicit conflict
instead of silent last-writer-wins data loss.

### 6. Failure is scoped and graceful

The hardened provider will expose only three operational states:

- `available` — Wiki and configured recall paths work;
- `degraded` — canonical Wiki operations work but semantic recall or maintenance
  is unavailable;
- `unavailable` — the canonical Wiki cannot be safely read.

A GBrain, embedding, dashboard, or maintenance failure must not disable safe Wiki
capture or unrelated Hermes operation.

### 7. Health claims come from live checks

Status reports will distinguish Wiki readability, Wiki writability, Git state,
semantic recall, lexical recall, embedding coverage, maintenance freshness, and
backup/restore evidence. A successful command is not reported as recovery unless
a representative restored copy was actually opened and queried.

Diagnostics and support output exclude secrets, Wiki bodies, prompts, memory
contents, authorization material, and unnecessary absolute paths.

### 8. Backup and rebuild are both explicit

The hardened provider will discover its actual configured Wiki and GBrain paths
without requiring provider initialization. Backups will include canonical state
outside `HERMES_HOME`. Derived GBrain state will either be backed up consistently
or marked for rebuild. A temporary restore drill will verify representative Wiki
reads, Git integrity, and lexical/semantic retrieval.

### 9. Uninstall preserves user data

Uninstall will remove only plugin-owned integration files and jobs. It will
preserve the Wiki, Hermes sessions, built-in memory, and GBrain data unless the
user separately requests data removal. Repeated uninstall will be safe and will
report leftovers.

### 10. Evaluate recall usefulness, not only infrastructure score

A small fixed question set will measure whether expected Wiki pages are recalled,
where they rank, query latency, semantic-versus-lexical path, and injected context
size. GBrain health is an operational signal, not the product's definition of
success.

## Explicitly excluded

The following Seneschal concepts are intentionally not part of Hermes Wiki
Memory:

- gates, admission, approval, or authority systems;
- requirement registries and traceability matrices;
- lifecycle state machines and release claims;
- immutable receipt chains or a second evidence database;
- organization overlays and custody-domain frameworks;
- policy composition and trusted-time machinery;
- task, Kanban, worker, project, or provider orchestration;
- cross-domain exchange protocols;
- generalized estate discovery or management;
- fail-closed behavior that blocks ordinary recall when safe degradation exists.

## Simplicity rule

A principle enters the product only when it maps to:

1. one concrete user-facing reliability outcome;
2. a small implementation in the existing plugin;
3. an automated behavioral test.

Otherwise it remains historical Seneschal design material and is not transferred.
