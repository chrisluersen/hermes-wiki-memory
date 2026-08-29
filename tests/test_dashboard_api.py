from __future__ import annotations

import importlib.util
import sqlite3
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


def test_sections_breakdown_per_project_and_knowledge(dashboard_module, tmp_path):
    wiki = tmp_path / "wiki"
    for relative in (
        "Projects/Personal/coffee.md",
        "Projects/Personal/recipes/brew.md",
        "Projects/Work/companies/acme.md",
        "Topics/concepts/alpha.md",
        "Topics/entities/beta.md",
        "Ideas/gamma.md",
        "Inbox/wke_1.md",
        "Inbox/wke_2.md",
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

    sections = dashboard_module.get_sections()

    # Projects: one entry per project dir, recursive page count.
    project_names = {s["name"] for s in sections["projects"]["Projects"]}
    assert project_names == {"Personal", "Work"}
    personal = next(s for s in sections["projects"]["Projects"] if s["name"] == "Personal")
    assert personal["pages"] == 2
    assert personal["mtime"] > 0

    # Knowledge: categories flattened across all knowledge roles.
    assert set(sections["knowledge"]["categories"]) == {"concepts", "entities"}
    assert sections["knowledge"]["categories"]["concepts"]["pages"] == 1
    assert sections["knowledge"]["total"] == 3  # 1 + 1 + 1 (Ideas is a flat knowledge root)

    # Inbox: pending captures, both present.
    assert sections["inbox"]["count"] == 2
    names = [item["name"] for item in sections["inbox"]["items"]]
    assert set(names) == {"wke_1.md", "wke_2.md"}

    # Archive missing → 0.
    assert sections["archive"] == 0


def test_sections_empty_wiki(dashboard_module, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    dashboard_module._test_config_module.load_config_readonly = lambda: {
        "memory": {"wiki": {"root": str(wiki), "layout": "adopt-existing"}}
    }

    sections = dashboard_module.get_sections()

    assert sections["projects"] == {"Projects": []}
    assert sections["knowledge"]["categories"] == {}
    assert sections["knowledge"]["total"] == 0
    assert sections["inbox"] == {"count": 0, "items": []}
    assert sections["archive"] == 0


def _make_board(root: Path, name: str, tasks: list[tuple[str, str, str, int]]) -> None:
    """Create a kanban board DB with (id, title, status, priority) tasks."""
    db = root / "kanban" / "boards" / name / "kanban.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, status TEXT, "
        "priority INTEGER, assignee TEXT, created_at REAL)"
    )
    for idx, (tid, title, status, priority) in enumerate(tasks):
        conn.execute(
            "INSERT INTO tasks (id, title, status, priority, assignee, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (tid, title, status, priority, "default", 100.0 + idx),
        )
    conn.commit()
    conn.close()


def test_work_aggregates_open_tasks_across_boards(dashboard_module, monkeypatch, tmp_path):
    hermes_root = tmp_path / "hermes"
    monkeypatch.setattr(dashboard_module, "_hermes_root", lambda: hermes_root)
    _make_board(hermes_root, "growth", [
        ("t1", "Ship feature", "ready", 0),
        ("t2", "Fix bug", "todo", 1),
        ("t3", "Done thing", "done", 0),
    ])
    _make_board(hermes_root, "personal", [
        ("t4", "Blocked task", "blocked", 2),
        ("t5", "Ready task", "ready", 0),
    ])

    work = dashboard_module.get_work()

    assert work["open_total"] == 4
    assert work["by_status"] == {"ready": 2, "todo": 1, "blocked": 1}
    # Both boards have a ready task, so all 4 open tasks are actionable.
    assert work["available"] == 4
    boards = {b["board"]: b for b in work["boards"]}
    assert set(boards) == {"growth", "personal"}
    assert boards["growth"]["open"] == 2
    assert {t["title"] for t in boards["growth"]["tasks"]} == {"Ship feature", "Fix bug"}
    # Done tasks excluded.
    assert all(t["status"] != "done" for b in work["boards"] for t in b["tasks"])


def test_work_no_boards(dashboard_module, monkeypatch, tmp_path):
    hermes_root = tmp_path / "hermes"
    monkeypatch.setattr(dashboard_module, "_hermes_root", lambda: hermes_root)

    work = dashboard_module.get_work()

    assert work == {"boards": [], "open_total": 0, "by_status": {}, "available": 0}
