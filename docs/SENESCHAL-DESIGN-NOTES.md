# Design Principles Extracted from Seneschal

## Status

This document records the small set of reliability principles retained from the
experimental `chrisluersen/seneschal` project before that repository is archived.
It is a design input, not a dependency, governance layer, or authorization
system.

- Seneschal source reviewed at commit:
  `da083149399a6e840b5c74f0c33f499a720b0def`
- Hermes Wiki Memory baseline when this record was created:
  `d1db1a5ae692662757af9fbcd4bfd7d2c799b9d8`
- No Seneschal source code was copied.
- General principles are reimplemented independently under this repository's MIT
  license.

## Product boundary

Hermes Wiki Memory remains a small, plug-and-play Hermes `MemoryProvider`.
It is not an agent-estate manager, policy engine, workflow system, task store,
secrets manager, or replacement for native Hermes and Git state.

The product has three responsibilities:

1. recall relevant Wiki knowledge for Hermes;
2. safely capture candidate knowledge into the Wiki;
3. report and maintain the health of its own memory integration.

## Retained principles

### 1. Markdown is canonical; retrieval is derived

The configured Markdown Wiki and its Git history contain durable knowledge.
GBrain embeddings, graph edges, indexes, dashboard counts, and recall caches are
derived and rebuildable. No user-authored fact may exist only in derived state.

### 2. Adopt the existing Wiki

The plugin maps semantic roles—capture, sources, notes, ideas, topics, projects,
index, log, and schema—onto the user's existing layout. It does not force a new
folder tree or create a parallel taxonomy.

### 3. Capture before promotion

Automatically inferred session insights and delegation summaries land in the
configured capture area with source-session provenance and `status: captured`.
They do not silently rewrite canonical topic or project pages. Explicit memory
tool writes remain explicit user/agent actions and may follow their configured
canonical path.

### 4. One GBrain owner per PGLite brain

All Hermes profiles and bots use one shared GBrain owner for a PGLite brain.
The plugin never competes for ownership, kills another owner, or deletes a live
owner's lock. If it cannot attach, recall degrades to lexical search while Wiki
capture remains available.

### 5. Writes are contained, concurrent-safe, and crash-safe

Every plugin-generated path must remain below the configured Wiki root. Page
updates use a cross-process lock, recheck the prior fingerprint after acquiring
the lock, write a sibling temporary file, flush it, and atomically replace the
target. A conflicting writer produces an explicit conflict instead of silent
last-writer-wins data loss.

### 6. Failure is scoped and graceful

The provider exposes only three operational states:

- `available` — Wiki and configured recall paths work;
- `degraded` — canonical Wiki operations work but semantic recall or maintenance
  is unavailable;
- `unavailable` — the canonical Wiki cannot be safely read.

A GBrain, embedding, dashboard, or maintenance failure must not disable safe Wiki
capture or unrelated Hermes operation.

### 7. Health claims come from live checks

Status reports distinguish Wiki readability, Wiki writability, Git state,
semantic recall, lexical recall, embedding coverage, maintenance freshness, and
backup/restore evidence. A successful command is not reported as recovery unless
a representative restored copy was actually opened and queried.

Diagnostics and support output exclude secrets, Wiki bodies, prompts, memory
contents, authorization material, and unnecessary absolute paths.

### 8. Backup and rebuild are both explicit

The provider discovers its actual configured Wiki and GBrain paths without
requiring provider initialization. Backups include canonical state outside
`HERMES_HOME`. Derived GBrain state is either backed up consistently or marked
for rebuild. A temporary restore drill verifies representative Wiki reads, Git
integrity, and lexical/semantic retrieval.

### 9. Uninstall preserves user data

Uninstall removes only plugin-owned integration files and jobs. It preserves the
Wiki, Hermes sessions, built-in memory, and GBrain data unless the user separately
requests data removal. Repeated uninstall is safe and reports leftovers.

### 10. Evaluate recall usefulness, not only infrastructure score

A small fixed question set measures whether expected Wiki pages are recalled,
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
