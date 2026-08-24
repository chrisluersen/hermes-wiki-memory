"""Wiki client for gbrain CLI + wiki file operations.

Shared between MemoryProvider and ContextEngine plugins.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from typing import Any, Optional

from hermes_constants import get_default_hermes_root

logger = logging.getLogger(__name__)


def _is_windows() -> bool:
    """Platform seam for Windows-only locking/retry behavior."""
    return os.name == "nt"

# Shared wiki brain lives at the Hermes ROOT, not the profile home — so every
# profile/bot in the fleet queries and writes the SAME wiki. get_hermes_home()
# returns profiles/<name> under a profile, which has no wiki/; the root does.
# WIKI_PATH env (e.g. in $HERMES_HOME/.env) overrides the default.
def resolve_wiki_path(config: Optional[dict] = None) -> Path:
    """Resolve one canonical Wiki root for provider and file operations.

    Provider config wins over the compatibility environment variable; both
    are resolved at call time so setup/tests can change them after import.
    """
    if config:
        configured = str(config.get("root", "")).strip()
        if configured:
            return Path(configured).expanduser().resolve()
    env = os.environ.get("WIKI_PATH", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (get_default_hermes_root() / "wiki").resolve()


WIKI_PATH = resolve_wiki_path()


# Per-model cap (chars) for the wiki context injected into the prompt.
# Conservative — keeps the injected block well under the model's window so
# the rest of the system prompt + conversation still fits. Tunable per model
# and overrideable globally via HERMES_WIKI_CONTEXT_MAX_CHARS.
MODEL_CONTEXT_CAP_CHARS = {
    # Tiny free tiers — small windows, overflow easily.
    "tencent/hy3:free": 1200,
    "deepseek/deepseek-chat:free": 1500,
}
DEFAULT_WIKI_CONTEXT_CHARS = 3000


def wiki_context_cap(model: str = "", config: Optional[dict] = None) -> int:
    """Resolve the max injected wiki-context chars for the active model.

    Priority: config.yaml memory.wiki.wiki_context_cap > HERMES_WIKI_CONTEXT_MAX_CHARS env
    > exact model match > ':free' heuristic (tight window) > provider prefix match > default.
    """
    # 1. config.yaml (preferred — user-facing, no env var needed)
    if config:
        cap = config.get("wiki_context_cap")
        if isinstance(cap, int) and cap > 0:
            return cap
    # 2. env override (kept for scripting/CI)
    env = os.environ.get("HERMES_WIKI_CONTEXT_MAX_CHARS")
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    if model:
        if model in MODEL_CONTEXT_CAP_CHARS:
            return MODEL_CONTEXT_CAP_CHARS[model]
        if ":free" in model:
            return 1200
        provider = model.split("/")[0]
        for key, val in MODEL_CONTEXT_CAP_CHARS.items():
            if key.split("/")[0] == provider:
                return val
    return DEFAULT_WIKI_CONTEXT_CHARS


def _truncate_block(text: str, max_chars: int) -> str:
    """Truncate a wiki context block, marking if cut, so it can never
    overflow the model's context window."""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    marker = "\n…(wiki context truncated to fit context window)"
    if len(marker) >= max_chars:
        return marker[:max_chars]
    return text[: max_chars - len(marker)].rstrip() + marker


@dataclass
class WikiPage:
    path: str
    title: str
    content: str
    frontmatter: dict[str, Any]


@dataclass(frozen=True)
class WikiRolePaths:
    capture: str
    projects: str
    knowledge_paths: tuple[str, ...]
    archive: str
    originals: str
    processed: str

    @property
    def knowledge(self) -> str:
        return self.knowledge_paths[0]


def _safe_role_path(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip().replace("\\", "/").strip("/")
    windows = PureWindowsPath(text)
    if (
        not text
        or Path(text).is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in Path(text).parts
        or any(part in {"", ".", ".."} for part in text.split("/"))
        or any(char in text for char in ':"|?*\x00')
    ):
        raise ValueError("Wiki role paths must be safe relative directories")
    return text


def _require_exact_existing_case(wiki: Path, relative: str) -> None:
    """Reject a configured alias whose spelling differs from an existing entry."""
    current = Path(wiki)
    for part in Path(relative).parts:
        if not current.is_dir():
            return
        try:
            children = list(current.iterdir())
        except OSError:
            return
        exact = next((child for child in children if child.name == part), None)
        if exact is not None:
            current = exact
            continue
        alias = next(
            (child for child in children if child.name.casefold() == part.casefold()),
            None,
        )
        if alias is not None:
            raise ValueError(
                f"Wiki role path must use exact on-disk spelling: {alias.name}"
            )
        return


def resolve_role_paths(wiki: Path, config: Optional[dict] = None) -> WikiRolePaths:
    """Resolve semantic roles without creating or moving any Wiki content."""
    cfg = config or {}
    layout = str(cfg.get("layout", "adopt-existing")).strip()
    configured = cfg.get("paths", {}) if isinstance(cfg.get("paths", {}), dict) else {}
    sources = configured.get("sources", {}) if isinstance(configured.get("sources", {}), dict) else {}
    existing = {child.name.lower(): child.name for child in Path(wiki).iterdir()} if Path(wiki).is_dir() else {}

    def adopt(*candidates: str) -> str:
        if layout == "adopt-existing":
            for candidate in candidates:
                found = existing.get(candidate.lower())
                if found:
                    return found
        return candidates[0]

    configured_knowledge = configured.get("knowledge")
    if isinstance(configured_knowledge, list):
        knowledge_paths = tuple(
            _safe_role_path(item, "Knowledge")
            for item in configured_knowledge
            if str(item).strip()
        )
    elif configured_knowledge:
        knowledge_paths = (_safe_role_path(configured_knowledge, "Knowledge"),)
    elif layout == "adopt-existing":
        adopted = tuple(
            existing[name.lower()]
            for name in ("Knowledge", "Topics", "Ideas")
            if name.lower() in existing
        )
        knowledge_paths = adopted or ("Knowledge",)
    else:
        knowledge_paths = ("Knowledge",)

    resolved = WikiRolePaths(
        capture=_safe_role_path(configured.get("capture"), adopt("Inbox")),
        projects=_safe_role_path(configured.get("projects"), adopt("Projects")),
        knowledge_paths=knowledge_paths,
        archive=_safe_role_path(configured.get("archive"), adopt("Archive")),
        originals=_safe_role_path(
            sources.get("originals"), adopt("Sources/Originals", "Clippings")
        ),
        processed=_safe_role_path(
            sources.get("processed"), adopt("Sources/Notes", "Notes")
        ),
    )
    explicit_values = [
        configured.get("capture"),
        configured.get("projects"),

        configured.get("archive"),
        sources.get("originals"),
        sources.get("processed"),
    ]
    for value in explicit_values:
        if value:
            _require_exact_existing_case(Path(wiki), _safe_role_path(value, "unused"))
    for value in knowledge_paths:
        if configured_knowledge:
            _require_exact_existing_case(Path(wiki), value)
    return resolved


class GBrainClient:
    """Attach to a shared GBrain MCP tool already owned by Hermes.

    The provider never starts, kills, or falls back to a private GBrain
    process. Source isolation belongs to the configured MCP server boundary.
    """

    def __init__(
        self,
        wiki: Path = WIKI_PATH,
        *,
        registry: Any = None,
        server_name: str = "gbrain",
        source: str = "",
        attested_source: str = "",
        timeout: Optional[float] = None,
    ):
        self.wiki = Path(wiki)
        self.server_name = str(server_name).strip() or "gbrain"
        self.source = str(source).strip()
        self.attested_source = str(attested_source).strip()
        self.timeout = timeout
        self.last_error = ""
        self._registry = registry

    def _tool_registry(self):
        if self._registry is not None:
            return self._registry
        try:
            from tools.registry import registry

            return registry
        except Exception as exc:
            self.last_error = f"Hermes tool registry unavailable: {exc}"
            return None

    @staticmethod
    def _safe_mcp_component(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_]", "_", str(value or ""))

    def _tool_name(self, tool: str) -> str:
        return (
            f"mcp__{self._safe_mcp_component(self.server_name)}"
            f"__{self._safe_mcp_component(tool)}"
        )

    def _call(self, tool: str, arguments: dict[str, Any]) -> str:
        self.last_error = ""
        if not self.source:
            self.last_error = "GBrain source binding is not configured"
            return ""
        if self.attested_source != self.source:
            self.last_error = "Configured GBrain source is not attested by the MCP server"
            return ""
        if not isinstance(self.timeout, (int, float)) or not 0 < float(self.timeout) <= 7:
            self.last_error = "GBrain MCP timeout must be configured between 0 and 7 seconds"
            return ""
        registry = self._tool_registry()
        if registry is None:
            return ""
        name = self._tool_name(tool)
        entry = registry.get_entry(name)
        if entry is None or not callable(getattr(entry, "handler", None)):
            self.last_error = f"Shared GBrain MCP tool is not registered: {name}"
            return ""
        expected_toolset = f"mcp-{self.server_name}"
        entry_toolset = getattr(entry, "toolset", None)
        if entry_toolset is not None and entry_toolset != expected_toolset:
            self.last_error = (
                f"Shared GBrain MCP toolset mismatch: expected {expected_toolset}"
            )
            return ""
        try:
            dispatch = getattr(registry, "dispatch", None)
            raw = dispatch(name, arguments) if callable(dispatch) else entry.handler(arguments)
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:
            self.last_error = f"Shared GBrain MCP call failed: {exc}"
            return ""
        if not isinstance(payload, dict):
            self.last_error = "Shared GBrain MCP returned an invalid envelope"
            return ""
        error = payload.get("error")
        if error:
            self.last_error = str(error)
            return ""
        result = payload.get("result", "")
        if isinstance(result, str):
            text = result.strip()
            try:
                nested = json.loads(text)
            except (TypeError, ValueError):
                return text
            return self._format_recall(nested)
        if isinstance(result, dict):
            return self._format_recall(result)
        return json.dumps(result, ensure_ascii=False)

    @staticmethod
    def _format_recall(payload: Any) -> str:
        if not isinstance(payload, dict) or payload.get("error"):
            return ""
        sections: list[str] = []
        facts = payload.get("facts") or []
        if isinstance(facts, list):
            rendered = [str(item.get("fact", "")).strip() for item in facts if isinstance(item, dict)]
            rendered = [item for item in rendered if item]
            if rendered:
                sections.append("### Facts\n" + "\n".join(f"- {item}" for item in rendered))
        results = payload.get("results") or []
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                slug = str(item.get("slug", "")).strip()
                title = str(item.get("title", "")).strip() or slug
                chunk = str(item.get("chunk", "")).strip()
                if slug or chunk:
                    sections.append(f"### {title} ({slug})\n{chunk}".strip())
        return "\n\n".join(sections)

    def query(self, query: str, limit: int = 10, max_chars: int = 1200) -> str:
        return self._call(
            "recall",
            {
                "query": query,
                "limit": limit,
                "budget_tokens": max(1, int(max_chars) // 4),
            },
        )

    def think(self, question: str) -> str:
        return self._call("think", {"question": question})

    def doctor(self) -> dict:
        return {
            "available": self.is_available(),
            "server": self.server_name,
            "source": self.source,
            "error": self.last_error,
        }

    def stats(self) -> str:
        return json.dumps(self.doctor(), ensure_ascii=False)

    def is_available(self) -> bool:
        if (
            not self.source
            or self.attested_source != self.source
            or not isinstance(self.timeout, (int, float))
            or not 0 < float(self.timeout) <= 7
            or not self.wiki.exists()
        ):
            return False
        registry = self._tool_registry()
        if registry is None:
            return False
        entry = registry.get_entry(self._tool_name("recall"))
        if entry is None:
            return False
        toolset = getattr(entry, "toolset", None)
        return toolset is None or toolset == f"mcp-{self.server_name}"

    def close(self) -> None:
        """The shared MCP owner belongs to Hermes, so shutdown is a no-op."""


class WikiFileClient:
    """File-level wiki operations (read, write, upsert, append)."""

    _thread_locks: dict[str, threading.Lock] = {}
    _thread_locks_guard = threading.Lock()
    _windows_reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }

    def __init__(self, wiki: Path = WIKI_PATH):
        self.wiki = Path(wiki).expanduser().resolve()
        wiki_digest = hashlib.sha256(self._lock_identity(self.wiki).encode("utf-8")).hexdigest()
        self._lock_root = Path(tempfile.gettempdir()) / "hermes-wiki-memory-locks" / wiki_digest

    @staticmethod
    def _normalized_path_text(value: str) -> str:
        """Normalize Windows extended prefixes and filesystem case semantics."""
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
        return os.path.normcase(value)

    @classmethod
    def _lock_identity(cls, target: Path) -> str:
        """Return a stable lexical identity independent of target existence."""
        return cls._normalized_path_text(os.path.abspath(str(target)))

    def _resolve_page_path(self, path: str) -> Path:
        """Return a contained page path, rejecting absolute and escape paths."""
        raw = str(path).strip()
        windows_path = PureWindowsPath(raw)
        normalized = raw.replace("\\", "/")
        parts = [part for part in normalized.split("/") if part]
        unsafe_part = any(
            part in {".", ".."}
            or part.endswith((" ", "."))
            or any(char in part for char in '<>:"|?*\x00')
            or part.rstrip(" .").split(".", 1)[0].upper() in self._windows_reserved_names
            for part in parts
        )
        invalid = (
            not raw
            or not parts
            or Path(raw).is_absolute()
            or windows_path.is_absolute()
            or bool(windows_path.drive)
            or unsafe_part
            or not normalized.lower().endswith(".md")
        )
        if invalid:
            raise ValueError("page path must be a safe Markdown path inside the Wiki root")
        candidate = self.wiki / normalized
        resolved_candidate = candidate.resolve()
        resolved_root = self.wiki.resolve()
        candidate_text = self._normalized_path_text(str(resolved_candidate))
        root_text = self._normalized_path_text(str(resolved_root))
        try:
            contained = os.path.commonpath([root_text, candidate_text]) == root_text
        except ValueError:
            contained = False
        if not contained:
            raise ValueError(
                "page path must be a safe Markdown path inside the Wiki root"
            )
        return candidate

    @classmethod
    def _thread_lock_for(cls, target: Path) -> threading.Lock:
        key = cls._lock_identity(target)
        with cls._thread_locks_guard:
            return cls._thread_locks.setdefault(key, threading.Lock())

    def _canonical_disk_path(self, target: Path) -> Path:
        """Use existing Windows component casing after the shared lock is held."""
        if not _is_windows():
            return target
        relative = target.relative_to(self.wiki)
        current = self.wiki
        for part in relative.parts:
            matched = None
            if current.is_dir():
                wanted = os.path.normcase(part)
                try:
                    matched = next(
                        (child.name for child in current.iterdir()
                         if os.path.normcase(child.name) == wanted),
                        None,
                    )
                except OSError:
                    matched = None
            current = current / (matched or part)
        return current

    def _require_contained_resolved_path(self, target: Path) -> Path:
        resolved_target = target.resolve()
        resolved_root = self.wiki.resolve()
        target_text = self._normalized_path_text(str(resolved_target))
        root_text = self._normalized_path_text(str(resolved_root))
        try:
            contained = os.path.commonpath([root_text, target_text]) == root_text
        except ValueError:
            contained = False
        if not contained:
            raise ValueError(
                "page path must be a safe Markdown path inside the Wiki root"
            )
        return target

    @contextmanager
    def _page_lock(self, target: Path):
        """Serialize page updates across threads and processes."""
        with self._thread_lock_for(target):
            self._lock_root.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(self._lock_identity(target).encode("utf-8")).hexdigest()
            lock_path = self._lock_root / f"{digest}.lock"
            deadline = time.monotonic() + 30.0
            while True:
                try:
                    try:
                        with lock_path.open("xb") as initializer:
                            initializer.write(b" ")
                            initializer.flush()
                            os.fsync(initializer.fileno())
                    except FileExistsError:
                        pass
                    handle = lock_path.open("r+b")
                    handle.seek(0, os.SEEK_END)
                    if handle.tell() < 1:
                        handle.seek(0)
                        handle.write(b" ")
                        handle.flush()
                        os.fsync(handle.fileno())
                    break
                except PermissionError:
                    if "handle" in locals() and not handle.closed:
                        handle.close()
                    if not _is_windows() or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
            try:
                if _is_windows():
                    import msvcrt

                    acquired = False
                    while True:
                        try:
                            handle.seek(0)
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                            acquired = True
                            break
                        except (OSError, PermissionError):
                            if time.monotonic() >= deadline:
                                raise TimeoutError(
                                    f"timed out waiting for Wiki page lock: {target}"
                                )
                            time.sleep(0.05)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                yield self._require_contained_resolved_path(
                    self._canonical_disk_path(target)
                )
            finally:
                try:
                    handle.seek(0)
                    if _is_windows():
                        import msvcrt

                        if acquired:
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()

    @staticmethod
    def _atomic_write(target: Path, text: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(
            f".{target.name}.{os.getpid()}-{threading.get_ident()}.tmp"
        )
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            deadline = time.monotonic() + 5.0
            while True:
                try:
                    os.replace(temp, target)
                    break
                except PermissionError:
                    if not _is_windows() or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
        finally:
            temp.unlink(missing_ok=True)

    def read_page(self, path: str) -> Optional[WikiPage]:
        full = self._resolve_page_path(path)
        if not full.exists() or not full.is_file():
            return None
        text = full.read_text(encoding="utf-8")
        fm, content = self._parse_frontmatter(text)
        title = fm.get("title", Path(path).stem)
        return WikiPage(path=path, title=title, content=content, frontmatter=fm)

    def upsert_page(
        self,
        path: str,
        title: str,
        content: str,
        frontmatter: Optional[dict[str, Any]] = None,
        *,
        expected_sha256: Optional[str] = None,
    ) -> None:
        """Create or replace a wiki page with frontmatter."""
        full = self._resolve_page_path(path)

        fm = dict(frontmatter or {})
        fm.setdefault("title", title)
        fm.setdefault("created", time.strftime("%Y-%m-%d"))
        fm["updated"] = time.strftime("%Y-%m-%d")

        # Serialize frontmatter as YAML
        import yaml
        fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        rendered = f"---\n{fm_text}\n---\n\n{content}\n"
        with self._page_lock(full) as locked_full:
            if expected_sha256 is not None:
                actual = (
                    hashlib.sha256(locked_full.read_bytes()).hexdigest()
                    if locked_full.is_file()
                    else ""
                )
                if actual != expected_sha256:
                    raise RuntimeError("page fingerprint conflict; refusing replacement")
            self._atomic_write(locked_full, rendered)

    def append_to_page(
        self,
        path: str,
        content: str,
        frontmatter: Optional[dict[str, Any]] = None,
    ) -> None:
        """Append content to existing page, creating if needed."""
        full = self._resolve_page_path(path)
        with self._page_lock(full) as locked_full:
            # Re-read after acquiring the lock so concurrent appends compose.
            if locked_full.exists() and locked_full.is_file():
                text = locked_full.read_text(encoding="utf-8")
                existing_fm, existing_content = self._parse_frontmatter(
                    text, strict=True
                )
                new_content = existing_content.rstrip() + "\n\n" + content + "\n"
                fm = {**existing_fm, **(frontmatter or {})}
                fm["updated"] = time.strftime("%Y-%m-%d")
            else:
                new_content = content + "\n"
                fm = dict(frontmatter or {})
                fm.setdefault("title", Path(path).stem)
                fm["created"] = time.strftime("%Y-%m-%d")
                fm["updated"] = time.strftime("%Y-%m-%d")

            import yaml
            fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
            self._atomic_write(locked_full, f"---\n{fm_text}\n---\n\n{new_content}")

    def create_event_page(
        self,
        path: str,
        title: str,
        content: str,
        frontmatter: dict[str, Any],
        event_id: str,
        integrity_sha256: str,
    ) -> bool:
        """Create one immutable event page; return False for an exact replay."""
        full = self._resolve_page_path(path)
        with self._page_lock(full) as locked_full:
            if locked_full.exists():
                if not locked_full.is_file():
                    raise RuntimeError("capture collision: event path is not a file")
                existing, existing_content = self._parse_frontmatter(
                    locked_full.read_text(encoding="utf-8"), strict=True
                )
                actual_integrity = self._capture_integrity(
                    existing, existing_content
                )
                if (
                    existing.get("event_id") == event_id
                    and existing.get("integrity_sha256") == integrity_sha256
                    and actual_integrity == integrity_sha256
                    and existing_content.rstrip("\n") == content.rstrip("\n")
                ):
                    return False
                raise RuntimeError("capture collision: event path has a different event_id")
            fm = dict(frontmatter)
            fm.setdefault("title", title)
            fm.setdefault("created", time.strftime("%Y-%m-%d"))
            fm.setdefault("updated", fm["created"])
            import yaml

            fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
            self._atomic_write(locked_full, f"---\n{fm_text}\n---\n\n{content}\n")
            return True

    @staticmethod
    def _capture_integrity(frontmatter: dict[str, Any], content: str) -> str:
        ignored = {"integrity_sha256", "created", "updated", "captured_at"}
        stable = {
            key: value for key, value in frontmatter.items() if key not in ignored
        }
        payload = json.dumps(
            {"frontmatter": stable, "content": content.rstrip("\n")},
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _parse_frontmatter(self, text: str, *, strict: bool = False) -> tuple[dict, str]:
        if not text.startswith("---"):
            return {}, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text
        import yaml
        try:
            fm = yaml.safe_load(parts[1]) or {}
            if not isinstance(fm, dict):
                raise ValueError("frontmatter must be a mapping")
        except Exception as exc:
            if strict:
                raise ValueError("malformed frontmatter; refusing to mutate page") from exc
            fm = {}
        return fm, parts[2].lstrip("\n")


class WikiClient:
    """Unified client combining gbrain + file operations."""

    LEXICAL_MAX_FILES = 2000
    LEXICAL_MAX_FILE_BYTES = 512 * 1024
    LEXICAL_MAX_TOTAL_BYTES = 8 * 1024 * 1024
    LEXICAL_MAX_SECONDS = 1.0
    _excluded_parts = frozenset({
        ".git", ".hermes", ".gbrain", "_meta", "sessions", "session-exports",
        "generated", "cache", "quarantine", "node_modules", "__pycache__",
    })

    def __init__(
        self,
        wiki: Path = WIKI_PATH,
        *,
        gbrain: Optional[GBrainClient] = None,
        gbrain_server: str = "gbrain",
        gbrain_source: str = "",
        gbrain_attested_source: str = "",
        gbrain_timeout: Optional[float] = None,
        config: Optional[dict] = None,
    ):
        self.config = dict(config or {})
        self.gbrain = gbrain or GBrainClient(
            wiki,
            server_name=gbrain_server,
            source=gbrain_source,
            attested_source=gbrain_attested_source,
            timeout=gbrain_timeout,
        )
        self.files = WikiFileClient(wiki)
        self.wiki = Path(wiki)
        self.paths = resolve_role_paths(self.wiki, self.config)

    def is_available(self) -> bool:
        return self.health()["status"] != "unavailable"

    def health(self) -> dict[str, Any]:
        wiki_exists = self.wiki.is_dir()
        wiki_readable = wiki_exists and os.access(self.wiki, os.R_OK)
        wiki_writable = wiki_exists and os.access(self.wiki, os.W_OK)
        semantic = wiki_readable and self.gbrain.is_available()
        lexical = wiki_readable
        capture = self.wiki / self.paths.capture
        capture_ready = capture.is_dir() and os.access(capture, os.W_OK)
        if not lexical:
            status = "unavailable"
        elif semantic and wiki_writable and capture_ready:
            status = "available"
        else:
            status = "degraded"
        return {
            "status": status,
            "wiki_exists": wiki_exists,
            "wiki_readable": wiki_readable,
            "wiki_writable": wiki_writable,
            "lexical_recall": lexical,
            "semantic_recall": semantic,
            "capture_ready": capture_ready,
            "capture_path": self.paths.capture,
            "embeddings": "unknown",
            "backup_policy": "canonical-wiki-required; gbrain-rebuild",
            "gbrain_server": self.gbrain.server_name,
            "gbrain_source": self.gbrain.source,
            "semantic_error": self.gbrain.last_error,
        }

    def prefetch(
        self, query: str, limit: int = 5, max_chars: Optional[int] = None
    ) -> str:
        """Semantic search + keyword fallback for per-turn recall.

        Output is capped at ``max_chars`` (resolved via wiki_context_cap() when
        None) so the injected block can never overflow the model's context window.
        """
        cap = max_chars if max_chars is not None else wiki_context_cap()
        # Try the shared GBrain owner first.
        if self.gbrain.is_available():
            result = self.gbrain.query(query, limit=limit, max_chars=cap)
            if result:
                block = f"## Wiki Recall (gbrain)\n{result}\n"
                return _truncate_block(block, cap)

        return self._lexical_prefetch(query, limit=limit, max_chars=cap)

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9][a-z0-9_-]+", text.lower()) if len(token) > 1}

    @classmethod
    def _path_weight(cls, relative: Path) -> int:
        first = relative.parts[0].lower() if relative.parts else ""
        if first in {"knowledge", "topics", "ideas"}:
            return 40
        if first == "projects":
            return 30
        if first in {"archive"}:
            return -25
        if first in {"clippings", "sources"}:
            return -10
        return 0

    def _lexical_prefetch(self, query: str, *, limit: int, max_chars: int) -> str:
        wanted = self._tokens(query)
        if not wanted or not self.wiki.is_dir():
            return ""
        ranked: list[tuple[int, str, str]] = []
        started = time.monotonic()
        scanned = 0
        total_bytes = 0
        root_text = WikiFileClient._normalized_path_text(str(self.wiki.resolve()))
        def iter_markdown(root: Path):
            stack = [root]
            while stack:
                current = stack.pop()
                try:
                    entries = sorted(
                        os.scandir(current), key=lambda entry: entry.name.casefold()
                    )
                except OSError:
                    continue
                directories = []
                for entry in entries:
                    if entry.name.casefold() in self._excluded_parts:
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            directories.append(Path(entry.path))
                        elif (
                            entry.is_file(follow_symlinks=False)
                            and entry.name.lower().endswith(".md")
                        ):
                            yield Path(entry.path)
                    except OSError:
                        continue
                stack.extend(reversed(directories))

        for path in iter_markdown(self.wiki):
            if scanned >= self.LEXICAL_MAX_FILES:
                break
            if time.monotonic() - started >= self.LEXICAL_MAX_SECONDS:
                break
            try:
                relative = path.relative_to(self.wiki)
            except ValueError:
                continue
            lowered_parts = {part.lower() for part in relative.parts}
            if lowered_parts & self._excluded_parts or not path.is_file() or path.is_symlink():
                continue
            try:
                resolved_text = WikiFileClient._normalized_path_text(str(path.resolve()))
                if os.path.commonpath([root_text, resolved_text]) != root_text:
                    continue
                size = path.stat().st_size
                if size > self.LEXICAL_MAX_FILE_BYTES:
                    continue
                if total_bytes + size > self.LEXICAL_MAX_TOTAL_BYTES:
                    break
                scanned += 1
                total_bytes += size
                text = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                continue
            path_tokens = self._tokens(relative.as_posix())
            body_tokens = self._tokens(text)
            path_hits = len(wanted & path_tokens)
            body_hits = len(wanted & body_tokens)
            if not path_hits and not body_hits:
                continue
            score = self._path_weight(relative) + path_hits * 20 + body_hits * 8
            excerpt = " ".join(text.replace("---", " ").split())[:500]
            ranked.append((score, relative.as_posix(), excerpt))
        if not ranked:
            return ""
        ranked.sort(key=lambda item: (-item[0], item[1].lower()))
        sections = [
            f"### {relative}\n{excerpt}"
            for _, relative, excerpt in ranked[: max(1, limit)]
        ]
        return _truncate_block(
            "## Wiki Recall (lexical)\n" + "\n\n".join(sections) + "\n",
            max_chars,
        )

    _secret_assignment = re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)\b"
        r"(\s*[:=]\s*)([^\s,;]+)"
    )
    _bearer_secret = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")
    _token_secret = re.compile(r"\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b")

    @classmethod
    def redact_capture_text(cls, text: str) -> str:
        raw = str(text)
        try:
            from agent.redact import redact_sensitive_text

            raw = redact_sensitive_text(raw, force=True)
        except Exception:
            pass
        redacted = cls._secret_assignment.sub(
            lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", raw
        )
        redacted = cls._bearer_secret.sub("Bearer [REDACTED]", redacted)
        return cls._token_secret.sub("[REDACTED]", redacted)

    @classmethod
    def _redact_value(cls, value: Any) -> Any:
        if isinstance(value, str):
            return cls.redact_capture_text(value)
        if isinstance(value, dict):
            return {str(key): cls._redact_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._redact_value(item) for item in value]
        return value

    def capture_event(
        self,
        *,
        event_type: str,
        content: str,
        session_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Write one idempotent, provenance-bearing event to the capture role."""
        clean_content = self.redact_capture_text(content).strip()
        reserved = {
            "type", "status", "event_id", "session_id", "captured_at",
            "extraction", "redaction", "title", "created", "updated",
        }
        clean_metadata = {
            key: value
            for key, value in self._redact_value(dict(metadata or {})).items()
            if key not in reserved
        }
        identity = json.dumps(
            {
                "event_type": event_type,
                "session_id": session_id,
                "content": clean_content,
                "metadata": clean_metadata,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        event_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        capture_dir = self.wiki / self.paths.capture
        _require_exact_existing_case(self.wiki, self.paths.capture)
        if not capture_dir.is_dir():
            raise RuntimeError(
                f"configured capture directory does not exist: {self.paths.capture}"
            )
        path = f"{self.paths.capture}/wke_{event_id[:26]}.md"
        title = f"Captured {event_type.replace('_', ' ').title()}"
        frontmatter = {
            **clean_metadata,
            "title": title,
            "type": event_type,
            "status": "captured",
            "event_id": event_id,
            "session_id": session_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "extraction": "heuristic" if event_type == "session_insight" else "hook",
            "redaction": {"applied": True, "policy": "hermes-force-v1"},
        }
        integrity_sha256 = self.files._capture_integrity(frontmatter, clean_content)
        frontmatter["integrity_sha256"] = integrity_sha256
        self.files.create_event_page(
            path,
            title,
            clean_content,
            frontmatter,
            event_id,
            integrity_sha256,
        )
        return path

    def extract_session_insights(self, messages: list[dict]) -> list[dict]:
        """Extract structured insights from session messages using LLM.

        Returns list of dicts: {title, path, content, frontmatter}
        """
        # This will be called with the agent's model via a prompt.
        # For now, return empty - the MemoryProvider will call an LLM to do this.
        return []


# Convenience function for simple scripts
def get_wiki_client() -> WikiClient:
    return WikiClient()
