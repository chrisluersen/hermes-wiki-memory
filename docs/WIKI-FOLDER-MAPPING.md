# Wiki Folder Mapping

## Decision

Hermes Wiki Memory uses semantic roles, not a mandatory physical taxonomy.
Folders should encode only distinctions that change custody, lifecycle, or
retrieval policy. Page subtype, status, provenance, and identity belong in
frontmatter, links, and generated views.

The deliberately small new-Wiki layout is:

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

The five human-facing choices are:

| Question | Role |
|---|---|
| Not classified yet? | `Inbox/` |
| Supports an active finite outcome? | `Projects/` |
| Reusable understanding? | `Knowledge/` |
| External source material? | `Sources/` |
| Inactive, completed, or superseded? | `Archive/` |

`_meta/` is machine-facing and excluded from ordinary recall.

Within `Sources/`, use one nested rule: preserve the received source in
`Originals/`; put a processed record about one source in `Notes/`.

## Existing Wiki compatibility

This is the target configuration contract for the roadmap. It is not a claim
that the current release already implements every field below.

Existing Wikis must be adopted, not reorganized by force. A compatible mapping
for a Wiki using the legacy role names is:

```yaml
layout: adopt-existing
paths:
  capture: Inbox
  projects: Projects
  knowledge:
    - Topics
    - Ideas
  sources:
    originals: Clippings
    processed: Notes
  meta: _meta
```

Map only paths that already exist, using their exact on-disk spelling and case.
Omit absent roles instead of creating directories implicitly. Adding an
`Archive` role or any other missing folder is a separate approved migration.

For a new Wiki, use `Sources/Originals` and `Sources/Notes`. `Clippings` is a
good existing compatibility name, but `Sources/Originals` is clearer for a new
installation because the preserved material may include PDFs, screenshots,
exports, datasets, and packages—not only web clippings.

Do not require the older universal tree:

```text
knowledge/concepts/
knowledge/entities/
knowledge/comparisons/
knowledge/queries/
work/ personal/ sessions/ plans/
```

That tree mixes ontology, output format, custody, runtime state, and work
state. Those dimensions overlap and should not be forced into exclusive paths.

## Metadata boundary

Durable pages may use a small envelope:

```yaml
id: wk_<opaque-stable-id>
type: concept | entity | decision | runbook | comparison | synthesis | project
status: captured | draft | stable | contested | superseded | archived
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: []
aliases: []
```

Add fields only when needed. Stable IDs are added lazily on touch, not through
a forced whole-vault retrofit. GBrain's `(source_id, slug)` is a locator, not
the permanent identity of a page, because moving a file can change its slug.

## Retrieval policy

- Promote `Knowledge/` and active `Projects/` for ordinary recall.
- Keep processed `Sources/Notes` searchable below curated knowledge.
- Demote `Sources/Originals`/existing `Clippings` and `Archive` by default.
- Exclude `Inbox/` until reviewed.
- Exclude `_meta/`, runtime directories, caches, session exports, and
  quarantine from ordinary Wiki retrieval.
- Keep full Hermes sessions in Hermes state; any transcript derivative is a
  separate derived source, not canonical Wiki knowledge.

The plugin must apply these exclusions explicitly; a schema pack alone is not a
complete retrieval policy.

Paths are case-sensitive configuration values even when the current filesystem
is not. Discovery and migration must preserve the exact on-disk spelling; do
not rely on Windows case folding for portability to Linux or case-sensitive
macOS volumes.

## Migration rule

Do not move existing content merely to make names prettier. A move can change
Obsidian links, GBrain slugs, scripts, and external references. The safe order
is:

1. configure role mapping and exclusions;
2. benchmark representative retrieval;
3. add stable IDs and redirects lazily;
4. harvest reusable project material into Knowledge;
5. archive completed projects as bounded units;
6. consider `Clippings` → `Sources/Originals` only if the usability benefit
   justifies deterministic link rewriting, backup, rollback, and reindex tests.

This document is a product contract and compatibility guide. It does not
authorize a live Wiki migration.
