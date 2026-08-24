# Security policy

## Supported versions

Hermes Wiki Memory is experimental. Security fixes are prepared against the current `master`; tagged `0.3.x` releases do not contain the `0.4.0` hardening candidate.

## Reporting a vulnerability

Do not include credentials, private Wiki content, personal information, or exploit payloads in a public issue.

1. Use GitHub's **Report a vulnerability** link when it is available on the repository Security tab.
2. If private reporting is unavailable, open a minimal public issue that says a private security contact is needed. Describe only the affected component and impact category; do not include reproduction details or sensitive data.

Useful non-sensitive information includes:

- affected commit or tag;
- operating system and Hermes version;
- whether the issue affects containment, capture redaction, MCP source isolation, backup/restore, or dashboard disclosure; and
- whether canonical Wiki bytes may have changed.

## Security boundaries

- Markdown Wiki content is canonical user data.
- GBrain indexes are derived and rebuildable.
- The provider must not own or stop the shared GBrain MCP server.
- Automatic captures must be redacted and confined to the configured capture role.
- Live Wiki migration, active-store reinitialization, credential use, and production activation require separate approval.
