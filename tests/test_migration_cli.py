from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def _fixture(repo: Path, tmp_path: Path):
    wiki = tmp_path / "wiki"
    for relative, content in {
        "Inbox/capture.md": "capture",
        "Projects/project.md": "project",
        "Topics/alpha.md": "alpha",
        "Ideas/beta.md": "[[Topics/alpha]]",
        "Clippings/raw.pdf": "raw",
        "Notes/source.md": "source",
    }.items():
        path = wiki / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    plan_path = tmp_path / "plan.json"
    report_path = tmp_path / "plan.md"
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
    assert result.returncode == 0, result.stderr
    plan = json.loads(plan_path.read_text())
    backup_archive = tmp_path / "backup.tar.gz"
    backup_archive.write_bytes(b"backup")
    restore = tmp_path / "restore"
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
        )
    )
    rehearsal_wiki = tmp_path / "rehearsal-wiki"
    shutil.copytree(wiki, rehearsal_wiki)
    rehearsal_journal = tmp_path / "rehearsal-journal.jsonl"
    rehearsal = tmp_path / "rehearsal.json"
    rehearsed = subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "apply",
            "--wiki",
            str(rehearsal_wiki),
            "--plan",
            str(plan_path),
            "--approved-plan-sha256",
            plan["plan_sha256"],
            "--journal",
            str(rehearsal_journal),
            "--lock",
            str(tmp_path / "rehearsal.lock"),
            "--rehearsal",
            "--rehearsal-result",
            str(rehearsal),
        ],
        capture_output=True,
        text=True,
    )
    assert rehearsed.returncode == 0, rehearsed.stderr
    return wiki, plan, plan_path, backup, rehearsal, restore


def test_apply_and_verify_cli_require_flags_and_emit_external_results(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    wiki, plan, plan_path, backup, rehearsal, _ = _fixture(repo, tmp_path)
    journal = tmp_path / "journal.jsonl"
    lock = tmp_path / "migration.lock"

    missing_flag = subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "apply",
            "--wiki",
            str(wiki),
            "--plan",
            str(plan_path),
            "--approved-plan-sha256",
            plan["plan_sha256"],
            "--backup-evidence",
            str(backup),
            "--rehearsal-evidence",
            str(rehearsal),
            "--journal",
            str(journal),
            "--lock",
            str(lock),
        ],
        capture_output=True,
        text=True,
    )
    assert missing_flag.returncode == 2

    applied = subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "apply",
            "--wiki",
            str(wiki),
            "--plan",
            str(plan_path),
            "--approved-plan-sha256",
            plan["plan_sha256"],
            "--backup-evidence",
            str(backup),
            "--rehearsal-evidence",
            str(rehearsal),
            "--journal",
            str(journal),
            "--lock",
            str(lock),
            "--apply",
        ],
        capture_output=True,
        text=True,
    )
    assert applied.returncode == 0, applied.stderr

    result_path = tmp_path / "verify.json"
    report_path = tmp_path / "verify.md"
    verified = subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "verify",
            "--wiki",
            str(wiki),
            "--plan",
            str(plan_path),
            "--journal",
            str(journal),
            "--result-out",
            str(result_path),
            "--report-out",
            str(report_path),
            "--capture-probe",
        ],
        capture_output=True,
        text=True,
    )
    assert verified.returncode == 0, verified.stderr
    result = json.loads(result_path.read_text())
    assert result["status"] == "verified"
    assert result["plan_sha256"] == plan["plan_sha256"]
    assert "# Wiki Workbench Migration Verification" in report_path.read_text()


def test_plan_cli_accepts_external_reviewed_decisions(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    wiki = tmp_path / "wiki"
    page = wiki / "Mystery" / "page.md"
    page.parent.mkdir(parents=True)
    page.write_text("mystery", encoding="utf-8")
    decisions = tmp_path / "decisions.json"
    decisions.write_text(
        json.dumps(
            {
                "Mystery": {
                    "action": "map",
                    "destination": "Knowledge/Mystery",
                }
            }
        ),
        encoding="utf-8",
    )
    plan_path = tmp_path / "plan.json"
    report_path = tmp_path / "plan.md"

    result = subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "plan",
            "--wiki",
            str(wiki),
            "--decisions",
            str(decisions),
            "--json-out",
            str(plan_path),
            "--report-out",
            str(report_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan["decisions"]["Mystery"]["action"] == "map"
    assert any(
        item.get("source") == "Mystery/page.md"
        and item.get("destination") == "Knowledge/Mystery/page.md"
        for item in plan["operations"]
    )


def test_apply_rehearsal_emits_independently_verifiable_evidence(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    wiki, plan, plan_path, _, _, restore = _fixture(repo, tmp_path)
    rehearsal_journal = tmp_path / "second-rehearsal-journal.jsonl"
    rehearsal_result = tmp_path / "rehearsal-result.json"

    rehearsed = subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "apply",
            "--wiki",
            str(restore),
            "--plan",
            str(plan_path),
            "--approved-plan-sha256",
            plan["plan_sha256"],
            "--journal",
            str(rehearsal_journal),
            "--lock",
            str(tmp_path / "rehearsal.lock"),
            "--rehearsal",
            "--rehearsal-result",
            str(rehearsal_result),
        ],
        capture_output=True,
        text=True,
    )

    assert rehearsed.returncode == 0, rehearsed.stderr
    evidence = json.loads(rehearsal_result.read_text(encoding="utf-8"))
    assert evidence["verified"] is True
    assert evidence["plan_sha256"] == plan["plan_sha256"]
    assert evidence["source_tree_sha256"] == plan["source"]["tree_sha256"]
    assert Path(evidence["rehearsal_wiki"]).resolve() == restore.resolve()
    assert Path(evidence["journal_path"]).resolve() == rehearsal_journal.resolve()
    assert not (wiki / "Knowledge").exists()


def test_rollback_cli_requires_flag_and_retains_migrated_tree(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    wiki, plan, plan_path, backup, rehearsal, restore = _fixture(repo, tmp_path)
    journal = tmp_path / "journal.jsonl"
    subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "apply",
            "--wiki",
            str(wiki),
            "--plan",
            str(plan_path),
            "--approved-plan-sha256",
            plan["plan_sha256"],
            "--backup-evidence",
            str(backup),
            "--rehearsal-evidence",
            str(rehearsal),
            "--journal",
            str(journal),
            "--lock",
            str(tmp_path / "lock"),
            "--apply",
        ],
        check=True,
    )
    retained = tmp_path / "retained-migrated"

    missing_flag = subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "rollback",
            "--wiki",
            str(wiki),
            "--backup-evidence",
            str(backup),
            "--expected-source-tree-sha256",
            plan["source"]["tree_sha256"],
            "--retained-migrated-tree",
            str(retained),
        ],
        capture_output=True,
        text=True,
    )
    assert missing_flag.returncode == 2

    rolled_back = subprocess.run(
        [
            sys.executable,
            str(repo / "migration_cli.py"),
            "rollback",
            "--wiki",
            str(wiki),
            "--backup-evidence",
            str(backup),
            "--expected-source-tree-sha256",
            plan["source"]["tree_sha256"],
            "--retained-migrated-tree",
            str(retained),
            "--rollback",
        ],
        capture_output=True,
        text=True,
    )
    assert rolled_back.returncode == 0, rolled_back.stderr
    assert retained.is_dir()
    assert restore.is_dir()
    assert (wiki / "Topics" / "alpha.md").is_file()
