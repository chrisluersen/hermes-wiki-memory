from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def dashboard_module(monkeypatch):
    constants = types.ModuleType("hermes_constants")
    constants.get_default_hermes_root = lambda: Path("C:/test-hermes-root")
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)

    hermes_cli = types.ModuleType("hermes_cli")
    hermes_cli.__path__ = []
    config_module = types.ModuleType("hermes_cli.config")
    config_module.load_config_readonly = lambda: {}
    hermes_cli.config = config_module
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", config_module)

    name = "wiki_dashboard_under_test"
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "dashboard" / "plugin_api.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module._test_config_module = config_module
    return module


def test_dashboard_uses_memory_wiki_root_before_environment(
    dashboard_module, monkeypatch, tmp_path
):
    env_root = tmp_path / "env-wiki"
    configured_root = tmp_path / "configured-wiki"
    monkeypatch.setenv("WIKI_PATH", str(env_root))
    dashboard_module._test_config_module.load_config_readonly = lambda: {
        "memory": {"wiki": {"root": str(configured_root)}}
    }

    assert dashboard_module._wiki_root() == configured_root.resolve()


def test_dashboard_uses_wiki_path_fallback(dashboard_module, monkeypatch, tmp_path):
    env_root = tmp_path / "env-wiki"
    monkeypatch.setenv("WIKI_PATH", str(env_root))

    assert dashboard_module._wiki_root() == env_root.resolve()


def test_dashboard_honors_gbrain_home_parent_semantics(
    dashboard_module, monkeypatch, tmp_path
):
    parent = tmp_path / "gbrain-parent"
    monkeypatch.setenv("GBRAIN_HOME", str(parent))

    assert dashboard_module._gbrain_dir() == (parent / ".gbrain").resolve()


def test_dashboard_rejects_invalid_gbrain_home(dashboard_module, monkeypatch):
    monkeypatch.setenv("GBRAIN_HOME", "relative/../gbrain")

    assert dashboard_module._gbrain_dir() is None


@pytest.mark.parametrize(("requested", "expected"), [(-5, 1), (0, 1), (20, 20), (5000, 100)])
def test_activity_clamps_limit_before_git(
    dashboard_module, monkeypatch, requested, expected
):
    calls = []

    def fake_git(*args, cwd):
        calls.append((args, cwd))
        return ""

    monkeypatch.setattr(dashboard_module, "_git", fake_git)

    dashboard_module.get_activity(requested)

    assert calls[0][0][1] == f"-{expected}"
