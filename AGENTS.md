# AGENTS.md — Hermes Wiki Memory

This repository is the **adapter**, not the user's Wiki. Markdown remains canonical; GBrain is optional derived retrieval; Hermes owns provider and MCP lifecycle.

## Start here

Before installing, configuring, or changing anything, read in this order:

1. `README.md` — product boundary, current verified status, and limitations.
2. `SETUP.md` — executable install, disposable validation, backup/restore, role mapping, activation, and rollback procedure.
3. `SECURITY.md` — secrets and private-reporting boundaries.
4. `docs/WIKI-FOLDER-MAPPING.md` — adopt existing Wiki folders without moving content.
5. `docs/RELIABILITY-ROADMAP.md` — implemented behavior versus optional future work.

If repository prose conflicts with the live Hermes CLI or official Hermes documentation, verify the live command and stop before mutation. Do not improvise around an invalid command.

## Safe default setup sequence

1. Inspect the target Hermes profile, Wiki path, folder case, existing plugin/config state, and backup destination.
2. Validate this repository and use a disposable Hermes profile/Wiki first.
3. Install the published release commit **disabled**:

   ```bash
   hermes plugins install chrisluersen/hermes-wiki-memory \
     --ref 72eea8af5e3168b5ef793164b14506807107ba4c \
     --no-enable
   ```

4. Follow `SETUP.md` exactly for disposable validation.
5. Before canonical activation, create a fresh backup outside destructive profile scope and verify an isolated restore.
6. Map the existing Wiki with `layout: adopt-existing`, exact on-disk spelling/case, and an existing capture directory. Do not create or move optional roles merely to match an example.
7. Activate **lexical-only** first: keep `memory.wiki.gbrain_source` empty, enable without tool override, select provider `wiki`, and verify detailed health shows lexical recall and capture ready while semantic recall is false.
8. Keep the backup, restored copy, and pre-activation config snapshot until verification is complete.

## Semantic retrieval is optional

Do not infer semantic activation from release publication or a successful canary. Before live semantic use, separately approve and verify:

- an isolated GBrain owner and explicit non-sensitive or approved corpus;
- embedding provider/model/dimensions and external credential use;
- a fixed retrieval acceptance set that materially beats lexical recall;
- exact MCP `GBRAIN_SOURCE` attestation and a positive timeout no greater than seven seconds;
- lexical fallback when the semantic owner is unavailable.

If the acceptance set fails, remain lexical-only. Do not lower thresholds, tune against the test set, add a daemon/reranker, index more folders, or rewrite the Wiki in the same scope.

## Hard boundaries

- Never copy credentials, another machine's absolute paths, profile state, source IDs, or live GBrain/PGLite bytes into a new installation.
- Never initialize Git in, reorganize, bulk-edit, or migrate the canonical Wiki merely for this plugin.
- Never index raw/binary `Clippings`, runtime directories, session exports, caches, `_meta`, or Projects without separate scope and retrieval evidence.
- Never start, stop, migrate, reinitialize, or delete an existing GBrain owner/store without exact approval.
- Never enable tool override for this provider.
- Never claim semantic production readiness from infrastructure health alone.
- Treat install, backup creation, restore, canonical activation, external embedding calls, MCP registration, gateway restart, semantic activation, and cleanup/deletion as separate HITL effects.
- Preserve all existing user work and fail closed on ambiguous paths, source scope, credentials, or ownership.

## Verification

For repository changes, run:

```bash
python tests/run.py
python -m py_compile __init__.py wiki_client.py recovery.py dashboard/plugin_api.py
hermes plugins doctor --ci .
git diff --check
```

For an installation, verify the exact installed Git HEAD, plugin version/state, profile-local config, backup/restore evidence, detailed provider health, bounded recall, capture destination, and that no unexpected Wiki files or folders were created.

Do not commit, push, open/merge a PR, modify a GitHub Release, change live Hermes/GBrain state, or delete evidence without the corresponding explicit approval.
