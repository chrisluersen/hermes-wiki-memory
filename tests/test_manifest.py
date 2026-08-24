from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_routes_through_exclusive_memory_loader():
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 1
    assert manifest["kind"] == "exclusive"
    assert manifest["category"] == "memory"