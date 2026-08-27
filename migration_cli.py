"""Explicit one-time Wiki workbench migration CLI.

This command is never invoked by normal plugin startup.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from migration import (
    apply_plan,
    build_plan,
    rollback_from_verified_restore,
    verify_migration,
)


def _outside(root: Path, candidate: Path) -> bool:
    root = root.resolve()
    candidate = candidate.resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError:
        return True
    return False


def _write_new(path: Path, content: str) -> None:
    path = path.resolve(strict=False)
    if path.exists():
        raise ValueError(f"refusing existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _plan_report(plan: dict) -> str:
    operations = plan.get("operations", [])
    blockers = plan.get("blockers", [])
    lines = [
        "# Wiki Workbench Migration Plan",
        "",
        f"- Status: **{plan['status']}**",
        f"- Plan SHA-256: `{plan['plan_sha256']}`",
        f"- Source tree SHA-256: `{plan['source']['tree_sha256']}`",
        f"- Inventory objects: {len(plan.get('inventory', []))}",
        f"- Planned operations: {len(operations)}",
        f"- Blockers: {len(blockers)}",
        "",
        "## Planned operations",
        "",
    ]
    if operations:
        lines.extend(
            f"- `{item['kind']}`: `{item['source']}` → `{item['destination']}`"
            for item in operations
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Blockers", ""])
    if blockers:
        lines.extend(
            f"- `{item['kind']}` at `{item['path']}`: {item['message']}"
            for item in blockers
        )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Final configuration",
            "",
            "```yaml",
            "layout: workbench",
            "capture: Inbox",
            "projects: Projects",
            "knowledge: Knowledge",
            "originals: Sources/Originals",
            "processed: Sources/Notes",
            "archive: Archive",
            "gbrain_source: ''",
            "```",
            "",
            "Apply is not authorized by this plan output. Backup, isolated rehearsal, exact plan-hash approval, and a separate apply confirmation are required.",
            "",
        ]
    )
    return "\n".join(lines)


def cmd_plan(args: argparse.Namespace) -> int:
    wiki = Path(args.wiki).resolve()
    json_out = Path(args.json_out)
    report_out = Path(args.report_out)
    if not _outside(wiki, json_out) or not _outside(wiki, report_out):
        raise ValueError("plan outputs must be outside the canonical Wiki")
    if json_out.resolve(strict=False) == report_out.resolve(strict=False):
        raise ValueError("JSON and report outputs must differ")
    if json_out.exists() or report_out.exists():
        raise ValueError("refusing existing output")
    decisions = None
    if args.decisions:
        decisions_path = Path(args.decisions)
        if not _outside(wiki, decisions_path):
            raise ValueError("decisions must be outside the canonical Wiki")
        decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    plan = build_plan(wiki, decisions=decisions)
    _write_new(json_out, json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_new(report_out, _plan_report(plan))
    print(plan["plan_sha256"])
    return 0 if plan["status"] == "ready" else 3


def cmd_apply(args: argparse.Namespace) -> int:
    rehearsal_mode = bool(args.rehearsal)
    if rehearsal_mode:
        if not args.rehearsal_result:
            raise ValueError("--rehearsal-result is required with --rehearsal")
        rehearsal_result = Path(args.rehearsal_result)
        if not _outside(Path(args.wiki), rehearsal_result):
            raise ValueError("rehearsal result must be outside the rehearsal Wiki")
        if rehearsal_result.exists():
            raise ValueError("refusing existing rehearsal result")
    result = apply_plan(
        Path(args.wiki),
        Path(args.plan),
        approved_plan_sha256=args.approved_plan_sha256,
        backup_evidence=Path(args.backup_evidence) if args.backup_evidence else None,
        rehearsal_evidence=(
            Path(args.rehearsal_evidence) if args.rehearsal_evidence else None
        ),
        journal_path=Path(args.journal),
        lock_path=Path(args.lock),
        confirmed=bool(args.apply or rehearsal_mode),
        resume=bool(args.resume),
        rehearsal=rehearsal_mode,
    )
    if rehearsal_mode:
        source_tree = None
        if args.backup_evidence:
            try:
                from migration import _load_json, _validate_backup_evidence

                plan = _load_json(Path(args.plan), "migration plan")
                _, restore = _validate_backup_evidence(
                    Path(args.wiki),
                    Path(args.backup_evidence),
                    plan["source"]["tree_sha256"],
                )
                source_tree = restore
            except (OSError, ValueError, KeyError):
                source_tree = None
        verification = verify_migration(
            Path(args.wiki),
            Path(args.plan),
            journal_path=Path(args.journal),
            disposable_capture_probe=True,
            source_tree=source_tree,
        )
        if verification["status"] != "verified":
            raise ValueError("rehearsal verification failed")
        _write_new(
            rehearsal_result,
            json.dumps(
                {
                    "verified": True,
                    "plan_sha256": verification["plan_sha256"],
                    "source_tree_sha256": verification["source_tree_sha256"],
                    "final_tree_sha256": verification["final_tree_sha256"],
                    "rehearsal_wiki": str(Path(args.wiki).resolve()),
                    "journal_path": str(Path(args.journal).resolve()),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    print(json.dumps(result, sort_keys=True))
    return 0


def _verification_report(result: dict) -> str:
    return "\n".join(
        [
            "# Wiki Workbench Migration Verification",
            "",
            f"- Status: **{result['status']}**",
            f"- Plan SHA-256: `{result['plan_sha256']}`",
            f"- Final tree SHA-256: `{result['final_tree_sha256']}`",
            f"- Accounted files: {result['accounted_files']}",
            f"- Hashes valid: {result['hashes_ok']}",
            f"- Links valid: {result['links_ok']}",
            f"- Canonical directories valid: {result['directories_ok']}",
            f"- Legacy roots absent: {result['legacy_absent']}",
            f"- Capture ready: {result['capture_ready']}",
            f"- Semantic active: {result['semantic_active']}",
            "",
            "Semantic activation and cleanup remain separately gated.",
            "",
        ]
    )


def cmd_verify(args: argparse.Namespace) -> int:
    wiki = Path(args.wiki).resolve()
    result_out = Path(args.result_out)
    report_out = Path(args.report_out)
    if not _outside(wiki, result_out) or not _outside(wiki, report_out):
        raise ValueError("verification outputs must be outside the canonical Wiki")
    if result_out.exists() or report_out.exists():
        raise ValueError("refusing existing output")
    result = verify_migration(
        wiki,
        Path(args.plan),
        journal_path=Path(args.journal),
        disposable_capture_probe=bool(args.capture_probe),
        backup_evidence=(Path(args.backup_evidence) if args.backup_evidence else None),
    )
    _write_new(
        result_out,
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _write_new(report_out, _verification_report(result))
    print(result["plan_sha256"])
    return 0 if result["status"] == "verified" else 4


def cmd_rollback(args: argparse.Namespace) -> int:
    result = rollback_from_verified_restore(
        Path(args.wiki),
        Path(args.backup_evidence),
        expected_source_tree_sha256=args.expected_source_tree_sha256,
        retained_migrated_tree=Path(args.retained_migrated_tree),
        confirmed=bool(args.rollback),
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="build a read-only migration plan")
    plan.add_argument("--wiki", required=True)
    plan.add_argument("--decisions")
    plan.add_argument("--json-out", required=True)
    plan.add_argument("--report-out", required=True)
    plan.set_defaults(handler=cmd_plan)

    apply = subparsers.add_parser("apply", help="apply one exact approved plan")
    apply.add_argument("--wiki", required=True)
    apply.add_argument("--plan", required=True)
    apply.add_argument("--approved-plan-sha256", required=True)
    apply.add_argument("--backup-evidence")
    apply.add_argument("--rehearsal-evidence")
    apply.add_argument("--journal", required=True)
    apply.add_argument("--lock", required=True)
    apply.add_argument("--apply", action="store_true")
    apply.add_argument("--rehearsal", action="store_true")
    apply.add_argument("--rehearsal-result")
    apply.add_argument("--resume", action="store_true")
    apply.set_defaults(handler=cmd_apply)

    verify = subparsers.add_parser("verify", help="verify a completed migration")
    verify.add_argument("--wiki", required=True)
    verify.add_argument("--plan", required=True)
    verify.add_argument("--journal", required=True)
    verify.add_argument("--result-out", required=True)
    verify.add_argument("--report-out", required=True)
    verify.add_argument("--capture-probe", action="store_true")
    verify.add_argument("--backup-evidence")
    verify.set_defaults(handler=cmd_verify)

    rollback = subparsers.add_parser(
        "rollback", help="restore a verified pre-migration tree"
    )
    rollback.add_argument("--wiki", required=True)
    rollback.add_argument("--backup-evidence", required=True)
    rollback.add_argument("--expected-source-tree-sha256", required=True)
    rollback.add_argument("--retained-migrated-tree", required=True)
    rollback.add_argument("--rollback", action="store_true")
    rollback.set_defaults(handler=cmd_rollback)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
