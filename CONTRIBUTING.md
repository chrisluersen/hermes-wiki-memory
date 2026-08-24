# Contributing

Thanks for helping improve Hermes Wiki Memory.

## Product invariants

Changes must preserve these boundaries:

- Markdown is canonical; GBrain is derived and rebuildable.
- Hermes owns sessions, provider lifecycle, and shared MCP connections.
- Existing Wikis are adopted in place; startup does not migrate or scaffold folders.
- Automatic inference lands in capture and never silently promotes established knowledge.
- No feature may weaken containment, redaction, atomic writes, or data-preserving removal.

## Development setup

Use Python 3.11. Install the test dependencies in an isolated environment:

```bash
python -m pip install fastapi pyyaml pytest
```

The supported standalone test entrypoint is:

```bash
python tests/run.py
```

The runner installs the minimal Hermes contract before pytest imports the repository-root plugin package. Plain `pytest` from the repository root is not the supported clean-environment entrypoint.

Also run:

```bash
python -m py_compile __init__.py wiki_client.py recovery.py dashboard/plugin_api.py
node --check dashboard/dist/index.js
```

For integration work, run the current Hermes plugin doctor against the repository.

## Test-driven changes

For behavior changes:

1. Add a focused failing test.
2. Confirm it fails for the intended reason.
3. Implement the smallest fix.
4. Run the focused test and the complete suite.
5. Add Windows/Linux coverage for path, locking, and portability changes.

Use temporary synthetic Wikis. Do not run tests against personal or production data.

## Pull requests

PRs should state:

- current behavior and intended change;
- canonical versus derived ownership impact;
- files and external systems touched;
- verification commands and exact results;
- skipped tests and why;
- migration/backup/rollback implications; and
- whether any live activation or release action remains approval-gated.

Do not include secrets, private Wiki text, credentials, or personal data in commits, tests, logs, issues, or PRs.
