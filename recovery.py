"""Recovery contracts for canonical Wiki data and rebuildable derived state."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


def tree_sha256(root: Path) -> str:
    """Hash relative paths and bytes deterministically, excluding Git internals."""
    root = Path(root)
    digest = hashlib.sha256()
    if not root.is_dir():
        return digest.hexdigest()
    for path in sorted(
        (p for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts),
        key=lambda p: p.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=Path(cwd),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def build_rebuild_manifest(
    wiki: Path,
    config: dict[str, Any],
    *,
    plugin_version: str,
) -> dict[str, Any]:
    """Describe canonical inputs required to rebuild derived GBrain state."""
    wiki = Path(wiki).resolve()
    return {
        "schema_version": 1,
        "plugin_version": plugin_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "wiki": {
            "root_hint": wiki.name,
            "tree_sha256": tree_sha256(wiki),
            "git_head": _git("rev-parse", "HEAD", cwd=wiki),
            "required": True,
        },
        "gbrain": {
            "storage_policy": "rebuild",
            "source_id": str(config.get("gbrain_source", "")).strip(),
            "embedding_model": str(config.get("embedding_model", "")).strip(),
        },
        "verification": {
            "required": ["tree_digest", "git_integrity", "lexical_recall"],
            "semantic_recall": "requires separately approved credentials and isolated rebuild",
        },
    }


def verify_restored_wiki(
    source: Path,
    restored: Path,
    *,
    lexical_probe: Callable[[Path], str],
) -> dict[str, Any]:
    """Verify a temporary restore without touching active Wiki or GBrain state."""
    source = Path(source)
    restored = Path(restored)
    fsck = subprocess.run(
        ["git", "fsck", "--strict"],
        cwd=restored,
        capture_output=True,
        text=True,
        timeout=30,
    )
    lexical = lexical_probe(restored)
    return {
        "tree_match": tree_sha256(source) == tree_sha256(restored),
        "git_ok": fsck.returncode == 0 and bool(_git("rev-parse", "HEAD", cwd=restored)),
        "lexical_ok": bool(lexical),
        "lexical_result": lexical,
    }


def remove_plugin_code(
    plugin_dir: Path,
    *,
    retained_paths: Iterable[Path] = (),
) -> dict[str, Any]:
    """Remove plugin code only; canonical and derived data paths are retained."""
    plugin_dir = Path(plugin_dir).resolve()
    resolved_retained = [Path(path).resolve() for path in retained_paths]
    for retained in resolved_retained:
        try:
            retained.relative_to(plugin_dir)
        except ValueError:
            continue
        raise ValueError("retained path is inside plugin directory")
    removed = plugin_dir.exists()
    if removed:
        shutil.rmtree(plugin_dir)
    return {
        "removed": removed,
        "retained_paths": [str(path) for path in resolved_retained],
    }
