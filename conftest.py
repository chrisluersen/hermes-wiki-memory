"""Collection bootstrap for testing this Hermes directory plugin standalone."""

from __future__ import annotations

import sys
import types
from abc import ABC, abstractmethod
from pathlib import Path


if "agent.memory_provider" not in sys.modules:
    agent_pkg = sys.modules.setdefault("agent", types.ModuleType("agent"))
    agent_pkg.__path__ = []
    memory_provider = types.ModuleType("agent.memory_provider")

    class MemoryProvider(ABC):
        @property
        @abstractmethod
        def name(self): ...

        @abstractmethod
        def is_available(self): ...

        @abstractmethod
        def initialize(self, session_id, **kwargs): ...

        @abstractmethod
        def get_tool_schemas(self): ...

        def backup_paths(self):
            return []

    memory_provider.MemoryProvider = MemoryProvider
    agent_pkg.memory_provider = memory_provider
    sys.modules["agent.memory_provider"] = memory_provider

if "hermes_constants" not in sys.modules:
    constants = types.ModuleType("hermes_constants")
    test_root = Path("C:/test-hermes-root")
    constants.get_default_hermes_root = lambda: test_root
    constants.get_hermes_home = lambda: test_root
    sys.modules["hermes_constants"] = constants
