"""Wiki Memory Provider — gbrain-powered semantic recall + session persistence.

Implements the MemoryProvider ABC for Hermes Agent.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from agent.memory_provider import MemoryProvider
from typing import Any, Dict, List, Optional

from .wiki_client import (
    WikiClient,
    _truncate_block,
    resolve_wiki_path,
    wiki_context_cap,
)
from .recovery import build_rebuild_manifest

logger = logging.getLogger(__name__)
PLUGIN_VERSION = "0.4.0"


def _load_provider_config(explicit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Read ``memory.wiki`` without mutating Hermes's cached config."""
    configured: Dict[str, Any] = {}
    try:
        from hermes_cli.config import load_config_readonly

        config = load_config_readonly() or {}
        memory = config.get("memory", {}) if isinstance(config, dict) else {}
        wiki = memory.get("wiki", {}) if isinstance(memory, dict) else {}
        if isinstance(wiki, dict):
            configured.update(wiki)
        if explicit:
            configured.update(explicit)
        server_name = str(configured.get("gbrain_server", "gbrain")).strip() or "gbrain"
        servers = config.get("mcp_servers", {}) if isinstance(config, dict) else {}
        server = servers.get(server_name, {}) if isinstance(servers, dict) else {}
        if isinstance(server, dict) and server:
            env = server.get("env", {}) if isinstance(server.get("env", {}), dict) else {}
            configured["_gbrain_attested_source"] = str(env.get("GBRAIN_SOURCE", "")).strip()
            configured["_gbrain_timeout"] = server.get("timeout")
    except Exception as exc:
        logger.debug("Wiki provider config unavailable: %s", exc)
    return configured


class WikiMemoryProvider(MemoryProvider):
    """Memory provider backed by the agent wiki + gbrain."""

    name = "wiki"

    def __init__(self):
        self._client: Optional[WikiClient] = None
        self._session_id: str = ""
        self._active_model: str = ""
        self._provider_config: Dict[str, Any] = {}
        self._initialized: bool = False

    # -- Core lifecycle ---------------------------------------------------------

    def is_available(self) -> bool:
        """Check if wiki and gbrain are accessible."""
        try:
            client = WikiClient(resolve_wiki_path(_load_provider_config()))
            try:
                return client.is_available()
            finally:
                client.gbrain.close()
        except Exception as e:
            logger.debug("Wiki provider unavailable: %s", e)
            return False

    def initialize(self, session_id: str, **kwargs) -> None:
        """Initialize for a session."""
        self._session_id = session_id
        agent_context = kwargs.get("agent_context", "primary")

        # Only fully initialize for primary agent contexts
        if agent_context != "primary":
            logger.debug("Wiki provider: skipping init for non-primary context: %s", agent_context)
            self._initialized = True
            return

        self._provider_config = _load_provider_config(
            kwargs.get("provider_config", {}) or {}
        )
        self._client = WikiClient(
            resolve_wiki_path(self._provider_config),
            gbrain_server=str(self._provider_config.get("gbrain_server", "gbrain")),
            gbrain_source=str(self._provider_config.get("gbrain_source", "")),
            gbrain_attested_source=str(
                self._provider_config.get("_gbrain_attested_source", "")
            ),
            gbrain_timeout=self._provider_config.get("_gbrain_timeout"),
            config=self._provider_config,
        )

        if not self._client.is_available():
            logger.warning("Wiki provider initialized but wiki/gbrain not fully available")

        self._initialized = True
        logger.info("Wiki memory provider initialized for session %s", session_id)

    def system_prompt_block(self) -> str:
        """Describe only recall/capture behavior that is actually available."""
        if not self._client or not self._client.is_available():
            return ""
        health = self._client.health()
        recall = (
            "- Semantic Wiki recall via the configured shared GBrain MCP owner\n"
            if health.get("semantic_recall")
            else "- Lexical Wiki recall is available; semantic GBrain recall is degraded\n"
        )
        return (
            "## Wiki Memory\n"
            + recall
            + "- Inferred insights, delegations, and memory events are captured to the configured capture folder\n"
            + "- Captures are candidates, not automatically promoted canonical knowledge\n"
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Recall relevant wiki context for the upcoming turn.

        Caps injected size per the active model (wiki_context_cap).
        """
        if not self._client:
            return ""
        return self._client.prefetch(
            query, max_chars=wiki_context_cap(self._active_model, self._provider_config)
        )

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """Queue background recall for next turn."""
        # Could spawn background thread here for heavy queries
        # For now, no-op — prefetch() is fast enough
        pass

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Persist a completed turn. Non-blocking — queue for background."""
        # Could write turn log to wiki for full history
        # For now, no-op — on_session_end does the heavy lifting
        pass

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """gbrain tools are provided by the native gbrain MCP server instead."""
        return []

    def get_config_schema(self) -> List[Dict[str, Any]]:
        """Settings rendered by ``hermes memory setup`` and the dashboard."""
        return [
            {
                "key": "root",
                "description": "Canonical Wiki root (blank uses WIKI_PATH or the Hermes root)",
                "default": "",
            },
            {
                "key": "wiki_context_cap",
                "description": "Maximum Wiki recall characters injected per turn",
                "default": 1200,
                "type": "integer",
                "minimum": 200,
                "maximum": 20000,
                "step": 100,
            },
            {"key": "gbrain_server", "description": "Hermes MCP server name for the shared GBrain owner", "default": "gbrain"},
            {"key": "gbrain_source", "description": "Explicit GBrain source bound by that MCP server", "default": ""},
            {"key": "layout", "description": "Wiki layout mapping mode", "default": "adopt-existing"},
            {"key": "capture_path", "description": "Capture role path", "default": "Inbox"},
            {"key": "projects_path", "description": "Projects role path", "default": "Projects"},
            {"key": "knowledge_path", "description": "Knowledge role path(s), comma-separated", "default": "Knowledge"},
            {"key": "archive_path", "description": "Archive role path", "default": "Archive"},
            {"key": "originals_path", "description": "Original sources role path", "default": "Sources/Originals"},
            {"key": "processed_path", "description": "Processed sources role path", "default": "Sources/Notes"},
        ]

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        """Persist supported settings under ``memory.wiki`` in config.yaml."""
        del hermes_home  # Hermes's config API resolves the active profile safely.
        from hermes_cli.config import (
            atomic_config_write,
            get_config_path,
            read_user_config_raw,
        )

        root = str(values.get("root", "")).strip()
        try:
            cap = int(values.get("wiki_context_cap", 1200))
        except (TypeError, ValueError) as exc:
            raise ValueError("wiki_context_cap must be an integer") from exc
        if not 200 <= cap <= 20000:
            raise ValueError("wiki_context_cap must be between 200 and 20000")

        def validate_role_value(value: Any, key: str) -> str:
            value = str(value).strip().replace("\\", "/").strip("/")
            if not value or Path(value).is_absolute() or ".." in Path(value).parts or ":" in value:
                raise ValueError(f"{key} must be a safe relative Wiki directory")
            return value

        def safe_role(key: str, default: str) -> str:
            return validate_role_value(values.get(key, default), key)

        layout = str(values.get("layout", "adopt-existing")).strip()
        if layout not in {"adopt-existing", "workbench"}:
            raise ValueError("layout must be adopt-existing or workbench")
        knowledge_paths = [
            validate_role_value(item, "knowledge_path")
            for item in str(values.get("knowledge_path", "Knowledge")).split(",")
            if item.strip()
        ]
        if not knowledge_paths:
            raise ValueError("knowledge_path must contain at least one directory")

        config = read_user_config_raw() or {}
        memory = config.setdefault("memory", {})
        if not isinstance(memory, dict):
            raise ValueError("memory config must be a mapping")
        memory["wiki"] = {
            "root": root,
            "wiki_context_cap": cap,
            "gbrain_server": str(values.get("gbrain_server", "gbrain")).strip() or "gbrain",
            "gbrain_source": str(values.get("gbrain_source", "")).strip(),
            "layout": layout,
            "paths": {
                "capture": safe_role("capture_path", "Inbox"),
                "projects": safe_role("projects_path", "Projects"),
                "knowledge": knowledge_paths[0] if len(knowledge_paths) == 1 else knowledge_paths,
                "archive": safe_role("archive_path", "Archive"),
                "sources": {
                    "originals": safe_role("originals_path", "Sources/Originals"),
                    "processed": safe_role("processed_path", "Sources/Notes"),
                },
            },
        }
        atomic_config_write(get_config_path(), config, sort_keys=False)

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        """gbrain tools are provided by the native gbrain MCP server instead."""
        return f"Unknown tool: {tool_name}"

    def shutdown(self) -> None:
        """Clean shutdown."""
        if self._client:
            self._client.gbrain.close()
            self._client = None
        self._initialized = False
        logger.debug("Wiki memory provider shutdown")

    # -- Optional hooks ---------------------------------------------------------

    def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None:
        """Per-turn tick. Capture the active model so per-model context caps apply."""
        self._active_model = kwargs.get("model", "") or ""
        logger.debug("Wiki provider: turn %d start (model=%s)", turn_number, self._active_model)

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """End-of-session: extract insights and persist to wiki."""
        if not self._client or not self._initialized:
            return

        logger.info("Wiki provider: extracting insights from session %s", self._session_id)

        try:
            insights = self._extract_insights_llm(messages)
            for insight in insights:
                self._client.capture_event(
                    event_type="session_insight",
                    content=insight["content"],
                    session_id=self._session_id,
                    metadata=insight.get("frontmatter", {}),
                )
            logger.info("Wiki provider: persisted %d insights to wiki", len(insights))
        except Exception as e:
            logger.error("Wiki provider: on_session_end failed: %s", e)

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        rewound: bool = False,
        **kwargs,
    ) -> None:
        """Handle mid-process session switch."""
        logger.debug("Wiki provider: session switch %s -> %s", self._session_id, new_session_id)
        self._session_id = new_session_id

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """Extract wiki-relevant context before compression.

        Output is capped at MAX_WIKI_CONTEXT_CHARS so the injected block
        can never overflow the model's context window.
        """
        if not self._client:
            return ""

        # Extract entity/concept references from recent messages
        refs = self._extract_wiki_references(messages)
        if not refs:
            return ""

        cap = wiki_context_cap(self._active_model, self._provider_config)
        wiki_context = []
        for ref in refs[:5]:  # Limit to top 5 refs
            result = self._client.prefetch(ref, limit=3, max_chars=cap)
            if result:
                wiki_context.append(f"### {ref}\n{result}")

        if not wiki_context:
            return ""

        block = "## Wiki Context (pre-compression)\n\n" + "\n\n".join(wiki_context) + "\n"
        return _truncate_block(block, cap)

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mirror built-in memory tool writes to wiki."""
        if not self._client or action not in ("add", "replace", "remove"):
            return

        self._client.capture_event(
            event_type="explicit_memory",
            content=content,
            session_id=self._session_id,
            metadata={
                "target": target,
                "action": action,
                **(metadata or {}),
            },
        )

    def on_delegation(self, task: str, result: str, **kwargs) -> None:
        """Capture subagent delegation outcomes to wiki."""
        if not self._client:
            return

        child_session_id = kwargs.get("child_session_id", "")
        self._client.capture_event(
            event_type="delegation",
            content=f"Task: {task}\n\nResult:\n{result}",
            session_id=self._session_id,
            metadata={
                "child_session_id": child_session_id,
            },
        )

    def backup_paths(self) -> List[str]:
        """Return canonical provider data; derived GBrain state is rebuilt."""
        paths = []
        provider_config = self._provider_config or _load_provider_config()
        wiki = self._client.wiki if self._client else resolve_wiki_path(provider_config)
        if wiki.exists():
            paths.append(str(wiki))
        return paths

    def rebuild_manifest(self) -> Dict[str, Any]:
        provider_config = self._provider_config or _load_provider_config()
        wiki = self._client.wiki if self._client else resolve_wiki_path(provider_config)
        return build_rebuild_manifest(
            wiki,
            provider_config,
            plugin_version=PLUGIN_VERSION,
        )

    # -- Internal helpers -------------------------------------------------------

    def _extract_wiki_references(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extract wiki entity/concept references from messages."""
        refs = []
        for msg in messages[-10:]:  # Last 10 messages
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            # Find [[wikilinks]] and common patterns
            wikilinks = re.findall(r"\[\[([^\]]+)\]\]", content)
            refs.extend(wikilinks)
            # Also look for "concepts/X" or "entities/X" patterns
            path_refs = re.findall(r"\b(concepts|entities|comparisons|queries)/[\w-]+\.md", content)
            refs.extend(path_refs)
        return list(dict.fromkeys(refs))  # Dedupe preserving order

    @staticmethod
    def _is_insight_clean(capture: str) -> bool:
        """Quality gate: reject captures that look like noise."""
        text = capture.strip()
        # Too short to be meaningful
        if len(text) < 12:
            return False
        # Too long = wrong capture boundary
        if len(text) > 300:
            return False
        # Escaped newline sequences (hallmark of tool output)
        if "\\n" in text:
            return False
        # Line-numbered content
        if re.match(r"\s*\d+\|", text):
            return False
        # JSON/status keys leaking through
        if re.search(r'"(?:status|error|result|output|exit_code)"', text):
            return False
        # Pure path references (not insights)
        if re.match(r"^[/\\]", text) or text.count("/") > 2:
            return False
        return True

    @staticmethod
    def _extract_insight_pattern(
        pattern: str, text: str, max_items: int = 8
    ) -> list[str]:
        """Extract captures from a pattern, filtered through quality gate."""
        matches = re.findall(pattern, text, re.IGNORECASE)
        results = []
        for m in matches:
            cleaned = m.strip().rstrip(".,;:!?\n")
            if cleaned and WikiMemoryProvider._is_insight_clean(cleaned):
                results.append(cleaned)
                if len(results) >= max_items:
                    break
        return results

    def _extract_insights_llm(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract structured insights from session using heuristics.
        
        Only user/assistant messages are scanned — tool output has raw \\n
        sequences, code, binary noise, and escaped JSON that produce garbage
        captures. Each extracted snippet passes a quality gate before being
        persisted. Full LLM extraction can be added later.
        """
        insights = []

        text_messages = [
            msg.get("content", "")
            for msg in messages
            if isinstance(msg.get("content"), str)
            and msg.get("role") in ("user", "assistant")
        ]
        full_text = "\n".join(text_messages)
        if not full_text.strip():
            return insights

        # Extract decisions (strong signal words only)
        decisions = self._extract_insight_pattern(
            r"(?:decided|decision|we'll go with|chose|selected)\s+(.+?)(?:\.|\n|$)",
            full_text,
        )
        if decisions:
            insights.append({
                "content": "\n".join(f"- {d}" for d in decisions),
                "frontmatter": {
                    "type": "session",
                    "category": "decisions",
                    "session_id": self._session_id,
                    "sources": "heuristic",
                },
            })

        # Extract learnings (no "important" — too common, too noisy)
        learnings = self._extract_insight_pattern(
            r"(?:learned|insight|key takeaway)\s+(.+?)(?:\.|\n|$)",
            full_text,
        )
        if learnings:
            insights.append({
                "content": "\n".join(f"- {item}" for item in learnings),
                "frontmatter": {
                    "type": "session",
                    "category": "learnings",
                    "session_id": self._session_id,
                    "sources": "heuristic",
                },
            })

        # Extract open questions (no "todo"/"follow-up"/"need to" — too noisy)
        questions = self._extract_insight_pattern(
            r"(?:open question|unresolved|still unclear)\s+(.+?)(?:\.|\n|$)",
            full_text,
        )
        if questions:
            insights.append({
                "content": "\n".join(f"- {q}" for q in questions),
                "frontmatter": {
                    "type": "session",
                    "category": "open_questions",
                    "session_id": self._session_id,
                    "sources": "heuristic",
                },
            })

        return insights


# Module-level instance for plugin discovery
register_memory_provider = WikiMemoryProvider


def register(ctx) -> None:
    """Register Wiki as a memory provider plugin."""
    ctx.register_memory_provider(WikiMemoryProvider())