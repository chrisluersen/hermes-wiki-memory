# Setup — Hermes Wiki Memory 0.4.0

This guide covers the published experimental `0.4.0` prerelease and
approval-gated activation. Release publication does not authorize a live Wiki
migration, credential use, or semantic MCP activation.

## Architecture

| Component | Owner | Role |
|---|---|---|
| Hermes | Hermes Agent | Sessions, provider lifecycle, hooks, MCP connections, configuration |
| Markdown Wiki | User | Canonical durable knowledge |
| Git | User/automation | Optional Wiki history; this plugin does not commit |
| GBrain | Shared Hermes MCP owner | Optional derived semantic retrieval |
| This plugin | `wiki` provider | Recall adapter, safe capture, role mapping, health, backup declaration |

The provider never starts or stops GBrain and never falls back to one-shot GBrain CLI calls.

## 0. Prerequisites

- Current Hermes Agent.
- A disposable test Wiki with an existing capture directory for initial
  validation, followed by an existing canonical Wiki for approved activation.
- For semantic recall only: a configured shared GBrain MCP server exposing the `verbs` surface and `recall`.
- Approved embedding credentials/model belong to GBrain, not this repository.

## 1. Validate source; install only a reviewed commit

The `owner/repo` command installs repository state, not uncommitted working-tree
bytes. Validate source without enabling it:

```bash
python tests/run.py
hermes plugins doctor --ci C:/path/to/hermes-wiki-memory
```

Create and select a disposable profile, then install the published tag's peeled
40-character commit **disabled**. Hermes intentionally requires a full SHA for
`--ref`; a tag name is not accepted:

```bash
hermes profile create wiki-test --no-skills
hermes profile use wiki-test
hermes plugins install chrisluersen/hermes-wiki-memory --ref 72eea8af5e3168b5ef793164b14506807107ba4c --no-enable
```

Confirm `hermes profile show wiki-test` identifies the disposable profile. Then
configure it through `hermes memory setup wiki` (or the equivalent profile-local
configuration UI) with a disposable Wiki root and existing capture directory.
Review the saved disposable profile/root configuration before enabling. Then
enable the provider and inspect its runtime status:

```bash
hermes plugins enable wiki --no-allow-tool-override
hermes memory status
```

Restart only the disposable profile's surfaces if the installed Hermes version
requires it. When testing is complete, restore the prior sticky profile with
`hermes profile use <ORIGINAL_PROFILE>`. Do not point either profile at the
canonical Wiki during this procedure.

A `degraded` lexical-only state is expected until semantic source/timeout attestation is configured.

### Canonical lexical-only activation

After disposable validation, take a fresh recoverable backup of the canonical
Wiki and restore it to an isolated directory. Verify representative bytes,
governance files, and bounded lexical recall before touching the live profile.
Then install the same exact plugin revision disabled in the intended profile,
save an `adopt-existing` mapping using exact on-disk path case, keep
`gbrain_source` empty, enable `wiki` without tool override, select
`memory.provider: wiki`, and verify detailed health reports lexical recall and
capture readiness while semantic recall remains false. Keep the restored copy
and pre-activation config snapshot until activation is proven.

## 2. Adopt an existing Wiki without moving content

Example:

```yaml
memory:
  provider: wiki
  wiki:
    root: C:/path/to/wiki
    layout: adopt-existing
    wiki_context_cap: 1200
    paths:
      capture: Inbox
      projects: Projects
      knowledge: [Topics, Ideas]
      sources:
        originals: Clippings
        processed: Notes
      archive: Archive
```

Rules:

- Use exact on-disk spelling and case.
- Every configured role is root-relative.
- Role resolution creates nothing and moves nothing.
- Automatic capture refuses to create a missing capture directory.
- Missing optional roles may be omitted from raw config; the setup UI currently emits scalar fields and uses comma-separated knowledge paths.

For a separately approved new-Wiki scaffold, use:

```text
Inbox/
Projects/
Knowledge/
Sources/Originals/
Sources/Notes/
Archive/
_meta/
```

## 3. Configure optional shared GBrain semantic recall

The provider uses Hermes's already-registered MCP tool:

```text
mcp__<sanitized-server-name>__recall
```

The MCP server must expose GBrain's `verbs` surface. The exact command and arguments depend on the installed GBrain version and should come from its documentation.

Provider admission requires both:

```yaml
memory:
  wiki:
    gbrain_server: gbrain-local
    gbrain_source: hermes-wiki

mcp_servers:
  gbrain-local:
    timeout: 6
    env:
      GBRAIN_SOURCE: hermes-wiki
```

Safety requirements:

- `GBRAIN_SOURCE` must exactly equal `memory.wiki.gbrain_source`.
- `timeout` must be greater than zero and no more than seven seconds, below Hermes's external-memory prefetch deadline.
- The registered `recall` tool must belong to the configured MCP server toolset.
- The provider sends `query`, `limit`, and `budget_tokens`; source scope is fixed at the server boundary.

If any check fails, semantic calls are skipped and bounded lexical recall is used.

## 4. Capture behavior

Automatic events land only under the configured capture role:

```text
<capture>/wke_<stable-event-id>.md
```

Properties:

- Hermes forced secret redaction runs before hashing and persistence.
- Identical replay returns the existing page without changing bytes or timestamps.
- A same-path/different-ID collision fails without overwrite.
- Session insights are labeled heuristic captures.
- Delegations and explicit memory add/replace/remove actions preserve provenance metadata.
- No automatic capture edits Topics, Ideas, Projects, Notes, Clippings, or other established pages.
- Full transcripts remain canonical in Hermes.

## 5. Retrieval policy

Lexical recall:

- searches only contained Markdown;
- rejects symlinked escapes;
- excludes `.git`, `.hermes`, `.gbrain`, `_meta`, sessions, generated, caches, quarantine, and build directories;
- prefers Knowledge/Topics/Ideas, then Projects;
- demotes Sources/Clippings and Archive;
- caps files, bytes per file, total bytes, elapsed time, result count, and injected characters.

Writes are serialized for cooperative plugin writers and containment is
revalidated under the page lock. A malicious external process racing a Windows
junction/reparse swap after that check is outside this Python path-based threat
model; use OS ACLs to prevent untrusted mutation of the Wiki parent directories.

Semantic GBrain recall wins when admitted and successful; all failures degrade to lexical recall.

## 6. Health

`available` requires:

- readable/writable Wiki;
- lexical recall;
- writable configured capture role;
- exact shared-MCP source/timeout attestation; and
- registered GBrain `recall` tool.

`degraded` means Wiki lexical recall still works while capture or semantic retrieval is unavailable. `unavailable` means there is no safe Wiki recall path.

The dashboard is read-only and never calls lock-taking GBrain doctor commands.

## 7. Backup and recovery

`backup_paths()` returns the canonical Markdown Wiki only. GBrain is derived and rebuilt.

Before activation:

1. Verify the Wiki is actually included by the chosen backup process. Hermes skips external provider paths outside the user home.
2. Generate/retain the provider rebuild manifest.
3. Restore to a separate temporary location.
4. Verify exact tree digest, representative bytes, Git HEAD and `git fsck --strict`.
5. Verify lexical recall and exclusion policy.
6. Only with separate approval, build a fresh isolated GBrain home, register the restored source, run full sync/embed, and verify semantic recall.

Never test recovery against the active PGLite store.

## 8. Plugin-code removal

Normal `hermes plugins remove wiki` removes the plugin install directory. The
provider's tested removal helper refuses to proceed if a declared retained path
is inside that directory. Plugin-code removal must retain:

- Wiki files and Git history;
- GBrain state;
- Hermes sessions/state.db;
- built-in Hermes memory; and
- user configuration, which may need manual cleanup afterward.

This is not a claim about full Hermes uninstall. Full Hermes uninstall can
remove an in-root Wiki and therefore requires a verified backup. No full
uninstall is authorized by this guide.

## 9. Development verification

```bash
python tests/run.py
python -m py_compile __init__.py wiki_client.py recovery.py dashboard/plugin_api.py
hermes plugins doctor --ci .
```

CI runs the behavioral suite on Ubuntu and Windows. A symlink test may skip on Windows processes lacking symlink privileges.

## 10. Verified evidence and remaining gates

Completed release evidence:

- Ubuntu and Windows behavioral CI passed on merged `master`;
- real Hermes loading and plugin-doctor checks passed;
- disposable lexical-only activation passed twice in separate real-Hermes
  processes against a synthetic Wiki; and
- the disposable profile, plugin, and fixture were removed afterward;
- an external canonical-Wiki backup and representative isolated restore passed;
- canonical-profile lexical-only activation passed with rollback evidence; and
- an isolated keyed GBrain semantic canary passed without changing the live
  semantic source.

Each installation must still separately approve and verify:

- its own backup/restore scope;
- its exact existing-folder role mapping; and
- canonical-profile enablement.

Semantic use additionally requires separate approval for:

- a fresh isolated GBrain canary with approved embedding settings;
- a bounded local retrieval acceptance set that must pass before production;
- exact live GBrain MCP source/timeout configuration; and
- a tested lexical fallback when the shared semantic owner is unavailable.

The `v0.4.0` tag and GitHub prerelease are published. That publication remains
separate from any installation's canonical or semantic activation.

Do not bundle live Wiki migration, GBrain schema changes, active-store reinitialization, or full Hermes uninstall with plugin activation.

## License

MIT. See [LICENSE](LICENSE).
