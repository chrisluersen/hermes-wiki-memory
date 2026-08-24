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
        def __init__(self, wiki):
            self.wiki = Path(wiki)
            created.append(self.wiki)

        def is_available(self):
            return True

    monkeypatch.setattr(plugin_module, "WikiClient", FakeClient)
    provider = plugin_module.WikiMemoryProvider()

    provider.initialize("session-1", agent_context="primary", provider_config={})

    assert created == [custom.resolve()]
    assert provider._client.wiki == custom.resolve()


def test_memory_wiki_root_overrides_environment(plugin_module, monkeypatch, tmp_path):
    env_root = tmp_path / "env-wiki"
    configured_root = tmp_path / "configured-wiki"
    env_root.mkdir()
    configured_root.mkdir()
    monkeypatch.setenv("WIKI_PATH", str(env_root))

    created = []

    class FakeClient:
        def __init__(self, wiki):
            self.wiki = Path(wiki)
            created.append(self.wiki)

        def is_available(self):
            return True

    monkeypatch.setattr(plugin_module, "WikiClient", FakeClient)
    provider = plugin_module.WikiMemoryProvider()

    provider.initialize(
        "session-1",
        agent_context="primary",
        provider_config={"root": str(configured_root)},
    )

    assert created == [configured_root.resolve()]


def test_initialize_reads_memory_wiki_config_when_hermes_passes_no_provider_config(
    plugin_module, monkeypatch, tmp_path
):
    env_root = tmp_path / "env-wiki"
    configured_root = tmp_path / "configured-wiki"
    env_root.mkdir()
    configured_root.mkdir()
    monkeypatch.setenv("WIKI_PATH", str(env_root))
    plugin_module._test_config_module.load_config_readonly = lambda: {
        "memory": {"wiki": {"root": str(configured_root), "wiki_context_cap": 777}}
    }

    created = []

    class FakeClient:
        def __init__(self, wiki):
            self.wiki = Path(wiki)
            created.append(self.wiki)

        def is_available(self):
            return True

    monkeypatch.setattr(plugin_module, "WikiClient", FakeClient)
    provider = plugin_module.WikiMemoryProvider()

    provider.initialize("session-1", agent_context="primary")

    assert created == [configured_root.resolve()]
    assert provider._provider_config == {
        "root": str(configured_root),
        "wiki_context_cap": 777,
    }


def test_backup_paths_are_available_before_initialize(plugin_module, monkeypatch, tmp_path):
    wiki = tmp_path / "wiki"
    gbrain_parent = tmp_path / "gbrain-parent"
    gbrain = gbrain_parent / ".gbrain"
    wiki.mkdir()
    gbrain.mkdir(parents=True)
    monkeypatch.setenv("WIKI_PATH", str(wiki))
    monkeypatch.setenv("GBRAIN_HOME", str(gbrain_parent))

    provider = plugin_module.WikiMemoryProvider()

    assert provider.backup_paths() == [str(wiki.resolve()), str(gbrain.resolve())]


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

    assert set(schema) == {"root", "wiki_context_cap"}
    assert schema["root"]["default"] == ""
    assert schema["wiki_context_cap"]["default"] == 1200
    assert schema["wiki_context_cap"]["minimum"] == 200


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
        {"root": "C:/Knowledge/Wiki", "wiki_context_cap": 1600},
        "C:/unused-hermes-home",
    )

    assert written == [
        (
            config_path,
            {
            "memory": {
                "provider": "wiki",
                "other": {"keep": True},
                "wiki": {"root": "C:/Knowledge/Wiki", "wiki_context_cap": 1600},
            }
            },
            {"sort_keys": False},
        )
    ]
