"""Wiki Memory Provider — gbrain-powered semantic recall + session persistence.

Implements the MemoryProvider ABC for Hermes Agent.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from hermes_constants import get_default_hermes_root, get_hermes_home
from typing import Any, Dict, List, Optional

from .wiki_client import (
    WikiClient,
    _truncate_block,
    wiki_context_cap,
)

logger = logging.getLogger(__name__)


class WikiMemoryProvider:
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
            client = WikiClient()
            return client.is_available()
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

        # Shared wiki brain at the Hermes ROOT (see wiki_client.WIKI_PATH)
        wiki_path = str(Path(get_default_hermes_root()) / "wiki")
        self._client = WikiClient(Path(wiki_path))
        self._provider_config = kwargs.get("provider_config", {}) or {}

        if not self._client.is_available():
            logger.warning("Wiki provider initialized but wiki/gbrain not fully available")

        self._initialized = True
        logger.info("Wiki memory provider initialized for session %s", session_id)

    def system_prompt_block(self) -> str:
        """Static provider info for system prompt."""
        if not self._client or not self._client.is_available():
            return ""
        return (
            "## Wiki Memory\n"
            "- Semantic recall via gbrain (query/think tools available)\n"
            "- Session insights auto-persisted to wiki on session end\n"
            "- Built-in memory tool writes mirrored to wiki\n"
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

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        """gbrain tools are provided by the native gbrain MCP server instead."""
        return f"Unknown tool: {tool_name}"

    def shutdown(self) -> None:
        """Clean shutdown."""
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
                self._client.files.append_to_page(
                    path=insight["path"],
                    content=insight["content"],
                    frontmatter=insight.get("frontmatter", {}),
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

        # Prefetch related wiki content
        wiki_context = []
        for ref in refs[:5]:  # Limit to top 5 refs
            result = self._client.gbrain.query(ref, limit=3)
            if result and not result.startswith("gbrain"):
                wiki_context.append(f"### {ref}\n{result}")

        if not wiki_context:
            return ""

        block = "## Wiki Context (pre-compression)\n\n" + "\n\n".join(wiki_context) + "\n"
        return _truncate_block(block, wiki_context_cap(self._active_model, self._provider_config))

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mirror built-in memory tool writes to wiki."""
        if not self._client or action not in ("add", "replace"):
            return

        # Create dated memory entry page (knowledge/entities/ since Phase 3a fold)
        date = time.strftime("%Y-%m-%d")
        path = f"knowledge/entities/memory-entries/{date}.md"
        entry = f"### {target} ({action})\n\n{content}\n\n---\n"

        self._client.files.append_to_page(
            path,
            entry,
            frontmatter={
                "type": "memory_entry",
                "key": target,
                "action": action,
                "session_id": self._session_id,
                "sources": [],
                **(metadata or {}),
            },
        )

    def on_delegation(self, task: str, result: str, **kwargs) -> None:
        """Capture subagent delegation outcomes to wiki."""
        if not self._client:
            return

        child_session_id = kwargs.get("child_session_id", "")
        date = time.strftime("%Y-%m-%d")
        path = f"knowledge/entities/delegations/{date}.md"

        entry = (
            f"### Delegation: {task}\n"
            f"- **Child session:** {child_session_id}\n"
            f"- **Parent session:** {self._session_id}\n\n"
            f"#### Result\n{result}\n\n---\n"
        )

        self._client.files.append_to_page(
            path,
            entry,
            frontmatter={
                "type": "delegation",
                "task": task,
                "child_session_id": child_session_id,
                "parent_session_id": self._session_id,
                "sources": [],
            },
        )

    def backup_paths(self) -> List[str]:
        """Extra paths for `hermes backup`."""
        paths = []
        if self._client:
            paths.append(str(self._client.wiki))
        gbrain_dir = Path.home() / ".gbrain"
        if gbrain_dir.exists():
            paths.append(str(gbrain_dir))
        return paths

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
                "path": f"knowledge/entities/session-insights/{time.strftime('%Y-%m-%d')}-decisions.md",
                "title": f"Session Decisions — {time.strftime('%Y-%m-%d')}",
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
                "path": f"knowledge/entities/session-insights/{time.strftime('%Y-%m-%d')}-learnings.md",
                "title": f"Session Learnings — {time.strftime('%Y-%m-%d')}",
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
                "path": f"knowledge/entities/session-insights/{time.strftime('%Y-%m-%d')}-open-questions.md",
                "title": f"Open Questions — {time.strftime('%Y-%m-%d')}",
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