from __future__ import annotations

from pathlib import Path


def test_provider_subclasses_current_memory_provider(plugin_module):
    from agent.memory_provider import MemoryProvider

    provider = plugin_module.WikiMemoryProvider()

    assert isinstance(provider, MemoryProvider)
    assert provider.name == "wiki"


def test_initialize_uses_configured_wiki_root(plugin_module, monkeypatch, tmp_path):
    custom = tmp_path / "custom-wiki"
    custom.mkdir()
    monkeypatch.setenv("WIKI_PATH", str(custom))
    created = []

    class FakeClient:
        def __init__(self, wiki, **kwargs):
            self.wiki = Path(wiki)
            created.append((self.wiki, kwargs))

        def is_available(self):
            return True

    monkeypatch.setattr(plugin_module, "WikiClient", FakeClient)
    provider = plugin_module.WikiMemoryProvider()
    provider.initialize("session-1", agent_context="primary", provider_config={})

    assert created == [(
        custom.resolve(),
        {
            "gbrain_server": "gbrain",
            "gbrain_source": "",
            "gbrain_attested_source": "",
            "gbrain_timeout": None,
            "config": {},
        },
    )]
    assert provider._client.wiki == custom.resolve()


def test_memory_wiki_root_overrides_environment(plugin_module, monkeypatch, tmp_path):
    env_root = tmp_path / "env-wiki"
    configured_root = tmp_path / "configured-wiki"
    env_root.mkdir()
    configured_root.mkdir()
    monkeypatch.setenv("WIKI_PATH", str(env_root))
    created = []

    class FakeClient:
        def __init__(self, wiki, **kwargs):
            self.wiki = Path(wiki)
            created.append((self.wiki, kwargs))

        def is_available(self):
            return True

    monkeypatch.setattr(plugin_module, "WikiClient", FakeClient)
    provider = plugin_module.WikiMemoryProvider()
    provider.initialize(
        "session-1",
        agent_context="primary",
        provider_config={"root": str(configured_root)},
    )

    assert created == [(
        configured_root.resolve(),
        {
            "gbrain_server": "gbrain",
            "gbrain_source": "",
            "gbrain_attested_source": "",
            "gbrain_timeout": None,
            "config": {"root": str(configured_root)},
        },
    )]


def test_initialize_reads_memory_wiki_config_when_hermes_passes_no_provider_config(
    plugin_module, monkeypatch, tmp_path
):
    env_root = tmp_path / "env-wiki"
    configured_root = tmp_path / "configured-wiki"
    env_root.mkdir()
    configured_root.mkdir()
    monkeypatch.setenv("WIKI_PATH", str(env_root))
    configured = {"root": str(configured_root), "wiki_context_cap": 777}
    plugin_module._test_config_module.load_config_readonly = lambda: {
        "memory": {"wiki": configured}
    }
    created = []

    class FakeClient:
        def __init__(self, wiki, **kwargs):
            self.wiki = Path(wiki)
            created.append((self.wiki, kwargs))

        def is_available(self):
            return True

    monkeypatch.setattr(plugin_module, "WikiClient", FakeClient)
    provider = plugin_module.WikiMemoryProvider()
    provider.initialize("session-1", agent_context="primary")

    assert created == [(
        configured_root.resolve(),
        {
            "gbrain_server": "gbrain",
            "gbrain_source": "",
            "gbrain_attested_source": "",
            "gbrain_timeout": None,
            "config": configured,
        },
    )]
    assert provider._provider_config == configured


def test_initialize_attests_shared_mcp_source_and_timeout(plugin_module, monkeypatch, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    configured = {
        "root": str(wiki),
        "gbrain_server": "gbrain-local",
        "gbrain_source": "wiki-main",
    }
    plugin_module._test_config_module.load_config_readonly = lambda: {
        "memory": {"wiki": configured},
        "mcp_servers": {
            "gbrain-local": {
                "timeout": 6,
                "env": {"GBRAIN_SOURCE": "wiki-main"},
            }
        },
    }
    created = []

    class FakeClient:
        def __init__(self, root, **kwargs):
            self.wiki = Path(root)
            created.append(kwargs)

        def is_available(self):
            return True

    monkeypatch.setattr(plugin_module, "WikiClient", FakeClient)
    provider = plugin_module.WikiMemoryProvider()

    provider.initialize("session-1", agent_context="primary")

    assert created[0]["gbrain_attested_source"] == "wiki-main"
    assert created[0]["gbrain_timeout"] == 6


def test_initialize_rejects_mismatched_mcp_source_attestation(plugin_module, monkeypatch, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    plugin_module._test_config_module.load_config_readonly = lambda: {
        "memory": {
            "wiki": {
                "root": str(wiki),
                "gbrain_server": "gbrain-local",
                "gbrain_source": "wiki-main",
            }
        },
        "mcp_servers": {
            "gbrain-local": {"timeout": 30, "env": {"GBRAIN_SOURCE": "other"}}
        },
    }
    created = []

    class FakeClient:
        def __init__(self, root, **kwargs):
            self.wiki = Path(root)
            created.append(kwargs)

        def is_available(self):
            return True

    monkeypatch.setattr(plugin_module, "WikiClient", FakeClient)
    provider = plugin_module.WikiMemoryProvider()

    provider.initialize("session-1", agent_context="primary")

    assert created[0]["gbrain_attested_source"] == "other"
    assert created[0]["gbrain_timeout"] == 30


def test_explicit_server_override_uses_matching_mcp_attestation(
    plugin_module, monkeypatch, tmp_path
):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    plugin_module._test_config_module.load_config_readonly = lambda: {
        "memory": {
            "wiki": {
                "root": str(wiki),
                "gbrain_server": "old-server",
                "gbrain_source": "old-source",
            }
        },
        "mcp_servers": {
            "old-server": {"timeout": 30, "env": {"GBRAIN_SOURCE": "old-source"}},
            "new-server": {"timeout": 6, "env": {"GBRAIN_SOURCE": "new-source"}},
        },
    }
    created = []

    class FakeClient:
        def __init__(self, root, **kwargs):
            self.wiki = Path(root)
            created.append(kwargs)

        def is_available(self):
            return True

    monkeypatch.setattr(plugin_module, "WikiClient", FakeClient)
    provider = plugin_module.WikiMemoryProvider()

    provider.initialize(
        "session-1",
        agent_context="primary",
        provider_config={
            "gbrain_server": "new-server",
            "gbrain_source": "new-source",
        },
    )

    assert created[0]["gbrain_server"] == "new-server"
    assert created[0]["gbrain_attested_source"] == "new-source"
    assert created[0]["gbrain_timeout"] == 6


def test_backup_paths_are_available_before_initialize(plugin_module, monkeypatch, tmp_path):
    wiki = tmp_path / "wiki"
    gbrain_parent = tmp_path / "gbrain-parent"
    gbrain = gbrain_parent / ".gbrain"
    wiki.mkdir()
    gbrain.mkdir(parents=True)
    monkeypatch.setenv("WIKI_PATH", str(wiki))
    monkeypatch.setenv("GBRAIN_HOME", str(gbrain_parent))

    provider = plugin_module.WikiMemoryProvider()

    assert provider.backup_paths() == [str(wiki.resolve())]


def test_backup_paths_ignore_invalid_gbrain_home(plugin_module, monkeypatch, tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    monkeypatch.setenv("WIKI_PATH", str(wiki))
    monkeypatch.setenv("GBRAIN_HOME", "relative/../gbrain")

    provider = plugin_module.WikiMemoryProvider()

    assert provider.backup_paths() == [str(wiki.resolve())]


def test_shutdown_closes_client_once_and_clears_reference(plugin_module):
    calls = []

    class FakeGBrain:
        def close(self):
            calls.append("close")

    class FakeClient:
        gbrain = FakeGBrain()

    provider = plugin_module.WikiMemoryProvider()
    provider._client = FakeClient()
    provider._initialized = True

    provider.shutdown()
    provider.shutdown()

    assert calls == ["close"]
    assert provider._client is None
    assert provider._initialized is False


def test_setup_schema_exposes_supported_wiki_settings(plugin_module):
    provider = plugin_module.WikiMemoryProvider()

    schema = {field["key"]: field for field in provider.get_config_schema()}

    assert set(schema) == {
        "root", "wiki_context_cap", "gbrain_server", "gbrain_source", "layout",
        "capture_path", "projects_path", "knowledge_path", "archive_path",
        "originals_path", "processed_path",
    }
    assert schema["root"]["default"] == ""
    assert schema["wiki_context_cap"]["default"] == 1200
    assert schema["wiki_context_cap"]["minimum"] == 200
    assert schema["gbrain_server"]["default"] == "gbrain"
    assert schema["gbrain_source"]["default"] == ""
    assert schema["layout"]["default"] == "adopt-existing"


def test_save_config_persists_values_under_memory_wiki(plugin_module):
    stored = {"memory": {"provider": "wiki", "other": {"keep": True}}}
    written = []
    config_path = Path("C:/test-hermes-root/config.yaml")
    plugin_module._test_config_module.load_config = lambda: (_ for _ in ()).throw(
        AssertionError("save_config must not round-trip merged defaults")
    )
    plugin_module._test_config_module.read_user_config_raw = lambda: stored
    plugin_module._test_config_module.get_config_path = lambda: config_path
    plugin_module._test_config_module.atomic_config_write = (
        lambda path, config, **kwargs: written.append((path, config, kwargs))
    )
    provider = plugin_module.WikiMemoryProvider()

    provider.save_config(
        {
            "root": "C:/Knowledge/Wiki",
            "wiki_context_cap": 1600,
            "gbrain_server": "knowledge",
            "gbrain_source": "wiki-main",
            "layout": "adopt-existing",
            "capture_path": "Inbox",
            "projects_path": "Projects",
            "knowledge_path": "Topics, Ideas",
            "archive_path": "Archive",
            "originals_path": "Clippings",
            "processed_path": "Notes",
        },
        "C:/unused-hermes-home",
    )

    assert written == [
        (
            config_path,
            {
            "memory": {
                "provider": "wiki",
                "other": {"keep": True},
                "wiki": {
                    "root": "C:/Knowledge/Wiki",
                    "wiki_context_cap": 1600,
                    "gbrain_server": "knowledge",
                    "gbrain_source": "wiki-main",
                    "layout": "adopt-existing",
                    "paths": {
                        "capture": "Inbox",
                        "projects": "Projects",
                        "knowledge": ["Topics", "Ideas"],
                        "archive": "Archive",
                        "sources": {"originals": "Clippings", "processed": "Notes"},
                    },
                },
            }
            },
            {"sort_keys": False},
        )
    ]


def test_session_end_routes_inferred_insights_to_capture(plugin_module, monkeypatch):
    captured = []
    provider = plugin_module.WikiMemoryProvider()
    provider._session_id = "session-1"
    provider._initialized = True
    provider._client = type(
        "Client",
        (),
        {"capture_event": lambda self, **kwargs: captured.append(kwargs)},
    )()
    monkeypatch.setattr(
        provider,
        "_extract_insights_llm",
        lambda messages: [
            {
                "content": "- use alpha",
                "frontmatter": {"category": "decisions", "sources": "heuristic"},
            }
        ],
    )

    provider.on_session_end([{"role": "user", "content": "decided use alpha"}])

    assert captured == [
        {
            "event_type": "session_insight",
            "content": "- use alpha",
            "session_id": "session-1",
            "metadata": {"category": "decisions", "sources": "heuristic"},
        }
    ]


def test_memory_and_delegation_hooks_route_to_capture(plugin_module):
    captured = []
    provider = plugin_module.WikiMemoryProvider()
    provider._session_id = "parent-1"
    provider._client = type(
        "Client",
        (),
        {"capture_event": lambda self, **kwargs: captured.append(kwargs)},
    )()

    provider.on_memory_write("add", "user", "prefers concise", {"origin": "memory"})
    provider.on_delegation(
        "inspect repo",
        "found issue",
        child_session_id="child-1",
    )

    assert captured[0] == {
        "event_type": "explicit_memory",
        "content": "prefers concise",
        "session_id": "parent-1",
        "metadata": {
            "target": "user",
            "action": "add",
            "origin": "memory",
        },
    }
    assert captured[1] == {
        "event_type": "delegation",
        "content": "Task: inspect repo\n\nResult:\nfound issue",
        "session_id": "parent-1",
        "metadata": {"child_session_id": "child-1"},
    }


def test_system_prompt_reports_degraded_lexical_mode_truthfully(plugin_module):
    provider = plugin_module.WikiMemoryProvider()
    provider._client = type(
        "Client",
        (),
        {
            "is_available": lambda self: True,
            "health": lambda self: {
                "status": "degraded",
                "semantic_recall": False,
                "lexical_recall": True,
            },
        },
    )()

    block = provider.system_prompt_block()

    assert "Lexical Wiki recall" in block
    assert "Semantic recall via gbrain" not in block
    assert "captured to the configured capture folder" in block


def test_pre_compress_uses_shared_prefetch_path(plugin_module, monkeypatch):
    calls = []
    provider = plugin_module.WikiMemoryProvider()
    provider._provider_config = {"wiki_context_cap": 500}
    provider._client = type(
        "Client",
        (),
        {"prefetch": lambda self, query, **kwargs: calls.append((query, kwargs)) or "recall"},
    )()
    monkeypatch.setattr(provider, "_extract_wiki_references", lambda messages: ["Alpha", "Beta"])

    result = provider.on_pre_compress([{"role": "user", "content": "[[Alpha]]"}])

    assert result == "## Wiki Context (pre-compression)\n\n### Alpha\nrecall\n\n### Beta\nrecall\n"
    assert calls == [
        ("Alpha", {"limit": 3, "max_chars": 500}),
        ("Beta", {"limit": 3, "max_chars": 500}),
    ]


def test_memory_remove_is_captured_without_deleting_wiki_pages(plugin_module):
    captured = []
    provider = plugin_module.WikiMemoryProvider()
    provider._session_id = "session-1"
    provider._client = type(
        "Client",
        (),
        {"capture_event": lambda self, **kwargs: captured.append(kwargs)},
    )()

    provider.on_memory_write(
        "remove",
        "user",
        "",
        {"old_text": "obsolete preference"},
    )

    assert captured == [
        {
            "event_type": "explicit_memory",
            "content": "",
            "session_id": "session-1",
            "metadata": {
                "target": "user",
                "action": "remove",
                "old_text": "obsolete preference",
            },
        }
    ]
