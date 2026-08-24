from __future__ import annotations

import json
import shutil
import subprocess

import pytest


def test_rebuild_manifest_is_secret_free_and_treats_gbrain_as_derived(
    recovery_module, tmp_path
):
    wiki = tmp_path / "wiki"
    page = wiki / "Knowledge" / "alpha.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Alpha\ncanonical", encoding="utf-8")

    manifest = recovery_module.build_rebuild_manifest(
        wiki,
        {
            "gbrain_source": "wiki-main",
            "embedding_model": "example-model",
            "API_KEY": "must-not-leak",
        },
        plugin_version="0.4.0",
    )

    encoded = json.dumps(manifest, sort_keys=True)
    assert manifest["wiki"]["required"] is True
    assert manifest["gbrain"]["storage_policy"] == "rebuild"
    assert manifest["gbrain"]["source_id"] == "wiki-main"
    assert "must-not-leak" not in encoded
    assert len(manifest["wiki"]["tree_sha256"]) == 64


def test_restored_wiki_matches_digest_git_and_lexical_recall(
    recovery_module, wiki_module, tmp_path
):
    source = tmp_path / "source"
    page = source / "Knowledge" / "alpha.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Alpha Architecture\ncanonical alpha decision", encoding="utf-8")
    excluded = source / "_meta" / "alpha-generated.md"
    excluded.parent.mkdir()
    excluded.write_text("internal alpha runtime", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture"],
        cwd=source,
        check=True,
        capture_output=True,
    )
    restored = tmp_path / "restored"
    shutil.copytree(source, restored)

    report = recovery_module.verify_restored_wiki(
        source,
        restored,
        lexical_probe=lambda root: wiki_module.WikiClient(root)._lexical_prefetch(
            "alpha architecture", limit=5, max_chars=1000
        ),
    )

    assert report["tree_match"] is True
    assert report["git_ok"] is True
    assert report["lexical_ok"] is True
    assert "Knowledge/alpha.md" in report["lexical_result"]
    assert "_meta" not in report["lexical_result"]


def test_plugin_code_removal_twice_preserves_data(recovery_module, tmp_path):
    plugin_dir = tmp_path / "plugins" / "hermes-wiki-memory"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text("name: wiki", encoding="utf-8")
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    page = wiki / "alpha.md"
    page.write_bytes(b"canonical bytes")
    before = recovery_module.tree_sha256(wiki)

    first = recovery_module.remove_plugin_code(plugin_dir, retained_paths=[wiki])
    second = recovery_module.remove_plugin_code(plugin_dir, retained_paths=[wiki])

    assert first["removed"] is True
    assert second["removed"] is False
    assert recovery_module.tree_sha256(wiki) == before
    assert page.read_bytes() == b"canonical bytes"


def test_plugin_code_removal_refuses_retained_path_inside_plugin(
    recovery_module, tmp_path
):
    plugin = tmp_path / "plugins" / "wiki"
    retained = plugin / "data" / "canonical.md"
    retained.parent.mkdir(parents=True)
    retained.write_text("canonical", encoding="utf-8")

    with pytest.raises(ValueError, match="retained path is inside plugin directory"):
        recovery_module.remove_plugin_code(plugin, retained_paths=[retained])

    assert retained.read_text(encoding="utf-8") == "canonical"