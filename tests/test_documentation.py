from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def normalized(text: str) -> str:
    return " ".join(text.replace("\n>", "\n").split())


def test_release_versions_are_consistent():
    plugin = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    dashboard = json.loads((ROOT / "dashboard" / "manifest.json").read_text(encoding="utf-8"))

    assert plugin["version"] == "0.4.0"
    assert dashboard["version"] == plugin["version"]


def test_readme_describes_current_ownership_and_safety_boundaries():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    normalized_readme = normalized(readme)

    required = [
        "provider never starts, kills, or falls back to a private GBrain process",
        "bounded lexical recall",
        "layout: adopt-existing",
        "forced Hermes secret redaction",
        "GBrain storage is derived",
        "validated production posture remains lexical-only",
        "released commit passed disposable lexical-only activation",
        "tagged and published",
    ]
    assert all(text.lower() in normalized_readme.lower() for text in required)

    forbidden = [
        "persistent `gbrain serve` child",
        "Falls back to one-shot CLI calls",
        "semantic-role mapping is not",
        "capture idempotency/redaction remain",
        "experimental candidate `0.4.0`",
        "Before production enablement or a formal release",
    ]
    assert not any(text.lower() in normalized_readme.lower() for text in forbidden)


def test_release_docs_separate_release_from_production_activation():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "docs" / "RELIABILITY-ROADMAP.md").read_text(encoding="utf-8")
    setup = (ROOT / "SETUP.md").read_text(encoding="utf-8")

    assert "## [0.4.0] - 2026-08-24" in changelog
    assert "disposable lexical-only activation passed" in changelog
    normalized_changelog = normalized(changelog)
    assert "A full private-Wiki semantic rebuild is not a release prerequisite" in normalized_changelog
    assert "production remains lexical-only" in normalized_changelog
    normalized_roadmap = normalized(roadmap)
    assert "PR/CI, disposable installation, canonical recovery, and lexical-only activation evidence are complete" in normalized_roadmap
    assert "merged, tagged, and published" in roadmap
    assert "121 behavioral test functions" not in roadmap
    assert "20–30 meaningful behavioral tests" not in roadmap
    normalized_setup = normalized(setup)
    assert "publication remains separate from any installation's canonical or semantic activation" in normalized_setup
    assert "disposable installation/restart testing" not in setup


def test_operational_status_records_completed_recovery_and_semantic_stop_decision():
    readme = normalized((ROOT / "README.md").read_text(encoding="utf-8"))
    setup = normalized((ROOT / "SETUP.md").read_text(encoding="utf-8"))
    roadmap = normalized((ROOT / "docs" / "RELIABILITY-ROADMAP.md").read_text(encoding="utf-8"))
    design = normalized((ROOT / "docs" / "SENESCHAL-DESIGN-NOTES.md").read_text(encoding="utf-8"))
    corpus = "\n".join([readme, setup, roadmap, design])

    required = [
        "canonical-profile lexical-only activation",
        "representative canonical-Wiki",
        "isolated keyed semantic canary",
        "missed its predeclared production threshold",
        "production posture remains lexical-only",
    ]
    assert all(text.lower() in corpus.lower() for text in required)

    stale = [
        "not yet tagged",
        "restore remains required",
        "restore evidence remains gated",
        "canary remains required",
        "semantic canary remains gated",
        "tag creation, and GitHub Release publication remain",
    ]
    assert not any(text.lower() in corpus.lower() for text in stale)


def test_setup_requires_attested_shared_mcp_and_separate_live_approval():
    setup = (ROOT / "SETUP.md").read_text(encoding="utf-8")

    assert "`GBRAIN_SOURCE` must exactly equal" in setup
    assert "no more than seven seconds" in setup
    assert "separate approval" in setup
    assert "Never test recovery against the active PGLite store" in setup


def test_setup_pins_personal_install_to_migration_capable_merged_commit():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    setup = (ROOT / "SETUP.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    import re

    refs = re.findall(r"hermes plugins install[^\n]+--ref\s+(\S+)", setup)
    assert refs == ["f4a408c3a84bb44ae0adc202dd395587b61087b7"]
    assert re.fullmatch(r"[0-9a-f]{40}", refs[0])
    assert "--ref v0.4.0" not in setup
    assert "migration-capable merged commit" in readme
    assert "f4a408c3a84bb44ae0adc202dd395587b61087b7" in agents
    assert "install the exact tag" not in readme


def test_agents_entrypoint_routes_fresh_agents_through_safe_setup():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    normalized_agents = normalized(agents)

    read_order = [
        "`README.md`",
        "`SETUP.md`",
        "`SECURITY.md`",
        "`docs/WIKI-FOLDER-MAPPING.md`",
        "`docs/RELIABILITY-ROADMAP.md`",
        "`CONTRIBUTING.md`",
    ]
    positions = [agents.index(item) for item in read_order]
    assert positions == sorted(positions)

    required = [
        "--ref f4a408c3a84bb44ae0adc202dd395587b61087b7",
        "--no-enable",
        "disposable Hermes profile/Wiki first",
        "fresh Wiki-only backup outside destructive profile scope",
        "one-time migration to the canonical workbench",
        "python migration_cli.py plan",
        "python migration_cli.py apply",
        "python migration_cli.py verify",
        "python migration_cli.py rollback",
        "exact migration plan hash",
        "activate **lexical-only** with `layout: workbench`",
        "memory.wiki.gbrain_source` empty",
        "fixed retrieval acceptance set",
        "remain lexical-only",
        "separate HITL effects",
        "Python 3.11 test dependencies",
    ]
    assert all(item.lower() in normalized_agents.lower() for item in required)

    forbidden = [
        "--ref v0.4.0",
        "C:/Users/",
        "production semantic activation is approved",
    ]
    assert not any(item.lower() in normalized_agents.lower() for item in forbidden)


def test_setup_explains_map_versus_migrate_without_overwrite_mode():
    setup = normalized((ROOT / "SETUP.md").read_text(encoding="utf-8"))
    required = [
        "Option A — map in place",
        "Option B — migrate once",
        "There is no overwrite mode",
        "destination overwrite is refused",
        "layout: adopt-existing",
        "layout: workbench",
    ]
    assert all(item.lower() in setup.lower() for item in required)


def test_setup_has_copyable_backup_restore_and_evidence_procedure():
    setup = normalized((ROOT / "SETUP.md").read_text(encoding="utf-8"))
    required = [
        "prepare_backup_evidence.py create",
        "prepare_backup_evidence.py verify",
        "python -m zipfile -t",
        "python -m zipfile -l",
        "prepare_backup_evidence.py",
        "backup_sha256",
        "restore_path",
        "retain `.git`",
        "outside the canonical Wiki",
    ]
    assert all(item.lower() in setup.lower() for item in required)


def test_setup_has_copyable_lexical_activation_and_readback_commands():
    setup = normalized((ROOT / "SETUP.md").read_text(encoding="utf-8"))
    required = [
        "hermes profile export",
        "hermes config set --force memory.wiki.layout workbench",
        "hermes config set --force memory.wiki.paths.knowledge Knowledge",
        "hermes config set --force memory.wiki.gbrain_source \"\"",
        "hermes config set memory.provider wiki",
        "hermes plugins enable wiki --no-allow-tool-override",
        "hermes config get memory.wiki --json",
        "hermes memory status",
        "semantic recall remains false",
    ]
    assert all(item.lower() in setup.lower() for item in required)


def test_plans_mark_repository_work_complete_and_personal_work_remaining():
    original = normalized(
        (ROOT / ".hermes" / "plans" / "2026-08-24_211129-canonical-personal-wiki-workbench-migration.md").read_text(encoding="utf-8")
    )
    finish = normalized(
        (ROOT / ".hermes" / "plans" / "2026-08-25_042223-finish-canonical-workbench-migration.md").read_text(encoding="utf-8")
    )
    corpus = original + "\n" + finish
    assert "Repository implementation status: complete" in corpus
    assert "Merged commit: `f4a408c3a84bb44ae0adc202dd395587b61087b7`" in corpus
    assert "Remaining work is Personal-Hermes-only" in corpus


def test_personal_migration_docs_are_single_path_non_destructive_and_gated():
    readme = normalized((ROOT / "README.md").read_text(encoding="utf-8"))
    setup = normalized((ROOT / "SETUP.md").read_text(encoding="utf-8"))
    mapping = normalized(
        (ROOT / "docs" / "WIKI-FOLDER-MAPPING.md").read_text(encoding="utf-8")
    )
    changelog = normalized((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    corpus = "\n".join([readme, setup, mapping, changelog])

    required = [
        "normal plugin startup never migrates",
        "one-time canonical migration",
        "plan → apply → verify → rollback",
        "verified external backup",
        "isolated rehearsal",
        "exact approved plan SHA-256",
        "--decisions",
        "--rehearsal",
        "--rehearsal-result",
        "rehearsal_wiki",
        "journal_path",
        "layout: workbench",
        "Sources/Originals",
        "Sources/Notes",
        "semantic activation remains separate",
        "cleanup remains separate",
    ]
    assert all(item.lower() in corpus.lower() for item in required)
    assert "choose Wiki setup mode" not in corpus
    assert "migration daemon" in corpus


def test_setup_requires_reproducible_rehearsal_not_a_verified_boolean():
    setup = normalized((ROOT / "SETUP.md").read_text(encoding="utf-8"))
    assert "apply --rehearsal" in setup
    assert "independently reruns verification" in setup
    assert "bare `verified: true`" in setup
    assert "8 MiB" in setup
    canonical = setup.split("### Canonical lexical-only activation", 1)[1].split(
        "### One-time Personal Wiki migration", 1
    )[0]
    assert "after successful migration verification" in canonical.lower()
    assert "layout: workbench" in canonical
    assert "adopt-existing" not in canonical


def test_setup_contains_copyable_personal_hermes_migration_prompt():
    setup = normalized((ROOT / "SETUP.md").read_text(encoding="utf-8"))
    required = [
        "## Personal Hermes migration prompt",
        "Inventory my Personal Wiki read-only",
        "create and verify an external backup",
        "isolated rehearsal restore",
        "Stop for my approval before changing the canonical Wiki",
        "set `layout: workbench`",
        "semantic activation and cleanup separately gated",
        "Do not build a daemon",
    ]
    assert all(item in setup for item in required)


def test_setup_bootstraps_clean_python_test_dependencies():
    setup = normalized((ROOT / "SETUP.md").read_text(encoding="utf-8"))
    assert "Source validation requires Python 3.11" in setup
    assert "python -m pip install fastapi pyyaml pytest" in setup
    assert setup.index("python -m pip install fastapi pyyaml pytest") < setup.index(
        "python tests/run.py"
    )


def test_relative_markdown_links_resolve():
    for document in [ROOT / "README.md", ROOT / "SETUP.md"]:
        text = document.read_text(encoding="utf-8")
        import re

        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = document.parent / target.split("#", 1)[0]
            assert path.exists(), f"broken link in {document.name}: {target}"


def test_community_files_exist_and_yaml_templates_parse():
    required = [
        ROOT / "SECURITY.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md",
        ROOT / ".github" / "dependabot.yml",
        ROOT / ".github" / "ISSUE_TEMPLATE" / "bug.yml",
        ROOT / ".github" / "ISSUE_TEMPLATE" / "feature.yml",
        ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml",
    ]
    assert all(path.exists() for path in required)
    for path in required:
        if path.suffix == ".yml":
            assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None


def test_security_guidance_prohibits_public_secret_disclosure():
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

    assert "Do not include credentials" in security
    assert "public issue" in security
    assert "Report a vulnerability" in security
