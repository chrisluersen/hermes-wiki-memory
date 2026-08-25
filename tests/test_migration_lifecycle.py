from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest


def _write_rehearsal_evidence(migration_module, wiki, plan, plan_path, tmp_path):
    rehearsal_wiki = tmp_path / "rehearsal-wiki"
    shutil.copytree(wiki, rehearsal_wiki)
    journal = tmp_path / "rehearsal-journal.jsonl"
    migration_module.apply_plan(
        rehearsal_wiki,
        plan_path,
        approved_plan_sha256=plan["plan_sha256"],
        backup_evidence=None,
        rehearsal_evidence=None,
        journal_path=journal,
        lock_path=tmp_path / "rehearsal.lock",
        confirmed=True,
        rehearsal=True,
    )
    verification = migration_module.verify_migration(
        rehearsal_wiki, plan_path, journal_path=journal
    )
    assert verification["status"] == "verified"
    rehearsal = tmp_path / "rehearsal.json"
    rehearsal.write_text(
        json.dumps(
            {
                "verified": True,
                "plan_sha256": plan["plan_sha256"],
                "source_tree_sha256": plan["source"]["tree_sha256"],
                "final_tree_sha256": verification["final_tree_sha256"],
                "rehearsal_wiki": str(rehearsal_wiki),
                "journal_path": str(journal),
            }
        ),
        encoding="utf-8",
    )
    return rehearsal


def _ready_fixture(migration_module, tmp_path: Path):
    wiki = tmp_path / "wiki"
    files = {
        "Inbox/capture.md": "capture",
        "Projects/project.md": "project",
        "Topics/alpha.md": "# Alpha",
        "Ideas/beta.md": "See [[Topics/alpha]]",
        "Clippings/raw.pdf": "raw",
        "Notes/source.md": "See [alpha](../Topics/alpha.md)",
    }
    for relative, content in files.items():
        path = wiki / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    plan = migration_module.build_plan(wiki)
    assert plan["status"] == "ready"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    backup_archive = tmp_path / "backup.tar.gz"
    backup_archive.write_bytes(b"synthetic verified backup")
    restore = tmp_path / "isolated-restore"
    shutil.copytree(wiki, restore)
    backup = tmp_path / "backup.json"
    backup.write_text(
        json.dumps(
            {
                "verified": True,
                "source_tree_sha256": plan["source"]["tree_sha256"],
                "backup_path": str(backup_archive),
                "backup_sha256": __import__("hashlib").sha256(backup_archive.read_bytes()).hexdigest(),
                "restore_path": str(restore),
            }
        ),
        encoding="utf-8",
    )
    rehearsal = _write_rehearsal_evidence(
        migration_module, wiki, plan, plan_path, tmp_path
    )
    return wiki, plan, plan_path, backup, rehearsal


def _apply(migration_module, wiki, plan, plan_path, backup, rehearsal, tmp_path):
    journal = tmp_path / "journal.jsonl"
    migration_module.apply_plan(
        wiki,
        plan_path,
        approved_plan_sha256=plan["plan_sha256"],
        backup_evidence=backup,
        rehearsal_evidence=rehearsal,
        journal_path=journal,
        lock_path=tmp_path / "lock",
        confirmed=True,
    )
    return journal


def test_verify_proves_exact_workbench_links_lexical_and_disposable_capture(
    migration_module, wiki_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    journal = _apply(
        migration_module, wiki, plan, plan_path, backup, rehearsal, tmp_path
    )

    result = migration_module.verify_migration(
        wiki,
        plan_path,
        journal_path=journal,
        lexical_probe=lambda root, query: wiki_module.WikiClient(
            root, config={"layout": "workbench"}
        )._lexical_prefetch(query, limit=5, max_chars=2000),
        lexical_queries=[
            ("alpha", "Knowledge/Topics/alpha.md"),
            ("project", "Projects/project.md"),
            ("source", "Sources/Notes/source.md"),
        ],
        disposable_capture_probe=True,
    )

    assert result["status"] == "verified"
    assert result["plan_sha256"] == plan["plan_sha256"]
    assert result["accounted_files"] == len(
        [item for item in plan["inventory"] if item["kind"] == "file"]
    )
    assert result["links_ok"] is True
    assert result["lexical_ok"] is True
    assert result["capture_ready"] is True
    assert result["semantic_active"] is False
    assert result["final_config"]["layout"] == "workbench"
    assert not list((wiki / "Inbox").glob(".migration-capture-probe-*"))


def test_verify_runs_default_bounded_lexical_checks_without_callback(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    journal = _apply(
        migration_module, wiki, plan, plan_path, backup, rehearsal, tmp_path
    )

    result = migration_module.verify_migration(
        wiki,
        plan_path,
        journal_path=journal,
    )

    assert result["status"] == "verified"
    assert result["lexical_ok"] is True
    assert {item["role"] for item in result["lexical_results"]} == {
        "knowledge",
        "projects",
        "processed-sources",
    }
    assert result["rollback_ready"] is False

    with_backup = migration_module.verify_migration(
        wiki,
        plan_path,
        journal_path=journal,
        backup_evidence=backup,
    )
    assert with_backup["rollback_ready"] is True


def test_verify_reports_tamper_unexpected_files_and_broken_links(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    journal = _apply(
        migration_module, wiki, plan, plan_path, backup, rehearsal, tmp_path
    )
    (wiki / "Knowledge" / "Topics" / "alpha.md").write_text("tampered")
    (wiki / "unexpected.md").write_text("[[Missing/page]]")

    result = migration_module.verify_migration(
        wiki,
        plan_path,
        journal_path=journal,
    )

    assert result["status"] == "failed"
    assert result["hashes_ok"] is False
    assert result["unexpected_files"] == ["unexpected.md"]
    assert "unexpected.md" in result["unexpected_objects"]
    assert result["objects_ok"] is False


def test_verify_rejects_unexpected_directories_special_objects_and_empty_legacy_root(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    journal = _apply(
        migration_module, wiki, plan, plan_path, backup, rehearsal, tmp_path
    )
    (wiki / "UnexpectedEmpty").mkdir()
    (wiki / "Topics").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = wiki / "linked-outside"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        link = None

    result = migration_module.verify_migration(
        wiki, plan_path, journal_path=journal
    )

    assert result["status"] == "failed"
    assert "UnexpectedEmpty" in result["unexpected_objects"]
    assert "Topics" in result["unexpected_objects"]
    if link is not None:
        assert "linked-outside" in result["unexpected_objects"]
    assert result["legacy_absent"] is False


def test_verify_rejects_link_escape_and_bounds_unexpected_markdown(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    journal = _apply(
        migration_module, wiki, plan, plan_path, backup, rehearsal, tmp_path
    )
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    project = wiki / "Projects" / "project.md"
    project.write_text("[outside](../../outside.md)", encoding="utf-8")
    oversized = wiki / "Projects" / "unexpected-large.md"
    oversized.write_bytes(b"x" * (migration_module.MAX_REWRITE_MARKDOWN_BYTES + 1))

    result = migration_module.verify_migration(
        wiki, plan_path, journal_path=journal
    )

    assert result["status"] == "failed"
    assert "Projects/unexpected-large.md" in result["unexpected_files"]
    assert "Projects/project.md" in result["hash_mismatches"]
    assert result["links_ok"] is False
    assert any("escapes Wiki" in item for item in result["broken_links"])


def test_verify_fails_closed_on_expected_non_utf8_markdown(
    migration_module, tmp_path
):
    wiki = tmp_path / "wiki"
    page = wiki / "Projects" / "binary.md"
    page.parent.mkdir(parents=True)
    page.write_bytes(b"\xff\xfe\xfd")
    plan = migration_module.build_plan(wiki)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    journal = tmp_path / "journal.jsonl"
    migration_module.apply_plan(
        wiki,
        plan_path,
        approved_plan_sha256=plan["plan_sha256"],
        backup_evidence=None,
        rehearsal_evidence=None,
        journal_path=journal,
        lock_path=tmp_path / "lock",
        confirmed=True,
        rehearsal=True,
    )

    result = migration_module.verify_migration(
        wiki, plan_path, journal_path=journal
    )

    assert result["status"] == "failed"
    assert result["links_ok"] is False
    assert any("not UTF-8" in item for item in result["broken_links"])


def test_backup_first_rollback_restores_preimage_and_retains_migrated_tree(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    evidence = json.loads(backup.read_text())
    restored = Path(evidence["restore_path"])
    _apply(migration_module, wiki, plan, plan_path, backup, rehearsal, tmp_path)
    migrated_hash = migration_module.inventory_tree(wiki)["tree_sha256"]
    failed_tree = tmp_path / "retained-migrated-tree"

    result = migration_module.rollback_from_verified_restore(
        wiki,
        backup,
        expected_source_tree_sha256=plan["source"]["tree_sha256"],
        retained_migrated_tree=failed_tree,
        confirmed=True,
    )

    assert result["status"] == "rolled-back"
    assert migration_module.inventory_tree(wiki)["tree_sha256"] == plan["source"][
        "tree_sha256"
    ]
    assert migration_module.inventory_tree(failed_tree)["tree_sha256"] == migrated_hash
    assert restored.is_dir()
    original_hold = Path(result["same_volume_original_hold"])
    assert original_hold.is_dir()
    assert migration_module.inventory_tree(original_hold)["tree_sha256"] == migrated_hash


def test_rollback_refuses_wrong_restore_without_moving_current_tree(
    migration_module, tmp_path
):
    wiki, plan, _, backup, _ = _ready_fixture(migration_module, tmp_path)
    evidence = json.loads(backup.read_text())
    restored = Path(evidence["restore_path"])
    (restored / "Topics" / "alpha.md").write_text("wrong")
    before = migration_module.inventory_tree(wiki)["tree_sha256"]

    with pytest.raises(ValueError, match="restore tree"):
        migration_module.rollback_from_verified_restore(
            wiki,
            backup,
            expected_source_tree_sha256=plan["source"]["tree_sha256"],
            retained_migrated_tree=tmp_path / "retained",
            confirmed=True,
        )
    assert migration_module.inventory_tree(wiki)["tree_sha256"] == before


def test_rollback_refuses_forged_backup_artifact_hash_before_moving_wiki(
    migration_module, tmp_path
):
    wiki, plan, _, backup, _ = _ready_fixture(migration_module, tmp_path)
    evidence = json.loads(backup.read_text(encoding="utf-8"))
    evidence["backup_sha256"] = "0" * 64
    backup.write_text(json.dumps(evidence), encoding="utf-8")
    before = migration_module.inventory_tree(wiki)["tree_sha256"]

    with pytest.raises(ValueError, match="backup artifact hash"):
        migration_module.rollback_from_verified_restore(
            wiki,
            backup,
            expected_source_tree_sha256=plan["source"]["tree_sha256"],
            retained_migrated_tree=tmp_path / "retained",
            confirmed=True,
        )

    assert migration_module.inventory_tree(wiki)["tree_sha256"] == before
    assert not (tmp_path / "retained").exists()


def test_rollback_restores_original_if_post_swap_verification_fails(
    migration_module, tmp_path, monkeypatch
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    _apply(migration_module, wiki, plan, plan_path, backup, rehearsal, tmp_path)
    migrated_hash = migration_module.inventory_tree(wiki)["tree_sha256"]
    retained = tmp_path / "retained-migrated"
    real_inventory = migration_module.inventory_tree
    post_swap_calls = 0

    def fail_canonical_post_swap(path):
        nonlocal post_swap_calls
        result = real_inventory(path)
        if Path(path).resolve() == wiki.resolve():
            post_swap_calls += 1
            if post_swap_calls == 2:
                return {**result, "tree_sha256": "0" * 64}
        return result

    monkeypatch.setattr(migration_module, "inventory_tree", fail_canonical_post_swap)

    with pytest.raises(ValueError, match="restored canonical tree verification"):
        migration_module.rollback_from_verified_restore(
            wiki,
            backup,
            expected_source_tree_sha256=plan["source"]["tree_sha256"],
            retained_migrated_tree=retained,
            confirmed=True,
        )

    assert real_inventory(wiki)["tree_sha256"] == migrated_hash
    assert real_inventory(retained)["tree_sha256"] == migrated_hash
    assert list(wiki.parent.glob(f".{wiki.name}.rollback-failed-*"))


def test_rollback_restores_original_when_failed_restore_rename_is_refused(
    migration_module, tmp_path, monkeypatch
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    _apply(migration_module, wiki, plan, plan_path, backup, rehearsal, tmp_path)
    migrated_hash = migration_module.inventory_tree(wiki)["tree_sha256"]
    retained = tmp_path / "retained-migrated"
    real_inventory = migration_module.inventory_tree
    real_replace = migration_module.os.replace
    canonical_calls = 0

    def fail_post_swap_verification(path):
        nonlocal canonical_calls
        result = real_inventory(path)
        if Path(path).resolve() == wiki.resolve():
            canonical_calls += 1
            if canonical_calls == 2:
                return {**result, "tree_sha256": "0" * 64}
        return result

    def refuse_failed_restore_rename(source, destination):
        if Path(source).resolve() == wiki.resolve() and ".rollback-failed-" in str(
            destination
        ):
            raise OSError("injected quarantine rename refusal")
        return real_replace(source, destination)

    monkeypatch.setattr(migration_module, "inventory_tree", fail_post_swap_verification)
    monkeypatch.setattr(migration_module.os, "replace", refuse_failed_restore_rename)

    with pytest.raises(ValueError, match="restored canonical tree verification"):
        migration_module.rollback_from_verified_restore(
            wiki,
            backup,
            expected_source_tree_sha256=plan["source"]["tree_sha256"],
            retained_migrated_tree=retained,
            confirmed=True,
        )

    assert real_inventory(wiki)["tree_sha256"] == migrated_hash
    failed = list(wiki.parent.glob(f".{wiki.name}.rollback-failed-*"))
    assert len(failed) == 1
    assert real_inventory(failed[0])["tree_sha256"] == plan["source"][
        "tree_sha256"
    ]
