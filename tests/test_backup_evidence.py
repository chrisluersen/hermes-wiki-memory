from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def backup_module(migration_module, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    name = "wiki_backup_evidence_under_test"
    monkeypatch.setitem(sys.modules, "migration", migration_module)
    spec = importlib.util.spec_from_file_location(
        name, root / "prepare_backup_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _wiki(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    for relative in (
        ".git/refs/heads",
        ".obsidian",
        "Inbox",
        "Projects",
        "Topics/Empty",
        "Ideas",
        "Clippings/attachments",
        "Notes",
    ):
        (wiki / relative).mkdir(parents=True, exist_ok=True)
    (wiki / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (wiki / ".git" / "refs" / "heads" / "main").write_text(
        "0" * 40 + "\n", encoding="ascii"
    )
    (wiki / ".obsidian" / "config").write_text("{}", encoding="utf-8")
    (wiki / "Inbox" / "capture.md").write_text("capture", encoding="utf-8")
    (wiki / "Topics" / "α.md").write_text("alpha", encoding="utf-8")
    (wiki / "Clippings" / "attachments" / "image.bin").write_bytes(
        b"\x00\x01synthetic"
    )
    return wiki


def test_backup_create_verify_round_trip_preserves_full_tree_and_evidence(
    backup_module, migration_module, tmp_path
):
    wiki = _wiki(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    archive = evidence / "wiki.zip"
    creation = evidence / "creation.json"
    restore = evidence / "restore"
    result = evidence / "backup.json"
    source_hash = migration_module.inventory_tree(wiki)["tree_sha256"]

    created = backup_module.create_backup(wiki, archive, creation)
    verified = backup_module.verify_backup(wiki, creation, restore, result)

    assert created["source_tree_sha256"] == source_hash
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == created[
        "backup_sha256"
    ]
    assert verified["verified"] is True
    assert verified["source_tree_sha256"] == source_hash
    assert verified["restore_path"] == str(restore.resolve())
    assert migration_module.inventory_tree(restore)["tree_sha256"] == source_hash
    assert (restore / ".git" / "HEAD").is_file()
    assert (restore / "Topics" / "Empty").is_dir()
    assert (restore / "Topics" / "α.md").read_text(encoding="utf-8") == "alpha"
    accepted, accepted_restore = migration_module._validate_backup_evidence(
        wiki, result, source_hash
    )
    assert accepted["backup_sha256"] == created["backup_sha256"]
    assert accepted_restore == restore.resolve()


def test_backup_create_and_verify_cli_are_separate_invocations(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    wiki = _wiki(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    archive = evidence / "wiki.zip"
    creation = evidence / "creation.json"
    restore = evidence / "restore"
    result = evidence / "backup.json"

    created = subprocess.run(
        [
            sys.executable,
            str(repo / "prepare_backup_evidence.py"),
            "create",
            "--wiki",
            str(wiki),
            "--archive",
            str(archive),
            "--result-out",
            str(creation),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert created.returncode == 0, created.stderr
    assert archive.is_file() and creation.is_file()
    assert not restore.exists() and not result.exists()

    verified = subprocess.run(
        [
            sys.executable,
            str(repo / "prepare_backup_evidence.py"),
            "verify",
            "--wiki",
            str(wiki),
            "--creation-result",
            str(creation),
            "--restore",
            str(restore),
            "--evidence-out",
            str(result),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(result.read_text(encoding="utf-8"))["verified"] is True


def test_backup_fails_closed_on_source_drift_archive_tamper_and_overwrite(
    backup_module, tmp_path
):
    wiki = _wiki(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    archive = evidence / "wiki.zip"
    creation = evidence / "creation.json"
    backup_module.create_backup(wiki, archive, creation)

    with pytest.raises(ValueError, match="already exists"):
        backup_module.create_backup(wiki, archive, evidence / "other.json")

    (wiki / "Topics" / "α.md").write_text("drift", encoding="utf-8")
    with pytest.raises(ValueError, match="source changed"):
        backup_module.verify_backup(
            wiki, creation, evidence / "restore", evidence / "backup.json"
        )

    (wiki / "Topics" / "α.md").write_text("alpha", encoding="utf-8")
    archive.write_bytes(archive.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="archive hash"):
        backup_module.verify_backup(
            wiki, creation, evidence / "restore", evidence / "backup.json"
        )


def test_backup_rejects_symlink_or_reparse_source_without_following(
    backup_module, tmp_path, monkeypatch
):
    wiki = _wiki(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = wiki / "escape"
    try:
        link.symlink_to(outside)
    except OSError:
        real_inventory = backup_module.inventory_tree

        def simulated(root):
            result = real_inventory(root)
            result["entries"].append(
                {
                    "path": "escape",
                    "kind": "reparse-point",
                    "size": 0,
                    "sha256": "",
                    "flags": [],
                }
            )
            return result

        monkeypatch.setattr(backup_module, "inventory_tree", simulated)

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    with pytest.raises(ValueError, match="unsupported objects"):
        backup_module.create_backup(
            wiki, evidence / "wiki.zip", evidence / "creation.json"
        )


def test_backup_verify_rejects_archive_traversal_and_existing_restore(
    backup_module, tmp_path
):
    wiki = _wiki(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    archive = evidence / "wiki.zip"
    creation = evidence / "creation.json"
    created = backup_module.create_backup(wiki, archive, creation)

    malicious = evidence / "malicious.zip"
    with zipfile.ZipFile(malicious, "w") as bundle:
        bundle.writestr("wiki/../escape.txt", "escape")
    record = json.loads(creation.read_text(encoding="utf-8"))
    record["backup_path"] = str(malicious)
    record["backup_sha256"] = hashlib.sha256(malicious.read_bytes()).hexdigest()
    malicious_result = evidence / "malicious.json"
    malicious_result.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(ValueError, match="unsafe member"):
        backup_module.verify_backup(
            wiki,
            malicious_result,
            evidence / "restore",
            evidence / "backup.json",
        )

    existing = evidence / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="already exists"):
        backup_module.verify_backup(
            wiki, creation, existing, evidence / "backup.json"
        )


def test_backup_verify_refuses_restore_destination_created_during_publication(
    backup_module, tmp_path, monkeypatch
):
    wiki = _wiki(tmp_path)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    archive = evidence / "wiki.zip"
    creation = evidence / "creation.json"
    restore = evidence / "restore"
    backup_module.create_backup(wiki, archive, creation)
    real_inventory = backup_module.inventory_tree
    inventory_calls = 0

    def create_racing_destination(root):
        nonlocal inventory_calls
        result = real_inventory(root)
        inventory_calls += 1
        if inventory_calls == 2:
            restore.mkdir()
            (restore / "intruder.txt").write_text("do not overwrite", encoding="utf-8")
        return result

    monkeypatch.setattr(backup_module, "inventory_tree", create_racing_destination)

    with pytest.raises(ValueError, match="backup restore already exists"):
        backup_module.verify_backup(
            wiki, creation, restore, evidence / "backup.json"
        )

    assert (restore / "intruder.txt").read_text(encoding="utf-8") == "do not overwrite"
    assert not (evidence / "backup.json").exists()
