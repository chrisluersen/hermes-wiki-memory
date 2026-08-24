from __future__ import annotations

import time


CASES = [
    ("alpha architecture decision", "Knowledge/alpha.md"),
    ("beta rollout milestone", "Projects/beta.md"),
    ("gamma operating principle", "Knowledge/gamma.md"),
    ("delta customer finding", "Knowledge/delta.md"),
    ("epsilon design constraint", "Knowledge/epsilon.md"),
]


def test_synthetic_lexical_recall_benchmark(wiki_module, tmp_path):
    wiki = tmp_path / "wiki"
    pages = {
        "Knowledge/alpha.md": "# Alpha architecture\nThe alpha architecture decision uses canonical markdown.",
        "Projects/beta.md": "# Beta rollout\nThe beta rollout milestone is integration testing.",
        "Knowledge/gamma.md": "# Gamma\nThe gamma operating principle is local-first ownership.",
        "Knowledge/delta.md": "# Delta\nThe delta customer finding requires transparent provenance.",
        "Knowledge/epsilon.md": "# Epsilon\nThe epsilon design constraint is bounded context.",
        "Sources/Originals/alpha.md": "Raw alpha architecture source material.",
        "Archive/beta.md": "Old superseded beta rollout milestone.",
        "_meta/gamma.md": "Generated gamma operating principle cache.",
        ".hermes/delta.md": "Runtime delta customer finding transcript.",
        "Knowledge/distractor.md": "Architecture rollout principle finding design words only.",
    }
    for relative, text in pages.items():
        path = wiki / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    client = wiki_module.WikiClient(wiki)
    reports = []

    for query, expected in CASES:
        started = time.perf_counter()
        result = client._lexical_prefetch(query, limit=5, max_chars=1000)
        reports.append(
            {
                "query": query,
                "expected": expected,
                "route": "lexical",
                "latency_ms": (time.perf_counter() - started) * 1000,
                "injected_chars": len(result),
                "hit": expected in result,
                "excluded_violation": "_meta/" in result or ".hermes/" in result,
            }
        )

    assert all(report["hit"] for report in reports)
    assert not any(report["excluded_violation"] for report in reports)
    assert all(report["injected_chars"] <= 1055 for report in reports)
    assert all(report["route"] == "lexical" for report in reports)