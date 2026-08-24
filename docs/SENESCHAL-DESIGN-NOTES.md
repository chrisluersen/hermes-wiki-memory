# Design Principles Extracted from Seneschal

## Status

This document records the small set of reliability principles retained from the
experimental `chrisluersen/seneschal` project before that repository is archived.
It is a design input, not a dependency, governance layer, or authorization
system.

> **Implementation status:** Candidate `0.4.0` implements the bounded core of
> these principles locally. Live semantic activation, representative private-
> Wiki restore/rebuild evidence and Windows reparse coverage remain gated; see
> the reliability roadmap.

- Seneschal source reviewed at commit:
  `da083149399a6e840b5c74f0c33f499a720b0def`
- Hermes Wiki Memory baseline when this record was created:
  `d1db1a5ae692662757af9fbcd4bfd7d2c799b9d8`
- No Seneschal source code was copied.
- General principles are reimplemented independently under this repository's MIT
  license.

## Product boundary

Hermes Wiki Memory is intended to remain a small, plug-and-play Hermes memory
provider. Direct `MemoryProvider` compatibility is now implemented; the
remaining P0/P1 acceptance tests still gate production readiness.
It is not an agent-estate manager, policy engine, workflow system, task store,
secrets manager, or replacement for native Hermes and Git state.

The product has three bounded responsibilities:

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

The candidate maps semantic roles onto an existing layout rather than
force a new folder tree or create a parallel taxonomy. The simple new-Wiki
target is `Inbox/`, `Projects/`, `Knowledge/`, `Sources/Originals/`,
`Sources/Notes/`, `Archive/`, and `_meta/`; the roadmap's `adopt-existing`
mapping lets an existing `Clippings/`/`Notes/`/`Topics/`/`Ideas/` layout remain
physically unchanged without creating or moving folders.

### 3. Capture before promotion

Automatically inferred session insights and delegation summaries land in the
configured capture area with source-session provenance and `status: captured`.
They will not silently rewrite canonical topic or project pages. Explicit memory
tool add/replace/remove events also land as immutable captures; promotion into a
topic, project, or other established page remains a separate explicit action.

### 4. One GBrain owner per PGLite brain

Approved Hermes profiles and bots use the Hermes-managed shared GBrain MCP owner.
The plugin never competes for ownership, kills another
owner, or deletes a live owner's lock. If it cannot attach, recall degrades to
lexical search while Wiki capture remains available.

### 5. Writes are contained, concurrent-safe, and crash-safe

Every plugin-generated path remains below the configured Wiki root. Immutable
capture creation and append updates use cross-process locking, sibling temporary
files, flush/fsync, and atomic replacement. Capture collisions fail closed, and
mutable replacement can require a matching prior fingerprint under the lock.

### 6. Failure is scoped and graceful

The provider exposes three operational states:

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

The provider discovers its configured Wiki without initialization. Canonical
Markdown is the required backup; derived GBrain state is marked for rebuild in a
secret-free manifest. A temporary synthetic restore verifies bytes, Git integrity,
and lexical retrieval. A private-Wiki restore plus semantic rebuild remains gated.

### 9. Plugin-code removal preserves user data

Plugin-code removal deletes only the plugin install directory and refuses to run
when a declared retained path is nested inside it. It preserves external Wiki,
Hermes-session, built-in-memory, and GBrain paths. This does not describe full
Hermes uninstall, which remains separately destructive and backup-gated.

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
