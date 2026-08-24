"""Wiki Memory dashboard plugin — backend API routes.

Mounted at /api/plugins/wiki/ by the dashboard plugin system.

This is the status + activity pane for the wiki memory provider (hermes-wiki-memory):
  - overview  — aggregate health: wiki location, page counts, git head, gbrain
                availability, provider status, config summary.
  - activity  — recent wiki git commits (the durable activity log).
  - counts    — page counts by knowledge/ category and by entities subdir.

Everything is read LIVE from the on-disk sources at request time — no mirrors,
no sync, no cache. The durable source of truth for "what changed in the brain"
is the wiki git history, so activity is derived from git log, not from any
sidecar the plugin maintains.

IMPORTANT (proven 2026-08-23): NEVER call `gbrain doctor` (or any gbrain CLI
that takes the advisory DB lock) from this API. gbrain holds a schema advisory
lock during embed/sync; a doctor call can hang for up to 600s and time out
(exit 124) — which would stall the whole dashboard request. gbrain availability
is probed here WITHOUT running doctor: we check the binary exists and the
config.json resolves. Full health is gbrain's own job, surfaced separately.

Security note
-------------
Plugin HTTP routes go through the dashboard's session-token auth middleware
just like core API routes. This plugin is read-only — it exposes no mutating
endpoints, so the blast radius of the token is bounded to information
disclosure of wiki page counts, commit subjects, and plugin config values.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter

log = logging.getLogger(__name__)

router = APIRouter()


def _hermes_root() -> Path:
    """Resolve the shared Hermes root that anchors the wiki.

    Mirrors kanban_db.kanban_home(): get_default_hermes_root() returns
    ``<root>`` even when HERMES_HOME is ``<root>/profiles/<name>`` — the wiki
    brain is shared across profiles by design, so it must resolve to the root.
    """
    from hermes_constants import get_default_hermes_root

    return get_default_hermes_root()


def _wiki_root() -> Path:
    """Resolve the same Wiki root precedence as the memory provider."""
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly() or {}
        memory = config.get("memory", {}) if isinstance(config, dict) else {}
        wiki = memory.get("wiki", {}) if isinstance(memory, dict) else {}
        configured = str(wiki.get("root", "")).strip() if isinstance(wiki, dict) else ""
        if configured:
            return Path(configured).expanduser().resolve()
    except Exception as exc:
        log.debug("wiki dashboard: config unavailable: %s", exc)
    env = os.environ.get("WIKI_PATH", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (_hermes_root() / "wiki").resolve()


def _wiki_config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly() or {}
        memory = config.get("memory", {}) if isinstance(config, dict) else {}
        wiki = memory.get("wiki", {}) if isinstance(memory, dict) else {}
        return wiki if isinstance(wiki, dict) else {}
    except Exception:
        return {}


def _health(wiki: Path) -> dict[str, Any]:
    cfg = _wiki_config()
    server = str(cfg.get("gbrain_server", "gbrain")).strip() or "gbrain"
    source = str(cfg.get("gbrain_source", "")).strip()
    attested_source = ""
    timeout: Any = None
    try:
        from hermes_cli.config import load_config_readonly

        full = load_config_readonly() or {}
        servers = full.get("mcp_servers", {}) if isinstance(full, dict) else {}
        server_cfg = servers.get(server, {}) if isinstance(servers, dict) else {}
        if isinstance(server_cfg, dict):
            env = server_cfg.get("env", {}) if isinstance(server_cfg.get("env", {}), dict) else {}
            attested_source = str(env.get("GBRAIN_SOURCE", "")).strip()
            timeout = server_cfg.get("timeout")
    except Exception:
        pass
    readable = wiki.is_dir() and os.access(wiki, os.R_OK)
    writable = wiki.is_dir() and os.access(wiki, os.W_OK)
    paths = cfg.get("paths", {}) if isinstance(cfg.get("paths", {}), dict) else {}
    capture_path = str(paths.get("capture", "Inbox")).strip().replace("\\", "/")
    capture = wiki / capture_path
    capture_ready = capture.is_dir() and os.access(capture, os.W_OK)
    semantic = False
    if (
        readable
        and source
        and source == attested_source
        and isinstance(timeout, (int, float))
        and 0 < float(timeout) <= 7
    ):
        try:
            from tools.registry import registry

            safe_server = re.sub(r"[^A-Za-z0-9_]", "_", server)
            semantic = registry.get_entry(f"mcp__{safe_server}__recall") is not None
        except Exception:
            semantic = False
    status = (
        "unavailable"
        if not readable
        else "available"
        if semantic and writable and capture_ready
        else "degraded"
    )
    return {
        "status": status,
        "wiki_readable": readable,
        "wiki_writable": writable,
        "lexical_recall": readable,
        "semantic_recall": semantic,
        "capture_ready": capture_ready,
        "capture_path": capture_path,
        "gbrain_server": server,
        "gbrain_source": source,
    }



def _git(*args: str, cwd: Path) -> Optional[str]:
    """Run a git command; return stdout or None on any failure."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("wiki dashboard: git %s failed: %s", args[0], exc)
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def _count_md(root: Path) -> int:
    """Count .md files under a dir (non-recursive unless asked)."""
    if not root.exists():
        return 0
    return sum(1 for p in root.glob("*.md"))



@router.get("/overview")
def get_overview() -> dict[str, Any]:
    """Aggregate brain-health snapshot for the wiki tab."""
    wiki = _wiki_root()
    return {
        "wiki_root": str(wiki),
        "wiki_exists": wiki.exists(),
        "git_head": _git("rev-parse", "--short", "HEAD", cwd=wiki),
        "git_branch": _git("branch", "--show-current", cwd=wiki),
        "git_ahead": _git_ahead(wiki),
        "health": _health(wiki),
        "last_commit": _last_commit(wiki),
    }


def _git_ahead(wiki: Path) -> Optional[str]:
    """Count of unpushed commits, e.g. '2' or None if not a git repo."""
    out = _git("rev-list", "--count", "@{u}..HEAD", cwd=wiki)
    return out


def _last_commit(wiki: Path) -> Optional[dict[str, Any]]:
    """Most recent commit (short hash, subject, author date ISO)."""
    out = _git(
        "log", "-1", "--format=%h%x09%s%x09%aI",
        cwd=wiki,
    )
    if not out:
        return None
    parts = out.split("\t")
    if len(parts) < 3:
        return {"hash": parts[0] if parts else "", "subject": "", "date": ""}
    return {"hash": parts[0], "subject": parts[1], "date": parts[2]}


@router.get("/activity")
def get_activity(limit: int = 15) -> dict[str, Any]:
    """Recent wiki commits — the durable activity log of the brain."""
    limit = max(1, min(int(limit), 100))
    wiki = _wiki_root()
    out = _git(
        "log", f"-{limit}", "--format=%h%x09%s%x09%aI",
        cwd=wiki,
    )
    commits: list[dict[str, str]] = []
    if out:
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            commits.append({"hash": parts[0], "subject": parts[1], "date": parts[2]})
    return {"commits": commits, "count": len(commits)}


@router.get("/counts")
def get_counts() -> dict[str, Any]:
    """Page counts by configured semantic role."""
    wiki = _wiki_root()
    cfg = _wiki_config()
    paths = cfg.get("paths", {}) if isinstance(cfg.get("paths", {}), dict) else {}
    sources = paths.get("sources", {}) if isinstance(paths.get("sources", {}), dict) else {}

    def values(value: Any, default: str) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return [str(value or default)]

    role_paths = {
        "capture": values(paths.get("capture"), "Inbox"),
        "projects": values(paths.get("projects"), "Projects"),
        "knowledge": values(paths.get("knowledge"), "Knowledge"),
        "originals": values(sources.get("originals"), "Sources/Originals"),
        "processed": values(sources.get("processed"), "Sources/Notes"),
        "archive": values(paths.get("archive"), "Archive"),
    }
    roles = {
        role: sum(1 for relative in relatives for path in (wiki / relative).rglob("*.md") if path.is_file())
        for role, relatives in role_paths.items()
    }
    return {"roles": roles, "total": sum(roles.values())}
