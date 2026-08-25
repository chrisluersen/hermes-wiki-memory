from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _snapshot(root: Path) -> dict[str, tuple[str, int, str]]:
    result = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[rel] = ("symlink", 0, str(path.readlink()))
        elif path.is_dir():
            result[rel] = ("directory", 0, "")
        else:
            data = path.read_bytes()
            result[rel] = ("file", len(data), hashlib.sha256(data).hexdigest())
    return result


def test_plan_hash_is_deterministic_and_excludes_generated_time(migration_module):
    plan = {
        "schema_version": 1,
        "generated_at": "2026-01-01T00:00:00Z",
        "source": {"root_hint": "wiki", "tree_sha256": "a" * 64},
        "inventory": [
            {"path": "Topics/alpha.md", "kind": "file", "size": 5, "sha256": "b" * 64},
        ],
        "operations": [
            {
                "kind": "move",
                "source": "Topics/alpha.md",
                "destination": "Knowledge/Topics/alpha.md",
                "preimage_sha256": "b" * 64,
            }
        ],
        "rewrites": [],
        "blockers": [],
        "final_config": {"layout": "workbench"},
    }
    reordered = copy.deepcopy(plan)
    reordered["generated_at"] = "2030-01-01T00:00:00Z"
    reordered["inventory"] = list(reversed(reordered["inventory"]))
    reordered["operations"] = list(reversed(reordered["operations"]))

    first = migration_module.plan_sha256(plan)
    second = migration_module.plan_sha256(reordered)

    assert first == second
    assert len(first) == 64
    changed = copy.deepcopy(plan)
    changed["operations"][0]["destination"] = "Knowledge/alpha.md"
    assert migration_module.plan_sha256(changed) != first


def test_plan_validation_rejects_unsafe_unknown_duplicate_and_semantic_state(
    migration_module, tmp_path
):
    wiki = tmp_path / "wiki"
    page = wiki / "Topics" / "alpha.md"
    page.parent.mkdir(parents=True)
    page.write_text("alpha", encoding="utf-8")
    plan = migration_module.build_plan(wiki)

    unsafe = copy.deepcopy(plan)
    move = next(item for item in unsafe["operations"] if item["kind"] == "move")
    move["destination"] = "../escape.md"
    unsafe["plan_sha256"] = migration_module.plan_sha256(unsafe)
    with pytest.raises(ValueError, match="safe relative"):
        migration_module.validate_plan(unsafe)

    unknown = copy.deepcopy(plan)
    unknown["operations"][0]["kind"] = "delete"
    unknown["plan_sha256"] = migration_module.plan_sha256(unknown)
    with pytest.raises(ValueError, match="operation kind"):
        migration_module.validate_plan(unknown)

    duplicate = copy.deepcopy(plan)
    duplicate["operations"].append(copy.deepcopy(duplicate["operations"][-1]))
    duplicate["plan_sha256"] = migration_module.plan_sha256(duplicate)
    with pytest.raises(ValueError, match="duplicate operation"):
        migration_module.validate_plan(duplicate)

    semantic = copy.deepcopy(plan)
    semantic["final_config"]["gbrain_source"] = "live-source"
    semantic["plan_sha256"] = migration_module.plan_sha256(semantic)
    with pytest.raises(ValueError, match="semantic activation"):
        migration_module.validate_plan(semantic)


def test_inventory_is_recursive_deterministic_and_read_only(migration_module, tmp_path):
    wiki = tmp_path / "wiki"
    (wiki / ".obsidian").mkdir(parents=True)
    (wiki / "Topics" / "nested").mkdir(parents=True)
    (wiki / "Attachments").mkdir()
    (wiki / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")
    (wiki / "Topics" / "nested" / "café.md").write_text("# Café", encoding="utf-8")
    (wiki / "Attachments" / "image.png").write_bytes(b"png")
    before = _snapshot(wiki)

    first = migration_module.inventory_tree(wiki)
    second = migration_module.inventory_tree(wiki)

    assert _snapshot(wiki) == before
    assert first == second
    paths = [entry["path"] for entry in first["entries"]]
    assert paths == sorted(paths)
    assert ".obsidian" in paths
    assert ".obsidian/app.json" in paths
    assert "Topics/nested/café.md" in paths
    assert "Attachments/image.png" in paths
    assert len(first["tree_sha256"]) == 64
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )


def test_large_binary_inventory_and_move_use_streaming_helpers(migration_module, tmp_path):
    source = tmp_path / "large.bin"
    source.write_bytes((b"0123456789abcdef" * 131_072) + b"end")
    size, digest = migration_module._entry_digest(source, "file")

    assert size == source.stat().st_size
    assert digest == migration_module._file_sha256(source)

    destination = tmp_path / "destination" / "large.bin"
    copied_digest = migration_module._atomic_copy_new(source, destination)
    assert copied_digest == digest
    assert destination.stat().st_size == size
    assert source.is_file()


def test_move_rehashes_published_destination_before_source_deletion(
    migration_module, tmp_path, monkeypatch
):
    wiki = tmp_path / "wiki"
    source = wiki / "Clippings" / "raw.bin"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"canonical-source-bytes")
    plan = migration_module.build_plan(wiki)
    operation = next(
        item for item in plan["operations"] if item.get("source") == "Clippings/raw.bin"
    )
    destination = wiki / operation["destination"]
    real_hash = migration_module._file_sha256

    def corrupt_destination_hash(path):
        if Path(path) == destination and destination.exists():
            return "0" * 64
        return real_hash(path)

    monkeypatch.setattr(migration_module, "_file_sha256", corrupt_destination_hash)

    with pytest.raises(ValueError, match="destination verification"):
        migration_module._apply_operation(wiki, operation)
    assert source.is_file()
    assert destination.is_file()


def test_oversized_markdown_blocks_planning_instead_of_loading_unbounded_text(
    migration_module, tmp_path, monkeypatch
):
    wiki = tmp_path / "wiki"
    page = wiki / "Notes" / "large.md"
    page.parent.mkdir(parents=True)
    page.write_bytes(b"x" * 33)
    monkeypatch.setattr(migration_module, "MAX_REWRITE_MARKDOWN_BYTES", 32)

    plan = migration_module.build_plan(wiki)

    assert plan["status"] == "blocked"
    assert any(
        blocker["kind"] == "oversized-markdown" and blocker["path"] == "Notes/large.md"
        for blocker in plan["blockers"]
    )


def test_plan_maps_legacy_roles_and_blocks_unknown_roots(migration_module, tmp_path):
    wiki = tmp_path / "wiki"
    fixtures = {
        "Inbox/capture.md": "capture",
        "Projects/active.md": "project",
        "Topics/shared.md": "topic",
        "Ideas/shared.md": "idea",
        "Clippings/source.pdf": "source",
        "Notes/source.md": "note",
        ".obsidian/app.json": "{}",
        "Attachments/image.png": "image",
        "Mystery/unknown.md": "unknown",
    }
    for relative, content in fixtures.items():
        path = wiki / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    plan = migration_module.build_plan(wiki)
    moves = {
        operation["source"]: operation["destination"]
        for operation in plan["operations"]
        if operation["kind"] in {"move", "rewrite"}
    }

    assert moves["Topics/shared.md"] == "Knowledge/Topics/shared.md"
    assert moves["Ideas/shared.md"] == "Knowledge/Ideas/shared.md"
    assert moves["Clippings/source.pdf"] == "Sources/Originals/source.pdf"
    assert moves["Notes/source.md"] == "Sources/Notes/source.md"
    assert "Inbox/capture.md" not in moves
    assert "Projects/active.md" not in moves
    assert ".obsidian/app.json" not in moves
    assert "Attachments/image.png" not in moves
    assert any(blocker["path"] == "Mystery" for blocker in plan["blockers"])
    assert plan["status"] == "blocked"
    assert plan["final_config"]["layout"] == "workbench"
    assert plan["plan_sha256"] == migration_module.plan_sha256(plan)
    mkdirs = {
        item["destination"] for item in plan["operations"] if item["kind"] == "mkdir"
    }
    assert {
        "Inbox",
        "Projects",
        "Knowledge",
        "Sources",
        "Sources/Originals",
        "Sources/Notes",
        "Archive",
        "_meta",
    }.issubset(mkdirs)


def test_reviewed_root_decisions_are_hash_bound_safe_and_deterministic(
    migration_module, tmp_path
):
    wiki = tmp_path / "wiki"
    for relative in ("Mystery/nested/page.md", "Loose/file.md"):
        path = wiki / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    decisions = {
        "Mystery": {"action": "map", "destination": "Archive/Mystery"},
        "Loose": {"action": "retain"},
    }

    plan = migration_module.build_plan(wiki, decisions=decisions)
    moves = {
        item["source"]: item["destination"]
        for item in plan["operations"]
        if item["kind"] in {"move", "rewrite"}
    }

    assert plan["status"] == "ready"
    assert plan["decisions"] == decisions
    assert moves["Mystery/nested/page.md"] == "Archive/Mystery/nested/page.md"
    assert "Loose/file.md" not in moves
    assert plan["plan_sha256"] == migration_module.plan_sha256(plan)
    assert migration_module.build_plan(wiki, decisions=decisions)["plan_sha256"] == plan[
        "plan_sha256"
    ]
    changed = migration_module.build_plan(
        wiki,
        decisions={
            "Mystery": {"action": "retain"},
            "Loose": {"action": "retain"},
        },
    )
    assert changed["plan_sha256"] != plan["plan_sha256"]

    for invalid, message in (
        ({"Missing": {"action": "retain"}}, "unknown decision root"),
        ({"Mystery": {"action": "delete"}, "Loose": {"action": "retain"}}, "decision action"),
        (
            {
                "Mystery": {"action": "map", "destination": "../escape"},
                "Loose": {"action": "retain"},
            },
            "safe relative",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            migration_module.build_plan(wiki, decisions=invalid)


def test_reviewed_mapped_root_is_removed_and_verified_absent(
    migration_module, tmp_path
):
    wiki = tmp_path / "wiki"
    page = wiki / "Mystery" / "nested" / "page.md"
    page.parent.mkdir(parents=True)
    page.write_text("mystery", encoding="utf-8")
    plan = migration_module.build_plan(
        wiki,
        decisions={
            "Mystery": {"action": "map", "destination": "Knowledge/Mystery"}
        },
    )
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

    assert not (wiki / "Mystery").exists()
    result = migration_module.verify_migration(
        wiki, plan_path, journal_path=journal
    )
    assert result["status"] == "verified"
    (wiki / "Mystery").mkdir()
    failed = migration_module.verify_migration(
        wiki, plan_path, journal_path=journal
    )
    assert failed["status"] == "failed"
    assert failed["legacy_absent"] is False


def test_reviewed_mapping_preserves_empty_nested_directories(
    migration_module, tmp_path
):
    wiki = tmp_path / "wiki"
    empty = wiki / "Mystery" / "nested" / "empty"
    empty.mkdir(parents=True)
    plan = migration_module.build_plan(
        wiki,
        decisions={
            "Mystery": {"action": "map", "destination": "Knowledge/Mystery"}
        },
    )
    assert any(
        item["kind"] == "mkdir"
        and item["destination"] == "Knowledge/Mystery/nested/empty"
        for item in plan["operations"]
    )
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

    assert (wiki / "Knowledge" / "Mystery" / "nested" / "empty").is_dir()
    assert not (wiki / "Mystery").exists()
    assert migration_module.verify_migration(
        wiki, plan_path, journal_path=journal
    )["status"] == "verified"


def test_plan_retains_standard_root_governance_files_but_blocks_arbitrary_root_file(
    migration_module, tmp_path
):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    for name in (
        "AGENTS.md",
        "SCHEMA.md",
        "index.md",
        "log.md",
        "README.md",
        "LICENSE",
        ".gitignore",
    ):
        (wiki / name).write_text(name, encoding="utf-8")
    (wiki / "mystery.bin").write_bytes(b"mystery")

    plan = migration_module.build_plan(wiki)

    assert {item["path"] for item in plan["blockers"] if item["kind"] == "unknown-root"} == {
        "mystery.bin"
    }
    governance = {
        entry["path"]
        for entry in plan["inventory"]
        if entry["path"] != "mystery.bin"
    }
    assert not any(
        operation["source"] in governance
        and operation["kind"] in {"move", "rewrite"}
        for operation in plan["operations"]
    )


def test_inventory_records_symlink_without_traversing_target(
    migration_module, tmp_path
):
    wiki = tmp_path / "wiki"
    outside = tmp_path / "outside"
    wiki.mkdir()
    outside.mkdir()
    (outside / "secret.md").write_text("outside", encoding="utf-8")
    link = wiki / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted on this platform")

    inventory = migration_module.inventory_tree(wiki)
    entries = {entry["path"]: entry for entry in inventory["entries"]}

    assert entries["linked"]["kind"] == "symlink"
    assert "linked/secret.md" not in entries
    plan = migration_module.build_plan(wiki)
    assert any(
        blocker["kind"] == "unsupported-source-object" and blocker["path"] == "linked"
        for blocker in plan["blockers"]
    )


def test_reparse_attribute_classifies_as_unsupported_without_directory_semantics(
    migration_module
):
    directory_mode = 0o040755
    reparse_attribute = 0x0400

    assert (
        migration_module._entry_kind(
            directory_mode,
            file_attributes=reparse_attribute,
        )
        == "reparse-point"
    )
    assert migration_module._entry_kind(directory_mode, file_attributes=0) == "directory"


def test_plan_detects_destination_casefold_collision(migration_module, tmp_path):
    wiki = tmp_path / "wiki"
    for relative in ("Topics/Alpha.md", "Knowledge/Topics/alpha.md"):
        path = wiki / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")

    plan = migration_module.build_plan(wiki)

    assert plan["status"] == "blocked"
    assert any(item["kind"] == "destination-casefold-collision" for item in plan["blockers"])


def test_plan_rewrites_only_affected_links_outside_code(migration_module, tmp_path):
    wiki = tmp_path / "wiki"
    topic = wiki / "Topics" / "alpha.md"
    note = wiki / "Notes" / "ref.md"
    attachment = wiki / "Clippings" / "diagram.png"
    topic.parent.mkdir(parents=True)
    note.parent.mkdir(parents=True)
    attachment.parent.mkdir(parents=True)
    topic.write_text("# Alpha", encoding="utf-8")
    attachment.write_bytes(b"png")
    note.write_text(
        "See [[Topics/alpha#Why|Alpha]], ![[Clippings/diagram.png]], "
        "and [alpha](../Topics/alpha.md#Why).\n"
        "Keep [[alpha]] and `[[Topics/alpha]]`.\n"
        "```md\n[[Topics/alpha]]\n```\n",
        encoding="utf-8",
    )

    plan = migration_module.build_plan(wiki)
    rewrite = next(item for item in plan["operations"] if item["source"] == "Notes/ref.md")

    assert rewrite["kind"] == "rewrite"
    assert rewrite["destination"] == "Sources/Notes/ref.md"
    expected_postimage = (
        "See [[Knowledge/Topics/alpha#Why|Alpha]], "
        "![[Sources/Originals/diagram.png]], "
        "and [alpha](../../Knowledge/Topics/alpha.md#Why).\n"
        "Keep [[alpha]] and `[[Topics/alpha]]`.\n"
        "```md\n[[Topics/alpha]]\n```\n"
    )
    assert "postimage_text" not in rewrite
    assert migration_module._apply_rewrites(
        note.read_text(encoding="utf-8"), rewrite["rewrites"]
    ) == expected_postimage
    assert len(rewrite["rewrites"]) >= 3
    assert all(
        set(item) >= {"start", "end", "expected", "replacement", "kind"}
        for item in rewrite["rewrites"]
    )
    assert rewrite["postimage_sha256"] == hashlib.sha256(
        expected_postimage.encode("utf-8")
    ).hexdigest()


def test_plan_does_not_duplicate_private_markdown_body(migration_module, tmp_path):
    wiki = tmp_path / "wiki"
    topic = wiki / "Topics" / "alpha.md"
    note = wiki / "Notes" / "private.md"
    topic.parent.mkdir(parents=True)
    note.parent.mkdir(parents=True)
    topic.write_text("alpha", encoding="utf-8")
    secret_body = "private prose that must not be copied into retained plan evidence"
    note.write_text(f"{secret_body}\n[[Topics/alpha]]\n", encoding="utf-8")

    plan = migration_module.build_plan(wiki)
    serialized = json.dumps(plan, ensure_ascii=False)

    assert secret_body not in serialized
    operation = next(item for item in plan["operations"] if item["source"] == "Notes/private.md")
    assert "postimage_text" not in operation


def test_markdown_rewrite_preserves_query_string_and_fragment(
    migration_module, tmp_path
):
    wiki = tmp_path / "wiki"
    topic = wiki / "Topics" / "alpha.md"
    note = wiki / "Notes" / "query.md"
    topic.parent.mkdir(parents=True)
    note.parent.mkdir(parents=True)
    topic.write_text("alpha", encoding="utf-8")
    original = "[alpha](../Topics/alpha.md?mode=raw#Why)\n"
    note.write_text(original, encoding="utf-8")

    plan = migration_module.build_plan(wiki)
    operation = next(item for item in plan["operations"] if item["source"] == "Notes/query.md")
    rewritten = migration_module._apply_rewrites(original, operation["rewrites"])

    assert rewritten == "[alpha](../../Knowledge/Topics/alpha.md?mode=raw#Why)\n"


def test_plan_and_apply_rewrite_links_in_retained_project_file(
    migration_module, tmp_path
):
    wiki = tmp_path / "wiki"
    topic = wiki / "Topics" / "alpha.md"
    project = wiki / "Projects" / "active.md"
    topic.parent.mkdir(parents=True)
    project.parent.mkdir(parents=True)
    topic.write_text("alpha", encoding="utf-8")
    project.write_text("Use [[Topics/alpha]].", encoding="utf-8")
    plan = migration_module.build_plan(wiki)
    rewrite = next(item for item in plan["operations"] if item["source"] == "Projects/active.md")

    assert rewrite["kind"] == "rewrite"
    assert rewrite["destination"] == "Projects/active.md"
    assert rewrite["in_place"] is True

    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    backup_archive = tmp_path / "backup.tar.gz"
    backup_archive.write_bytes(b"backup")
    restore = tmp_path / "isolated-restore"
    shutil.copytree(wiki, restore)
    backup = tmp_path / "backup.json"
    backup.write_text(
        json.dumps(
            {
                "verified": True,
                "source_tree_sha256": plan["source"]["tree_sha256"],
                "backup_path": str(backup_archive),
                "backup_sha256": hashlib.sha256(backup_archive.read_bytes()).hexdigest(),
                "restore_path": str(restore),
            }
        )
    )
    rehearsal_wiki = tmp_path / "rehearsal-wiki"
    shutil.copytree(wiki, rehearsal_wiki)
    rehearsal_journal = tmp_path / "rehearsal-journal.jsonl"
    migration_module.apply_plan(
        rehearsal_wiki,
        plan_path,
        approved_plan_sha256=plan["plan_sha256"],
        backup_evidence=None,
        rehearsal_evidence=None,
        journal_path=rehearsal_journal,
        lock_path=tmp_path / "rehearsal.lock",
        confirmed=True,
        rehearsal=True,
    )
    rehearsal_verification = migration_module.verify_migration(
        rehearsal_wiki, plan_path, journal_path=rehearsal_journal
    )
    assert rehearsal_verification["status"] == "verified"
    rehearsal = tmp_path / "rehearsal.json"
    rehearsal.write_text(
        json.dumps(
            {
                "verified": True,
                "source_tree_sha256": plan["source"]["tree_sha256"],
                "plan_sha256": plan["plan_sha256"],
                "final_tree_sha256": rehearsal_verification["final_tree_sha256"],
                "rehearsal_wiki": str(rehearsal_wiki),
                "journal_path": str(rehearsal_journal),
            }
        )
    )
    migration_module.apply_plan(
        wiki,
        plan_path,
        approved_plan_sha256=plan["plan_sha256"],
        backup_evidence=backup,
        rehearsal_evidence=rehearsal,
        journal_path=tmp_path / "journal.jsonl",
        lock_path=tmp_path / "lock",
        confirmed=True,
    )
    assert project.read_text(encoding="utf-8") == "Use [[Knowledge/Topics/alpha]]."


def test_plan_cli_writes_external_review_outputs_and_never_mutates_wiki(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    wiki = tmp_path / "wiki"
    unknown = wiki / "Mystery" / "unknown.md"
    unknown.parent.mkdir(parents=True)
    unknown.write_text("unknown", encoding="utf-8")
    before = _snapshot(wiki)
    plan_path = tmp_path / "out" / "plan.json"
    report_path = tmp_path / "out" / "plan.md"

    result = subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "plan",
            "--wiki",
            str(wiki),
            "--json-out",
            str(plan_path),
            "--report-out",
            str(report_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 3
    assert _snapshot(wiki) == before
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["status"] == "blocked"
    assert plan["plan_sha256"] in result.stdout
    report = report_path.read_text(encoding="utf-8")
    assert "# Wiki Workbench Migration Plan" in report
    assert plan["plan_sha256"] in report
    assert "Mystery" in report

    overwrite = subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "plan",
            "--wiki",
            str(wiki),
            "--json-out",
            str(plan_path),
            "--report-out",
            str(report_path),
        ],
        capture_output=True,
        text=True,
    )
    assert overwrite.returncode == 2
    assert "refusing existing output" in overwrite.stderr.lower()


def test_plan_cli_refuses_outputs_inside_wiki(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    wiki = tmp_path / "wiki"
    (wiki / "Inbox").mkdir(parents=True)

    result = subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "plan",
            "--wiki",
            str(wiki),
            "--json-out",
            str(wiki / "plan.json"),
            "--report-out",
            str(tmp_path / "report.md"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert not (wiki / "plan.json").exists()


def _ready_fixture(migration_module, tmp_path):
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
    backup = tmp_path / "backup.json"
    backup_archive = tmp_path / "backup.tar.gz"
    backup_archive.write_bytes(b"synthetic verified backup")
    restore = tmp_path / "isolated-restore"
    shutil.copytree(wiki, restore)
    backup.write_text(
        json.dumps(
            {
                "verified": True,
                "source_tree_sha256": plan["source"]["tree_sha256"],
                "backup_path": str(backup_archive),
                "backup_sha256": hashlib.sha256(backup_archive.read_bytes()).hexdigest(),
                "restore_path": str(restore),
            }
        ),
        encoding="utf-8",
    )
    rehearsal_wiki = tmp_path / "rehearsal-wiki"
    shutil.copytree(wiki, rehearsal_wiki)
    rehearsal_journal = tmp_path / "rehearsal-journal.jsonl"
    migration_module.apply_plan(
        rehearsal_wiki,
        plan_path,
        approved_plan_sha256=plan["plan_sha256"],
        backup_evidence=None,
        rehearsal_evidence=None,
        journal_path=rehearsal_journal,
        lock_path=tmp_path / "rehearsal.lock",
        confirmed=True,
        rehearsal=True,
    )
    rehearsal_verification = migration_module.verify_migration(
        rehearsal_wiki,
        plan_path,
        journal_path=rehearsal_journal,
    )
    assert rehearsal_verification["status"] == "verified"
    rehearsal = tmp_path / "rehearsal.json"
    rehearsal.write_text(
        json.dumps(
            {
                "verified": True,
                "plan_sha256": plan["plan_sha256"],
                "source_tree_sha256": plan["source"]["tree_sha256"],
                "final_tree_sha256": rehearsal_verification["final_tree_sha256"],
                "rehearsal_wiki": str(rehearsal_wiki),
                "journal_path": str(rehearsal_journal),
            }
        ),
        encoding="utf-8",
    )
    return wiki, plan, plan_path, backup, rehearsal


def test_apply_requires_exact_hash_unchanged_tree_and_verified_evidence(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    journal = tmp_path / "journal.jsonl"
    lock = tmp_path / "migration.lock"
    before = _snapshot(wiki)

    with pytest.raises(ValueError, match="plan hash"):
        migration_module.apply_plan(
            wiki,
            plan_path,
            approved_plan_sha256="0" * 64,
            backup_evidence=backup,
            rehearsal_evidence=rehearsal,
            journal_path=journal,
            lock_path=lock,
            confirmed=True,
        )
    assert _snapshot(wiki) == before

    (wiki / "Topics" / "drift.md").write_text("drift", encoding="utf-8")
    with pytest.raises(ValueError, match="source tree drift"):
        migration_module.apply_plan(
            wiki,
            plan_path,
            approved_plan_sha256=plan["plan_sha256"],
            backup_evidence=backup,
            rehearsal_evidence=rehearsal,
            journal_path=journal,
            lock_path=lock,
            confirmed=True,
        )


def test_apply_independently_rejects_forged_backup_and_restore_evidence(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    evidence = json.loads(backup.read_text())
    evidence["backup_sha256"] = "0" * 64
    backup.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match="backup artifact hash"):
        migration_module.apply_plan(
            wiki,
            plan_path,
            approved_plan_sha256=plan["plan_sha256"],
            backup_evidence=backup,
            rehearsal_evidence=rehearsal,
            journal_path=tmp_path / "journal.jsonl",
            lock_path=tmp_path / "lock",
            confirmed=True,
        )

    evidence["backup_sha256"] = hashlib.sha256(
        Path(evidence["backup_path"]).read_bytes()
    ).hexdigest()
    (Path(evidence["restore_path"]) / "Topics" / "alpha.md").write_text(
        "tampered", encoding="utf-8"
    )
    backup.write_text(json.dumps(evidence), encoding="utf-8")
    with pytest.raises(ValueError, match="backup restore tree"):
        migration_module.apply_plan(
            wiki,
            plan_path,
            approved_plan_sha256=plan["plan_sha256"],
            backup_evidence=backup,
            rehearsal_evidence=rehearsal,
            journal_path=tmp_path / "journal.jsonl",
            lock_path=tmp_path / "lock",
            confirmed=True,
        )


def test_apply_rejects_rehearsal_final_hash_claim_that_does_not_match_verification(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    evidence = json.loads(rehearsal.read_text(encoding="utf-8"))
    evidence["final_tree_sha256"] = "0" * 64
    rehearsal.write_text(json.dumps(evidence), encoding="utf-8")

    with pytest.raises(ValueError, match="rehearsal final tree"):
        migration_module.apply_plan(
            wiki,
            plan_path,
            approved_plan_sha256=plan["plan_sha256"],
            backup_evidence=backup,
            rehearsal_evidence=rehearsal,
            journal_path=tmp_path / "journal.jsonl",
            lock_path=tmp_path / "lock",
            confirmed=True,
        )


def test_apply_journals_moves_rewrites_and_supports_idempotent_resume(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    journal = tmp_path / "journal.jsonl"
    lock = tmp_path / "migration.lock"

    result = migration_module.apply_plan(
        wiki,
        plan_path,
        approved_plan_sha256=plan["plan_sha256"],
        backup_evidence=backup,
        rehearsal_evidence=rehearsal,
        journal_path=journal,
        lock_path=lock,
        confirmed=True,
    )

    assert result["status"] == "applied"
    assert (wiki / "Knowledge" / "Topics" / "alpha.md").read_text() == "# Alpha"
    assert "[[Knowledge/Topics/alpha]]" in (
        wiki / "Knowledge" / "Ideas" / "beta.md"
    ).read_text()
    assert "../../Knowledge/Topics/alpha.md" in (
        wiki / "Sources" / "Notes" / "source.md"
    ).read_text()
    assert (wiki / "Sources" / "Originals" / "raw.pdf").read_text() == "raw"
    assert not (wiki / "Topics").exists()
    assert not (wiki / "Ideas").exists()
    assert not (wiki / "Clippings").exists()
    assert not (wiki / "Notes").exists()
    for relative in (
        "Inbox",
        "Projects",
        "Knowledge",
        "Sources/Originals",
        "Sources/Notes",
        "Archive",
        "_meta",
    ):
        assert (wiki / relative).is_dir()
    journal_lines = [json.loads(line) for line in journal.read_text().splitlines()]
    assert journal_lines[0]["event"] == "migration-start"
    assert journal_lines[-1]["event"] == "migration-complete"
    assert all(item["plan_sha256"] == plan["plan_sha256"] for item in journal_lines)
    assert not lock.exists()

    resumed = migration_module.apply_plan(
        wiki,
        plan_path,
        approved_plan_sha256=plan["plan_sha256"],
        backup_evidence=backup,
        rehearsal_evidence=rehearsal,
        journal_path=journal,
        lock_path=lock,
        confirmed=True,
        resume=True,
    )
    assert resumed["status"] == "already-applied"


def test_apply_stops_after_injected_interruption_and_resumes(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    journal = tmp_path / "journal.jsonl"
    lock = tmp_path / "migration.lock"

    with pytest.raises(RuntimeError, match="injected interruption"):
        migration_module.apply_plan(
            wiki,
            plan_path,
            approved_plan_sha256=plan["plan_sha256"],
            backup_evidence=backup,
            rehearsal_evidence=rehearsal,
            journal_path=journal,
            lock_path=lock,
            confirmed=True,
            interrupt_after=2,
        )
    assert not lock.exists()

    resumed = migration_module.apply_plan(
        wiki,
        plan_path,
        approved_plan_sha256=plan["plan_sha256"],
        backup_evidence=backup,
        rehearsal_evidence=rehearsal,
        journal_path=journal,
        lock_path=lock,
        confirmed=True,
        resume=True,
    )
    assert resumed["status"] == "applied"


def test_resume_refuses_drift_in_remaining_source(migration_module, tmp_path):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    journal = tmp_path / "journal.jsonl"
    lock = tmp_path / "migration.lock"
    with pytest.raises(RuntimeError, match="injected interruption"):
        migration_module.apply_plan(
            wiki,
            plan_path,
            approved_plan_sha256=plan["plan_sha256"],
            backup_evidence=backup,
            rehearsal_evidence=rehearsal,
            journal_path=journal,
            lock_path=lock,
            confirmed=True,
            interrupt_after=1,
        )
    remaining = next(
        operation
        for operation in plan["operations"]
        if operation["kind"] in {"move", "rewrite"}
        and (wiki / operation["source"]).is_file()
    )
    (wiki / remaining["source"]).write_text("drifted", encoding="utf-8")

    with pytest.raises(ValueError, match="remaining source drift"):
        migration_module.apply_plan(
            wiki,
            plan_path,
            approved_plan_sha256=plan["plan_sha256"],
            backup_evidence=backup,
            rehearsal_evidence=rehearsal,
            journal_path=journal,
            lock_path=lock,
            confirmed=True,
            resume=True,
        )


def test_resume_reconciles_exact_post_operation_pre_journal_crash(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    operation = next(
        item for item in plan["operations"] if item["kind"] in {"move", "rewrite"}
    )
    journal = tmp_path / "journal.jsonl"
    start_events = [
        {
            "event": "migration-start",
            "plan_sha256": plan["plan_sha256"],
            "source_tree_sha256": plan["source"]["tree_sha256"],
        },
        {
            "event": "operation-start",
            "plan_sha256": plan["plan_sha256"],
            "source": operation["source"],
            "destination": operation["destination"],
        },
    ]
    journal.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in start_events),
        encoding="utf-8",
    )
    migration_module._apply_operation(wiki, operation)

    result = migration_module.apply_plan(
        wiki,
        plan_path,
        approved_plan_sha256=plan["plan_sha256"],
        backup_evidence=backup,
        rehearsal_evidence=rehearsal,
        journal_path=journal,
        lock_path=tmp_path / "lock",
        confirmed=True,
        resume=True,
    )

    assert result["status"] == "applied"
    events = [json.loads(line) for line in journal.read_text().splitlines()]
    assert any(
        item["event"] == "operation-reconciled"
        and item["source"] == operation["source"]
        for item in events
    )


def test_apply_refuses_existing_destination_and_external_lock(
    migration_module, tmp_path
):
    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path
    )
    journal = tmp_path / "journal.jsonl"
    lock = tmp_path / "migration.lock"
    destination = wiki / "Knowledge" / "Topics" / "alpha.md"
    destination.parent.mkdir(parents=True)
    destination.write_text("race", encoding="utf-8")
    with pytest.raises(ValueError, match="source tree drift|destination exists"):
        migration_module.apply_plan(
            wiki,
            plan_path,
            approved_plan_sha256=plan["plan_sha256"],
            backup_evidence=backup,
            rehearsal_evidence=rehearsal,
            journal_path=journal,
            lock_path=lock,
            confirmed=True,
        )

    wiki, plan, plan_path, backup, rehearsal = _ready_fixture(
        migration_module, tmp_path / "lock-case"
    )
    journal = tmp_path / "lock-case" / "journal.jsonl"
    lock = tmp_path / "lock-case" / "migration.lock"
    lock.write_text("held", encoding="utf-8")
    with pytest.raises(ValueError, match="migration lock"):
        migration_module.apply_plan(
            wiki,
            plan_path,
            approved_plan_sha256=plan["plan_sha256"],
            backup_evidence=backup,
            rehearsal_evidence=rehearsal,
            journal_path=journal,
            lock_path=lock,
            confirmed=True,
        )
