# Setup — Hermes Wiki Memory 0.4.0 runtime + merged migration tooling

This guide covers the published experimental `0.4.0` provider runtime plus the
repository-owned migration tooling merged afterward at
`f4a408c3a84bb44ae0adc202dd395587b61087b7`. Provider runtime files are
byte-identical between those revisions. Install that immutable provider commit;
run `prepare_backup_evidence.py` and the documentation/tests from the separately
reviewed current checkout. Release publication does not authorize a live Wiki
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
bytes. Source validation requires Python 3.11 plus `fastapi`, `pyyaml`, and
`pytest`. Install them in an isolated Python environment, then validate without
enabling the plugin:

```bash
python -m pip install fastapi pyyaml pytest
python tests/run.py
hermes plugins doctor --ci C:/path/to/hermes-wiki-memory
```

Create and select a disposable profile. Current Hermes scans the complete Git
tree during `plugins install`; this instruction-bearing repository can receive
a `DANGEROUS` verdict from false-positive persistence matches in `AGENTS.md`,
plans, and setup prose even after the exact source and runtime files have been
reviewed. A dangerous verdict cannot be accepted with `--force`.

Do not disable scanning globally or leave it disabled. After validating this
exact checkout, record the active profile's prior value, install the immutable
40-character commit **disabled** under a shell trap, and restore the prior
setting even if installation fails. Hermes intentionally requires a full SHA
for `--ref`; a tag name is not accepted:

```bash
hermes profile create wiki-test --no-skills
hermes profile use wiki-test

install_reviewed_wiki_plugin() (
  set -e
  PROFILE_NAME=${1:?pass the exact active profile name}
  REVIEWED_CHECKOUT_SHA="REPLACE_WITH_REVIEWED_CURRENT_CHECKOUT_40_CHARACTER_SHA"
  test "$(git rev-parse HEAD)" = "$REVIEWED_CHECKOUT_SHA"
  test -z "$(git status --porcelain)"

  SCAN_WAS_SET=true
  SCAN_PREVIOUS=$(hermes config get plugins.scan_on_install 2>/dev/null) || SCAN_WAS_SET=false
  restore_plugin_scan() {
    if [ "$SCAN_WAS_SET" = true ]; then
      hermes config set plugins.scan_on_install "$SCAN_PREVIOUS"
    else
      hermes config unset plugins.scan_on_install
    fi
  }
  trap restore_plugin_scan EXIT
  hermes config set plugins.scan_on_install false
  hermes plugins install chrisluersen/hermes-wiki-memory --ref f4a408c3a84bb44ae0adc202dd395587b61087b7 --no-enable
  restore_plugin_scan
  trap - EXIT

  PROFILE_PATH=$(hermes profile show "$PROFILE_NAME" | python -c "import sys; print(next(line.split(':', 1)[1].strip() for line in sys.stdin if line.startswith('Path:')))" )
  PLUGIN_DIR="$PROFILE_PATH/plugins/wiki"
  test "$(git -C "$PLUGIN_DIR" rev-parse HEAD)" = "f4a408c3a84bb44ae0adc202dd395587b61087b7"
  test -z "$(git -C "$PLUGIN_DIR" status --porcelain)"
)
install_reviewed_wiki_plugin wiki-test
```

If `plugins.scan_on_install` was explicitly `true`, the restoration performed
above is equivalent to `hermes config set plugins.scan_on_install true`; if the
key was absent, `hermes config unset plugins.scan_on_install` restores the
default-on state without persisting a new setting. Stop if the scanner state
cannot be restored or the installed Git checkout is not the exact clean commit.
Apply the same bounded sequence in the intended Personal profile, passing its
exact reviewed profile name to `install_reviewed_wiki_plugin`; never copy the
disposable plugin directory or profile state.

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

## 2. Choose the existing-Wiki path explicitly

There are two safe operator-selected choices. They are not a startup menu and
the provider never chooses or executes one automatically.

### Option A — map in place

Use `layout: adopt-existing` with exact existing folder names. This creates,
moves, renames, and overwrites nothing. Continue at **Adopt an existing Wiki
without moving content** below.

### Option B — migrate once

Use the explicit `plan → apply → verify → rollback` workflow, then activate
`layout: workbench`. This is the intended Personal Hermes path.

There is no overwrite mode. Destination overwrite is refused, collisions and
unknown roots block planning, and source drift or missing backup/rehearsal
evidence blocks apply. Existing destination content must be classified or
resolved in a new reviewed plan; it is never replaced in place.

### Canonical lexical-only activation

After disposable validation, install the same exact plugin revision disabled in
the intended profile. Complete the backup, rehearsal, apply, and verification
procedure below before activation. After successful migration verification,
save `layout: workbench` with the exact canonical paths, keep `gbrain_source`
empty, enable `wiki` without tool override, select `memory.provider: wiki`, and
verify detailed health reports lexical recall and capture readiness while
semantic recall remains false. Keep the backup, restored copy, migration
evidence, and pre-activation config snapshot until separately approved cleanup.

### One-time Personal Wiki migration to the canonical workbench

For the intended Personal Hermes installation, do not keep a permanent mapping
between legacy folders and the preferred layout. Perform one explicit **one-time
canonical migration** to:

```text
Inbox/
Projects/
Knowledge/
Sources/Originals/
Sources/Notes/
Archive/
_meta/
```

Normal plugin startup never migrates. The migration lifecycle is:

```text
plan → apply → verify → rollback
```

Planning is read-only. Write its outputs outside the canonical Wiki. If the
Wiki contains `.git`, retain `.git` explicitly in the reviewed decisions file;
the migration accounts for hidden objects but never guesses their disposition:

```bash
python migration_cli.py plan \
  --wiki C:/path/to/wiki \
  --decisions C:/path/to/evidence/migration-decisions.json \
  --json-out C:/path/to/evidence/migration-plan.json \
  --report-out C:/path/to/evidence/migration-plan.md
```

The plan recursively inventories files, hidden paths, attachments, links,
embeds, case/Unicode collisions, Windows-reserved names, and unsupported link or
filesystem objects. Unknown roots and ambiguous destinations remain blockers.
After reviewing them, use an external JSON decision map. Each root may be
`retain`, exact `map` with a safe relative `destination`, or
`review-required`; invalid roots/actions/paths fail closed. Decisions are part
of the exact plan SHA-256. Example:

```json
{
  ".git": {"action": "retain"},
  "Mystery": {"action": "map", "destination": "Knowledge/Mystery"}
}
```

Review the report and exact plan SHA-256; planning performs zero Wiki/config
writes. Markdown files larger than 8 MiB block rewrite planning for explicit
review rather than being loaded without a bound.

Before apply, require all of these external artifacts:

- a verified external backup containing the complete source tree;
- a pristine isolated backup restore for rollback;
- a separate successful isolated rehearsal Wiki;
- backup evidence bound to the source-tree SHA-256;
- rehearsal evidence bound to the source-tree SHA-256 and exact approved plan SHA-256;
- an external append-only journal path; and
- an external exclusive lock path.

#### Create and independently verify the Wiki-only backup

Backup creation and restore verification are separate HITL effects. Both output
paths must be outside the canonical Wiki, must have existing parent
directories, and must not already exist. The helper includes hidden paths and
empty directories, so retain `.git` and its history when present. It refuses
symlinks/reparse points, special objects, unsafe names, source drift, archive
tampering, traversal, duplicate archive members, and overwrite.

After separate backup-creation approval:

```bash
python prepare_backup_evidence.py create \
  --wiki C:/path/to/wiki \
  --archive C:/path/to/evidence/wiki-backup.zip \
  --result-out C:/path/to/evidence/backup-creation.json
```

Optional read-only archive inspection:

```bash
python -m zipfile -t C:/path/to/evidence/wiki-backup.zip
python -m zipfile -l C:/path/to/evidence/wiki-backup.zip
```

After separate isolated-restore approval:

```bash
python prepare_backup_evidence.py verify \
  --wiki C:/path/to/wiki \
  --creation-result C:/path/to/evidence/backup-creation.json \
  --restore C:/path/to/evidence/backup-restore \
  --evidence-out C:/path/to/evidence/backup.json
```

The helper independently stream-hashes the archive, safely restores it to a
new directory, compares the exact migration inventory/tree hash, and writes the
`backup.json` consumed by apply/verify/rollback. Backup evidence includes
`backup_sha256` and `restore_path`:

```json
{"verified": true, "source_tree_sha256": "<sha256>", "backup_path": "C:/external/wiki-backup.zip", "backup_sha256": "<archive-sha256>", "restore_path": "C:/external/backup-restore"}
```

Copy the pristine restore to a separate rehearsal Wiki, then exercise the exact
plan through the existing apply command in rehearsal mode:

```bash
python migration_cli.py apply --rehearsal \
  --wiki C:/external/rehearsal-wiki \
  --plan C:/path/to/evidence/migration-plan.json \
  --approved-plan-sha256 <approved-plan-sha256> \
  --journal C:/path/to/evidence/rehearsal-journal.jsonl \
  --lock C:/path/to/evidence/rehearsal.lock \
  --rehearsal-result C:/path/to/evidence/rehearsal.json
```

The result binds `source_tree_sha256`, `plan_sha256`, `final_tree_sha256`,
`rehearsal_wiki`, and `journal_path`. Canonical apply independently reruns
verification against that Wiki and journal; a bare `verified: true` declaration
is never sufficient.

Apply only after separate approval of the exact plan hash:

```bash
python migration_cli.py apply \
  --wiki C:/path/to/wiki \
  --plan C:/path/to/evidence/migration-plan.json \
  --approved-plan-sha256 <approved-plan-sha256> \
  --backup-evidence C:/path/to/evidence/backup.json \
  --rehearsal-evidence C:/path/to/evidence/rehearsal.json \
  --journal C:/path/to/evidence/migration-journal.jsonl \
  --lock C:/path/to/evidence/migration.lock \
  --apply
```

Apply refuses source drift, blockers, destination overwrite, unsafe paths,
wrong hashes, missing evidence, and lock contention. If interrupted, inspect the
journal and rerun the same command with `--resume`; remaining sources and
completed destinations are revalidated before another write.

Independently verify after apply:

```bash
python migration_cli.py verify \
  --wiki C:/path/to/wiki \
  --plan C:/path/to/evidence/migration-plan.json \
  --journal C:/path/to/evidence/migration-journal.jsonl \
  --backup-evidence C:/path/to/evidence/backup.json \
  --result-out C:/path/to/evidence/migration-verification.json \
  --report-out C:/path/to/evidence/migration-verification.md \
  --capture-probe
```

Verification checks exact accounting and hashes, canonical directories, removed
legacy roots, supported path-qualified wikilinks/embeds/Markdown links,
bounded lexical retrieval from Knowledge/Projects/Sources/Notes, disposable
capture readiness, and semantic inactivity.
`rollback_ready` is true only when verification independently revalidates the
external backup artifact hash and pristine restore tree; without
`--backup-evidence`, it remains false.

Rollback is backup-first. It verifies the isolated restored tree before moving
the migrated tree to a retained external path and restoring canonical bytes.
It also retains the same-volume original hold after a successful swap; both
copies remain cleanup-gated evidence:

```bash
python migration_cli.py rollback \
  --wiki C:/path/to/wiki \
  --backup-evidence C:/path/to/evidence/backup.json \
  --expected-source-tree-sha256 <pre-migration-tree-sha256> \
  --retained-migrated-tree C:/path/to/evidence/retained-migrated-tree \
  --rollback
```

The migration does not initialize Git, start/stop GBrain, activate semantics, or
delete the backup, rehearsal, plan, journal, verification evidence, or retained
tree. Semantic activation remains separate and cleanup remains separate.

After successful verification, save this provider configuration and activate it
through the normal separately approved Hermes configuration path:

```yaml
memory:
  provider: wiki
  wiki:
    layout: workbench
    paths:
      capture: Inbox
      projects: Projects
      knowledge: Knowledge
      sources:
        originals: Sources/Originals
        processed: Sources/Notes
      archive: Archive
    gbrain_source: ""
```

Before changing configuration, separately approve and export the intended
profile as the pre-activation snapshot:

```bash
hermes profile export <PERSONAL_PROFILE> \
  --output C:/path/to/evidence/personal-profile-pre-wiki.tar.gz
```

Then apply the exact lexical-only configuration through Hermes's atomic config
writer. Replace only the Wiki root/profile placeholder with the reviewed
Personal values:

```bash
hermes profile use <PERSONAL_PROFILE>
hermes config set --force memory.wiki.root C:/path/to/wiki
hermes config set --force memory.wiki.layout workbench
hermes config set --force memory.wiki.paths.capture Inbox
hermes config set --force memory.wiki.paths.projects Projects
hermes config set --force memory.wiki.paths.knowledge Knowledge
hermes config set --force memory.wiki.paths.sources.originals Sources/Originals
hermes config set --force memory.wiki.paths.sources.processed Sources/Notes
hermes config set --force memory.wiki.paths.archive Archive
hermes config set --force memory.wiki.gbrain_server wiki-lexical-only-unregistered
hermes config set --force memory.wiki.gbrain_source ""
hermes config set memory.provider wiki
hermes plugins enable wiki --no-allow-tool-override
```

Read back exact saved state and runtime status:

```bash
hermes config get memory.wiki --json
hermes config get memory.provider
hermes plugins show wiki
hermes memory status
```

Require the reviewed Wiki root, `layout: workbench`, canonical role paths,
lexical recall true, capture ready true, and semantic recall remains false.
`--force` only suppresses the core CLI's unknown-key notice for plugin-owned
leaf settings; it does not replace the `memory.wiki` mapping because every
write uses a dotted leaf path.
If any fact differs, stop and use the retained migration evidence or separately
approved rollback; do not activate GBrain or delete evidence to make health
appear green.

## Personal Hermes migration prompt

> Clone this repository and switch this session into its root. Read `AGENTS.md`.
> I explicitly prefer a one-time migration to the canonical power-user
> workbench layout rather than permanent `adopt-existing` mapping. Inventory my
> Personal Wiki read-only, classify every existing path, create and verify an
> external backup and isolated rehearsal restore, then produce an exact
> hash-bound migration/link-rewrite/rollback plan. Stop for my approval before
> changing the canonical Wiki. After approval, migrate once, verify bytes,
> links, attachments, capture, and lexical retrieval, set `layout: workbench`,
> and leave semantic activation and cleanup separately gated. Do not build a
> daemon, dual-layout synchronization layer, or generalized migration framework.

## 3. Adopt an existing Wiki without moving content

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

## 4. Configure optional shared GBrain semantic recall

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

## 5. Capture behavior

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

## 6. Retrieval policy

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

## 7. Health

`available` requires:

- readable/writable Wiki;
- lexical recall;
- writable configured capture role;
- exact shared-MCP source/timeout attestation; and
- registered GBrain `recall` tool.

`degraded` means Wiki lexical recall still works while capture or semantic retrieval is unavailable. `unavailable` means there is no safe Wiki recall path.

The dashboard is read-only and never calls lock-taking GBrain doctor commands.

## 8. Backup and recovery

`backup_paths()` returns the canonical Markdown Wiki only. GBrain is derived and rebuilt.

Before activation:

1. Verify the Wiki is actually included by the chosen backup process. Hermes skips external provider paths outside the user home.
2. Generate/retain the provider rebuild manifest.
3. Restore to a separate temporary location.
4. Verify exact tree digest, representative bytes, Git HEAD and `git fsck --strict`.
5. Verify lexical recall and exclusion policy.
6. Only with separate approval, build a fresh isolated GBrain home, register the restored source, run full sync/embed, and verify semantic recall.

Never test recovery against the active PGLite store.

## 9. Plugin-code removal

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

## 10. Development verification

```bash
python tests/run.py
python -m py_compile __init__.py wiki_client.py recovery.py migration.py migration_cli.py prepare_backup_evidence.py dashboard/plugin_api.py
hermes plugins doctor --ci .
```

CI runs the behavioral suite on Ubuntu and Windows. A symlink test may skip on Windows processes lacking symlink privileges.

## 11. Verified evidence and remaining gates

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
