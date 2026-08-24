from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_release_versions_are_consistent():
    plugin = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    dashboard = json.loads((ROOT / "dashboard" / "manifest.json").read_text(encoding="utf-8"))

    assert plugin["version"] == "0.4.0"
    assert dashboard["version"] == plugin["version"]


def test_readme_describes_current_ownership_and_safety_boundaries():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    required = [
        "provider never starts, kills, or falls back to a private GBrain process",
        "bounded lexical recall",
        "layout: adopt-existing",
        "forced Hermes secret redaction",
        "GBrain storage is derived",
        "not released or production-enabled",
    ]
    assert all(text in readme for text in required)

    forbidden = [
        "persistent `gbrain serve` child",
        "Falls back to one-shot CLI calls",
        "semantic-role mapping is not",
        "capture idempotency/redaction remain",
    ]
    assert not any(text in readme for text in forbidden)


def test_setup_requires_attested_shared_mcp_and_separate_live_approval():
    setup = (ROOT / "SETUP.md").read_text(encoding="utf-8")

    assert "`GBRAIN_SOURCE` must exactly equal" in setup
    assert "no more than seven seconds" in setup
    assert "separate approval" in setup
    assert "Never test recovery against the active PGLite store" in setup


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
