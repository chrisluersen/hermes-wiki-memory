from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKER = r'''
import importlib.util, sys, types
from pathlib import Path
repo=Path(sys.argv[1]); wiki=Path(sys.argv[2]); page=sys.argv[3]; marker=sys.argv[4]
constants=types.ModuleType("hermes_constants")
constants.get_default_hermes_root=lambda: wiki.parent
constants.get_hermes_home=lambda: wiki.parent
sys.modules["hermes_constants"]=constants
spec=importlib.util.spec_from_file_location("cross_process_wiki_client", repo / "wiki_client.py")
mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
mod.WikiFileClient(wiki).append_to_page(page, marker)
'''


def _run_writers(wiki: Path, pages: list[str]) -> str:
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", WORKER, str(ROOT), str(wiki), page, f"marker-{index:02d}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index, page in enumerate(pages)
    ]
    failures = []
    for index, worker in enumerate(workers):
        stdout, stderr = worker.communicate(timeout=30)
        if worker.returncode:
            failures.append((index, worker.returncode, stdout, stderr))
    assert not failures, repr(failures)
    return (wiki / "Knowledge" / "log.md").read_text(encoding="utf-8")


def test_cross_process_appends_preserve_every_entry(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    count = 12

    text = _run_writers(wiki, ["Knowledge/log.md"] * count)

    for index in range(count):
        assert text.count(f"marker-{index:02d}") == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows case-alias regression")
def test_windows_case_alias_appends_share_one_lock(tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "Knowledge").mkdir(parents=True)
    count = 12
    pages = ["Knowledge/log.md" if index % 2 == 0 else "knowledge/LOG.md" for index in range(count)]

    text = _run_writers(wiki, pages)

    for index in range(count):
        assert text.count(f"marker-{index:02d}") == 1
