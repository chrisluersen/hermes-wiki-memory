"""One-time canonical Wiki workbench migration contracts and operations.

Normal provider startup never imports or calls this module. Migration is an
explicit, separately approved operator workflow.
"""

from __future__ import annotations

import hashlib
import difflib
import json
import os
import posixpath
import re
import shutil
import stat
import tempfile
import unicodedata
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

PLAN_SCHEMA_VERSION = 1
RESULT_SCHEMA_VERSION = 1
STREAM_CHUNK_BYTES = 1024 * 1024
MAX_REWRITE_MARKDOWN_BYTES = 8 * 1024 * 1024
_IGNORED_PLAN_HASH_FIELDS = {"generated_at", "plan_sha256"}
_CANONICAL_ROOTS = {
    "Inbox",
    "Projects",
    "Knowledge",
    "Sources",
    "Archive",
    "_meta",
    ".obsidian",
    "Attachments",
}
_LEGACY_PREFIXES = {
    "Topics": "Knowledge/Topics",
    "Ideas": "Knowledge/Ideas",
    "Clippings": "Sources/Originals",
    "Notes": "Sources/Notes",
}
_WORKBENCH_DIRECTORIES = (
    "Inbox",
    "Projects",
    "Knowledge",
    "Sources",
    "Sources/Originals",
    "Sources/Notes",
    "Archive",
    "_meta",
)
_RETAINED_ROOT_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "HERMES.md",
    ".hermes.md",
    "SCHEMA.md",
    "index.md",
    "log.md",
    "README.md",
    "LICENSE",
    ".gitignore",
}


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _canonicalize(item)
            for key, item in sorted(value.items())
            if key not in _IGNORED_PLAN_HASH_FIELDS
        }
    if isinstance(value, list):
        items = [_canonicalize(item) for item in value]
        if all(isinstance(item, dict) for item in items):
            return sorted(
                items,
                key=lambda item: json.dumps(
                    item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ),
            )
        return items
    return value


def canonical_plan_bytes(plan: dict[str, Any]) -> bytes:
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError(f"unsupported migration plan schema: {plan.get('schema_version')}")
    canonical = _canonicalize(deepcopy(plan))
    return json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def plan_sha256(plan: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_plan_bytes(plan)).hexdigest()


def _validate_relative_path(value: Any, label: str) -> str:
    text = str(value or "").replace("\\", "/").strip("/")
    windows = PureWindowsPath(text)
    if (
        not text
        or Path(text).is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in Path(text).parts
        or any(part in {"", ".", ".."} for part in text.split("/"))
        or any(char in text for char in ':"|?*\x00')
    ):
        raise ValueError(f"{label} must be a safe relative path")
    return text


def validate_plan(plan: dict[str, Any]) -> None:
    if not isinstance(plan, dict):
        raise ValueError("migration plan must be a mapping")
    canonical_hash = plan_sha256(plan)
    if plan.get("plan_sha256") != canonical_hash:
        raise ValueError("stored plan hash does not match canonical plan")
    if plan.get("final_config", {}).get("layout") != "workbench":
        raise ValueError("final configuration must use workbench layout")
    if str(plan.get("final_config", {}).get("gbrain_source", "")):
        raise ValueError("semantic activation is not allowed in a migration plan")
    operations = plan.get("operations")
    if not isinstance(operations, list):
        raise ValueError("operations must be a list")
    seen: set[tuple[str, str, str]] = set()
    destinations: set[str] = set()
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError("migration operation must be a mapping")
        kind = operation.get("kind")
        if kind not in {"mkdir", "move", "rewrite"}:
            raise ValueError(f"unsupported operation kind: {kind}")
        source = _validate_relative_path(operation.get("source"), "operation source")
        destination = _validate_relative_path(
            operation.get("destination"), "operation destination"
        )
        identity = (str(kind), source, destination)
        if identity in seen:
            raise ValueError("duplicate operation")
        seen.add(identity)
        if kind != "mkdir":
            folded = unicodedata.normalize("NFC", destination).casefold()
            if folded in destinations:
                raise ValueError("duplicate operation destination")
            destinations.add(folded)
            digest = str(operation.get("preimage_sha256", ""))
            if not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("operation preimage hash must be SHA-256")
            if kind == "rewrite":
                postimage = str(operation.get("postimage_sha256", ""))
                if not re.fullmatch(r"[0-9a-f]{64}", postimage):
                    raise ValueError("rewrite postimage hash must be SHA-256")


def _entry_kind(mode: int, *, file_attributes: int = 0) -> str:
    if stat.S_ISLNK(mode):
        return "symlink"
    if file_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400):
        return "reparse-point"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    return "unsupported"


def _entry_digest(path: Path, kind: str) -> tuple[int, str]:
    if kind == "file":
        return _stream_file_digest(path)
    if kind == "symlink":
        target = os.readlink(path)
        data = os.fsencode(target)
        return len(data), hashlib.sha256(data).hexdigest()
    return 0, ""


def _stream_file_digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(STREAM_CHUNK_BYTES), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _file_sha256(path: Path) -> str:
    return _stream_file_digest(path)[1]


def _path_flags(relative: str) -> list[str]:
    flags: list[str] = []
    windows = PureWindowsPath(relative)
    for part in windows.parts:
        stem = part.rstrip(" .").split(".", 1)[0].casefold()
        if stem in {"con", "prn", "aux", "nul"} or (
            len(stem) == 4 and stem[:3] in {"com", "lpt"} and stem[3].isdigit()
        ):
            flags.append("windows-reserved-name")
        if ":" in part:
            flags.append("ads-like-name")
    if unicodedata.normalize("NFC", relative) != relative:
        flags.append("non-nfc-path")
    return sorted(set(flags))


def inventory_tree(root: Path) -> dict[str, Any]:
    """Inventory a Wiki without following links or mutating source state."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("Wiki root must be an existing directory")

    entries: list[dict[str, Any]] = []
    stack = [root]
    while stack:
        current = stack.pop()
        children = sorted(os.scandir(current), key=lambda item: item.name)
        for child in children:
            path = Path(child.path)
            relative = path.relative_to(root).as_posix()
            info = child.stat(follow_symlinks=False)
            kind = _entry_kind(
                info.st_mode,
                file_attributes=int(getattr(info, "st_file_attributes", 0)),
            )
            size, digest = _entry_digest(path, kind)
            entry: dict[str, Any] = {
                "path": relative,
                "kind": kind,
                "size": size,
                "sha256": digest,
                "flags": _path_flags(relative),
            }
            if kind == "symlink":
                entry["target"] = os.readlink(path)
            entries.append(entry)
            if kind == "directory":
                stack.append(path)

    entries.sort(key=lambda entry: entry["path"])
    casefolded: dict[str, list[str]] = {}
    normalized: dict[str, list[str]] = {}
    for entry in entries:
        casefolded.setdefault(entry["path"].casefold(), []).append(entry["path"])
        normalized.setdefault(unicodedata.normalize("NFC", entry["path"]), []).append(
            entry["path"]
        )
    collisions = {
        "casefold": sorted(values for values in casefolded.values() if len(values) > 1),
        "unicode_nfc": sorted(values for values in normalized.values() if len(values) > 1),
    }
    digest = hashlib.sha256(
        json.dumps(
            entries,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "root_hint": root.name,
        "entries": entries,
        "collisions": collisions,
        "tree_sha256": digest,
    }


def _target_path(
    relative: str, decisions: dict[str, dict[str, str]] | None = None
) -> tuple[str, str]:
    parts = relative.split("/")
    root = parts[0]
    if len(parts) == 1 and root in _RETAINED_ROOT_FILES:
        return relative, "retain"
    if root in _LEGACY_PREFIXES:
        suffix = "/".join(parts[1:])
        return f"{_LEGACY_PREFIXES[root]}/{suffix}".rstrip("/"), "move"
    if root in _CANONICAL_ROOTS:
        return relative, "retain"
    decision = (decisions or {}).get(root)
    if decision:
        action = decision["action"]
        if action == "retain":
            return relative, "retain"
        if action == "map":
            suffix = "/".join(parts[1:])
            return f"{decision['destination']}/{suffix}".rstrip("/"), "move"
    return relative, "review-required"


def _normalize_decisions(
    unknown_roots: set[str], decisions: dict[str, Any] | None
) -> dict[str, dict[str, str]]:
    if decisions is None:
        return {}
    if not isinstance(decisions, dict):
        raise ValueError("migration decisions must be a mapping")
    normalized: dict[str, dict[str, str]] = {}
    for raw_root, raw_decision in sorted(decisions.items()):
        root = _validate_relative_path(raw_root, "decision root")
        if "/" in root or root not in unknown_roots:
            raise ValueError(f"unknown decision root: {root}")
        if not isinstance(raw_decision, dict):
            raise ValueError(f"decision for {root} must be a mapping")
        action = str(raw_decision.get("action", ""))
        allowed_keys = {"action", "destination"} if action == "map" else {"action"}
        if action not in {"retain", "map", "review-required"}:
            raise ValueError(f"unsupported decision action for {root}")
        if set(raw_decision) - allowed_keys:
            raise ValueError(f"unsupported decision fields for {root}")
        item = {"action": action}
        if action == "map":
            item["destination"] = _validate_relative_path(
                raw_decision.get("destination"), "decision destination"
            )
        normalized[root] = item
    return normalized


def _split_suffix(target: str) -> tuple[str, str]:
    positions = [
        position
        for token in ("?", "#", "|")
        if (position := target.find(token)) >= 0
    ]
    if positions:
        index = min(positions)
        return target[:index], target[index:]
    return target, ""


def _resolve_reference(source: str, reference: str, moves: dict[str, str]) -> str | None:
    path, suffix = _split_suffix(reference)
    if not path or "://" in path:
        return None
    source_dir = posixpath.dirname(source)
    normalized = posixpath.normpath(posixpath.join(source_dir, path))
    candidates = [normalized]
    if not posixpath.splitext(normalized)[1]:
        candidates.append(normalized + ".md")
    moved = next((moves[item] for item in candidates if item in moves), None)
    if not moved:
        return None
    if not posixpath.splitext(path)[1] and moved.endswith(".md"):
        moved = moved[:-3]
    return moved + suffix


def _resolve_wikilink(reference: str, moves: dict[str, str]) -> str | None:
    path, suffix = _split_suffix(reference)
    if not path or "://" in path or "/" not in path:
        return None
    normalized = posixpath.normpath(path.lstrip("/"))
    candidates = [normalized]
    if not posixpath.splitext(normalized)[1]:
        candidates.append(normalized + ".md")
    moved = next((moves[item] for item in candidates if item in moves), None)
    if not moved:
        return None
    if not posixpath.splitext(path)[1] and moved.endswith(".md"):
        moved = moved[:-3]
    return moved + suffix


def _rewrite_text(source: str, destination: str, text: str, moves: dict[str, str]) -> tuple[str, list[dict[str, str]]]:
    changed_kinds: list[str] = []
    output: list[str] = []
    fenced = False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            output.append(line)
            continue
        if fenced:
            output.append(line)
            continue
        pieces = re.split(r"(`[^`]*`)", line)
        for index in range(0, len(pieces), 2):
            segment = pieces[index]

            def replace_wiki(match: re.Match[str]) -> str:
                prefix, target = match.group(1), match.group(2)
                rewritten = _resolve_wikilink(target, moves)
                if not rewritten:
                    return match.group(0)
                changed_kinds.append("wikilink")
                return f"{prefix}[[{rewritten}]]"

            segment = re.sub(r"(!?)\[\[([^\]]+)\]\]", replace_wiki, segment)

            def replace_markdown(match: re.Match[str]) -> str:
                label, target = match.group(1), match.group(2)
                resolved = _resolve_reference(source, target, moves)
                if not resolved:
                    return match.group(0)
                moved_path, moved_suffix = _split_suffix(resolved)
                relative = posixpath.relpath(moved_path, posixpath.dirname(destination))
                rewritten = relative + moved_suffix
                changed_kinds.append("markdown")
                return f"[{label}]({rewritten})"

            segment = re.sub(r"\[([^\]]*)\]\(([^)]+)\)", replace_markdown, segment)
            pieces[index] = segment
        output.append("".join(pieces))
    postimage = "".join(output)
    # Fast path: if nothing actually changed (the common case), skip the
    # quadratic difflib pass entirely. Output is provably identical since a
    # diff of identical strings yields only "equal" opcodes.
    if postimage == text:
        return postimage, []
    rewrites: list[dict[str, Any]] = []
    kind = changed_kinds[0] if len(set(changed_kinds)) == 1 else "reference"
    for tag, start, end, replacement_start, replacement_end in difflib.SequenceMatcher(
        None, text, postimage, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        rewrites.append(
            {
                "start": start,
                "end": end,
                "expected": text[start:end],
                "replacement": postimage[replacement_start:replacement_end],
                "kind": kind,
            }
        )
    return postimage, rewrites


def _apply_rewrites(text: str, rewrites: list[dict[str, Any]]) -> str:
    previous_start = len(text) + 1
    result = text
    for rewrite in sorted(rewrites, key=lambda item: item["start"], reverse=True):
        start = int(rewrite["start"])
        end = int(rewrite["end"])
        expected = str(rewrite["expected"])
        if not (0 <= start <= end <= len(text)) or end > previous_start:
            raise ValueError("invalid or overlapping rewrite range")
        if text[start:end] != expected:
            raise ValueError("rewrite preimage range does not match source")
        result = result[:start] + str(rewrite["replacement"]) + result[end:]
        previous_start = start
    return result


def build_plan(
    root: Path, *, decisions: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a deterministic, read-only workbench migration plan."""
    root = Path(root).resolve()
    inventory = inventory_tree(root)
    operations: list[dict[str, Any]] = [
        {
            "kind": "mkdir",
            "source": relative,
            "destination": relative,
            "preimage_sha256": "",
            "rollback": {"restore_from_backup": relative},
        }
        for relative in _WORKBENCH_DIRECTORIES
    ]
    blockers: list[dict[str, Any]] = []
    moves: dict[str, str] = {}

    unknown_root_set = {
        entry["path"].split("/", 1)[0]
        for entry in inventory["entries"]
        if _target_path(entry["path"])[1] == "review-required"
    }
    normalized_decisions = _normalize_decisions(unknown_root_set, decisions)
    unknown_roots = sorted(
        root
        for root in unknown_root_set
        if normalized_decisions.get(root, {}).get("action")
        not in {"retain", "map"}
    )
    blockers.extend(
        {"kind": "unknown-root", "path": item, "message": "operator classification required"}
        for item in unknown_roots
    )

    file_entries = [entry for entry in inventory["entries"] if entry["kind"] == "file"]
    for entry in inventory["entries"]:
        if entry["kind"] != "directory":
            continue
        destination, kind = _target_path(entry["path"], normalized_decisions)
        if kind == "move" and destination != entry["path"]:
            operations.append(
                {
                    "kind": "mkdir",
                    "source": entry["path"],
                    "destination": destination,
                    "preimage_sha256": "",
                    "rollback": {"restore_from_backup": entry["path"]},
                }
            )
    for entry in file_entries:
        destination, kind = _target_path(entry["path"], normalized_decisions)
        if kind == "move":
            moves[entry["path"]] = destination

    destinations: dict[str, list[str]] = {}
    for entry in file_entries:
        destination = moves.get(entry["path"], entry["path"])
        destinations.setdefault(destination.casefold(), []).append(entry["path"])
    for sources in sorted(destinations.values()):
        if len(sources) > 1:
            blockers.append(
                {
                    "kind": "destination-casefold-collision",
                    "path": sources[0],
                    "sources": sources,
                    "message": "multiple sources resolve to one portable destination",
                }
            )

    for entry in file_entries:
        source = entry["path"]
        destination = moves.get(source, source)
        operation: dict[str, Any] | None = None
        if source in moves:
            operation = {
                "kind": "move",
                "source": source,
                "destination": destination,
                "preimage_sha256": entry["sha256"],
                "size": entry["size"],
                "rollback": {"restore_from_backup": source},
            }
        if source.lower().endswith(".md"):
            if entry["size"] > MAX_REWRITE_MARKDOWN_BYTES:
                blockers.append(
                    {
                        "kind": "oversized-markdown",
                        "path": source,
                        "message": "operator review required before bounded rewrite planning",
                    }
                )
                original = ""
            else:
                try:
                    original = (root / source).read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    original = ""
            if original:
                postimage, rewrites = _rewrite_text(source, destination, original, moves)
                if rewrites:
                    operation = {
                        "kind": "rewrite",
                        "source": source,
                        "destination": destination,
                        "preimage_sha256": entry["sha256"],
                        "size": entry["size"],
                        "rollback": {"restore_from_backup": source},
                        "rewrites": rewrites,
                        "postimage_sha256": hashlib.sha256(postimage.encode("utf-8")).hexdigest(),
                        "in_place": source == destination,
                    }
        if operation is not None:
            operations.append(operation)

    for collision_kind, groups in inventory["collisions"].items():
        for group in groups:
            blockers.append(
                {
                    "kind": f"source-{collision_kind}-collision",
                    "path": group[0],
                    "sources": group,
                    "message": "source tree is not portable without an operator decision",
                }
            )
    for entry in inventory["entries"]:
        if entry["kind"] in {"symlink", "reparse-point", "unsupported"} or entry["flags"]:
            blockers.append(
                {
                    "kind": "unsupported-source-object",
                    "path": entry["path"],
                    "flags": entry["flags"],
                    "object_kind": entry["kind"],
                    "message": "operator review required",
                }
            )

    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "root_hint": inventory["root_hint"],
            "tree_sha256": inventory["tree_sha256"],
        },
        "inventory": inventory["entries"],
        "decisions": normalized_decisions,
        "operations": sorted(operations, key=lambda item: item["source"]),
        "rewrites": [
            {"source": item["source"], "rewrites": item.get("rewrites", [])}
            for item in operations
            if item.get("rewrites")
        ],
        "blockers": sorted(blockers, key=lambda item: (item["kind"], item["path"])),
        "status": "blocked" if blockers else "ready",
        "final_config": {
            "layout": "workbench",
            "paths": {
                "capture": "Inbox",
                "projects": "Projects",
                "knowledge": "Knowledge",
                "sources": {
                    "originals": "Sources/Originals",
                    "processed": "Sources/Notes",
                },
                "archive": "Archive",
            },
            "gbrain_source": "",
        },
    }
    plan["plan_sha256"] = plan_sha256(plan)
    validate_plan(plan)
    return plan


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label} evidence") from exc
    if not isinstance(value, dict):
        raise ValueError(f"invalid {label} evidence")
    return value


def _require_external(wiki: Path, path: Path, label: str) -> Path:
    resolved = Path(path).resolve(strict=False)
    try:
        resolved.relative_to(wiki.resolve())
    except ValueError:
        return resolved
    raise ValueError(f"{label} must be outside the canonical Wiki")


def _validate_backup_evidence(
    wiki: Path, evidence_path: Path, expected_source_hash: str
) -> tuple[dict[str, Any], Path]:
    external_evidence = _require_external(
        wiki, Path(evidence_path), "backup evidence"
    )
    evidence = _load_json(external_evidence, "backup")
    backup_path = _require_external(
        wiki, Path(str(evidence.get("backup_path", ""))), "backup artifact"
    )
    restore = _require_external(
        wiki, Path(str(evidence.get("restore_path", ""))), "backup restore"
    )
    if (
        evidence.get("verified") is not True
        or evidence.get("source_tree_sha256") != expected_source_hash
        or not backup_path.is_file()
    ):
        raise ValueError("backup evidence does not match expected source tree")
    declared_hash = str(evidence.get("backup_sha256", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", declared_hash) or _file_sha256(
        backup_path
    ) != declared_hash:
        raise ValueError("backup artifact hash does not match evidence")
    if (
        not restore.is_dir()
        or inventory_tree(restore)["tree_sha256"] != expected_source_hash
    ):
        raise ValueError("backup restore tree does not match expected source tree")
    return evidence, restore


def _journal_entries(path: Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError
            entries.append(item)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("corrupted migration journal") from exc
    return entries


def _append_journal(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def _migration_lock(path: Path, plan_hash: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError("migration lock already exists") from exc
    try:
        os.write(descriptor, (plan_hash + "\n").encode("ascii"))
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _expected_destination_hash(operation: dict[str, Any]) -> str:
    return str(operation.get("postimage_sha256") or operation.get("preimage_sha256", ""))


def _verify_completed_operation(wiki: Path, operation: dict[str, Any]) -> None:
    destination = wiki / operation["destination"]
    if operation["kind"] == "mkdir":
        if not destination.is_dir():
            raise ValueError(f"completed directory missing: {operation['destination']}")
        return
    if not destination.is_file():
        raise ValueError(f"completed destination missing: {operation['destination']}")
    digest = _file_sha256(destination)
    if digest != _expected_destination_hash(operation):
        raise ValueError(f"completed destination drift: {operation['destination']}")


def _operation_matches_completed_state(wiki: Path, operation: dict[str, Any]) -> bool:
    destination = wiki / operation["destination"]
    if operation["kind"] == "mkdir":
        return destination.is_dir()
    source = wiki / operation["source"]
    if not destination.is_file():
        return False
    if _file_sha256(destination) != _expected_destination_hash(operation):
        return False
    if operation.get("in_place"):
        return source == destination
    return not source.exists()


def _atomic_write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"destination exists: {path}")
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.migration-", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path)
        except FileExistsError as exc:
            raise ValueError(f"destination exists: {path}") from exc
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _atomic_copy_new(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError(f"destination exists: {destination}")
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.migration-", dir=destination.parent
    )
    temp = Path(temp_name)
    digest = hashlib.sha256()
    try:
        with Path(source).open("rb") as input_handle, os.fdopen(
            descriptor, "wb"
        ) as output_handle:
            for chunk in iter(lambda: input_handle.read(STREAM_CHUNK_BYTES), b""):
                output_handle.write(chunk)
                digest.update(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        try:
            os.link(temp, destination)
        except FileExistsError as exc:
            raise ValueError(f"destination exists: {destination}") from exc
        return digest.hexdigest()
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _apply_operation(wiki: Path, operation: dict[str, Any]) -> None:
    source = wiki / operation["source"]
    destination = wiki / operation["destination"]
    if operation["kind"] == "mkdir":
        destination.mkdir(parents=True, exist_ok=True)
        return
    in_place = bool(operation.get("in_place"))
    if destination.exists() and not in_place:
        raise ValueError(f"destination exists: {operation['destination']}")
    if not source.is_file():
        raise ValueError(f"source missing: {operation['source']}")
    if _file_sha256(source) != operation["preimage_sha256"]:
        raise ValueError(f"source hash drift: {operation['source']}")
    if operation["kind"] == "rewrite":
        source_text = source.read_text(encoding="utf-8")
        destination_data = _apply_rewrites(
            source_text, operation["rewrites"]
        ).encode("utf-8")
    elif not in_place:
        copied_digest = _atomic_copy_new(source, destination)
        if copied_digest != operation["preimage_sha256"]:
            raise ValueError(f"destination verification failed: {operation['destination']}")
        if _file_sha256(destination) != operation["preimage_sha256"]:
            raise ValueError(f"destination verification failed: {operation['destination']}")
        source.unlink()
        return
    if in_place:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.migration-", dir=destination.parent
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(destination_data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, destination)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass
    else:
        _atomic_write_new(destination, destination_data)
    if _file_sha256(destination) != _expected_destination_hash(operation):
        raise ValueError(f"destination verification failed: {operation['destination']}")
    if not in_place:
        source.unlink()


def _remove_empty_source_roots(wiki: Path, roots: set[str]) -> None:
    for name in sorted(roots):
        root = wiki / name
        if not root.is_dir():
            continue
        directories = sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            root.rmdir()
        except OSError:
            pass


def apply_plan(
    wiki: Path,
    plan_path: Path,
    *,
    approved_plan_sha256: str,
    backup_evidence: Path | None,
    rehearsal_evidence: Path | None,
    journal_path: Path,
    lock_path: Path,
    confirmed: bool,
    resume: bool = False,
    rehearsal: bool = False,
    interrupt_after: int | None = None,
) -> dict[str, Any]:
    """Apply one exact ready plan after backup/rehearsal evidence and approval."""
    wiki = Path(wiki).resolve()
    plan_path = _require_external(wiki, Path(plan_path), "plan")
    journal_path = _require_external(wiki, Path(journal_path), "journal")
    lock_path = _require_external(wiki, Path(lock_path), "lock")
    if not confirmed:
        raise ValueError("explicit apply confirmation required")

    plan = _load_json(plan_path, "migration plan")
    canonical_hash = plan_sha256(plan)
    validate_plan(plan)
    if plan.get("plan_sha256") != canonical_hash or approved_plan_sha256 != canonical_hash:
        raise ValueError("plan hash does not match approved plan")
    if plan.get("status") != "ready" or plan.get("blockers"):
        raise ValueError("migration plan is blocked")

    source_hash = plan["source"]["tree_sha256"]
    if not rehearsal:
        if backup_evidence is None or rehearsal_evidence is None:
            raise ValueError("backup and rehearsal evidence are required for canonical apply")
        rehearsal_evidence = _require_external(
            wiki, Path(rehearsal_evidence), "rehearsal evidence"
        )
        backup, restore_path = _validate_backup_evidence(
            wiki, Path(backup_evidence), source_hash
        )
        rehearsal_record = _load_json(rehearsal_evidence, "rehearsal")
        if (
            rehearsal_record.get("verified") is not True
            or rehearsal_record.get("source_tree_sha256") != source_hash
            or rehearsal_record.get("plan_sha256") != canonical_hash
        ):
            raise ValueError("rehearsal evidence is not verified for this plan")
        rehearsal_wiki = _require_external(
            wiki,
            Path(str(rehearsal_record.get("rehearsal_wiki", ""))),
            "rehearsal Wiki",
        )
        rehearsal_journal = _require_external(
            wiki,
            Path(str(rehearsal_record.get("journal_path", ""))),
            "rehearsal journal",
        )
        rehearsal_verification = verify_migration(
            rehearsal_wiki,
            plan_path,
            journal_path=rehearsal_journal,
        )
        if rehearsal_verification["status"] != "verified":
            raise ValueError("rehearsal verification does not match this plan")
        if (
            rehearsal_record.get("final_tree_sha256")
            != rehearsal_verification["final_tree_sha256"]
        ):
            raise ValueError("rehearsal final tree hash does not match verification")

    entries = _journal_entries(journal_path)
    if entries and any(item.get("plan_sha256") != canonical_hash for item in entries):
        raise ValueError("journal plan hash mismatch")
    if entries and not resume:
        raise ValueError("existing journal requires explicit resume")
    if entries and entries[-1].get("event") == "migration-complete":
        for operation in plan["operations"]:
            _verify_completed_operation(wiki, operation)
        return {"status": "already-applied", "plan_sha256": canonical_hash}

    completed = {
        item["source"]
        for item in entries
        if item.get("event") in {"operation-complete", "operation-reconciled"}
        and item.get("source")
    }
    reconciled: list[dict[str, Any]] = []
    if entries:
        if entries[0].get("event") != "migration-start" or entries[0].get("source_tree_sha256") != source_hash:
            raise ValueError("journal source tree mismatch")
        for operation in plan["operations"]:
            if operation["source"] in completed:
                _verify_completed_operation(wiki, operation)
            elif _operation_matches_completed_state(wiki, operation):
                completed.add(operation["source"])
                reconciled.append(operation)
            elif operation["kind"] in {"move", "rewrite"}:
                source = wiki / operation["source"]
                destination = wiki / operation["destination"]
                if not source.is_file() or _file_sha256(source) != operation["preimage_sha256"]:
                    raise ValueError(f"remaining source drift: {operation['source']}")
                if destination.exists() and not operation.get("in_place"):
                    raise ValueError(f"remaining destination drift: {operation['destination']}")
    elif inventory_tree(wiki)["tree_sha256"] != source_hash:
        raise ValueError("source tree drift since planning")

    with _migration_lock(lock_path, canonical_hash):
        if not entries:
            _append_journal(
                journal_path,
                {
                    "event": "migration-start",
                    "plan_sha256": canonical_hash,
                    "source_tree_sha256": source_hash,
                },
            )
        for operation in reconciled:
            _append_journal(
                journal_path,
                {
                    "event": "operation-reconciled",
                    "plan_sha256": canonical_hash,
                    "source": operation["source"],
                    "destination": operation["destination"],
                    "sha256": _expected_destination_hash(operation),
                },
            )
        applied_this_run = 0
        for operation in plan["operations"]:
            if operation["source"] in completed:
                continue
            _append_journal(
                journal_path,
                {
                    "event": "operation-start",
                    "plan_sha256": canonical_hash,
                    "source": operation["source"],
                    "destination": operation["destination"],
                },
            )
            _apply_operation(wiki, operation)
            _append_journal(
                journal_path,
                {
                    "event": "operation-complete",
                    "plan_sha256": canonical_hash,
                    "source": operation["source"],
                    "destination": operation["destination"],
                    "sha256": _expected_destination_hash(operation),
                },
            )
            applied_this_run += 1
            if interrupt_after is not None and applied_this_run >= interrupt_after:
                raise RuntimeError("injected interruption")
        mapped_roots = {
            operation["source"].split("/", 1)[0]
            for operation in plan["operations"]
            if operation["kind"] in {"mkdir", "move", "rewrite"}
            and operation["source"].split("/", 1)[0]
            != operation["destination"].split("/", 1)[0]
        }
        _remove_empty_source_roots(wiki, mapped_roots)
        final_hash = inventory_tree(wiki)["tree_sha256"]
        _append_journal(
            journal_path,
            {
                "event": "migration-complete",
                "plan_sha256": canonical_hash,
                "final_tree_sha256": final_hash,
            },
        )
    return {
        "status": "rehearsed" if rehearsal else "applied",
        "plan_sha256": canonical_hash,
        "final_tree_sha256": final_hash,
        "applied_operations": len(plan["operations"]),
    }


def _expected_objects(plan: dict[str, Any]) -> dict[str, dict[str, str]]:
    moved_sources = {
        operation["source"]
        for operation in plan["operations"]
        if operation["kind"] in {"move", "rewrite"}
    }
    decisions = plan.get("decisions", {})
    expected: dict[str, dict[str, str]] = {}
    for entry in plan["inventory"]:
        if entry["kind"] == "file":
            if entry["path"] not in moved_sources:
                expected[entry["path"]] = {
                    "kind": "file",
                    "sha256": entry["sha256"],
                }
        elif entry["kind"] == "directory":
            destination, classification = _target_path(entry["path"], decisions)
            if classification != "review-required":
                expected[destination] = {"kind": "directory", "sha256": ""}
    for operation in plan["operations"]:
        if operation["kind"] == "mkdir":
            # On case-insensitive filesystems (Windows/macOS) a mkdir
            # destination may be physically identical to a retained directory
            # that differs only by case (e.g. "knowledge" vs "Knowledge").
            # Only require it as a distinct expected object when no existing
            # expected directory already covers it case-insensitively.
            folded_dest = operation["destination"].casefold()
            already_covered = any(
                expected_path.casefold() == folded_dest
                for expected_path in expected
            )
            if not already_covered:
                expected[operation["destination"]] = {"kind": "directory", "sha256": ""}
        elif operation["kind"] in {"move", "rewrite"}:
            expected[operation["destination"]] = {
                "kind": "file",
                "sha256": _expected_destination_hash(operation),
            }
    return expected


def _link_targets(root: Path, relative: str, text: str) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        pieces = re.split(r"(`[^`]*`)", line)
        for index in range(0, len(pieces), 2):
            segment = pieces[index]
            for match in re.finditer(r"!?\[\[([^\]]+)\]\]", segment):
                target, _ = _split_suffix(match.group(1))
                if "/" in target:
                    targets.append(("wikilink", target))
            for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", segment):
                target, _ = _split_suffix(match.group(1))
                # Exclude site-root-relative links ("/...") the same way as
                # scheme URLs ("://") and anchors ("#..."): they are external
                # references, not Wiki-internal paths. On Windows a bare "/"
                # target would resolve to a drive root (empty filename) and
                # crash the link verifier.
                if (
                    target
                    and "://" not in target
                    and not target.startswith("#")
                    and not target.startswith("/")
                ):
                    targets.append(("markdown", target))
    return targets


def _links_resolve(root: Path, relative: str, text: str) -> tuple[bool, list[str]]:
    broken: list[str] = []
    resolved_root = root.resolve()
    for kind, target in _link_targets(root, relative, text):
        if kind == "wikilink":
            candidate = root / target.lstrip("/")
        else:
            candidate = (root / relative).parent / target
        candidates = [candidate]
        if not candidate.suffix:
            candidates.append(candidate.with_suffix(".md"))
        contained = []
        escaped = False
        for path in candidates:
            resolved = path.resolve(strict=False)
            try:
                resolved.relative_to(resolved_root)
            except ValueError:
                escaped = True
                continue
            contained.append(resolved)
        if escaped and not contained:
            broken.append(f"{relative}: {target} escapes Wiki")
        elif not any(path.exists() for path in contained):
            broken.append(f"{relative}: {target}")
    return not broken, broken


def _default_lexical_verification(
    wiki: Path, expected: dict[str, str]
) -> tuple[bool, list[dict[str, Any]]]:
    roles = {
        "knowledge": "Knowledge/",
        "projects": "Projects/",
        "processed-sources": "Sources/Notes/",
    }
    results: list[dict[str, Any]] = []
    all_ok = True
    for role, prefix in roles.items():
        candidates = sorted(
            path
            for path in expected
            if path.startswith(prefix) and path.lower().endswith(".md")
        )
        if not candidates:
            results.append({"role": role, "expected_path": "", "query": "", "ok": True, "skipped": True})
            continue
        expected_path = candidates[0]
        text = (wiki / expected_path).read_text(encoding="utf-8", errors="replace")
        tokens = [token.casefold() for token in re.findall(r"[\w-]{4,}", text, flags=re.UNICODE)]
        query = next((token for token in tokens if not token.isdigit()), "")
        ok = False
        if query:
            scanned_files = 0
            scanned_bytes = 0
            for path in sorted((wiki / prefix.rstrip("/")).rglob("*.md")):
                if scanned_files >= 200 or scanned_bytes >= 2_000_000:
                    break
                with path.open("rb") as handle:
                    data = handle.read(256_000)
                scanned_files += 1
                scanned_bytes += len(data)
                if query in data.decode("utf-8", errors="replace").casefold():
                    relative = path.relative_to(wiki).as_posix()
                    if relative == expected_path:
                        ok = True
                        break
        all_ok = all_ok and ok
        results.append(
            {
                "role": role,
                "expected_path": expected_path,
                "query": query,
                "ok": ok,
                "skipped": False,
            }
        )
    return all_ok, results


def verify_migration(
    wiki: Path,
    plan_path: Path,
    *,
    journal_path: Path,
    lexical_probe=None,
    lexical_queries: list[tuple[str, str]] | None = None,
    disposable_capture_probe: bool = False,
    backup_evidence: Path | None = None,
) -> dict[str, Any]:
    """Independently verify final state from plan bytes, not journal assertions."""
    wiki = Path(wiki).resolve()
    plan = _load_json(Path(plan_path), "migration plan")
    canonical_hash = plan_sha256(plan)
    validate_plan(plan)
    journal = _journal_entries(Path(journal_path))
    journal_complete = bool(
        journal
        and journal[-1].get("event") == "migration-complete"
        and all(item.get("plan_sha256") == canonical_hash for item in journal)
    )
    expected_objects = _expected_objects(plan)
    expected = {
        path: item["sha256"]
        for path, item in expected_objects.items()
        if item["kind"] == "file"
    }
    inventory = inventory_tree(wiki)
    actual_objects = {
        entry["path"]: {"kind": entry["kind"], "sha256": entry["sha256"]}
        for entry in inventory["entries"]
    }
    actual_files = {
        entry["path"]: entry["sha256"]
        for entry in inventory["entries"]
        if entry["kind"] == "file"
    }
    unexpected = sorted(set(actual_files) - set(expected))
    missing = sorted(set(expected) - set(actual_files))
    hash_mismatches = sorted(
        path
        for path in set(expected) & set(actual_files)
        if expected[path] != actual_files[path]
    )
    hashes_ok = not missing and not hash_mismatches
    unexpected_objects = sorted(set(actual_objects) - set(expected_objects))
    missing_objects = sorted(set(expected_objects) - set(actual_objects))
    kind_mismatches = sorted(
        path
        for path in set(expected_objects) & set(actual_objects)
        if expected_objects[path]["kind"] != actual_objects[path]["kind"]
    )
    objects_ok = not unexpected_objects and not missing_objects and not kind_mismatches

    required_directories = list(_WORKBENCH_DIRECTORIES)
    directories_ok = all((wiki / relative).is_dir() for relative in required_directories)
    mapped_roots = set(_LEGACY_PREFIXES) | {
        root
        for root, decision in plan.get("decisions", {}).items()
        if decision.get("action") == "map"
    }
    legacy_absent = all(not (wiki / relative).exists() for relative in mapped_roots)
    # Structural integrity (regular file, bounded size, valid UTF-8) must always
    # hold — it is data-integrity, not wiki content debt. Link *resolution* is a
    # separate concern: it only matters when the plan can actually change links
    # (move/rewrite ops). mkdir-only plans touch nothing, so broken links there
    # are pre-existing wiki debt — still reported, but not migration breakage.
    links_ok = True
    structural_ok = True
    broken_links: list[str] = []
    for relative in sorted(expected):
        if not relative.lower().endswith(".md") or relative not in actual_files:
            continue
        entry = actual_objects[relative]
        if entry["kind"] != "file":
            structural_ok = False
            links_ok = False
            broken_links.append(f"{relative}: not a regular file")
            continue
        if (wiki / relative).stat().st_size > MAX_REWRITE_MARKDOWN_BYTES:
            structural_ok = False
            links_ok = False
            broken_links.append(f"{relative}: exceeds bounded Markdown verification size")
            continue
        try:
            text = (wiki / relative).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            structural_ok = False
            links_ok = False
            broken_links.append(f"{relative}: expected Markdown is not UTF-8")
            continue
        ok, broken = _links_resolve(wiki, relative, text)
        links_ok = links_ok and ok
        broken_links.extend(broken)

    if lexical_probe and lexical_queries:
        lexical_results = []
        lexical_ok = True
        for query, expected_path in lexical_queries:
            output = lexical_probe(wiki, query)
            ok = expected_path in output
            lexical_results.append(
                {"query": query, "expected_path": expected_path, "ok": ok}
            )
            lexical_ok = lexical_ok and ok
    else:
        lexical_ok, lexical_results = _default_lexical_verification(wiki, expected)

    capture_ready = (wiki / "Inbox").is_dir() and os.access(wiki / "Inbox", os.W_OK)
    if disposable_capture_probe and capture_ready:
        probe = wiki / "Inbox" / f".migration-capture-probe-{os.getpid()}"
        try:
            with probe.open("x", encoding="utf-8") as handle:
                handle.write("synthetic capture readiness probe\n")
                handle.flush()
                os.fsync(handle.fileno())
            capture_ready = probe.read_text(encoding="utf-8") == "synthetic capture readiness probe\n"
        finally:
            try:
                probe.unlink()
            except FileNotFoundError:
                pass

    rollback_ready = False
    if backup_evidence is not None:
        try:
            _validate_backup_evidence(
                wiki, Path(backup_evidence), plan["source"]["tree_sha256"]
            )
            rollback_ready = True
        except (OSError, ValueError):
            rollback_ready = False

    # Link resolution is only meaningful to verify when the plan can actually
    # change links. move/rewrite operations rewrite path references; mkdir-only
    # plans (adopt-existing) touch nothing, so any broken links in the tree are
    # pre-existing wiki debt, not migration breakage. Keep reporting them for
    # transparency but don't block verification on them in that case. Structural
    # integrity (structural_ok) is always required — that is data-integrity, not
    # content debt.
    plan_mutates_links = any(
        operation.get("kind") in {"move", "rewrite"}
        for operation in plan.get("operations", [])
    )
    links_gate = links_ok or not plan_mutates_links

    status = "verified" if all(
        [
            plan.get("plan_sha256") == canonical_hash,
            journal_complete,
            hashes_ok,
            not unexpected,
            objects_ok,
            directories_ok,
            legacy_absent,
            links_gate,
            structural_ok,
            lexical_ok,
            capture_ready,
        ]
    ) else "failed"
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": status,
        "plan_sha256": canonical_hash,
        "source_tree_sha256": plan["source"]["tree_sha256"],
        "final_tree_sha256": inventory["tree_sha256"],
        "accounted_files": len(expected),
        "hashes_ok": hashes_ok,
        "missing_files": missing,
        "unexpected_files": unexpected,
        "unexpected_objects": unexpected_objects,
        "missing_objects": missing_objects,
        "kind_mismatches": kind_mismatches,
        "objects_ok": objects_ok,
        "hash_mismatches": hash_mismatches,
        "directories_ok": directories_ok,
        "legacy_absent": legacy_absent,
        "links_ok": links_ok,
        "structural_ok": structural_ok,
        "broken_links": broken_links,
        "lexical_ok": lexical_ok,
        "lexical_results": lexical_results,
        "capture_ready": capture_ready,
        "semantic_active": False,
        "journal_complete": journal_complete,
        "final_config": plan["final_config"],
        "rollback_ready": rollback_ready,
    }


def rollback_from_verified_restore(
    wiki: Path,
    backup_evidence: Path,
    *,
    expected_source_tree_sha256: str,
    retained_migrated_tree: Path,
    confirmed: bool,
) -> dict[str, Any]:
    """Replace a migrated Wiki only after verifying an isolated restored tree."""
    if not confirmed:
        raise ValueError("explicit rollback confirmation required")
    wiki = Path(wiki).resolve()
    retained = _require_external(wiki, Path(retained_migrated_tree), "retained migrated tree")
    if retained.exists():
        raise ValueError("retained migrated tree destination exists")
    _, restore = _validate_backup_evidence(
        wiki, Path(backup_evidence), expected_source_tree_sha256
    )
    migrated_hash = inventory_tree(wiki)["tree_sha256"]
    shutil.copytree(wiki, retained, symlinks=True)
    if inventory_tree(retained)["tree_sha256"] != migrated_hash:
        raise ValueError("retained migrated tree verification failed")
    staging = wiki.parent / f".{wiki.name}.rollback-staging-{os.getpid()}"
    original_hold = wiki.parent / f".{wiki.name}.rollback-original-{os.getpid()}"
    failed_restore = wiki.parent / f".{wiki.name}.rollback-failed-{os.getpid()}"
    if any(path.exists() for path in (staging, original_hold, failed_restore)):
        raise ValueError("rollback staging path exists")
    shutil.copytree(restore, staging, symlinks=True)
    if inventory_tree(staging)["tree_sha256"] != expected_source_tree_sha256:
        shutil.rmtree(staging)
        raise ValueError("rollback staging verification failed")
    try:
        os.replace(wiki, original_hold)
        os.replace(staging, wiki)
        if inventory_tree(wiki)["tree_sha256"] != expected_source_tree_sha256:
            raise ValueError("restored canonical tree verification failed")
    except Exception as rollback_error:
        quarantine_error: Exception | None = None
        if wiki.exists():
            try:
                failed_hash = inventory_tree(wiki)["tree_sha256"]
                try:
                    os.replace(wiki, failed_restore)
                except OSError:
                    shutil.copytree(wiki, failed_restore, symlinks=True)
                    if inventory_tree(failed_restore)["tree_sha256"] != failed_hash:
                        raise ValueError("failed restore quarantine verification failed")
                    shutil.rmtree(wiki)
            except Exception as exc:
                quarantine_error = exc
                if wiki.exists():
                    shutil.rmtree(wiki)
        if original_hold.exists():
            os.replace(original_hold, wiki)
        if quarantine_error is not None:
            raise ValueError(
                "canonical Wiki restored but failed restore could not be retained"
            ) from quarantine_error
        raise rollback_error
    return {
        "status": "rolled-back",
        "restored_tree_sha256": expected_source_tree_sha256,
        "retained_migrated_tree": str(retained),
        "same_volume_original_hold": str(original_hold),
        "restore_path": str(restore),
        "semantic_rebuild_required": True,
    }
