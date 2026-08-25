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


def test_setup_pins_plugin_install_to_full_release_commit():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    setup = (ROOT / "SETUP.md").read_text(encoding="utf-8")
    import re

    refs = re.findall(r"hermes plugins install[^\n]+--ref\s+(\S+)", setup)
    assert refs == ["72eea8af5e3168b5ef793164b14506807107ba4c"]
    assert re.fullmatch(r"[0-9a-f]{40}", refs[0])
    assert "--ref v0.4.0" not in setup
    assert "published tag's peeled 40-character commit" in readme
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
    ]
    positions = [agents.index(item) for item in read_order]
    assert positions == sorted(positions)

    required = [
        "--ref 72eea8af5e3168b5ef793164b14506807107ba4c",
        "--no-enable",
        "disposable Hermes profile/Wiki first",
        "fresh backup outside destructive profile scope",
        "layout: adopt-existing",
        "Activate **lexical-only** first",
        "memory.wiki.gbrain_source` empty",
        "fixed retrieval acceptance set",
        "remain lexical-only",
        "separate HITL effects",
    ]
    assert all(item.lower() in normalized_agents.lower() for item in required)

    forbidden = [
        "--ref v0.4.0",
        "C:/Users/",
        "production semantic activation is approved",
    ]
    assert not any(item.lower() in normalized_agents.lower() for item in forbidden)


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
