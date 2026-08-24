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


def test_overview_reports_degraded_when_only_lexical_recall_is_available(
    dashboard_module, monkeypatch, tmp_path
):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    dashboard_module._test_config_module.load_config_readonly = lambda: {
        "memory": {
            "wiki": {
                "root": str(wiki),
                "gbrain_server": "gbrain",
                "gbrain_source": "wiki-main",
            }
        }
    }
    registry_module = types.ModuleType("tools.registry")
    registry_module.registry = types.SimpleNamespace(get_entry=lambda name: None)
    monkeypatch.setitem(sys.modules, "tools.registry", registry_module)

    health = dashboard_module.get_overview()["health"]

    assert health["status"] == "degraded"
    assert health["lexical_recall"] is True
    assert health["semantic_recall"] is False
    assert health["capture_ready"] is False


def test_overview_reports_available_for_bound_shared_recall_tool(
    dashboard_module, monkeypatch, tmp_path
):
    wiki = tmp_path / "wiki"
    (wiki / "Inbox").mkdir(parents=True)
    dashboard_module._test_config_module.load_config_readonly = lambda: {
        "memory": {
            "wiki": {
                "root": str(wiki),
                "gbrain_server": "gbrain-local",
                "gbrain_source": "wiki-main",
                "paths": {"capture": "Inbox"},
            }
        },
        "mcp_servers": {
            "gbrain-local": {"timeout": 6, "env": {"GBRAIN_SOURCE": "wiki-main"}}
        },
    }
    registry_module = types.ModuleType("tools.registry")
    registry_module.registry = types.SimpleNamespace(
        get_entry=lambda name: types.SimpleNamespace(handler=lambda args: "{}")
        if name == "mcp__gbrain_local__recall"
        else None
    )
    monkeypatch.setitem(sys.modules, "tools.registry", registry_module)

    health = dashboard_module.get_overview()["health"]

    assert health["status"] == "available"
    assert health["semantic_recall"] is True
    assert health["capture_ready"] is True


def test_overview_degrades_when_semantic_recall_works_but_capture_role_is_missing(
    dashboard_module, monkeypatch, tmp_path
):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    dashboard_module._test_config_module.load_config_readonly = lambda: {
        "memory": {
            "wiki": {
                "root": str(wiki),
                "gbrain_server": "gbrain-local",
                "gbrain_source": "wiki-main",
                "paths": {"capture": "Inbox"},
            }
        },
        "mcp_servers": {
            "gbrain-local": {"timeout": 6, "env": {"GBRAIN_SOURCE": "wiki-main"}}
        },
    }
    registry_module = types.ModuleType("tools.registry")
    registry_module.registry = types.SimpleNamespace(
        get_entry=lambda name: types.SimpleNamespace(handler=lambda args: "{}")
    )
    monkeypatch.setitem(sys.modules, "tools.registry", registry_module)

    health = dashboard_module.get_overview()["health"]

    assert health["semantic_recall"] is True
    assert health["capture_ready"] is False
    assert health["status"] == "degraded"


def test_counts_follow_configured_semantic_roles(dashboard_module, tmp_path):
    wiki = tmp_path / "wiki"
    for relative in (
        "Inbox/a.md",
        "Projects/p.md",
        "Topics/t.md",
        "Ideas/i.md",
        "Clippings/raw.md",
        "Notes/n.md",
        "Archive/old.md",
    ):
        path = wiki / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("page", encoding="utf-8")
    dashboard_module._test_config_module.load_config_readonly = lambda: {
        "memory": {
            "wiki": {
                "root": str(wiki),
                "layout": "adopt-existing",
                "paths": {
                    "capture": "Inbox",
                    "projects": "Projects",
                    "knowledge": ["Topics", "Ideas"],
                    "archive": "Archive",
                    "sources": {"originals": "Clippings", "processed": "Notes"},
                },
            }
        }
    }

    counts = dashboard_module.get_counts()

    assert counts["roles"] == {
        "capture": 1,
        "projects": 1,
        "knowledge": 2,
        "originals": 1,
        "processed": 1,
        "archive": 1,
    }
    assert counts["total"] == 7
