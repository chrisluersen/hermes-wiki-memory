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
import subprocess
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter

log = logging.getLogger(__name__)

router = APIRouter()

# Subdirectories of knowledge/ we surface counts for.
_KNOWLEDGE_DIRS = ("concepts", "entities", "comparisons", "queries", "references")

# Subdirectories of knowledge/entities/ (where the provider writes dated pages).
_ENTITIES_SUBDIRS = (
    "cooking", "delegations", "fleet", "games", "memory-entries",
    "profiles", "repos", "session-insights",
)


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


def _gbrain_dir() -> Optional[Path]:
    parent = os.environ.get("GBRAIN_HOME", "").strip()
    if not parent:
        return (Path.home() / ".gbrain").resolve()
    raw = Path(parent).expanduser()
    if not raw.is_absolute() or ".." in raw.parts:
        return None
    return (raw / ".gbrain").resolve()


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


def _gbrain_available() -> dict[str, Any]:
    """Probe gbrain WITHOUT running doctor (advisory-lock hang trap)."""
    gb = _gbrain_dir()
    cfg = gb / "config.json" if gb is not None else None
    bin_name = "gbrain" if _platform_is_posix() else "gbrain.cmd"
    on_path = _which(bin_name) or _which("gbrain")
    return {
        "binary_on_path": bool(on_path),
        "config_exists": bool(cfg and cfg.exists()),
        "config_path": str(cfg) if cfg else "",
    }


def _platform_is_posix() -> bool:
    import os
    return os.name == "posix"


def _which(name: str) -> Optional[str]:
    from shutil import which
    try:
        return which(name)
    except Exception:
        return None


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
        "gbrain": _gbrain_available(),
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
    """Page counts by knowledge category and entities subdir."""
    wiki = _wiki_root()
    knowledge = wiki / "knowledge"
    categories: dict[str, int] = {}
    for d in _KNOWLEDGE_DIRS:
        categories[d] = _count_md(knowledge / d)
    entities_dir = knowledge / "entities"
    entities_subdirs: dict[str, int] = {}
    for d in _ENTITIES_SUBDIRS:
        entities_subdirs[d] = _count_md(entities_dir / d)
    return {
        "categories": categories,
        "entities_subdirs": entities_subdirs,
        "total": sum(categories.values()),
    }
