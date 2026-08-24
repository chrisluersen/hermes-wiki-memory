from __future__ import annotations

import sys
import types

import pytest
from types import SimpleNamespace


def _offline_client(module, wiki, config=None):
    return module.WikiClient(
        wiki,
        gbrain=module.GBrainClient(
            wiki,
            registry=SimpleNamespace(get_entry=lambda name: None),
            source="wiki-main",
        ),
        config=config or {},
    )


def test_adopt_existing_maps_roles_without_creating_directories(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    for name in ("Inbox", "Projects", "Clippings", "Notes", "Topics", "Ideas"):
        (wiki / name).mkdir(parents=True)
    before = sorted(path.relative_to(wiki).as_posix() for path in wiki.rglob("*"))

    paths = wiki_module.resolve_role_paths(wiki, {"layout": "adopt-existing"})

    assert paths.capture == "Inbox"
    assert paths.projects == "Projects"
    assert paths.knowledge == "Topics"
    assert paths.knowledge_paths == ("Topics", "Ideas")
    assert paths.originals == "Clippings"
    assert paths.processed == "Notes"
    assert sorted(path.relative_to(wiki).as_posix() for path in wiki.rglob("*")) == before


def test_workbench_role_defaults_are_clean_layout(wiki_module, tmp_path):
    paths = wiki_module.resolve_role_paths(tmp_path / "wiki", {"layout": "workbench"})

    assert paths.capture == "Inbox"
    assert paths.projects == "Projects"
    assert paths.knowledge == "Knowledge"
    assert paths.originals == "Sources/Originals"
    assert paths.processed == "Sources/Notes"
    assert paths.archive == "Archive"


def test_explicit_role_paths_override_adoption(wiki_module, tmp_path):
    paths = wiki_module.resolve_role_paths(
        tmp_path / "wiki",
        {
            "layout": "adopt-existing",
            "paths": {
                "capture": "Incoming",
                "knowledge": "Ideas",
                "sources": {"originals": "Raw", "processed": "Notes"},
            },
        },
    )

    assert paths.capture == "Incoming"
    assert paths.knowledge == "Ideas"
    assert paths.originals == "Raw"
    assert paths.processed == "Notes"


def test_explicit_multiple_knowledge_paths_are_preserved(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "Topics").mkdir(parents=True)
    (wiki / "Ideas").mkdir()

    paths = wiki_module.resolve_role_paths(
        wiki,
        {
            "layout": "adopt-existing",
            "paths": {"knowledge": ["Topics", "Ideas"]},
        },
    )

    assert paths.knowledge == "Topics"
    assert paths.knowledge_paths == ("Topics", "Ideas")


def test_capture_event_is_idempotent_and_redacts_secrets(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "Inbox").mkdir(parents=True)
    client = _offline_client(wiki_module, wiki, {"layout": "workbench"})
    content = "Decision: use alpha. API_KEY=sk-super-secret-token"

    first = client.capture_event(
        event_type="session_insight",
        content=content,
        session_id="session-1",
        metadata={"category": "decision"},
    )
    capture = wiki / first
    original_bytes = capture.read_bytes()
    original_mtime = capture.stat().st_mtime_ns
    second = client.capture_event(
        event_type="session_insight",
        content=content,
        session_id="session-1",
        metadata={"category": "decision"},
    )

    assert first == second
    captures = list((wiki / "Inbox").glob("*.md"))
    assert captures == [wiki / first]
    text = captures[0].read_text(encoding="utf-8")
    assert "sk-super-secret-token" not in text
    assert "API_KEY=[REDACTED]" in text
    assert "event_id:" in text
    assert "status: captured" in text
    assert "session_id: session-1" in text
    assert capture.read_bytes() == original_bytes
    assert capture.stat().st_mtime_ns == original_mtime


def test_capture_never_edits_existing_knowledge_page(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    established = wiki / "Knowledge" / "alpha.md"
    established.parent.mkdir(parents=True)
    established.write_text("canonical", encoding="utf-8")
    (wiki / "Inbox").mkdir()
    client = _offline_client(wiki_module, wiki, {"layout": "workbench"})

    client.capture_event(
        event_type="delegation",
        content="Delegation found alpha result",
        session_id="parent-1",
        metadata={"child_session_id": "child-1"},
    )

    assert established.read_text(encoding="utf-8") == "canonical"
    assert len(list((wiki / "Inbox").glob("*.md"))) == 1


def test_capture_requires_existing_configured_capture_directory(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    client = _offline_client(wiki_module, wiki, {"layout": "workbench"})

    with pytest.raises(RuntimeError, match="capture directory"):
        client.capture_event(
            event_type="session_insight",
            content="Decision: use alpha",
            session_id="session-1",
        )

    assert not (wiki / "Inbox").exists()


def test_capture_collision_fails_without_overwrite(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "Inbox").mkdir(parents=True)
    client = _offline_client(wiki_module, wiki, {"layout": "workbench"})
    path = client.capture_event(
        event_type="session_insight",
        content="Decision: use alpha",
        session_id="session-1",
    )
    target = wiki / path
    target.write_text("---\nevent_id: wrong\n---\n\ncollision", encoding="utf-8")
    collision_bytes = target.read_bytes()

    with pytest.raises(RuntimeError, match="collision"):
        client.capture_event(
            event_type="session_insight",
            content="Decision: use alpha",
            session_id="session-1",
        )

    assert target.read_bytes() == collision_bytes


def test_capture_same_event_id_rejects_corrupted_existing_body(
    wiki_module, tmp_path
):
    wiki = tmp_path / "wiki"
    (wiki / "Inbox").mkdir(parents=True)
    client = _offline_client(wiki_module, wiki, {"layout": "workbench"})
    path = client.capture_event(
        event_type="delegation",
        content="canonical body",
        session_id="session-1",
        metadata={"tool_name": "delegate"},
    )
    target = wiki / path
    original = target.read_text(encoding="utf-8")
    target.write_text(
        original.replace("canonical body", "forged body"), encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="capture collision"):
        client.capture_event(
            event_type="delegation",
            content="canonical body",
            session_id="session-1",
            metadata={"tool_name": "delegate"},
        )

    assert "forged body" in target.read_text(encoding="utf-8")


def test_capture_same_event_id_rejects_corrupted_existing_envelope(
    wiki_module, tmp_path
):
    wiki = tmp_path / "wiki"
    (wiki / "Inbox").mkdir(parents=True)
    client = _offline_client(wiki_module, wiki, {"layout": "workbench"})
    path = client.capture_event(
        event_type="delegation",
        content="canonical body",
        session_id="session-1",
        metadata={"tool_name": "delegate"},
    )
    target = wiki / path
    original = target.read_text(encoding="utf-8")
    target.write_text(
        original.replace("status: captured", "status: promoted"), encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="capture collision"):
        client.capture_event(
            event_type="delegation",
            content="canonical body",
            session_id="session-1",
            metadata={"tool_name": "delegate"},
        )

    assert "status: promoted" in target.read_text(encoding="utf-8")


def test_capture_uses_hermes_forced_redaction_before_hashing(
    wiki_module, monkeypatch, tmp_path
):
    wiki = tmp_path / "wiki"
    (wiki / "Inbox").mkdir(parents=True)
    calls = []
    redact_module = types.ModuleType("agent.redact")

    def redact_sensitive_text(text, *, force=False, **kwargs):
        calls.append((text, force))
        return str(text).replace("private-value", "[HERMES-REDACTED]")

    redact_module.redact_sensitive_text = redact_sensitive_text
    monkeypatch.setitem(sys.modules, "agent.redact", redact_module)
    client = _offline_client(wiki_module, wiki, {"layout": "workbench"})

    path = client.capture_event(
        event_type="explicit_memory",
        content="private-value",
        session_id="session-1",
        metadata={"old_text": "private-value"},
    )

    persisted = (wiki / path).read_text(encoding="utf-8")
    assert calls and all(force is True for _, force in calls)
    assert "private-value" not in persisted
    assert "[HERMES-REDACTED]" in persisted


def test_capture_metadata_cannot_override_reserved_envelope_fields(
    wiki_module, tmp_path
):
    wiki = tmp_path / "wiki"
    (wiki / "Inbox").mkdir(parents=True)
    client = _offline_client(wiki_module, wiki, {"layout": "workbench"})

    canonical_path = client.capture_event(
        event_type="delegation",
        content="safe result",
        session_id="session-real",
    )
    path = client.capture_event(
        event_type="delegation",
        content="safe result",
        session_id="session-real",
        metadata={
            "event_id": "attacker",
            "status": "promoted",
            "session_id": "session-fake",
            "redaction": {"applied": False},
        },
    )
    page = client.files.read_page(path)

    assert page is not None
    assert page.frontmatter["event_id"] != "attacker"
    assert page.frontmatter["status"] == "captured"
    assert page.frontmatter["session_id"] == "session-real"
    assert page.frontmatter["redaction"] == {
        "applied": True,
        "policy": "hermes-force-v1",
    }
    assert path == canonical_path


def test_explicit_role_path_rejects_case_alias_of_existing_directory(
    wiki_module, tmp_path
):
    wiki = tmp_path / "wiki"
    (wiki / "inbox").mkdir(parents=True)

    with pytest.raises(ValueError, match="exact on-disk spelling"):
        wiki_module.resolve_role_paths(
            wiki,
            {"layout": "adopt-existing", "paths": {"capture": "Inbox"}},
        )
