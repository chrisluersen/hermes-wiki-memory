"""Create and independently verify Wiki-only migration backup evidence.

This helper is explicit and operator-invoked. It never runs during provider
startup and never writes inside the canonical Wiki.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from migration import STREAM_CHUNK_BYTES, inventory_tree

SCHEMA_VERSION = 1


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(STREAM_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _external_path(wiki: Path, path: Path, label: str) -> Path:
    resolved = Path(path).resolve(strict=False)
    try:
        resolved.relative_to(wiki.resolve())
    except ValueError:
        return resolved
    raise ValueError(f"{label} must be outside the canonical Wiki")


def _require_new_path(path: Path, label: str) -> None:
    if path.exists():
        raise ValueError(f"{label} already exists")
    if not path.parent.is_dir():
        raise ValueError(f"{label} parent must already exist")


def _write_json_new(path: Path, value: dict[str, Any]) -> None:
    _require_new_path(path, "result")
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".partial", dir=path.parent
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp, path)
    except FileExistsError as exc:
        raise ValueError("result already exists") from exc
    finally:
        temp.unlink(missing_ok=True)


def _validate_backupable_inventory(inventory: dict[str, Any]) -> None:
    blocked = [
        entry["path"]
        for entry in inventory["entries"]
        if entry["kind"] in {"symlink", "reparse-point", "unsupported"}
        or entry["flags"]
    ]
    if blocked:
        raise ValueError(
            "backup source contains unsupported objects or paths: "
            + ", ".join(blocked[:10])
        )


def create_backup(wiki: Path, archive: Path, result_out: Path) -> dict[str, Any]:
    wiki = Path(wiki).resolve()
    if not wiki.is_dir():
        raise ValueError("Wiki root must be an existing directory")
    archive = _external_path(wiki, Path(archive), "backup archive")
    result_out = _external_path(wiki, Path(result_out), "creation result")
    _require_new_path(archive, "backup archive")
    _require_new_path(result_out, "creation result")

    before = inventory_tree(wiki)
    _validate_backupable_inventory(before)
    root_name = wiki.name
    if not root_name or root_name in {".", ".."} or "/" in root_name or "\\" in root_name:
        raise ValueError("Wiki root must have a portable directory name")

    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{archive.name}.", suffix=".partial", dir=archive.parent
    )
    os.close(descriptor)
    temp = Path(temp_name)
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            bundle.write(wiki, arcname=f"{root_name}/")
            for entry in before["entries"]:
                source = wiki / entry["path"]
                arcname = f"{root_name}/{entry['path']}"
                if entry["kind"] == "directory":
                    arcname += "/"
                bundle.write(source, arcname=arcname)
        after = inventory_tree(wiki)
        if after["tree_sha256"] != before["tree_sha256"]:
            raise ValueError("Wiki source changed while backup was being created")
        try:
            os.link(temp, archive)
        except FileExistsError as exc:
            raise ValueError("backup archive already exists") from exc
    finally:
        temp.unlink(missing_ok=True)

    result = {
        "schema_version": SCHEMA_VERSION,
        "source_tree_sha256": before["tree_sha256"],
        "root_name": root_name,
        "backup_path": str(archive),
        "backup_sha256": _sha256_file(archive),
    }
    _write_json_new(result_out, result)
    return result


def _load_creation_result(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid backup creation result") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid backup creation result")
    source_hash = str(value.get("source_tree_sha256", ""))
    archive_hash = str(value.get("backup_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash) or not re.fullmatch(
        r"[0-9a-f]{64}", archive_hash
    ):
        raise ValueError("invalid backup creation hashes")
    return value


def _safe_member_path(name: str, root_name: str) -> tuple[Path, bool]:
    if not name or "\\" in name:
        raise ValueError("backup archive contains an unsafe member path")
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("backup archive contains an unsafe member path")
    if not pure.parts or pure.parts[0] != root_name:
        raise ValueError("backup archive root does not match creation evidence")
    relative_parts = pure.parts[1:]
    if not relative_parts:
        return Path(), True
    return Path(*relative_parts), name.endswith("/")


def _extract_verified_archive(
    archive: Path, restore: Path, root_name: str, expected_tree_hash: str
) -> None:
    staging = Path(
        tempfile.mkdtemp(prefix=f".{restore.name}.", suffix=".partial", dir=restore.parent)
    )
    staged_root = staging / root_name
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(archive) as bundle:
            bad_member = bundle.testzip()
            if bad_member is not None:
                raise ValueError(f"backup archive CRC failure: {bad_member}")
            for info in bundle.infolist():
                relative, directory = _safe_member_path(info.filename, root_name)
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise ValueError("backup archive contains a symlink")
                identity = unicodedata.normalize(
                    "NFC", relative.as_posix()
                ).casefold()
                if identity in seen and relative != Path():
                    raise ValueError("backup archive contains duplicate member paths")
                seen.add(identity)
                target = staged_root / relative
                resolved = target.resolve(strict=False)
                try:
                    resolved.relative_to(staged_root.resolve(strict=False))
                except ValueError as exc:
                    raise ValueError("backup archive member escapes restore root") from exc
                if directory or info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with bundle.open(info) as source, os.fdopen(descriptor, "wb") as output:
                    shutil.copyfileobj(source, output, STREAM_CHUNK_BYTES)
                    output.flush()
                    os.fsync(output.fileno())
        if not staged_root.is_dir():
            raise ValueError("backup archive did not restore a Wiki root")
        restored = inventory_tree(staged_root)
        if restored["tree_sha256"] != expected_tree_hash:
            raise ValueError("restored Wiki tree does not match creation evidence")
        try:
            restore.mkdir()
        except FileExistsError as exc:
            raise ValueError("backup restore already exists") from exc
        try:
            for child in staged_root.iterdir():
                os.replace(child, restore / child.name)
        except BaseException as exc:
            raise ValueError(
                "backup restore publication failed; partial restore retained"
            ) from exc
        if inventory_tree(restore)["tree_sha256"] != expected_tree_hash:
            raise ValueError("published backup restore tree does not match evidence")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def verify_backup(
    wiki: Path,
    creation_result: Path,
    restore: Path,
    evidence_out: Path,
) -> dict[str, Any]:
    wiki = Path(wiki).resolve()
    if not wiki.is_dir():
        raise ValueError("Wiki root must be an existing directory")
    creation_result = _external_path(
        wiki, Path(creation_result), "backup creation result"
    )
    restore = _external_path(wiki, Path(restore), "backup restore")
    evidence_out = _external_path(wiki, Path(evidence_out), "backup evidence")
    _require_new_path(restore, "backup restore")
    _require_new_path(evidence_out, "backup evidence")

    creation = _load_creation_result(creation_result)
    source_hash = str(creation["source_tree_sha256"])
    if inventory_tree(wiki)["tree_sha256"] != source_hash:
        raise ValueError("Wiki source changed since backup creation")
    archive = _external_path(
        wiki, Path(str(creation.get("backup_path", ""))), "backup archive"
    )
    if not archive.is_file() or _sha256_file(archive) != creation["backup_sha256"]:
        raise ValueError("backup archive hash does not match creation evidence")
    root_name = str(creation.get("root_name", ""))
    if not root_name:
        raise ValueError("backup creation result has no root name")

    _extract_verified_archive(archive, restore, root_name, source_hash)
    evidence = {
        "verified": True,
        "source_tree_sha256": source_hash,
        "backup_path": str(archive),
        "backup_sha256": creation["backup_sha256"],
        "restore_path": str(restore),
    }
    _write_json_new(evidence_out, evidence)
    return evidence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and verify Wiki-only backup evidence for migration."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="create a new external Wiki ZIP")
    create.add_argument("--wiki", required=True)
    create.add_argument("--archive", required=True)
    create.add_argument("--result-out", required=True)

    verify = subparsers.add_parser(
        "verify", help="restore and verify a previously created Wiki ZIP"
    )
    verify.add_argument("--wiki", required=True)
    verify.add_argument("--creation-result", required=True)
    verify.add_argument("--restore", required=True)
    verify.add_argument("--evidence-out", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            result = create_backup(
                Path(args.wiki), Path(args.archive), Path(args.result_out)
            )
        else:
            result = verify_backup(
                Path(args.wiki),
                Path(args.creation_result),
                Path(args.restore),
                Path(args.evidence_out),
            )
    except ValueError as exc:
        print(f"error: {exc}", file=__import__("sys").stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
