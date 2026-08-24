from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_client_module(monkeypatch):
    constants = types.ModuleType("hermes_constants")
    constants.get_default_hermes_root = lambda: ROOT
    constants.get_hermes_home = lambda: ROOT
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)
    name = "wiki_client_shutdown_under_test"
    spec = importlib.util.spec_from_file_location(name, ROOT / "wiki_client.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_close_does_not_shutdown_shared_registry_owner(monkeypatch, tmp_path):
    module = _load_client_module(monkeypatch)
    calls = []
    registry = types.SimpleNamespace(
        get_entry=lambda name: types.SimpleNamespace(handler=lambda args: calls.append(args))
    )
    client = module.GBrainClient(tmp_path, registry=registry)

    client.close()

    assert calls == []
    assert not hasattr(client, "_proc")
