"""Read-only terminal-wait input comparison for bounded derive re-entry."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from .authority_boundary import authority_watch_row
from .repo_skill_adapter import COMPONENT_PATH_FIELDS
from .selection_publication import publication_status
from .selection_tick_baseline import (
    carry_forward_sticky_rows,
    changed_watch_entries,
    load_json_object,
    load_json_objects,
    validated_previous_tick,
)
from .selection_tick_packet import render_selection_tick_packet
from .selection_tick_io import (
    MAX_FILE_BYTES as MAX_FILE_BYTES,
    bounded_paths as _bounded_paths,
    safe_json_object as _safe_json_object,
    safe_path as _safe_path,
    sha256_and_size as _sha256_and_size,
)
from .selection_tick_limits import (
    MAX_AUTHORITY_PACKETS,
    MAX_CALLER_WATCH_PATHS,
    MAX_RETIREMENT_FILES,
    MAX_TASK_PACK_FILES,
    MAX_WATCH_ENTRIES,
)
from .selection_tick_policy import (
    DEFAULT_MINIMUM_MATERIAL_DELTA,
    opaque_ids,
    selection_policy,
)
from .selection_tick_premise import (
    premise_input_contract,
    validate_premise_watch_row,
)


DEFAULT_WATCH_PATHS = (
    "task.md",
    ".agent_goal/final_goal.md",
    ".agent_goal/conventions.md",
    ".agent_goal/goal_architecture.md",
    ".agent_goal/goal_theory.md",
    ".agent_goal/goal_schema_contract.md",
    ".agent_advice/index.jsonl",
    ".issue/index.jsonl",
    ".schema/contracts.jsonl",
    ".contract/index.jsonl",
)
ADAPTER_ROOT = ".codex/skills"
ADAPTER_MANIFEST_NAME = "adapter.manifest.json"
MAX_ADAPTER_MANIFESTS = 64
MAX_EXACT_PREMISES = 64


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _adapter_paths(root: Path) -> list[str]:
    adapter_root = root / ADAPTER_ROOT
    if not adapter_root.is_dir() or adapter_root.is_symlink():
        return []
    manifests = _bounded_paths(
        adapter_root.glob(f"*/{ADAPTER_MANIFEST_NAME}"),
        MAX_ADAPTER_MANIFESTS,
        "adapter manifest",
    )
    paths: list[str] = []
    for manifest_path in manifests:
        relative_manifest = manifest_path.relative_to(root).as_posix()
        value, normalized_manifest = _safe_json_object(
            root, relative_manifest, "adapter manifest"
        )
        paths.append(normalized_manifest)
        for path_field, _hash_field in COMPONENT_PATH_FIELDS:
            raw = value.get(path_field)
            if isinstance(raw, str) and raw.strip():
                paths.append(raw.strip())
    return paths


def _pack_paths(root: Path) -> list[str]:
    pack_root = root / ".task" / "task_pack"
    paths: list[str] = []
    if not pack_root.is_dir():
        return paths
    for path in _bounded_paths(
        pack_root.glob("*.json"), MAX_TASK_PACK_FILES, "task-pack state"
    ):
        _value, normalized = _safe_json_object(
            root, path.relative_to(root).as_posix(), "task-pack state"
        )
        paths.append(normalized)
    return paths


def _retirement_paths(root: Path) -> list[str]:
    retirement_root = root / ".task" / "task_pack_retirement"
    if not retirement_root.exists():
        return []
    if retirement_root.is_symlink() or not retirement_root.is_dir():
        raise ValueError("task-pack retirement store is unsafe")
    paths: list[str] = []
    for path in _bounded_paths(
        retirement_root.glob("*/*.json"),
        MAX_RETIREMENT_FILES,
        "task-pack retirement artifact",
    ):
        _value, normalized = _safe_json_object(
            root,
            path.relative_to(root).as_posix(),
            "task-pack retirement artifact",
        )
        paths.append(normalized)
    return paths


def _workflow_evidence_class(normalized: str) -> str:
    if normalized == "task.md":
        return "task_state"
    if normalized == ".agent_goal/agent_authority.md":
        return "authority"
    if normalized.startswith(".agent_goal/"):
        return "goal_truth"
    if normalized.startswith(".agent_advice/"):
        return "advice"
    if normalized.startswith(".issue/"):
        return "issue"
    if normalized.startswith((".schema/", ".contract/")):
        return "schema_contract"
    if normalized.startswith(".codex/skills/") or normalized.endswith(
        "domain_adapter.py"
    ):
        return "adapter"
    if normalized.startswith(".task/task_pack/"):
        return "task_pack"
    if normalized.startswith(".task/task_pack_retirement/"):
        return "task_pack"
    return "custom_watch"


def _entry(
    root: Path,
    raw: str,
    *,
    explicit: bool,
    premise_id: str | None = None,
) -> dict[str, Any]:
    path, normalized = _safe_path(root, raw, explicit=explicit)
    exists = path.is_file()
    if premise_id is not None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", premise_id):
            raise ValueError("premise IDs must be bounded opaque IDs")
        watch_identity = f"exact_subject:{premise_id}"
    else:
        watch_identity = normalized
    row: dict[str, Any] = {
        "watch_id": "watch-"
        + hashlib.sha256(watch_identity.encode("utf-8")).hexdigest()[:24],
        "exists": exists,
        "kind": "exact_premise" if premise_id is not None else "workflow_input",
        "evidence_class": "exact_subject"
        if premise_id is not None
        else _workflow_evidence_class(normalized),
    }
    if premise_id is None:
        row["path"] = normalized
    else:
        row["premise_id"] = premise_id
        row["path_redacted"] = True
    if exists:
        row["sha256"], row["size_bytes"] = _sha256_and_size(path)
    return row


def _validated_exact_premise_inputs(
    premise_paths: Sequence[str],
    premise_ids: Sequence[str],
) -> tuple[list[str], list[str]]:
    if any(not isinstance(item, str) for item in premise_paths) or any(
        not isinstance(item, str) for item in premise_ids
    ):
        raise ValueError("exact premise paths and IDs must be strings")
    premise_path_list = [item.strip() for item in premise_paths]
    premise_id_list = [item.strip() for item in premise_ids]
    if (
        len(premise_path_list) > MAX_EXACT_PREMISES
        or len(premise_id_list) > MAX_EXACT_PREMISES
    ):
        raise ValueError(f"exact premise count exceeds {MAX_EXACT_PREMISES}")
    if (
        any(not item for item in premise_path_list)
        or len(premise_path_list) != len(set(premise_path_list))
        or any(not item for item in premise_id_list)
        or len(premise_id_list) != len(set(premise_id_list))
    ):
        raise ValueError("exact premise paths and IDs must be nonempty and unique")
    if len(premise_path_list) != len(premise_id_list):
        raise ValueError("each premise path requires one unique --premise-id")
    if premise_id_list:
        opaque_ids(premise_id_list, "premise_ids")
    return premise_path_list, premise_id_list


def _watch_rows(
    root: Path,
    watch_paths: Sequence[str],
    premise_paths: Sequence[str],
    premise_ids: Sequence[str],
    authority_packets: Sequence[dict[str, Any]],
    previous: dict[str, Any] | None,
    premise_contract: str,
) -> tuple[list[dict[str, Any]], bool]:
    premise_path_list, premise_id_list = _validated_exact_premise_inputs(
        premise_paths, premise_ids
    )
    requested = [
        *DEFAULT_WATCH_PATHS,
        *watch_paths,
        *_adapter_paths(root),
        *_pack_paths(root),
        *_retirement_paths(root),
    ]
    if any(not isinstance(item, str) for item in requested):
        raise ValueError("selection watch paths must be strings")
    deduped = list(dict.fromkeys(item for item in requested if item.strip()))
    if ".agent_goal/agent_authority.md" in deduped:
        raise ValueError(
            "terminal wait cannot watch the mutable whole authority policy; supply an exact v2 authority packet"
        )
    rows = [_entry(root, raw, explicit=False) for raw in deduped]
    for raw, premise_id in zip(premise_path_list, premise_id_list, strict=True):
        path, _normalized = _safe_path(root, raw, explicit=True)
        row = _entry(root, raw, explicit=True, premise_id=premise_id)
        rows.append(
            validate_premise_watch_row(
                root=root,
                path=path,
                row=row,
                premise_id=premise_id,
                previous=previous,
                contract=premise_contract,
            )
        )
    authority_rows = [authority_watch_row(packet) for packet in authority_packets]
    authority_scope_ids = [str(row["authority_scope_id"]) for row in authority_rows]
    if len(authority_scope_ids) != len(set(authority_scope_ids)):
        raise ValueError(
            "authority packets must have unique exact request/operation/subject scopes"
        )
    rows.extend(authority_rows)
    if len(rows) > MAX_WATCH_ENTRIES:
        raise ValueError(f"selection watch entry count exceeds {MAX_WATCH_ENTRIES}")
    rows.sort(key=lambda row: (str(row["kind"]), str(row["watch_id"])))
    return rows, bool(premise_path_list)


def build_selection_tick(
    root: Path,
    *,
    previous: dict[str, Any] | None = None,
    watch_paths: Sequence[str] = (),
    premise_paths: Sequence[str] = (),
    premise_ids: Sequence[str] = (),
    authority_packets: Sequence[dict[str, Any]] = (),
    wake_predicates: Sequence[str] = (),
    watched_evidence_classes: Sequence[str] = (),
    minimum_material_delta: str = DEFAULT_MINIMUM_MATERIAL_DELTA,
    acknowledge_selection_tick_id: str | None = None,
    selection_receipt_ref: str | None = None,
    selection_receipt_sha256: str | None = None,
    premise_contract: str | None = None,
) -> dict[str, Any]:
    if len(watch_paths) > MAX_CALLER_WATCH_PATHS:
        raise ValueError(f"watch path count exceeds {MAX_CALLER_WATCH_PATHS}")
    if len(authority_packets) > MAX_AUTHORITY_PACKETS:
        raise ValueError(f"authority packet count exceeds {MAX_AUTHORITY_PACKETS}")
    if any(not isinstance(item, str) for item in watch_paths):
        raise ValueError("watch paths must be strings")
    if any(not isinstance(item, dict) for item in authority_packets):
        raise ValueError("authority packets must be objects")
    root = root.expanduser().resolve(strict=True)
    premise_paths, premise_ids = _validated_exact_premise_inputs(
        premise_paths, premise_ids
    )
    previous_tick = validated_previous_tick(
        root,
        previous,
        acknowledge_selection_tick_id,
        selection_receipt_ref,
        selection_receipt_sha256,
    )
    previous = previous_tick.packet if previous_tick else None
    active_premise_contract = premise_input_contract(previous, premise_contract)
    rows, exact_premise_supplied = _watch_rows(
        root,
        watch_paths,
        premise_paths,
        premise_ids,
        authority_packets,
        previous,
        active_premise_contract,
    )
    rows, carried_watch_ids = carry_forward_sticky_rows(previous, rows)
    manifest_sha256 = hashlib.sha256(_canonical(rows)).hexdigest()
    previous_sha, active_predicates, active_classes, active_minimum = selection_policy(
        previous,
        wake_predicates,
        watched_evidence_classes,
        minimum_material_delta,
    )
    changed_entries = changed_watch_entries(previous, rows) if previous else []
    fresh_exact_premise_detected = bool(
        exact_premise_supplied
        and (
            previous is None
            or any(
                row["evidence_class"] == "exact_subject"
                and row["change_kind"] in {"added", "content_changed"}
                for row in changed_entries
            )
        )
    )
    return render_selection_tick_packet(
        previous=previous,
        previous_tick=previous_tick,
        previous_sha=previous_sha,
        rows=rows,
        manifest_sha256=manifest_sha256,
        changed_entries=changed_entries,
        active_predicates=active_predicates,
        active_classes=active_classes,
        active_minimum=active_minimum,
        exact_premise_supplied=exact_premise_supplied,
        fresh_exact_premise_detected=fresh_exact_premise_detected,
        carried_watch_ids=carried_watch_ids,
        publication=publication_status(root),
        acknowledge_selection_tick_id=acknowledge_selection_tick_id,
        premise_contract=active_premise_contract,
    )


def _load_previous(path: str | None, root: Path) -> dict[str, Any] | None:
    if not path:
        from .terminal_wait_baseline import current_selection_tick_packet

        return current_selection_tick_packet(root)
    return load_json_object(root, path, "previous selection-tick packet")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--previous-json")
    parser.add_argument("--watch-path", action="append", default=[])
    parser.add_argument("--premise-path", action="append", default=[])
    parser.add_argument("--premise-id", action="append", default=[])
    parser.add_argument("--authority-packet", action="append", default=[])
    parser.add_argument("--acknowledge-selection-tick-id")
    parser.add_argument("--selection-receipt-ref")
    parser.add_argument("--selection-receipt-sha256")
    parser.add_argument("--premise-input-contract")
    parser.add_argument("--wake-predicate", action="append", default=[])
    parser.add_argument("--watched-evidence-class", action="append", default=[])
    parser.add_argument(
        "--minimum-material-delta", default=DEFAULT_MINIMUM_MATERIAL_DELTA
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if len(args.watch_path) > MAX_CALLER_WATCH_PATHS:
            raise ValueError(f"watch path count exceeds {MAX_CALLER_WATCH_PATHS}")
        if len(args.authority_packet) > MAX_AUTHORITY_PACKETS:
            raise ValueError(f"authority packet count exceeds {MAX_AUTHORITY_PACKETS}")
        premise_paths, premise_ids = _validated_exact_premise_inputs(
            args.premise_path, args.premise_id
        )
        root = Path(args.root)
        previous = _load_previous(args.previous_json, root)
        authority_packets = load_json_objects(
            root, args.authority_packet, "authority packet"
        )
        packet = build_selection_tick(
            root,
            previous=previous,
            watch_paths=args.watch_path,
            premise_paths=premise_paths,
            premise_ids=premise_ids,
            authority_packets=authority_packets,
            wake_predicates=args.wake_predicate,
            watched_evidence_classes=args.watched_evidence_class,
            minimum_material_delta=args.minimum_material_delta,
            acknowledge_selection_tick_id=args.acknowledge_selection_tick_id,
            selection_receipt_ref=args.selection_receipt_ref,
            selection_receipt_sha256=args.selection_receipt_sha256,
            premise_contract=args.premise_input_contract,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"status": "block", "error": str(exc), "mutation_performed": False},
                ensure_ascii=False,
            )
        )
        return 2
    json.dump(packet, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
