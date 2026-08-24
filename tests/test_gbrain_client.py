from __future__ import annotations

import importlib.util
import subprocess
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


def test_close_reaps_process_after_forced_kill(monkeypatch, tmp_path):
    module = _load_client_module(monkeypatch)
    client = module.GBrainClient(tmp_path)
    calls = []

    class FakeStdin:
        def close(self):
            calls.append("stdin.close")

    class FakeProcess:
        stdin = FakeStdin()

        def wait(self, timeout):
            calls.append(("wait", timeout))
            if calls.count(("wait", 5)) == 1:
                raise subprocess.TimeoutExpired("gbrain", timeout)
            return 0

        def kill(self):
            calls.append("kill")

    client._proc = FakeProcess()

    client.close()

    assert calls == ["stdin.close", ("wait", 5), "kill", ("wait", 5)]
    assert client._proc is None
