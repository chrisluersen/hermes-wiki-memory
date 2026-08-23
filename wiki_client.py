"""Wiki client for gbrain CLI + wiki file operations.

Shared between MemoryProvider and ContextEngine plugins.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Optional
from queue import Queue, Empty

from hermes_constants import get_default_hermes_root, get_hermes_home

logger = logging.getLogger(__name__)

# Shared wiki brain lives at the Hermes ROOT, not the profile home — so every
# profile/bot in the fleet queries and writes the SAME wiki. get_hermes_home()
# returns profiles/<name> under a profile, which has no wiki/; the root does.
WIKI_PATH = Path(str(get_default_hermes_root() / "wiki"))

# gbrain reads these with env precedence; the Hermes .env lists them as ${VAR}
# placeholders (Bitwarden-resolved only at Hermes runtime). A child inheriting
# the placeholder gets "Cannot connect to database: \"${GBRAIN_DATABASE_URL}\"".
# Strip unresolved ones so gbrain falls back to ~/.gbrain/config.json.
_GBRAIN_PLACEHOLDER_VARS = (
    "GBRAIN_DATABASE_URL",
    "GBRAIN_DIRECT_DATABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_DB_PASSWORD",
)

# Server-side LLM expansion (`openai:gpt-5.x`) adds ~8s per query and has been
# observed failing with provider_error. The `search` tool is hybrid retrieval
# without expansion and returns the same hit array — ~5.6s warm, but the FIRST
# search call on a freshly spawned server pays a cold embedding path (~18s),
# so keep headroom (a warm hang then falls back via the respawn path anyway).
_QUERY_TOOL = "search"
_QUERY_TIMEOUT = 25
_THINK_TIMEOUT = 25


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
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n…(wiki context truncated to fit context window)"


@dataclass
class WikiPage:
    path: str
    title: str
    content: str
    frontmatter: dict[str, Any]


class GBrainClient:
    """Wrapper around gbrain — persistent `serve` child + JSON-RPC over stdio.

    Per-query `gbrain query` subprocess spawns paid ~6.5s of DB init per call,
    which blew the old 5s timeout on every prefetch (the "gbrain query timed
    out after 5s" warning spam). A long-lived `gbrain serve` child pays that
    init once per Hermes process, then answers warm: `search` ~5.6s, `think`
    ~0.2s (synthesis), no per-call spawn cost.

    Falls back to one-shot CLI calls if the persistent server cannot start or
    the JSON-RPC channel dies (respawn once, then CLI fallback).
    """

    def __init__(self, wiki: Path = WIKI_PATH):
        self.wiki = wiki
        self._gbrain_cmd = self._resolve_gbrain_cmd()
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._pending: dict[int, Queue] = {}
        self._next_id = 1
        self._serve_ok = False

    def _resolve_gbrain_cmd(self) -> Optional[str]:
        # Standard lookup: GBRAIN_CMD env -> PATH -> bun global install
        cmd = os.environ.get("GBRAIN_CMD", "").strip()
        if cmd:
            return cmd
        cmd = shutil.which("gbrain") or ""
        if cmd:
            return cmd
        bun = Path.home() / ".bun" / "bin" / "gbrain.exe"
        if bun.exists():
            return str(bun)
        return None

    def _env(self) -> dict:
        env = os.environ.copy()
        # Strip ${VAR} placeholders so gbrain falls back to ~/.gbrain/config.json
        for key in _GBRAIN_PLACEHOLDER_VARS:
            val = env.get(key)
            if val and "${" in val:
                env.pop(key, None)
        # Ensure bun and hermes venv in PATH
        hermes_bin = str(get_hermes_home() / "hermes-agent" / ".venv" / "Scripts")
        bun_dir = str(Path.home() / ".bun" / "bin")
        paths = env.get("PATH", "")
        for d in (bun_dir, hermes_bin):
            if d not in paths:
                paths = f"{d}{os.pathsep}{paths}"
        env["PATH"] = paths
        return env

    # -- Persistent serve child + JSON-RPC ------------------------------------

    def _start_server(self) -> bool:
        """Spawn `gbrain serve`, do the MCP initialize handshake."""
        if not self._gbrain_cmd:
            return False
        try:
            self._proc = subprocess.Popen(
                [self._gbrain_cmd, "serve"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                env=self._env(),
                cwd=self.wiki,
                bufsize=1,
            )
        except Exception as exc:
            logger.warning("gbrain serve spawn failed: %s", exc)
            self._proc = None
            return False
        self._next_id = 1
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        # initialize handshake (covers the ~6.5s cold DB init)
        try:
            resp = self._rpc("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "hermes-wiki-client", "version": "1"},
            }, timeout=30)
            if resp is None or "result" not in resp:
                logger.warning("gbrain serve initialize failed: %s", (resp or {}).get("error"))
                self._stop_server()
                return False
            # notifications/initialized (no response expected)
            self._send_jsonrpc("notifications/initialized", {})
            self._serve_ok = True
            return True
        except Exception as exc:
            logger.warning("gbrain serve initialize raised: %s", exc)
            self._stop_server()
            return False

    def _stop_server(self) -> None:
        proc, self._proc = self._proc, None
        if proc:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._serve_ok = False

    def _read_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            for raw in proc.stdout:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                rid = msg.get("id")
                if isinstance(rid, int) and rid in self._pending:
                    self._pending.pop(rid).put(msg)
        except Exception:
            pass
        finally:
            # Server exited or stream closed: fail any pending requests
            for q in self._pending.values():
                q.put(None)
            self._pending.clear()

    def _send_jsonrpc(self, method: str, params: dict) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("gbrain serve not running")
        self._proc.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params,
        }) + "\n")
        self._proc.stdin.flush()

    def _rpc(self, method: str, params: dict, timeout: float) -> Optional[dict]:
        """Send a request with id, wait for the matching response."""
        if self._proc is None or self._proc.stdin is None:
            return None
        q: Queue = Queue()
        self._next_id += 1
        rid = self._next_id
        self._pending[rid] = q
        try:
            self._proc.stdin.write(json.dumps({
                "jsonrpc": "2.0", "id": rid, "method": method, "params": params,
            }) + "\n")
            self._proc.stdin.flush()
            try:
                return q.get(timeout=timeout)
            except Empty:
                logger.warning("gbrain %s JSON-RPC timed out after %ss", method, timeout)
                return None
        except Exception as exc:
            logger.warning("gbrain %s JSON-RPC failed: %s", method, exc)
            return None
        finally:
            self._pending.pop(rid, None)

    def _call_tool(self, name: str, arguments: dict, timeout: float) -> Optional[str]:
        """Call an MCP tool; returns the first text content, or None."""
        with self._lock:
            if not self._serve_ok and not self._start_server():
                return None
            resp = self._rpc("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
            if resp is None:
                # Channel dead — one respawn attempt, then give up
                self._stop_server()
                if not self._start_server():
                    return None
                resp = self._rpc("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)
            if resp is None:
                return None
            if "error" in resp:
                logger.warning("gbrain tool %s error: %s", name, resp["error"])
                return None
            content = resp.get("result", {}).get("content") or []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    return item.get("text", "").strip() or None
            return None

    def _call_cli(self, args: list[str], timeout: int = 60) -> Optional[str]:
        """One-shot CLI fallback (same semantics as the old _run)."""
        if not self._gbrain_cmd:
            return None
        cmd = [self._gbrain_cmd] + args
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._env(),
                cwd=self.wiki,
            )
            if res.returncode == 0:
                return res.stdout.strip()
            logger.warning("gbrain %s exited rc=%s: %s", args[0], res.returncode, (res.stderr or res.stdout or "").strip()[:200])
        except subprocess.TimeoutExpired:
            logger.warning("gbrain %s timed out after %ss", args[0], timeout)
        except FileNotFoundError:
            logger.warning("gbrain binary not found: %s", self._gbrain_cmd)
        except Exception as exc:
            logger.warning("gbrain %s failed: %s", args[0], exc)
        return None

    # -- Public API -----------------------------------------------------------

    def query(self, query: str, limit: int = 10) -> str:
        """Semantic search via the persistent server's `search` tool (no LLM expansion).

        Falls back to one-shot CLI `search` if the server path is unavailable.
        The 5s cap is gone: a warm search runs ~5.6s; cold (first call of the
        process) pays the ~6.5s server init inside the 30s handshake.
        """
        text = self._call_tool(_QUERY_TOOL, {"query": query, "limit": limit}, _QUERY_TIMEOUT)
        if text is not None:
            return text
        return self._call_cli(["search", query, "--limit", str(limit)], timeout=_QUERY_TIMEOUT + 5) or "gbrain query failed"

    def think(self, question: str) -> str:
        """Multi-hop synthesis via gbrain think (persistent server first)."""
        text = self._call_tool("think", {"question": question}, _THINK_TIMEOUT)
        if text is not None:
            return text
        return self._call_cli(["think", question], timeout=_THINK_TIMEOUT + 5) or "gbrain think failed"

    def doctor(self) -> dict:
        """Health check as JSON."""
        out = self._call_cli(["doctor", "--json"], timeout=30)
        if out:
            try:
                return json.loads(out)
            except Exception as exc:
                logger.warning("gbrain doctor JSON parse failed: %s", exc)
                return {"raw": out}
        return {"error": "gbrain doctor failed"}

    def stats(self) -> str:
        return self._call_cli(["stats"], timeout=15) or "gbrain stats failed"

    def is_available(self) -> bool:
        return self._gbrain_cmd is not None and self.wiki.exists()


class WikiFileClient:
    """File-level wiki operations (read, write, upsert, append)."""

    def __init__(self, wiki: Path = WIKI_PATH):
        self.wiki = wiki

    def read_page(self, path: str) -> Optional[WikiPage]:
        full = self.wiki / path
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
    ) -> None:
        """Create or replace a wiki page with frontmatter."""
        full = self.wiki / path
        full.parent.mkdir(parents=True, exist_ok=True)

        fm = frontmatter or {}
        fm.setdefault("title", title)
        fm.setdefault("created", time.strftime("%Y-%m-%d"))
        fm["updated"] = time.strftime("%Y-%m-%d")

        # Serialize frontmatter as YAML
        import yaml
        fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        full.write_text(f"---\n{fm_text}\n---\n\n{content}\n", encoding="utf-8")

    def append_to_page(
        self,
        path: str,
        content: str,
        frontmatter: Optional[dict[str, Any]] = None,
    ) -> None:
        """Append content to existing page, creating if needed."""
        existing = self.read_page(path)
        if existing:
            new_content = existing.content.rstrip() + "\n\n" + content + "\n"
            fm = {**existing.frontmatter, **(frontmatter or {})}
            fm["updated"] = time.strftime("%Y-%m-%d")
        else:
            new_content = content + "\n"
            fm = frontmatter or {}
            fm.setdefault("title", Path(path).stem)
            fm["created"] = time.strftime("%Y-%m-%d")
            fm["updated"] = time.strftime("%Y-%m-%d")

        full = self.wiki / path
        full.parent.mkdir(parents=True, exist_ok=True)

        import yaml
        fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        full.write_text(f"---\n{fm_text}\n---\n\n{new_content}", encoding="utf-8")

    def _parse_frontmatter(self, text: str) -> tuple[dict, str]:
        if not text.startswith("---"):
            return {}, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return {}, text
        import yaml
        try:
            fm = yaml.safe_load(parts[1]) or {}
        except Exception:
            fm = {}
        return fm, parts[2].lstrip("\n")


class WikiClient:
    """Unified client combining gbrain + file operations."""

    def __init__(self, wiki: Path = WIKI_PATH):
        self.gbrain = GBrainClient(wiki)
        self.files = WikiFileClient(wiki)
        self.wiki = wiki

    def is_available(self) -> bool:
        return self.gbrain.is_available() and self.wiki.exists()

    def prefetch(
        self, query: str, limit: int = 5, max_chars: Optional[int] = None
    ) -> str:
        """Semantic search + keyword fallback for per-turn recall.

        Output is capped at ``max_chars`` (resolved via wiki_context_cap() when
        None) so the injected block can never overflow the model's context window.
        """
        cap = max_chars if max_chars is not None else wiki_context_cap()
        # Try gbrain first
        if self.gbrain.is_available():
            result = self.gbrain.query(query, limit=limit)
            if result and not result.startswith("gbrain"):
                block = f"## Wiki Recall (gbrain)\n{result}\n"
                return _truncate_block(block, cap)

        # Fallback: FTS5 keyword search via wiki-mcp-server would be ideal,
        # but we don't have DB access here. Return empty for now.
        # The MemoryManager calls prefetch() before each turn, so it's OK to be fast.
        return ""

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
