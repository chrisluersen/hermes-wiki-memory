from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
HERMES_ROOT = Path("C:/test-hermes-root")


@pytest.fixture
def wiki_module(monkeypatch):
    """Load ``wiki_client.py`` with the smallest Hermes constants contract."""
    constants = sys.modules["hermes_constants"]
    constants.get_default_hermes_root = lambda: HERMES_ROOT
    constants.get_hermes_home = lambda: HERMES_ROOT
    name = "wiki_client_under_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "wiki_client.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def recovery_module(monkeypatch):
    name = "wiki_recovery_under_test"
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "recovery.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def plugin_module(monkeypatch):
    """Load the plugin package with the smallest supported Hermes contract."""
    for name in list(sys.modules):
        if name == "hermes_wiki_memory" or name.startswith("hermes_wiki_memory."):
            sys.modules.pop(name)

    constants = sys.modules["hermes_constants"]
    constants.get_default_hermes_root = lambda: HERMES_ROOT
    constants.get_hermes_home = lambda: HERMES_ROOT

    hermes_cli = types.ModuleType("hermes_cli")
    hermes_cli.__path__ = []
    config_module = types.ModuleType("hermes_cli.config")
    config_module.load_config_readonly = lambda: {}
    config_module.load_config = lambda: {}
    config_module.save_config = lambda config: None
    config_module.read_user_config_raw = lambda: {}
    config_module.get_config_path = lambda: HERMES_ROOT / "config.yaml"
    config_module.atomic_config_write = lambda path, config: None
    hermes_cli.config = config_module
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", config_module)

    spec = importlib.util.spec_from_file_location(
        "hermes_wiki_memory",
        REPO_ROOT / "__init__.py",
        submodule_search_locations=[str(REPO_ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "hermes_wiki_memory", module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module._test_config_module = config_module
    return module
