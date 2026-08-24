from __future__ import annotations

import importlib.util
import os
import threading
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_wiki_client():
    import sys

    spec = importlib.util.spec_from_file_location(
        "wiki_client_under_test", REPO_ROOT / "wiki_client.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def wiki_module(monkeypatch):
    import sys
    import types

    constants = types.ModuleType("hermes_constants")
    constants.get_default_hermes_root = lambda: REPO_ROOT
    constants.get_hermes_home = lambda: REPO_ROOT
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)
    return _load_wiki_client()


@pytest.mark.parametrize("path", ["../escape.md", "nested/../../escape.md", "C:/escape.md", "/escape.md"])
def test_writes_reject_paths_outside_wiki(wiki_module, tmp_path, path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    client = wiki_module.WikiFileClient(wiki)

    with pytest.raises(ValueError, match="inside the Wiki root"):
        client.upsert_page(path, "Escape", "must not be written")

    assert not (tmp_path / "escape.md").exists()


@pytest.mark.parametrize(
    "path",
    [
        r"..\escape.md",
        "Knowledge/page.md:secret",
        "Knowledge/CON.md",
        "Knowledge/CON.foo.md",
        "Knowledge/NUL.any.md",
        "Knowledge/COM1.backup.md",
        "Knowledge/aux.txt",
        "Knowledge/page.txt",
    ],
)
def test_writes_reject_unsafe_page_names(wiki_module, tmp_path, path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    client = wiki_module.WikiFileClient(wiki)

    with pytest.raises(ValueError, match="safe Markdown path"):
        client.upsert_page(path, "Unsafe", "must not be written")


def test_read_rejects_paths_outside_wiki(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    client = wiki_module.WikiFileClient(wiki)

    with pytest.raises(ValueError, match="inside the Wiki root"):
        client.read_page("../outside.md")


def test_write_rejects_symlink_parent_escape(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    outside = tmp_path / "outside"
    wiki.mkdir()
    outside.mkdir()
    link = wiki / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted on this platform")
    client = wiki_module.WikiFileClient(wiki)

    with pytest.raises(ValueError, match="inside the Wiki root"):
        client.upsert_page("linked/escape.md", "Escape", "must not be written")

    assert not (outside / "escape.md").exists()


def test_upsert_uses_atomic_replace_and_leaves_no_temp_file(wiki_module, monkeypatch, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    client = wiki_module.WikiFileClient(wiki)
    calls = []
    real_replace = os.replace

    def recording_replace(src, dst):
        calls.append((Path(src), Path(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(wiki_module.os, "replace", recording_replace)

    client.upsert_page("Knowledge/page.md", "Page", "body")

    target = wiki / "Knowledge" / "page.md"
    assert calls and calls[-1][1] == target
    assert target.exists()
    assert not list(target.parent.glob(".*.tmp"))


def test_upsert_does_not_mutate_caller_frontmatter(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    client = wiki_module.WikiFileClient(wiki)
    frontmatter = {"type": "note"}

    client.upsert_page("Knowledge/page.md", "Page", "body", frontmatter)

    assert frontmatter == {"type": "note"}


def test_concurrent_appends_preserve_every_entry(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    client_a = wiki_module.WikiFileClient(wiki)
    client_b = wiki_module.WikiFileClient(wiki)
    barrier = threading.Barrier(2)
    failures = []

    def append(client, marker):
        try:
            barrier.wait(timeout=5)
            client.append_to_page("Knowledge/log.md", marker)
        except BaseException as exc:
            failures.append(exc)

    threads = [
        threading.Thread(target=append, args=(client_a, "entry-a")),
        threading.Thread(target=append, args=(client_b, "entry-b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not failures
    text = (wiki / "Knowledge" / "log.md").read_text(encoding="utf-8")
    assert text.count("entry-a") == 1
    assert text.count("entry-b") == 1


def test_windows_case_aliases_share_lock_identity(wiki_module, monkeypatch, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    client = wiki_module.WikiFileClient(wiki)
    monkeypatch.setattr(wiki_module.os.path, "normcase", lambda value: value.lower())

    upper = client._resolve_page_path("Knowledge/Case.md")
    lower = client._resolve_page_path("knowledge/case.md")

    assert client._lock_identity(upper) == client._lock_identity(lower)


def test_lock_identity_is_stable_when_target_appears(wiki_module, monkeypatch, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    client = wiki_module.WikiFileClient(wiki)
    monkeypatch.setattr(wiki_module.os.path, "normcase", lambda value: value.lower())
    target = client._resolve_page_path("Knowledge/Case.md")
    before = client._lock_identity(target)

    (wiki / "Knowledge").mkdir()
    (wiki / "Knowledge" / "case.md").write_text("existing", encoding="utf-8")

    after = client._lock_identity(target)
    assert after == before


def test_lock_artifacts_live_outside_wiki(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    client = wiki_module.WikiFileClient(wiki)

    client.append_to_page("Knowledge/log.md", "entry")

    assert not (wiki / ".wiki-memory-locks").exists()
    assert client._lock_root != wiki
    assert client._lock_root.exists()
