from __future__ import annotations

import json
from types import SimpleNamespace


def test_gbrain_adapter_calls_registered_shared_mcp_tool(wiki_module, tmp_path):
    calls = []

    def handler(args, **kwargs):
        calls.append((args, kwargs))
        return json.dumps({"result": "semantic result"})

    registry = SimpleNamespace(
        get_entry=lambda name: SimpleNamespace(handler=handler)
        if name == "mcp__gbrain__recall"
        else None
    )
    registry.dispatch = lambda name, args: handler(args)
    client = wiki_module.GBrainClient(
        tmp_path,
        registry=registry,
        server_name="gbrain",
        source="wiki-main",
        attested_source="wiki-main",
        timeout=6,
    )

    assert client.query("shared owner", limit=3, max_chars=1200) == "semantic result"
    assert calls == [
        (
            {"query": "shared owner", "limit": 3, "budget_tokens": 300},
            {},
        )
    ]


def test_gbrain_adapter_never_spawns_or_owns_a_process(wiki_module, tmp_path):
    client = wiki_module.GBrainClient(tmp_path, registry=SimpleNamespace(get_entry=lambda name: None))

    assert not hasattr(client, "_proc")
    client.close()


def test_gbrain_adapter_normalizes_error_envelope(wiki_module, tmp_path):
    registry = SimpleNamespace(
        get_entry=lambda name: SimpleNamespace(
            handler=lambda args, **kwargs: json.dumps({"error": "server unavailable"})
        )
    )
    client = wiki_module.GBrainClient(
        tmp_path,
        registry=registry,
        source="wiki-main",
        attested_source="wiki-main",
        timeout=6,
    )

    assert client.query("anything") == ""
    assert client.last_error == "server unavailable"


def test_gbrain_adapter_requires_configured_source_binding(wiki_module, tmp_path):
    calls = []
    registry = SimpleNamespace(
        get_entry=lambda name: SimpleNamespace(
            handler=lambda args, **kwargs: calls.append(args) or json.dumps({"result": "hit"})
        )
    )
    client = wiki_module.GBrainClient(tmp_path, registry=registry, source="")

    assert client.query("anything") == ""
    assert calls == []
    assert "source" in client.last_error.lower()


def test_gbrain_adapter_uses_configured_server_name(wiki_module, tmp_path):
    names = []
    registry = SimpleNamespace(get_entry=lambda name: names.append(name) or None)
    client = wiki_module.GBrainClient(
        tmp_path,
        registry=registry,
        server_name="gbrain-local",
        source="wiki-main",
        attested_source="wiki-main",
        timeout=6,
    )

    assert client.query("anything") == ""
    assert names == ["mcp__gbrain_local__recall"]


def test_gbrain_adapter_rejects_registry_entry_from_wrong_toolset(wiki_module, tmp_path):
    calls = []
    registry = SimpleNamespace(
        get_entry=lambda name: SimpleNamespace(
            handler=lambda args: calls.append(args),
            toolset="mcp-other",
        ),
        dispatch=lambda name, args: calls.append(args),
    )
    client = wiki_module.GBrainClient(
        tmp_path,
        registry=registry,
        server_name="gbrain-local",
        source="wiki-main",
        attested_source="wiki-main",
        timeout=6,
    )

    assert client.query("alpha") == ""
    assert calls == []
    assert "toolset" in client.last_error.lower()


def test_gbrain_adapter_rejects_unattested_source_or_unsafe_timeout(wiki_module, tmp_path):
    calls = []
    registry = SimpleNamespace(
        get_entry=lambda name: SimpleNamespace(
            handler=lambda args, **kwargs: calls.append(args) or "{}"
        )
    )

    mismatched = wiki_module.GBrainClient(
        tmp_path,
        registry=registry,
        source="wiki-main",
        attested_source="other",
        timeout=6,
    )
    unsafe_timeout = wiki_module.GBrainClient(
        tmp_path,
        registry=registry,
        source="wiki-main",
        attested_source="wiki-main",
        timeout=30,
    )

    assert mismatched.query("alpha") == ""
    assert unsafe_timeout.query("alpha") == ""
    assert calls == []


def test_gbrain_adapter_formats_nested_recall_results(wiki_module, tmp_path):
    inner = {
        "protocol_version": "1",
        "facts": [{"fact": "Alpha is canonical", "entity_slug": "alpha"}],
        "results": [{"slug": "knowledge/alpha", "title": "Alpha", "chunk": "Alpha detail"}],
    }
    registry = SimpleNamespace(
        get_entry=lambda name: SimpleNamespace(
            handler=lambda args, **kwargs: json.dumps({"result": json.dumps(inner)})
        )
    )
    client = wiki_module.GBrainClient(
        tmp_path,
        registry=registry,
        source="wiki-main",
        attested_source="wiki-main",
        timeout=6,
    )

    result = client.query("alpha")

    assert "Alpha is canonical" in result
    assert "knowledge/alpha" in result
    assert "Alpha detail" in result


def test_lexical_fallback_prefers_knowledge_and_excludes_runtime_paths(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    for relative, text in {
        "Knowledge/alpha.md": "# Alpha Architecture\nCanonical alpha decision and rationale.",
        "Projects/alpha-rollout.md": "# Alpha Rollout\nActive alpha implementation milestone.",
        "Sources/Originals/alpha-source.md": "# Alpha Source\nRaw alpha material.",
        "Archive/alpha-old.md": "# Alpha Old\nSuperseded alpha notes.",
        "_meta/alpha-generated.md": "# Alpha Generated\nInternal runtime alpha data.",
        ".hermes/alpha-session.md": "# Alpha Session\nRuntime alpha transcript.",
    }.items():
        path = wiki / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    client = wiki_module.WikiClient(
        wiki,
        gbrain=wiki_module.GBrainClient(
            wiki,
            registry=SimpleNamespace(get_entry=lambda name: None),
            source="wiki-main",
        ),
    )
    result = client.prefetch("alpha architecture", limit=4, max_chars=2000)

    assert result.startswith("## Wiki Recall (lexical)")
    assert "Knowledge/alpha.md" in result
    assert "Projects/alpha-rollout.md" in result
    assert "Sources/Originals/alpha-source.md" in result
    assert result.index("Knowledge/alpha.md") < result.index("Sources/Originals/alpha-source.md")
    assert "_meta" not in result
    assert ".hermes" not in result


def test_lexical_fallback_respects_context_cap(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    page = wiki / "Knowledge" / "large.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Large\n" + "alpha " * 300, encoding="utf-8")
    client = wiki_module.WikiClient(
        wiki,
        gbrain=wiki_module.GBrainClient(
            wiki,
            registry=SimpleNamespace(get_entry=lambda name: None),
            source="wiki-main",
        ),
    )

    result = client.prefetch("alpha", max_chars=220)

    assert len(result) <= 275
    assert "truncated" in result


def test_semantic_result_wins_over_lexical_fallback(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    registry = SimpleNamespace(
        get_entry=lambda name: SimpleNamespace(
            handler=lambda args: json.dumps({"result": "semantic hit"})
        )
    )
    registry.dispatch = lambda name, args: registry.get_entry(name).handler(args)
    client = wiki_module.WikiClient(
        wiki,
        gbrain=wiki_module.GBrainClient(
            wiki,
            registry=registry,
            source="wiki-main",
            attested_source="wiki-main",
            timeout=6,
        ),
    )

    result = client.prefetch("alpha", max_chars=500)

    assert result == "## Wiki Recall (gbrain)\nsemantic hit\n"


def test_health_is_degraded_when_lexical_works_without_gbrain(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    client = wiki_module.WikiClient(
        wiki,
        gbrain=wiki_module.GBrainClient(
            wiki,
            registry=SimpleNamespace(get_entry=lambda name: None),
            source="wiki-main",
        ),
    )

    health = client.health()

    assert health["status"] == "degraded"
    assert health["wiki_readable"] is True
    assert health["wiki_writable"] is True
    assert health["lexical_recall"] is True
    assert health["semantic_recall"] is False
    assert client.is_available() is True


def test_health_is_unavailable_when_wiki_is_missing(wiki_module, tmp_path):
    wiki = tmp_path / "missing"
    client = wiki_module.WikiClient(
        wiki,
        gbrain=wiki_module.GBrainClient(
            wiki,
            registry=SimpleNamespace(get_entry=lambda name: None),
            source="wiki-main",
        ),
    )

    assert client.health()["status"] == "unavailable"
    assert client.is_available() is False


def test_health_is_available_when_shared_semantic_tool_is_bound(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / "Inbox").mkdir(parents=True)
    registry = SimpleNamespace(get_entry=lambda name: SimpleNamespace(handler=lambda args: "{}"))
    client = wiki_module.WikiClient(
        wiki,
        gbrain=wiki_module.GBrainClient(
            wiki,
            registry=registry,
            source="wiki-main",
            attested_source="wiki-main",
            timeout=6,
        ),
    )

    assert client.health()["status"] == "available"


def test_lexical_recall_ignores_symlinked_file_outside_wiki(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    knowledge = wiki / "Knowledge"
    knowledge.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("unique outside secret alpha", encoding="utf-8")
    link = knowledge / "linked.md"
    try:
        link.symlink_to(outside)
    except OSError:
        import pytest

        pytest.skip("symlink creation is not permitted on this platform")
    client = wiki_module.WikiClient(wiki)

    assert client._lexical_prefetch("unique outside secret", limit=5, max_chars=1000) == ""


def test_lexical_recall_skips_oversized_files(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    page = wiki / "Knowledge" / "oversized.md"
    page.parent.mkdir(parents=True)
    page.write_text("alpha " * 100_000, encoding="utf-8")
    client = wiki_module.WikiClient(wiki)

    assert client._lexical_prefetch("alpha", limit=5, max_chars=1000) == ""


def test_lexical_recall_stops_at_file_budget(wiki_module, monkeypatch, tmp_path):
    wiki = tmp_path / "wiki"
    knowledge = wiki / "Knowledge"
    knowledge.mkdir(parents=True)
    for index in range(5):
        (knowledge / f"{index}.md").write_text(f"alpha page {index}", encoding="utf-8")
    monkeypatch.setattr(wiki_module.WikiClient, "LEXICAL_MAX_FILES", 2)
    client = wiki_module.WikiClient(wiki)

    result = client._lexical_prefetch("alpha", limit=5, max_chars=1000)

    assert result.count("### Knowledge/") == 2


def test_lexical_recall_does_not_materialize_eager_rglob(
    wiki_module, monkeypatch, tmp_path
):
    wiki = tmp_path / "wiki"
    (wiki / "Knowledge").mkdir(parents=True)
    (wiki / "Knowledge" / "alpha.md").write_text(
        "streaming traversal needle", encoding="utf-8"
    )
    client = wiki_module.WikiClient(wiki)

    def forbidden_rglob(*args, **kwargs):
        raise AssertionError("lexical recall must not materialize Path.rglob")

    monkeypatch.setattr(wiki_module.Path, "rglob", forbidden_rglob)

    assert "streaming traversal needle" in client.prefetch("needle")


def test_truncate_block_never_exceeds_configured_cap(wiki_module):
    for cap in (0, 1, 10, 40, 100):
        assert len(wiki_module._truncate_block("x" * 500, cap)) <= cap
