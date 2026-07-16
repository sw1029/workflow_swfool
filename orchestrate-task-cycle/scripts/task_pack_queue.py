#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import task_pack_replacement  # noqa: E402


PACK_STATUSES = {"active", "completed", "blocked", "terminal_blocked", "superseded"}
ITEM_STATUSES = {
    "planned",
    "promoted",
    "in_progress",
    "consumed",
    "inserted",
    "reordered",
    "skipped",
    "blocked",
    "terminal_blocked",
    "superseded",
}
VALIDATION_PROFILES = {"current_only", "affected_chain", "full_chain"}
PROGRESS_TARGETS = {"advanced", "safety_only", "no_progress", "regressed"}
PROGRESS_KINDS = {"goal_productive", "governance_only"}
OPEN_RESIDUAL_STATUSES = {"planned", "promoted", "in_progress", "inserted", "reordered", "blocked"}
PACK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ITEM_KIND_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA256_PATTERN = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")
PROMOTION_VALIDATION_VERDICTS = {"complete", "pass", "passed"}
PROMOTION_TERMINAL_EXECUTION_STATUSES = {
    "blocked_no_execution",
    "complete",
    "completed",
    "no_execution",
    "not_applicable",
    "skipped",
    "success",
}
ISSUE_NOOP_STATUSES = {"not_applicable", "skipped"}
ISSUE_MUTATION_STATUSES = {"closed", "created", "open", "reopened", "resolved", "tracked", "updated"}
PACK_COHERENCE_VERSION = 1
PACK_COHERENCE_MUTATIONS = {
    "create",
    "promote",
    "insert",
    "reorder",
    "skip",
    "supersede",
    "terminal_block",
    "mark_consumed",
    "normalize_initial_selection_provenance",
    "replace",
}
PROMOTION_ORIGINS = {
    "predecessor_completion",
    "bootstrap_initial_selection",
    "authorized_initial_selection",
}
VERDICT_AXIS_STATUSES = {"pass", "fail", "partial", "blocked", "not_evaluated", "not_applicable", "conflicted"}
VERDICT_AXES = (
    "task_acceptance_verdict",
    "artifact_truth_verdict",
    "artifact_semantic_verdict",
    "pack_transition_verdict",
    "historical_index_verdict",
    "goal_readiness_verdict",
)
INITIAL_SELECTION_RECEIPT_VERSION = 1
CREATION_SNAPSHOT_CANONICALIZATION_VERSION = 1
AUTHORITY_RECEIPT_TEMPORALITIES = {
    "contemporaneous_selection_authority",
    "current_ratification",
    "retrospective_evidence_assessment",
}
AUTHORITY_RECEIPT_SOURCE_KINDS = {
    "explicit_current_user_instruction",
    "effective_authority_policy",
    "contemporaneous_authority_record",
}
CONTEMPORANEOUS_AUTHORITY_SOURCE_KINDS = {
    "explicit_current_user_instruction",
    "effective_authority_policy",
    "contemporaneous_authority_record",
}
_PACK_MUTATION_THREAD_LOCK = threading.RLock()
_CONTENT_ADDRESSED_WRITE_STATE = threading.local()


class ContentAddressedWriteTransaction:
    """Roll back newly-created evidence unless a canonical consumer was published."""

    def __init__(self) -> None:
        self.created_paths: list[Path] = []
        self.created_directories: list[Path] = []
        self.canonical_consumers: list[tuple[Path, str]] = []
        self.committed = False

    def register_created(self, path: Path, created_directories: list[Path] | None = None) -> None:
        self.created_paths.append(path)
        self.created_directories.extend(created_directories or [])

    def guard_canonical_consumer(self, path: Path, expected_canonical_sha256: str) -> None:
        self.canonical_consumers.append((path, expected_canonical_sha256))

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        if self.committed:
            return
        for path, expected_digest in self.canonical_consumers:
            if not path.is_file():
                continue
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(body, dict) and canonical_pack_sha256(body) == expected_digest:
                return
        for path in reversed(self.created_paths):
            if path.is_file():
                path.unlink()
        for directory in sorted(set(self.created_directories), key=lambda value: len(value.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass


@contextmanager
def content_addressed_write_transaction():
    previous = getattr(_CONTENT_ADDRESSED_WRITE_STATE, "current", None)
    transaction = ContentAddressedWriteTransaction()
    _CONTENT_ADDRESSED_WRITE_STATE.current = transaction
    try:
        yield transaction
    finally:
        try:
            transaction.rollback()
        finally:
            _CONTENT_ADDRESSED_WRITE_STATE.current = previous


def guard_content_addressed_consumer(path: Path, expected_canonical_sha256: str) -> None:
    transaction = getattr(_CONTENT_ADDRESSED_WRITE_STATE, "current", None)
    if isinstance(transaction, ContentAddressedWriteTransaction):
        transaction.guard_canonical_consumer(path, expected_canonical_sha256)


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def pack_dir(root: Path) -> Path:
    return root / ".task" / "task_pack"


def creation_snapshot_dir(root: Path) -> Path:
    return pack_dir(root) / "creation_snapshots"


def creation_receipt_dir(root: Path) -> Path:
    return pack_dir(root) / "creation_receipts"


@contextmanager
def pack_mutation_lock(root: Path, *, create: bool = True):
    """Serialize through the stable workspace-root inode without lock residue."""

    root = root.resolve()
    if not root.is_dir():
        raise SystemExit("Task-pack workspace root must be an existing directory.")
    directory = _require_within(pack_dir(root), root, "Task pack directory")
    with _PACK_MUTATION_THREAD_LOCK:
        descriptor = os.open(root, os.O_RDONLY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            if create and not directory.is_dir():
                directory.mkdir(parents=True, exist_ok=True)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _require_within(path: Path, boundary: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    resolved_boundary = boundary.resolve(strict=False)
    try:
        resolved.relative_to(resolved_boundary)
    except ValueError as exc:
        raise SystemExit(f"{label} must stay inside {resolved_boundary}, including through symlinks.") from exc
    return resolved


def resolve_pack_path(root: Path, value: str, *, must_exist: bool = True) -> Path:
    raw = Path(str(value).strip())
    if not str(value).strip() or raw.is_absolute():
        raise SystemExit("Task pack path must be a non-empty workspace-relative path.")
    directory = _require_within(pack_dir(root), root, "Task pack directory")
    path = _require_within(root / raw, directory, "Task pack path")
    if path.suffix != ".json":
        raise SystemExit("Task pack path must identify a .json file under .task/task_pack.")
    if must_exist and not path.is_file():
        raise SystemExit(f"Task pack does not exist: {rel_path(root, path)}")
    return path


def bounded_workspace_path(root: Path, value: Any, label: str) -> Path:
    raw_value = str(value or "").strip()
    raw = Path(raw_value)
    if not raw_value or raw.is_absolute():
        raise SystemExit(f"{label} must be a non-empty workspace-relative path.")
    return _require_within(root / raw, root, label)


def bounded_workspace_file(root: Path, value: Any, label: str) -> Path:
    path = bounded_workspace_path(root, value, label)
    if not path.is_file():
        raise SystemExit(f"{label} does not identify an existing file: {value}")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_optional_file(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise SystemExit(f"Expected a regular file for hashing: {path}")
    return sha256_file(path)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def parse_rfc3339(value: Any, label: str) -> dt.datetime:
    raw = str(value or "").strip()
    if not raw:
        raise SystemExit(f"{label} is required.")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit(f"{label} must be RFC3339-compatible.") from exc
    if parsed.tzinfo is None:
        raise SystemExit(f"{label} must include a timezone.")
    return parsed


def _without_volatile_pack_fields(value: Any) -> Any:
    """Return the deterministic lifecycle state used for pack preconditions."""

    if isinstance(value, list):
        return [_without_volatile_pack_fields(item) for item in value]
    if not isinstance(value, dict):
        return value
    ignored = {
        "created_at",
        "updated_at",
        "timestamp",
        "promoted_at",
        "completed_at",
    }
    return {
        str(key): _without_volatile_pack_fields(item)
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        if key not in ignored and key != "mutation_log"
    }


def canonical_pack_sha256(data: dict[str, Any]) -> str:
    """Hash canonical pack state without timestamps or append-only mutation history."""

    payload = json.dumps(
        _without_volatile_pack_fields(data),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def pack_snapshot(root: Path, path: Path, data: dict[str, Any]) -> dict[str, Any]:
    ordered = sorted_items(data)
    item_ids = [str(item.get("item_id")) for item in ordered if item.get("item_id")]
    return {
        "canonical_pack_ref": rel_path(root, path),
        "canonical_pack_sha256": canonical_pack_sha256(data),
        "pack_file_sha256": sha256_file(path) if path.is_file() else None,
        "item_ids": item_ids,
        "item_order": item_ids,
        "current_item": data.get("current_item_id"),
    }


def _coherence_value(plan: dict[str, Any], key: str, *aliases: str) -> Any:
    nested = plan.get("pack_coherence")
    if isinstance(nested, dict):
        for candidate in (key, *aliases):
            if candidate in nested:
                return nested.get(candidate)
    for candidate in (key, *aliases):
        if candidate in plan:
            return plan.get(candidate)
    return None


def _coherence_field_declared(plan: dict[str, Any], key: str, *aliases: str) -> bool:
    nested = plan.get("pack_coherence")
    if isinstance(nested, dict) and any(candidate in nested for candidate in (key, *aliases)):
        return True
    return any(candidate in plan for candidate in (key, *aliases))


def pack_coherence_contract_version(plan: dict[str, Any]) -> int | None:
    nested = plan.get("pack_coherence")
    raw = nested.get("schema_version") if isinstance(nested, dict) else None
    if raw is None:
        raw = plan.get("pack_coherence_version")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


_pack_coherence_contract_version = pack_coherence_contract_version


def validate_pack_coherence_contract(
    root: Path,
    plan: dict[str, Any],
    *,
    receipt: dict[str, Any] | None = None,
    require_declared: bool = False,
    require_receipt: bool = False,
) -> dict[str, Any]:
    """Validate a derive plan/receipt against the canonical pack body.

    This is the single deterministic owner used both by mutation execution and
    the derive result contract. Legacy plans may be normalized at execution
    time, but a caller that declares the current contract must provide every
    before-snapshot precondition.
    """

    findings: list[dict[str, Any]] = []

    def finding(code: str, message: str, evidence: Any = None) -> None:
        item: dict[str, Any] = {"severity": "block", "code": code, "message": message}
        if evidence is not None:
            item["evidence"] = evidence
        findings.append(item)

    pack_ref = _coherence_value(plan, "canonical_pack_ref", "pack_path")
    if not non_empty(pack_ref):
        finding("canonical_pack_ref_missing", "Pack coherence requires `canonical_pack_ref` or legacy `pack_path`.")
        return {"status": "block", "findings": findings, "pack_coherence": None}
    try:
        path = resolve_pack_path(root, str(pack_ref))
        data = load_json(path)
    except SystemExit as exc:
        finding("canonical_pack_unreadable", str(exc))
        return {"status": "block", "findings": findings, "pack_coherence": None}

    actual = pack_snapshot(root, path, data)
    receipt_value = receipt or plan.get("pack_mutation_receipt")
    post_mutation_receipt = isinstance(receipt_value, dict)
    contract_version = _pack_coherence_contract_version(plan)
    current_contract = contract_version == PACK_COHERENCE_VERSION
    explicit_legacy = contract_version == 0
    if contract_version not in {0, PACK_COHERENCE_VERSION}:
        finding(
            "pack_coherence_version_missing_or_invalid",
            "Pack coherence requires schema/version 1; legacy normalization requires explicit version 0.",
        )
    mutation_kind = normalize_action(str(_coherence_value(plan, "mutation_kind", "action", "pack_disposition") or ""))
    if mutation_kind and mutation_kind not in PACK_COHERENCE_MUTATIONS:
        finding("pack_mutation_kind_invalid", "Pack coherence names an unsupported mutation kind.", {"mutation_kind": mutation_kind})
    outer_mutation_kind = normalize_action(str(plan.get("action") or plan.get("pack_disposition") or ""))
    if current_contract and outer_mutation_kind and mutation_kind != outer_mutation_kind:
        finding(
            "pack_mutation_kind_mismatch",
            "Pack coherence mutation kind does not match the requested mutation action.",
            {"declared": mutation_kind or None, "requested": outer_mutation_kind},
        )

    declared = {
        "before_pack_sha256": _coherence_value(plan, "before_pack_sha256", "canonical_pack_sha256"),
        "declared_before_item_ids": _coherence_value(plan, "declared_before_item_ids"),
        "declared_before_order": _coherence_value(plan, "declared_before_order"),
        "declared_current_item": _coherence_value(plan, "declared_current_item"),
    }
    contract_declared = current_contract
    expected_hash = ""
    if require_declared and not (current_contract or explicit_legacy):
        finding(
            "pack_coherence_precondition_missing",
            "Pack mutation contracts require an explicit current or legacy discriminator.",
        )
    proposed_ids = _coherence_value(plan, "proposed_after_item_ids")
    proposed_order = _coherence_value(plan, "proposed_after_order", "item_order")
    if current_contract:
        missing = [
            key
            for key in declared
            if not _coherence_field_declared(
                plan,
                key,
                "canonical_pack_sha256" if key == "before_pack_sha256" else key,
            )
        ]
        if not mutation_kind:
            missing.append("mutation_kind")
        if not isinstance(proposed_ids, list):
            missing.append("proposed_after_item_ids")
        if not isinstance(proposed_order, list):
            missing.append("proposed_after_order")
        if missing:
            finding("pack_coherence_precondition_incomplete", "Pack coherence before-snapshot fields are incomplete.", {"missing_fields": missing})
        expected_hash = str(declared["before_pack_sha256"] or "").removeprefix("sha256:").lower()
        if mutation_kind != "create" and not expected_hash:
            finding("pack_coherence_before_hash_missing", "Non-create current mutations require a canonical before-pack hash.")
        if expected_hash and not SHA256_PATTERN.fullmatch(expected_hash):
            finding("pack_coherence_before_hash_invalid", "Pack coherence before hash must be a full lowercase SHA-256 digest.")
        if expected_hash and not post_mutation_receipt and expected_hash != actual["canonical_pack_sha256"]:
            finding(
                "stale_pack_snapshot",
                "Mutation plan was derived from a stale canonical pack snapshot.",
                {"declared": expected_hash, "actual": actual["canonical_pack_sha256"]},
            )
        for key, actual_key in (
            ("declared_before_item_ids", "item_ids"),
            ("declared_before_order", "item_order"),
        ):
            if (
                declared[key] is not None
                and not post_mutation_receipt
                and [str(item) for item in declared[key] or []] != actual[actual_key]
            ):
                finding(
                    f"{key}_mismatch",
                    "Mutation plan does not match the canonical pack item identity/order.",
                    {"declared": declared[key], "actual": actual[actual_key]},
                )
        if (
            declared["declared_current_item"] is not None
            and not post_mutation_receipt
            and declared["declared_current_item"] != actual["current_item"]
        ):
            finding(
                "declared_current_item_mismatch",
                "Mutation plan current item does not match the canonical pack.",
                {"declared": declared["declared_current_item"], "actual": actual["current_item"]},
            )

    before_ids = set(actual["item_ids"])
    if isinstance(proposed_ids, list) and mutation_kind not in {"create", "insert"}:
        unknown = sorted({str(item) for item in proposed_ids} - before_ids)
        if unknown:
            finding("pack_coherence_unknown_item", "Proposed pack state contains item IDs absent from the canonical snapshot.", {"item_ids": unknown})
    if isinstance(proposed_order, list) and mutation_kind not in {"create", "insert"}:
        unknown = sorted({str(item) for item in proposed_order} - before_ids)
        if unknown:
            finding("pack_coherence_unknown_order_item", "Proposed pack order contains item IDs absent from the canonical snapshot.", {"item_ids": unknown})

    if require_receipt and current_contract and not isinstance(receipt_value, dict):
        finding("pack_mutation_receipt_missing", "Current post-mutation validation requires a complete pack mutation receipt.")
    if isinstance(receipt_value, dict):
        if current_contract:
            required_receipt_fields = (
                "schema_version",
                "canonical_pack_ref",
                "before_pack_sha256",
                "after_pack_sha256",
                "actual_before_item_ids",
                "actual_before_order",
                "actual_before_current_item",
                "actual_after_item_ids",
                "actual_after_order",
                "actual_after_current_item",
                "mutation_kind",
            )
            missing_receipt = [field for field in required_receipt_fields if field not in receipt_value]
            if missing_receipt:
                finding(
                    "pack_mutation_receipt_incomplete",
                    "Current pack mutation receipt is incomplete.",
                    {"missing_fields": missing_receipt},
                )
            if receipt_value.get("schema_version") != PACK_COHERENCE_VERSION:
                finding("pack_mutation_receipt_version_invalid", "Current pack mutation receipt requires schema_version=1.")
        if expected_hash and str(receipt_value.get("before_pack_sha256") or "").removeprefix("sha256:").lower() != expected_hash:
            finding("pack_receipt_before_hash_mismatch", "Mutation receipt does not preserve the declared before-pack hash.")
        receipt_ref = str(receipt_value.get("canonical_pack_ref") or "")
        if current_contract and receipt_ref != actual["canonical_pack_ref"]:
            finding("pack_receipt_ref_mismatch", "Mutation receipt references a different canonical pack.")
        after_hash = str(receipt_value.get("after_pack_sha256") or "").removeprefix("sha256:").lower()
        if current_contract and not SHA256_PATTERN.fullmatch(after_hash):
            finding("pack_receipt_after_hash_invalid", "Mutation receipt after hash must be a full lowercase SHA-256 digest.")
        if after_hash and after_hash != actual["canonical_pack_sha256"]:
            finding(
                "pack_receipt_after_hash_mismatch",
                "Mutation receipt after hash does not match the canonical pack body.",
                {"declared": after_hash, "actual": actual["canonical_pack_sha256"]},
            )
        for key, actual_key in (("actual_after_item_ids", "item_ids"), ("actual_after_order", "item_order")):
            value = receipt_value.get(key)
            if value is not None and [str(item) for item in value or []] != actual[actual_key]:
                finding(f"pack_receipt_{key}_mismatch", "Mutation receipt after-state does not match the canonical pack body.")
        if current_contract and receipt_value.get("actual_after_current_item") != actual["current_item"]:
            finding("pack_receipt_after_current_item_mismatch", "Mutation receipt current item does not match the canonical pack body.")
        receipt_mutation_kind = normalize_action(str(receipt_value.get("mutation_kind") or ""))
        if current_contract and receipt_mutation_kind != mutation_kind:
            finding("pack_receipt_mutation_kind_mismatch", "Mutation receipt kind does not match the declared plan mutation.")
        if current_contract:
            for key, declared_key in (
                ("actual_before_item_ids", "declared_before_item_ids"),
                ("actual_before_order", "declared_before_order"),
            ):
                if [str(item) for item in receipt_value.get(key) or []] != [str(item) for item in declared.get(declared_key) or []]:
                    finding(f"pack_receipt_{key}_before_mismatch", "Mutation receipt before-state does not match the declared plan snapshot.")
            if receipt_value.get("actual_before_current_item") != declared.get("declared_current_item"):
                finding("pack_receipt_before_current_item_mismatch", "Mutation receipt before current item does not match the declared plan snapshot.")

    normalized = {
        "schema_version": PACK_COHERENCE_VERSION,
        "contract_version": contract_version,
        "canonical_pack_ref": actual["canonical_pack_ref"],
        "before_pack_sha256": expected_hash if current_contract else actual["canonical_pack_sha256"],
        "declared_before_item_ids": declared["declared_before_item_ids"] if contract_declared else actual["item_ids"],
        "actual_before_item_ids": receipt_value.get("actual_before_item_ids") if post_mutation_receipt else actual["item_ids"],
        "declared_before_order": declared["declared_before_order"] if contract_declared else actual["item_order"],
        "actual_before_order": receipt_value.get("actual_before_order") if post_mutation_receipt else actual["item_order"],
        "declared_current_item": declared["declared_current_item"] if contract_declared else actual["current_item"],
        "actual_current_item": receipt_value.get("actual_before_current_item") if post_mutation_receipt else actual["current_item"],
        "proposed_after_item_ids": proposed_ids,
        "proposed_after_order": proposed_order,
        "mutation_kind": mutation_kind,
        "legacy_normalized": explicit_legacy,
    }
    return {"status": "block" if findings else "ok", "findings": findings, "pack_coherence": normalized, "path": path, "data": data}


def require_file_digest(path: Path, expected: Any, label: str) -> str:
    match = SHA256_PATTERN.fullmatch(str(expected or "").strip().lower())
    if not match:
        raise SystemExit(f"{label} requires a full lowercase SHA-256 digest.")
    expected_digest = match.group(1)
    observed = sha256_file(path)
    if observed != expected_digest:
        raise SystemExit(f"{label} SHA-256 does not match the referenced file.")
    return observed


def packet_field(packet: dict[str, Any], key: str) -> Any:
    payload = packet.get("result")
    if isinstance(payload, dict) and key in payload:
        return payload.get(key)
    return packet.get(key)


def normalized_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SystemExit(f"{label} must be a non-empty JSON list of workspace-relative files.")
    result: list[str] = []
    for item in value:
        normalized = str(item or "").strip()
        if not normalized:
            raise SystemExit(f"{label} cannot contain empty values.")
        result.append(normalized)
    return result


def verify_evidence_files(root: Path, values: Any, label: str) -> list[str]:
    normalized = normalized_string_list(values, label)
    verified: list[str] = []
    for value in normalized:
        verified.append(rel_path(root, bounded_workspace_file(root, value, label)))
    return verified


def load_bound_packet(root: Path, value: Any, digest: Any, label: str) -> tuple[Path, dict[str, Any], str]:
    path = bounded_workspace_file(root, value, label)
    observed_digest = require_file_digest(path, digest, label)
    try:
        packet = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{label} is not readable JSON: {exc}") from exc
    if not isinstance(packet, dict):
        raise SystemExit(f"{label} must contain a JSON object.")
    return path, packet, observed_digest


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load task pack {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Task pack must be a JSON object: {path}")
    return value


def load_plan(value: str | None) -> dict[str, Any]:
    if not value or value == "-":
        raw = sys.stdin.read()
        plan = json.loads(raw) if raw.strip() else {}
    else:
        stripped = value.strip()
        if stripped.startswith("{"):
            plan = json.loads(stripped)
        else:
            path = Path(stripped)
            plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise SystemExit("Mutation plan must be a JSON object.")
    return plan


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "pass", "met", "ok"}
    return bool(value)


def non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def verdict_axis_status(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("status") or value.get("verdict") or "").strip().lower()
    return str(value or "").strip().lower()


def preserve_verdict_axes(
    target: dict[str, Any],
    source: dict[str, Any],
    *,
    require_current: bool,
) -> None:
    raw_version = source.get("verdict_contract_version")
    try:
        version = int(raw_version) if raw_version is not None else None
    except (TypeError, ValueError):
        version = None
    supplied = {axis: source.get(axis) for axis in VERDICT_AXES}
    if require_current and version != 1:
        raise SystemExit("Current pack consumption requires verdict_contract_version=1 and all six verdict axes.")
    if version not in {None, 0, 1}:
        raise SystemExit("Verdict contract version must be 1, or explicit legacy version 0.")
    if any(value is not None for value in supplied.values()) and version is None:
        raise SystemExit("Verdict axes require an explicit verdict contract version.")
    if version == 1:
        missing = [axis for axis, value in supplied.items() if value is None]
        if missing:
            raise SystemExit(f"Current verdict contract is missing: {', '.join(missing)}")
        target["verdict_contract_version"] = 1
        target.update(supplied)
    elif version == 0:
        target["verdict_contract_version"] = 0


def scope_fidelity_records(item: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    value = item.get("scope_fidelity", item.get("scope_fidelity_records"))
    if value is None:
        return [], True
    if isinstance(value, dict):
        return [value], True
    if isinstance(value, list) and all(isinstance(record, dict) for record in value):
        return value, True
    return [], False


def write_json(path: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_content_addressed_file(path: Path, payload: bytes, label: str) -> str:
    """Write immutable content once or verify the existing bytes."""

    digest = sha256_bytes(payload)
    if path.exists():
        if not path.is_file() or sha256_file(path) != digest:
            raise SystemExit(f"{label} conflicts with existing content-addressed evidence.")
        return digest
    created_directories: list[Path] = []
    parent = path.parent
    while not parent.exists():
        created_directories.append(parent)
        parent = parent.parent
    write_bytes_atomic(path, payload)
    transaction = getattr(_CONTENT_ADDRESSED_WRITE_STATE, "current", None)
    if isinstance(transaction, ContentAddressedWriteTransaction):
        transaction.register_created(path, created_directories)
    if sha256_file(path) != digest:
        raise SystemExit(f"{label} failed post-write SHA-256 verification.")
    return digest


def _forbidden_receipt_key_paths(value: Any, prefix: str = "$") -> list[str]:
    forbidden = {
        "bounded_quote",
        "raw_prompt",
        "prompt_body",
        "quote",
        "quote_body",
        "instruction_text",
        "transcript_body",
        "transcript_path",
        "user_message",
        "source_text",
        "corpus_metadata",
        "credential",
        "token",
        "secret",
    }
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if str(key).lower() in forbidden:
                found.append(path)
            found.extend(_forbidden_receipt_key_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_receipt_key_paths(item, f"{prefix}[{index}]"))
    return found


def _required_sha256(value: Any, label: str) -> str:
    normalized = str(value or "").removeprefix("sha256:").lower()
    if not SHA256_PATTERN.fullmatch(normalized):
        raise SystemExit(f"{label} requires a full lowercase SHA-256 digest.")
    return normalized


def persist_creation_snapshot(root: Path, pack_path: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Persist the exact planned creation body and a durable receipt."""

    payload = json_bytes(data)
    file_digest = sha256_bytes(payload)
    canonical_digest = canonical_pack_sha256(data)
    pack_id = str(data.get("pack_id") or "")
    snapshot_path = _require_within(
        creation_snapshot_dir(root) / f"{pack_id}-{file_digest[:16]}.json",
        creation_snapshot_dir(root),
        "Creation snapshot path",
    )
    write_content_addressed_file(snapshot_path, payload, "Creation snapshot")
    receipt = {
        "schema_version": 1,
        "receipt_kind": "task_pack_creation",
        "canonicalization_version": CREATION_SNAPSHOT_CANONICALIZATION_VERSION,
        "pack_ref": rel_path(root, pack_path),
        "pack_id": pack_id,
        "creation_snapshot_kind": "workspace_file",
        "creation_snapshot_state": "pre_selection",
        "creation_snapshot_ref": rel_path(root, snapshot_path),
        "creation_snapshot_file_sha256": file_digest,
        "creation_snapshot_canonical_sha256": canonical_digest,
        "item_ids": item_order(data),
        "current_item_id": data.get("current_item_id"),
        "created_at": data.get("created_at") or now_iso(),
    }
    receipt_path = _require_within(
        creation_receipt_dir(root) / f"{pack_id}-{file_digest[:16]}.json",
        creation_receipt_dir(root),
        "Creation receipt path",
    )
    write_content_addressed_file(receipt_path, json_bytes(receipt), "Creation receipt")
    return {
        **receipt,
        "creation_receipt_ref": rel_path(root, receipt_path),
        "creation_receipt_sha256": sha256_file(receipt_path),
    }


def load_bound_creation_snapshot(
    root: Path,
    receipt: dict[str, Any],
) -> tuple[dict[str, Any], bytes, str, str]:
    kind = str(receipt.get("pack_creation_snapshot_kind") or "workspace_file")
    reference = str(receipt.get("pack_creation_snapshot_ref") or "")
    if kind == "workspace_file":
        path = bounded_workspace_file(root, reference, "pack_creation_snapshot_ref")
        payload = path.read_bytes()
    elif kind == "git_blob":
        commit = str(receipt.get("pack_creation_git_commit") or "").lower()
        git_path = str(receipt.get("pack_creation_git_path") or "")
        if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            raise SystemExit("Git creation snapshot requires a full hexadecimal commit ID.")
        raw_path = Path(git_path)
        if not git_path or raw_path.is_absolute() or ".." in raw_path.parts:
            raise SystemExit("Git creation snapshot path must be workspace-relative and traversal-free.")
        expected_ref = f"git:{commit}:{raw_path.as_posix()}"
        if reference != expected_ref:
            raise SystemExit("Git creation snapshot ref does not match commit and path.")
        process = subprocess.run(
            ["git", "show", f"{commit}:{raw_path.as_posix()}"],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if process.returncode != 0:
            raise SystemExit("Git creation snapshot cannot be resolved from the declared commit.")
        payload = process.stdout
    else:
        raise SystemExit("Creation snapshot kind must be workspace_file or git_blob.")

    file_digest = sha256_bytes(payload)
    declared_file_digest = _required_sha256(
        receipt.get("pack_creation_snapshot_sha256"),
        "pack_creation_snapshot_sha256",
    )
    if file_digest != declared_file_digest:
        raise SystemExit("Creation snapshot file SHA-256 does not match.")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("Creation snapshot is not a UTF-8 JSON object.") from exc
    if not isinstance(data, dict):
        raise SystemExit("Creation snapshot must be a JSON object.")
    if receipt.get("pack_creation_canonicalization_version") != CREATION_SNAPSHOT_CANONICALIZATION_VERSION:
        raise SystemExit("Creation snapshot canonicalization version is unsupported.")
    canonical_digest = canonical_pack_sha256(data)
    if canonical_digest != _required_sha256(
        receipt.get("pack_creation_canonical_sha256"),
        "pack_creation_canonical_sha256",
    ):
        raise SystemExit("Creation snapshot canonical SHA-256 does not match.")
    return data, payload, file_digest, canonical_digest


def load_bound_authority_receipt(
    root: Path,
    reference: Any,
    expected_digest: Any,
    expected_operation: str,
    expected_subject: dict[str, Any],
    selected_at: Any,
) -> tuple[dict[str, Any], str]:
    path = bounded_workspace_file(root, reference, "authority_receipt_ref")
    digest = require_file_digest(path, expected_digest, "Authority receipt")
    try:
        authority = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("Authority receipt is not valid JSON.") from exc
    if not isinstance(authority, dict):
        raise SystemExit("Authority receipt must be a JSON object.")
    if _forbidden_receipt_key_paths(authority):
        raise SystemExit("Authority receipt contains forbidden body-bearing or sensitive keys.")
    if (
        authority.get("schema_version") != 1
        or authority.get("receipt_kind") != "operation_authority"
        or not non_empty(authority.get("receipt_id"))
    ):
        raise SystemExit("Authority receipt schema or kind is invalid.")
    if authority.get("operation") != expected_operation or authority.get("decision") != "allowed":
        raise SystemExit("Authority receipt operation/decision does not authorize this mutation.")
    if authority.get("subject") != expected_subject:
        raise SystemExit("Authority receipt subject does not match pack, snapshot, item, and task identity.")
    basis = authority.get("authority_basis")
    if not isinstance(basis, dict) or basis.get("integrity_status") != "verified":
        raise SystemExit("Authority receipt basis is missing verified integrity.")
    policy = bounded_workspace_file(root, basis.get("policy_ref"), "authority policy ref")
    source = bounded_workspace_file(root, basis.get("source_evidence_ref"), "authority source evidence ref")
    require_file_digest(policy, basis.get("policy_sha256"), "Authority policy")
    require_file_digest(source, basis.get("source_evidence_sha256"), "Authority source evidence")
    source_kind = str(basis.get("source_kind") or "")
    source_id = str(basis.get("source_id") or "").strip()
    if source_kind not in AUTHORITY_RECEIPT_SOURCE_KINDS or not source_id:
        raise SystemExit("Authority receipt requires a supported source_kind and opaque source_id.")
    temporality = str(authority.get("basis_temporality") or "")
    if temporality not in AUTHORITY_RECEIPT_TEMPORALITIES:
        raise SystemExit("Authority receipt temporality is invalid.")
    selected_time = parse_rfc3339(selected_at, "initial selection created_at")
    issued_time = parse_rfc3339(authority.get("issued_at"), "authority issued_at")
    effective_time = parse_rfc3339(authority.get("effective_at"), "authority effective_at")
    if effective_time > issued_time:
        raise SystemExit("Authority receipt effective_at cannot be after issued_at.")
    historical = authority.get("historical_effect") if isinstance(authority.get("historical_effect"), dict) else {}
    if temporality == "current_ratification":
        if source_kind != "explicit_current_user_instruction" or effective_time <= selected_time:
            raise SystemExit("Current ratification requires later explicit-user authority evidence.")
        if historical.get("historical_selection_authority_status") != "unverifiable_before_ratification":
            raise SystemExit("Current ratification must preserve unverified historical authority.")
        if historical.get("historical_authority_verdict") != "partial" or historical.get("retroactive_claim_allowed") is not False:
            raise SystemExit("Current ratification cannot create a historical authority pass.")
    elif temporality == "contemporaneous_selection_authority":
        if source_kind not in CONTEMPORANEOUS_AUTHORITY_SOURCE_KINDS or effective_time > selected_time:
            raise SystemExit("Contemporaneous selection authority requires a supported source effective by selection time.")
        if (
            historical.get("historical_selection_authority_status") != "verified"
            or historical.get("historical_authority_verdict") != "pass"
            or historical.get("retroactive_claim_allowed") is not False
        ):
            raise SystemExit("Contemporaneous selection authority requires a verified historical pass.")
    elif temporality == "retrospective_evidence_assessment":
        if (
            expected_operation != "task_pack.normalize_initial_selection"
            or source_kind != "contemporaneous_authority_record"
            or effective_time > selected_time
        ):
            raise SystemExit("Retrospective assessment requires an immutable contemporaneous authority record.")
        if (
            historical.get("historical_selection_authority_status") != "verified"
            or historical.get("historical_authority_verdict") != "pass"
            or historical.get("retroactive_claim_allowed") is not False
        ):
            raise SystemExit("Retrospective assessment cannot create or overstate historical authority.")
    effects = set(str(item) for item in authority.get("allowed_effects") or [])
    expected_effect = (
        "append_initial_selection_normalization_provenance"
        if expected_operation == "task_pack.normalize_initial_selection"
        else "promote_first_pack_item"
    )
    if effects != {expected_effect}:
        raise SystemExit("Authority receipt effects do not match the bounded operation.")
    return authority, digest


def validate_initial_selection_receipt(
    root: Path,
    pack_path: Path,
    current_pack: dict[str, Any],
    receipt: dict[str, Any],
    *,
    task_id: str,
    task_digest: str,
    operation: str,
    require_mutation_binding: bool = True,
) -> dict[str, Any]:
    if receipt.get("schema_version") != INITIAL_SELECTION_RECEIPT_VERSION:
        raise SystemExit("Initial selection receipt requires schema_version=1.")
    required = (
        "pack_ref",
        "pack_creation_snapshot_kind",
        "pack_creation_snapshot_ref",
        "pack_creation_snapshot_sha256",
        "pack_creation_canonical_sha256",
        "pack_creation_canonicalization_version",
        "creation_snapshot_state",
        "initial_item_id",
        "initial_order",
        "task_id",
        "task_snapshot_ref",
        "task_snapshot_sha256",
        "authority_receipt_ref",
        "authority_receipt_sha256",
        "authority_mode",
        "historical_selection_authority_status",
        "selection_reason",
        "created_at",
    )
    missing = [field for field in required if not non_empty(receipt.get(field))]
    if missing:
        raise SystemExit(f"Initial selection receipt is incomplete: {', '.join(missing)}")
    expected_pack_ref = rel_path(root, pack_path)
    if receipt.get("pack_ref") != expected_pack_ref:
        raise SystemExit("Initial selection receipt references a different canonical pack.")
    snapshot, _, snapshot_file_digest, snapshot_canonical_digest = load_bound_creation_snapshot(root, receipt)
    if snapshot.get("pack_id") != current_pack.get("pack_id"):
        raise SystemExit("Creation snapshot pack ID differs from the current pack.")
    ordered = sorted_items(snapshot)
    if not ordered or ordered[0].get("order") != 1:
        raise SystemExit("Creation snapshot does not contain a canonical first item.")
    first = ordered[0]
    item_id = str(receipt.get("initial_item_id") or "")
    if receipt.get("initial_order") != 1 or str(first.get("item_id") or "") != item_id:
        raise SystemExit("Initial item identity/order does not match the creation snapshot.")
    if str(receipt.get("task_id") or "") != task_id:
        raise SystemExit("Initial selection task ID does not match promotion provenance.")
    snapshot_promotion = first.get("promotion") if isinstance(first.get("promotion"), dict) else {}
    if receipt.get("creation_snapshot_state") == "created_with_initial_selection":
        if snapshot_promotion.get("task_id") != task_id:
            raise SystemExit("Legacy creation snapshot does not identify the selected task.")
    elif receipt.get("creation_snapshot_state") != "pre_selection":
        raise SystemExit("Creation snapshot state is invalid.")
    task_snapshot = bounded_workspace_file(root, receipt.get("task_snapshot_ref"), "task_snapshot_ref")
    _require_within(task_snapshot, pack_dir(root), "Initial task snapshot")
    declared_task_digest = require_file_digest(task_snapshot, receipt.get("task_snapshot_sha256"), "Initial task snapshot")
    if declared_task_digest != task_digest:
        raise SystemExit("Initial task snapshot SHA-256 differs from promotion task identity.")

    expected_subject = {
        "pack_ref": expected_pack_ref,
        "pack_creation_snapshot_ref": receipt.get("pack_creation_snapshot_ref"),
        "pack_creation_snapshot_sha256": snapshot_file_digest,
        "initial_item_id": item_id,
        "initial_order": 1,
        "task_id": task_id,
        "task_snapshot_ref": receipt.get("task_snapshot_ref"),
        "task_snapshot_sha256": task_digest,
    }
    authority_operation = (
        "task_pack.normalize_initial_selection"
        if operation == "normalize_initial_selection_provenance"
        else "task_pack.initial_selection"
    )
    authority, authority_digest = load_bound_authority_receipt(
        root,
        receipt.get("authority_receipt_ref"),
        receipt.get("authority_receipt_sha256"),
        authority_operation,
        expected_subject,
        receipt.get("created_at"),
    )
    if receipt.get("authority_mode") != authority.get("basis_temporality"):
        raise SystemExit("Initial selection and authority receipt temporal modes differ.")
    historical = authority.get("historical_effect") or {}
    if receipt.get("historical_selection_authority_status") != historical.get(
        "historical_selection_authority_status"
    ):
        raise SystemExit("Initial selection receipt overstates historical authority status.")
    expected_action = "normalize_initial_selection_provenance" if operation == "normalize_initial_selection_provenance" else "promote"
    if require_mutation_binding:
        matching = [
            row
            for row in current_pack.get("mutation_log", [])
            if isinstance(row, dict)
            and row.get("action") == expected_action
            and row.get("item_id") == item_id
        ]
        if len(matching) != 1:
            raise SystemExit("Initial selection receipt is not bound to one canonical mutation.")
        if expected_action == "promote" and str(matching[0].get("before_pack_sha256") or "") != snapshot_canonical_digest:
            raise SystemExit("Initial promotion mutation is not bound to the creation snapshot.")
        if expected_action == "normalize_initial_selection_provenance" and matching[0].get(
            "authority_receipt_sha256"
        ) != authority_digest:
            raise SystemExit("Initial normalization mutation is not bound to the authority receipt.")
    return {
        **receipt,
        "pack_creation_snapshot_sha256": snapshot_file_digest,
        "pack_creation_canonical_sha256": snapshot_canonical_digest,
        "task_snapshot_sha256": task_digest,
        "authority_receipt_sha256": authority_digest,
        "authority_mode": authority.get("basis_temporality"),
        "historical_selection_authority_status": historical.get("historical_selection_authority_status"),
    }


def pack_paths(root: Path) -> list[Path]:
    directory = _require_within(pack_dir(root), root, "Task pack directory")
    if not directory.is_dir():
        return []
    paths: list[Path] = []
    for candidate in directory.glob("*.json"):
        path = _require_within(candidate, directory, "Task pack path")
        if not path.is_file():
            raise SystemExit(f"Task pack path does not identify a file: {candidate}")
        paths.append(path)
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)


def validate_pack(
    data: dict[str, Any],
    path: Path | None = None,
    *,
    prospective_task_digests: set[str] | None = None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(severity: str, code: str, message: str, evidence: Any = None) -> None:
        item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
        if evidence is not None:
            item["evidence"] = evidence
        findings.append(item)

    for field in ("schema_version", "pack_id", "status", "goal", "items", "mutation_log"):
        if field not in data:
            add("block", "missing_required_field", f"Task pack is missing `{field}`.", {"path": str(path) if path else None})
    if data.get("schema_version") != 1:
        add("block", "unsupported_schema_version", "`schema_version` must be 1.", {"value": data.get("schema_version")})
    pack_id = str(data.get("pack_id") or "").strip()
    if not PACK_ID_PATTERN.fullmatch(pack_id):
        add("block", "invalid_pack_id", "`pack_id` must be one path-safe token of at most 128 characters.", {"pack_id": pack_id})
    if path is not None and pack_id and path.stem != pack_id:
        add(
            "block",
            "pack_id_path_mismatch",
            "Task pack filename must match its `pack_id`.",
            {"pack_id": pack_id, "filename": path.name},
        )
    status = data.get("status")
    if status not in PACK_STATUSES:
        add("block", "invalid_pack_status", "Invalid task pack status.", {"status": status})

    items = data.get("items")
    if not isinstance(items, list) or not items:
        add("block", "items_missing", "`items` must be a non-empty list.")
        return findings

    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    item_by_id: dict[str, dict[str, Any]] = {}
    residual_links: list[tuple[str, str]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            add("block", "invalid_item", "Task pack item must be an object.", {"index": index})
            continue
        for field in ("item_id", "order", "status", "title", "objective", "validation_profile", "progress_target"):
            if field not in item:
                add("block", "missing_item_field", f"Task pack item is missing `{field}`.", {"index": index})
        item_id = str(item.get("item_id") or "")
        if not item_id:
            add("block", "empty_item_id", "Task pack item has empty item_id.", {"index": index})
        elif not PACK_ID_PATTERN.fullmatch(item_id):
            add("block", "invalid_item_id", "Task pack item_id must be one path-safe token.", {"item_id": item_id})
        elif item_id in seen_ids:
            add("block", "duplicate_item_id", "Task pack item_id is duplicated.", {"item_id": item_id})
        seen_ids.add(item_id)
        if item_id:
            item_by_id[item_id] = item
        order = item.get("order")
        if not isinstance(order, int) or order <= 0:
            add("block", "invalid_item_order", "Task pack item order must be a positive integer.", {"item_id": item_id, "order": order})
        elif order in seen_orders:
            add("block", "duplicate_item_order", "Task pack item order is duplicated.", {"order": order})
        seen_orders.add(order) if isinstance(order, int) else None
        if item.get("status") not in ITEM_STATUSES:
            add("block", "invalid_item_status", "Invalid task pack item status.", {"item_id": item_id, "status": item.get("status")})
        if item.get("status") in {"promoted", "in_progress", "consumed"}:
            promotion = item.get("promotion")
            common_promotion_fields = (
                "task_id",
                "task_path",
                "task_sha256",
                "task_snapshot_path",
                "promoted_at",
            )
            predecessor_promotion_fields = (
                "validated_task_id",
                "validation_verdict",
                "execution_status",
                "run_report_path",
                "run_report_sha256",
                "validation_report_path",
                "validation_report_sha256",
                "validation_evidence_paths",
                "issue_packet_path",
                "issue_packet_sha256",
                "issue_status",
                "mutation_evidence_paths",
            )
            if not isinstance(promotion, dict):
                add(
                    "block",
                    "promotion_provenance_missing",
                    "Promoted/in-progress/consumed items require hash-bound task, run, validation, issue, and mutation provenance.",
                    {"item_id": item_id},
                )
            else:
                promotion_origin = str(promotion.get("promotion_origin") or "predecessor_completion").strip().lower()
                if promotion_origin not in PROMOTION_ORIGINS:
                    add(
                        "block",
                        "promotion_origin_invalid",
                        "Promotion origin is not recognized.",
                        {"item_id": item_id, "promotion_origin": promotion_origin},
                    )
                required_promotion_fields = common_promotion_fields + (
                    predecessor_promotion_fields if promotion_origin == "predecessor_completion" else ("initial_selection_receipt",)
                )
                missing_promotion = [field for field in required_promotion_fields if not non_empty(promotion.get(field))]
                if missing_promotion:
                    add(
                        "block",
                        "promotion_provenance_incomplete",
                        "Promoted/in-progress item provenance is incomplete.",
                        {"item_id": item_id, "missing_fields": missing_promotion},
                    )
                elif path is not None:
                    root = path.resolve().parents[2]
                    audit_plan = {**promotion, "evidence_paths": promotion.get("mutation_evidence_paths")}
                    try:
                        if promotion_origin == "predecessor_completion":
                            validate_promotion_provenance(
                                root,
                                audit_plan,
                                str(promotion.get("validated_task_id") or "").strip(),
                                str(promotion.get("validation_verdict") or "").strip().lower(),
                            )
                        else:
                            receipt = promotion.get("initial_selection_receipt")
                            if not isinstance(receipt, dict):
                                raise SystemExit("Initial promotion receipt is missing.")
                            if receipt.get("task_snapshot_ref") != promotion.get("task_snapshot_path"):
                                raise SystemExit("Initial receipt and promotion task snapshot refs differ.")
                            normalization = promotion.get("provenance_normalization")
                            operation = (
                                "normalize_initial_selection_provenance"
                                if isinstance(normalization, dict)
                                else "promote"
                            )
                            validate_initial_selection_receipt(
                                root,
                                path,
                                data,
                                receipt,
                                task_id=str(promotion.get("task_id") or ""),
                                task_digest=str(promotion.get("task_sha256") or ""),
                                operation=operation,
                            )
                        snapshot_path = bounded_workspace_file(
                            root,
                            promotion.get("task_snapshot_path"),
                            "Promotion task_snapshot_path",
                        )
                        _require_within(snapshot_path, pack_dir(root), "Promotion task_snapshot_path")
                        require_file_digest(snapshot_path, promotion.get("task_sha256"), "Promotion task snapshot")
                        if data.get("status") == "active" and item.get("status") in {"promoted", "in_progress"}:
                            prospective_digest = str(promotion.get("task_sha256") or "")
                            raw_task_path = str(promotion.get("task_path") or "")
                            bounded_workspace_path(root, raw_task_path, "Promotion task_path")
                            if prospective_task_digests and prospective_digest in prospective_task_digests:
                                pass
                            else:
                                task_path = bounded_workspace_file(root, raw_task_path, "Promotion task_path")
                                require_file_digest(task_path, prospective_digest, "Promotion task_path")
                    except SystemExit as exc:
                        add(
                            "block",
                            "promotion_provenance_invalid",
                            "Promoted/in-progress item provenance no longer verifies against durable artifacts.",
                            {"item_id": item_id, "error": str(exc)},
                        )
                if item.get("status") == "consumed":
                    completion = item.get("completion")
                    required_completion_fields = (
                        "completed_task_id",
                        "completed_at",
                        "validation_verdict",
                        "execution_status",
                        "run_report_path",
                        "run_report_sha256",
                        "validation_report_path",
                        "validation_report_sha256",
                        "validation_evidence_paths",
                        "issue_packet_path",
                        "issue_packet_sha256",
                        "issue_status",
                        "completion_evidence_paths",
                    )
                    if not isinstance(completion, dict):
                        add(
                            "block",
                            "completion_provenance_missing",
                            "Consumed items require hash-bound completion run, validation, issue, and mutation provenance.",
                            {"item_id": item_id},
                        )
                    else:
                        missing_completion = [
                            field for field in required_completion_fields if not non_empty(completion.get(field))
                        ]
                        promoted_task_id = str(promotion.get("task_id") or "").strip() if isinstance(promotion, dict) else ""
                        if missing_completion:
                            add(
                                "block",
                                "completion_provenance_incomplete",
                                "Consumed item completion provenance is incomplete.",
                                {"item_id": item_id, "missing_fields": missing_completion},
                            )
                        elif str(completion.get("completed_task_id") or "").strip() != promoted_task_id:
                            add(
                                "block",
                                "completion_task_identity_mismatch",
                                "Consumed item completion provenance must validate the task created by promotion.",
                                {"item_id": item_id, "promoted_task_id": promoted_task_id},
                            )
                        elif path is not None:
                            root = path.resolve().parents[2]
                            completion_plan = {
                                **completion,
                                "evidence_paths": completion.get("completion_evidence_paths"),
                            }
                            try:
                                validate_promotion_provenance(
                                    root,
                                    completion_plan,
                                    promoted_task_id,
                                    str(completion.get("validation_verdict") or "").strip().lower(),
                                )
                            except SystemExit as exc:
                                add(
                                    "block",
                                    "completion_provenance_invalid",
                                    "Consumed item completion provenance no longer verifies against durable artifacts.",
                                    {"item_id": item_id, "error": str(exc)},
                                )
        if item.get("validation_profile") not in VALIDATION_PROFILES:
            add("warn", "invalid_validation_profile", "Unexpected validation profile.", {"item_id": item_id, "validation_profile": item.get("validation_profile")})
        if item.get("progress_target") not in PROGRESS_TARGETS:
            add(
                "warn",
                "invalid_progress_target",
                "Unexpected progress target; keep work subtype in `item_kind` and use a canonical lifecycle outcome.",
                {"item_id": item_id, "progress_target": item.get("progress_target")},
            )
        progress_kind_expected = item.get("progress_kind_expected")
        if progress_kind_expected is not None and progress_kind_expected not in PROGRESS_KINDS:
            add(
                "warn",
                "invalid_progress_kind_expected",
                "`progress_kind_expected` should be goal_productive or governance_only; keep capability subtype in `item_kind`.",
                {"item_id": item_id, "progress_kind_expected": progress_kind_expected},
            )
        item_kind = item.get("item_kind")
        if item_kind is not None and (
            not isinstance(item_kind, str) or not ITEM_KIND_PATTERN.fullmatch(item_kind)
        ):
            add(
                "warn",
                "invalid_item_kind",
                "`item_kind` must be a non-empty bounded path-safe token when supplied.",
                {"item_id": item_id, "item_kind": item_kind},
            )
        if progress_kind_expected == "goal_productive" and item.get("progress_target") in {"safety_only", "no_progress"}:
            add(
                "warn",
                "progress_kind_target_mismatch",
                "A goal_productive pack item should not declare a safety_only/no_progress progress target.",
                {"item_id": item_id, "progress_target": item.get("progress_target")},
            )
        if item.get("positive_input_delta_required") is True and not item.get("required_new_input_kinds"):
            add("block", "positive_delta_kinds_missing", "Positive input delta gate requires `required_new_input_kinds`.", {"item_id": item_id})
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        raw_verdict_version = result.get("verdict_contract_version")
        try:
            verdict_version = int(raw_verdict_version) if raw_verdict_version is not None else None
        except (TypeError, ValueError):
            verdict_version = None
        supplied_verdict_axes = {axis: result.get(axis) for axis in VERDICT_AXES}
        if any(value is not None for value in supplied_verdict_axes.values()) and raw_verdict_version is None:
            add("block", "pack_verdict_contract_version_missing", "Verdict axes require explicit current version 1 or legacy version 0.", {"item_id": item_id})
        if raw_verdict_version is not None and verdict_version not in {0, 1}:
            add("block", "pack_verdict_contract_version_invalid", "Verdict contract version is invalid.", {"item_id": item_id})
        if verdict_version == 1 or any(value is not None for value in supplied_verdict_axes.values()):
            for axis, value in supplied_verdict_axes.items():
                if value is None:
                    add("block", "pack_verdict_axis_missing", "Current item verdict packets must preserve every verdict axis.", {"item_id": item_id, "axis": axis})
                    continue
                status_value = verdict_axis_status(value)
                if status_value not in VERDICT_AXIS_STATUSES:
                    add("block", "pack_verdict_axis_invalid", "Pack item verdict axis status is invalid.", {"item_id": item_id, "axis": axis, "status": status_value})
                evidence = value.get("evidence_ref") or value.get("evidence_refs") if isinstance(value, dict) else None
                if status_value != "not_applicable" and not non_empty(evidence):
                    add("block", "pack_verdict_axis_evidence_missing", "Pack item verdict axes require bounded evidence refs.", {"item_id": item_id, "axis": axis})
            goal_status = verdict_axis_status(supplied_verdict_axes.get("goal_readiness_verdict"))
            implementation_blocking = {
                axis
                for axis in ("task_acceptance_verdict", "artifact_truth_verdict", "artifact_semantic_verdict")
                if verdict_axis_status(supplied_verdict_axes.get(axis)) in {"fail", "blocked", "partial", "not_evaluated", "conflicted"}
            }
            readiness_blocking = {
                axis
                for axis in VERDICT_AXES[:-1]
                if verdict_axis_status(supplied_verdict_axes.get(axis)) in {"fail", "blocked", "partial", "not_evaluated", "conflicted"}
            }
            if implementation_blocking and str(result.get("progress_verdict") or "").lower() == "advanced":
                add(
                    "block",
                    "pack_implementation_failure_counted_as_progress",
                    "Task acceptance, artifact truth, or artifact semantics failure cannot become advanced progress.",
                    {"item_id": item_id, "blocking_axes": sorted(implementation_blocking)},
                )
            if readiness_blocking and goal_status == "pass":
                add(
                    "block",
                    "pack_failed_axis_counted_as_goal_ready",
                    "Goal readiness cannot pass while a required lifecycle axis is failed, blocked, partial, not evaluated, or conflicted.",
                    {"item_id": item_id, "blocking_axes": sorted(readiness_blocking)},
                )
        if item.get("positive_input_delta_required") is True and item.get("status") in {"consumed", "terminal_blocked"}:
            gate = result.get("positive_input_delta_gate") if isinstance(result.get("positive_input_delta_gate"), dict) else {}
            has_supplied = bool(
                result.get("has_supplied_input_delta")
                or gate.get("has_supplied_input_delta")
                or result.get("produced_domain_delta")
                or gate.get("produced_domain_delta")
                or result.get("supplied_input_artifact_paths")
                or gate.get("supplied_input_artifact_paths")
            )
            if not has_supplied:
                add(
                    "warn",
                    "consumed_item_missing_supplied_input_delta",
                    "Consumed evidence-family pack items should record a supplied input artifact or produced_domain_delta=true; derive/result-contract gates enforce this for new progress claims.",
                    {"item_id": item_id},
                )

        records, valid_scope_shape = scope_fidelity_records(item)
        if not valid_scope_shape:
            add("block", "scope_fidelity_invalid", "`scope_fidelity` must be an object or a list of objects.", {"item_id": item_id})
            records = []
        for record_index, record in enumerate(records):
            directive_id = str(record.get("directive_id") or "").strip()
            original_target = record.get("original_target", record.get("measurable_target"))
            item_acceptance = record.get("item_acceptance", item.get("acceptance"))
            has_target = non_empty(original_target)
            narrowed = truthy(record.get("narrowed"))
            residual_item_id = str(record.get("residual_item_id") or "").strip()
            verifier_contract = (
                record.get("acceptance_verifier_contract")
                if isinstance(record.get("acceptance_verifier_contract"), dict)
                else item.get("acceptance_verifier_contract") if isinstance(item.get("acceptance_verifier_contract"), dict)
                else {}
            )

            if has_target and not directive_id:
                add(
                    "block",
                    "scope_fidelity_directive_id_missing",
                    "Measurable scope_fidelity records require `directive_id`.",
                    {"item_id": item_id, "record_index": record_index},
                )
            if has_target and not non_empty(item_acceptance):
                add(
                    "block",
                    "scope_fidelity_item_acceptance_missing",
                    "Measurable scope_fidelity records require item acceptance copied from or traceable to the directive target.",
                    {"item_id": item_id, "directive_id": directive_id or None},
                )
            if narrowed:
                if not non_empty(record.get("narrow_reason")):
                    add(
                        "block",
                        "scope_fidelity_narrow_reason_missing",
                        "Narrowed measurable directives require `narrow_reason`.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                if not residual_item_id:
                    add(
                        "block",
                        "scope_fidelity_residual_item_missing",
                        "Narrowed measurable directives require `residual_item_id` so remaining scope stays open.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                else:
                    residual_links.append((item_id, residual_item_id))

            if has_target and item.get("status") == "consumed":
                acceptance_gate = result.get("acceptance_provenance_gate") if isinstance(result.get("acceptance_provenance_gate"), dict) else {}
                acceptance_gate = acceptance_gate or (result.get("scope_fidelity_gate") if isinstance(result.get("scope_fidelity_gate"), dict) else {})
                if not acceptance_gate:
                    add(
                        "block",
                        "acceptance_provenance_gate_missing",
                        "Consumed measurable pack items require an `acceptance_provenance_gate` result comparing actual achievement to the original directive target.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                    continue
                if truthy(acceptance_gate.get("acceptance_diluted")):
                    add(
                        "block",
                        "acceptance_diluted_item_consumed",
                        "A pack item with `acceptance_diluted=true` cannot be `consumed`; keep the residual target open and mark validation partial.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                target_met = truthy(acceptance_gate.get("target_met"))
                explicit_descope = truthy(acceptance_gate.get("explicit_descope_decision"))
                if not target_met and not explicit_descope:
                    add(
                        "block",
                        "measurable_target_unmet_without_descope",
                        "Consumed measurable pack items must meet the original target or record an explicit descope decision with residual scope.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                verifier_gate = result.get("acceptance_verifier_gate") if isinstance(result.get("acceptance_verifier_gate"), dict) else {}
                verifier_gate = verifier_gate or (
                    result.get("acceptance_verifier_contract")
                    if isinstance(result.get("acceptance_verifier_contract"), dict)
                    else {}
                )
                verifier_required = truthy(
                    verifier_contract.get("verifier_required")
                    or verifier_contract.get("required")
                    or verifier_gate.get("verifier_required")
                    or verifier_gate.get("required")
                ) or non_empty(verifier_contract.get("required_verifier")) or non_empty(verifier_gate.get("required_verifier"))
                evaluation_status = str(
                    verifier_gate.get("evaluation_status")
                    or verifier_contract.get("evaluation_status")
                    or ""
                ).strip().lower()
                required_hooks = (
                    verifier_gate.get("required_gate_hooks")
                    or verifier_contract.get("required_gate_hooks")
                    or record.get("required_gate_hooks")
                    or item.get("required_gate_hooks")
                )
                hook_status = str(
                    verifier_gate.get("gate_hook_status")
                    or verifier_contract.get("gate_hook_status")
                    or record.get("gate_hook_status")
                    or item.get("gate_hook_status")
                    or ""
                ).strip().lower()
                pass_with_coupled_verifier = truthy(
                    verifier_gate.get("pass_with_coupled_verifier")
                    or verifier_contract.get("pass_with_coupled_verifier")
                    or result.get("pass_with_coupled_verifier")
                    or (
                        result.get("coupled_verifier_gate", {}).get("pass_with_coupled_verifier")
                        if isinstance(result.get("coupled_verifier_gate"), dict)
                        else False
                    )
                )
                if verifier_required and (evaluation_status != "pass" or pass_with_coupled_verifier) and not explicit_descope:
                    add(
                        "block",
                        "acceptance_verifier_not_passed_item_consumed",
                        "Consumed measurable pack items require each required live verifier to pass without same-changeset verifier-source coupling, or an explicit descope decision with residual scope.",
                        {
                            "item_id": item_id,
                            "directive_id": directive_id or None,
                            "evaluation_status": evaluation_status or None,
                            "pass_with_coupled_verifier": pass_with_coupled_verifier,
                        },
                    )
                if non_empty(required_hooks) and hook_status in {"", "not_supplied", "absent", "missing", "fail_quiet", "not_evaluated"} and not explicit_descope:
                    add(
                        "block",
                        "required_gate_hook_missing_item_consumed",
                        "Consumed measurable pack items cannot depend on an acceptance-required gate hook that is absent, fail-quiet, or not_evaluated; preserve hook-supply work or residual scope.",
                        {
                            "item_id": item_id,
                            "directive_id": directive_id or None,
                            "gate_hook_status": hook_status or None,
                        },
                    )
                goal_axis_contract = (
                    record.get("goal_axis_contract")
                    if isinstance(record.get("goal_axis_contract"), dict)
                    else item.get("goal_axis_contract") if isinstance(item.get("goal_axis_contract"), dict)
                    else {}
                )
                goal_axis_gate = result.get("goal_axis_completeness_gate") if isinstance(result.get("goal_axis_completeness_gate"), dict) else {}
                pass_with_unobserved_axes = truthy(
                    goal_axis_gate.get("pass_with_unobserved_axes")
                    or goal_axis_contract.get("pass_with_unobserved_axes")
                    or result.get("pass_with_unobserved_axes")
                    or item.get("pass_with_unobserved_axes")
                )
                unobserved_goal_axes = (
                    goal_axis_gate.get("unobserved_goal_axes")
                    or goal_axis_contract.get("unobserved_goal_axes")
                    or result.get("unobserved_goal_axes")
                    or item.get("unobserved_goal_axes")
                )
                if (pass_with_unobserved_axes or non_empty(unobserved_goal_axes)) and not explicit_descope:
                    add(
                        "block",
                        "unobserved_goal_axes_item_consumed",
                        "Consumed review-backed measurable pack items require at least one mapped observing axis per active goal, or explicit residual/descope handling.",
                        {
                            "item_id": item_id,
                            "directive_id": directive_id or None,
                            "unobserved_goal_axes": unobserved_goal_axes or None,
                        },
                    )
                evidence_gate = result.get("evidence_provenance_gate") if isinstance(result.get("evidence_provenance_gate"), dict) else {}
                attested_only = truthy(result.get("attested_only_movement") or evidence_gate.get("attested_only_movement"))
                producer_attested = result.get("producer_attested_fields") or evidence_gate.get("producer_attested_fields")
                independently_verified = result.get("independently_verified_fields") or evidence_gate.get("independently_verified_fields")
                if (attested_only or (producer_attested and not independently_verified)) and not explicit_descope:
                    add(
                        "block",
                        "producer_attested_progress_item_consumed",
                        "Consumed measurable pack items cannot rely on producer-attested metric movement without independently verified evidence or explicit residual descope.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                verification_gate = result.get("verification_source_separation_gate") if isinstance(result.get("verification_source_separation_gate"), dict) else {}
                independent_source_status = str(
                    result.get("independent_source_separation_status")
                    or verification_gate.get("independent_source_separation_status")
                    or evidence_gate.get("independent_source_separation_status")
                    or ""
                ).strip().lower()
                independently_verified_downgraded = (
                    result.get("independently_verified_downgraded_fields")
                    or verification_gate.get("independently_verified_downgraded_fields")
                    or evidence_gate.get("independently_verified_downgraded_fields")
                )
                if independently_verified and independent_source_status in {"missing", "overlap", "blocked"} and not explicit_descope:
                    add(
                        "block",
                        "independent_verification_source_not_disjoint_item_consumed",
                        "Consumed measurable pack items cannot rely on independently_verified evidence unless verification_input_paths are disjoint from verified artifacts or the axis is self_grounded.",
                        {
                            "item_id": item_id,
                            "directive_id": directive_id or None,
                            "independent_source_separation_status": independent_source_status,
                        },
                    )
                if non_empty(independently_verified_downgraded) and not explicit_descope:
                    add(
                        "block",
                        "downgraded_independent_verification_item_consumed",
                        "Consumed measurable pack items cannot count independently_verified fields that were auto-downgraded to attested.",
                        {"item_id": item_id, "directive_id": directive_id or None, "downgraded_fields": independently_verified_downgraded},
                    )
                reachability_gate = result.get("acceptance_reachability_gate") if isinstance(result.get("acceptance_reachability_gate"), dict) else {}
                envelope_thaw_required = truthy(result.get("envelope_thaw_item_required") or reachability_gate.get("envelope_thaw_item_required"))
                envelope_thaw_item = result.get("envelope_thaw_item") or reachability_gate.get("envelope_thaw_item")
                if envelope_thaw_required and not (explicit_descope or non_empty(envelope_thaw_item)):
                    add(
                        "block",
                        "envelope_thaw_item_missing_item_consumed",
                        "Consumed measurable pack items cannot close acceptance that is unreachable under a frozen envelope without a reserved envelope_thaw_item or explicit residual/descope handling.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                diagnostics_gate = result.get("diagnostics_unavailable_gate") if isinstance(result.get("diagnostics_unavailable_gate"), dict) else {}
                instrumentation_required = truthy(result.get("instrumentation_supply_required") or diagnostics_gate.get("instrumentation_supply_required"))
                observable_without_instrumentation = truthy(
                    result.get("diagnostics_observable_without_new_instrumentation")
                    or result.get("existing_diagnostics_sufficient")
                    or result.get("success_failure_observable_without_instrumentation")
                )
                if instrumentation_required and not observable_without_instrumentation and not explicit_descope:
                    add(
                        "block",
                        "instrumentation_supply_missing_item_consumed",
                        "Consumed measurable pack items cannot close repeated diagnostics_unavailable without instrumentation supply or an explicit observability rationale.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                marginal_repair = truthy(record.get("marginal_repair") or item.get("marginal_repair"))
                next_rung = record.get("next_capability_rung") or item.get("next_capability_rung")
                higher_value = truthy(record.get("marginal_repair_higher_value") or item.get("marginal_repair_higher_value"))
                cost_policy = result.get("residual_gap_cost_policy") if isinstance(result.get("residual_gap_cost_policy"), dict) else {}
                residual_cost_below_policy = truthy(
                    record.get("residual_gap_cost_below_policy")
                    or item.get("residual_gap_cost_below_policy")
                    or result.get("residual_gap_cost_below_policy")
                    or cost_policy.get("below_policy")
                    or cost_policy.get("cost_disproportionate")
                )
                cycle_fixed_cost = record.get("cycle_fixed_cost") or item.get("cycle_fixed_cost") or result.get("cycle_fixed_cost") or cost_policy.get("cycle_fixed_cost")
                marginal_value_per_cycle_cost = (
                    record.get("marginal_value_per_cycle_cost")
                    or item.get("marginal_value_per_cycle_cost")
                    or result.get("marginal_value_per_cycle_cost")
                    or cost_policy.get("marginal_value_per_cycle_cost")
                )
                if marginal_repair and item.get("status") == "consumed" and not (explicit_descope and non_empty(next_rung)) and not higher_value:
                    add(
                        "block",
                        "marginal_repair_item_consumed_without_value_case",
                        "Consumed below-threshold residual-gap repairs require explicit descope plus the next capability rung, or recorded higher marginal value.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                if cycle_fixed_cost is not None and marginal_repair and not non_empty(marginal_value_per_cycle_cost):
                    add(
                        "block",
                        "residual_cycle_cost_ratio_missing_item_consumed",
                        "Consumed residual-gap repairs with cycle-cost evidence require `marginal_value_per_cycle_cost`.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                if residual_cost_below_policy and not (explicit_descope and non_empty(next_rung)) and not higher_value:
                    add(
                        "block",
                        "residual_cost_below_policy_item_consumed",
                        "Consumed residual-gap repairs below value-per-cycle-cost policy require residual descope plus the next capability rung, or recorded higher value.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                count_key_gate = result.get("count_key_hygiene_gate") if isinstance(result.get("count_key_hygiene_gate"), dict) else {}
                generation_dependent_count_key = truthy(
                    result.get("generation_dependent_count_key")
                    or count_key_gate.get("generation_dependent_count_key")
                    or item.get("generation_dependent_count_key")
                )
                generation_key_reset_claim = truthy(
                    result.get("family_novelty_claim")
                    or result.get("stall_reset_claim")
                    or count_key_gate.get("family_novelty_claim")
                    or count_key_gate.get("stall_reset_claim")
                )
                effective_count_key = result.get("effective_count_key") or count_key_gate.get("effective_count_key") or result.get("terminal_outcome_family_key")
                if generation_dependent_count_key and not non_empty(effective_count_key):
                    add(
                        "block",
                        "generation_count_key_without_effective_key_item_consumed",
                        "Consumed pack items with generation-dependent raw keys must preserve an effective adapter-collapsed count key or terminal-outcome fallback.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                if generation_dependent_count_key and generation_key_reset_claim:
                    add(
                        "block",
                        "generation_key_reset_claim_item_consumed",
                        "Consumed pack items cannot treat task/advice/pack/cycle/run/date/hash/version churn as a new family or stall reset.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )

    for item_id, residual_item_id in residual_links:
        residual = item_by_id.get(residual_item_id)
        if residual is None:
            add(
                "block",
                "scope_fidelity_residual_item_unknown",
                "`residual_item_id` must reference another pack item.",
                {"item_id": item_id, "residual_item_id": residual_item_id},
            )
        elif residual.get("status") not in OPEN_RESIDUAL_STATUSES:
            add(
                "block",
                "scope_fidelity_residual_item_not_open",
                "`residual_item_id` must remain open when the current item narrows a measurable directive.",
                {"item_id": item_id, "residual_item_id": residual_item_id, "residual_status": residual.get("status")},
            )

    in_flight_items = [
        str(item.get("item_id") or "")
        for item in items
        if isinstance(item, dict) and item.get("status") in {"promoted", "in_progress"}
    ]
    if len(in_flight_items) > 1:
        add(
            "block",
            "multiple_in_flight_pack_items",
            "A task pack may have at most one promoted/in-progress item at a time.",
            {"item_ids": in_flight_items},
        )

    current = data.get("current_item_id")
    if current and current not in seen_ids:
        add("block", "current_item_missing", "`current_item_id` does not match any item.", {"current_item_id": current})
    if data.get("status") == "terminal_blocked" and not data.get("terminal_blocker"):
        add("block", "terminal_blocker_missing", "`terminal_blocked` pack requires `terminal_blocker`.")
    terminal = data.get("terminal_blocker")
    if isinstance(terminal, dict):
        for field in ("semantic_signature", "blocker_signature", "required_handoff", "evidence_paths"):
            if not terminal.get(field):
                add("block", "terminal_blocker_field_missing", f"`terminal_blocker` requires `{field}`.", {"field": field})
        if terminal.get("provider_reattempt_required") is True:
            add(
                "block",
                "provider_terminal_seal_before_bounded_retry",
                "Task pack cannot terminal-block a provider family while bounded provider retry is still required.",
            )
        if terminal.get("authorized_alternative_path_exists") is True and not terminal.get("authorized_alternative_path_attempted"):
            add(
                "block",
                "seal_denied_authorized_alternative_unattempted",
                "Task pack cannot seal a family while an authority-permitted productive alternative remains unattempted.",
            )
        if terminal.get("untried_actionable_root_cause_exists") is True:
            add(
                "block",
                "seal_denied_untried_actionable_root_cause",
                "Task pack cannot terminal-block while a local, bounded, provider-free, in-scope, authority-allowed root-cause hypothesis remains untried.",
            )
        if terminal.get("terminal_quiescence") is True and terminal.get("commit_skipped_reason") != "terminal_quiescence":
            add(
                "warn",
                "terminal_quiescence_missing_commit_skip_reason",
                "Terminal quiescence should record `commit_skipped_reason: terminal_quiescence` to prevent closeout/report/recheck reproduction.",
            )
    if not isinstance(data.get("mutation_log", []), list):
        add("block", "mutation_log_invalid", "`mutation_log` must be a list.")
    return findings


def status_from_findings(findings: list[dict[str, Any]]) -> str:
    if any(item.get("severity") == "block" for item in findings):
        return "block"
    if findings:
        return "warn"
    return "ok"


def active_pack_candidates(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return [
        (path, data)
        for path in pack_paths(root)
        for data in [load_json(path)]
        if data.get("status") == "active"
    ]


def task_pack_store_findings(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    pending = task_pack_replacement.pending_transaction_ids(root)
    if pending:
        findings.append(
            {
                "severity": "block",
                "code": "replacement_transaction_pending",
                "message": "A prepared task-pack replacement requires forward recovery before other reads or mutations.",
                "evidence": {"transaction_ids": pending},
            }
        )
    active = active_pack_candidates(root)
    if len(active) > 1:
        findings.append(
            {
                "severity": "block",
                "code": "multiple_active_task_packs",
                "message": "Task-pack store must contain at most one active pack.",
                "evidence": {"active_pack_refs": [rel_path(root, path) for path, _data in active]},
            }
        )
    return findings


def active_pack(root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    findings = task_pack_store_findings(root)
    if findings:
        raise SystemExit(findings[0]["message"])
    active = active_pack_candidates(root)
    return active[0] if active else (None, None)


def sorted_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted((item for item in data.get("items", []) if isinstance(item, dict)), key=lambda item: item.get("order", 0))


def item_order(data: dict[str, Any]) -> list[str]:
    return [str(item.get("item_id")) for item in sorted_items(data) if item.get("item_id")]


def renumber_items(data: dict[str, Any]) -> None:
    for index, item in enumerate((item for item in data.get("items", []) if isinstance(item, dict)), start=1):
        item["order"] = index


def planned_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in sorted_items(data) if item.get("status") in {"planned", "inserted", "reordered", "blocked"}]


def active_in_flight_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in sorted_items(data) if item.get("status") in {"promoted", "in_progress"}]


def refresh_current_item(data: dict[str, Any]) -> None:
    remaining = [item for item in planned_items(data) if item.get("status") in {"planned", "inserted", "reordered"}]
    data["current_item_id"] = remaining[0].get("item_id") if remaining else None
    in_flight = any(
        isinstance(item, dict) and item.get("status") in {"promoted", "in_progress"}
        for item in data.get("items", [])
    )
    if not remaining and not in_flight and data.get("status") == "active":
        data["status"] = "completed"


def evidence_paths_from(plan: dict[str, Any]) -> list[str]:
    value = plan.get("evidence_paths") or plan.get("evidence") or []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def mutation_entry(action: str, plan: dict[str, Any], before_order: list[str], after_order: list[str]) -> dict[str, Any]:
    reason = str(plan.get("reason") or plan.get("mutation_reason") or "").strip()
    if not reason:
        raise SystemExit("Mutation plan requires `reason`.")
    return {
        "timestamp": now_iso(),
        "action": action,
        "reason": reason,
        "evidence_paths": evidence_paths_from(plan),
        "before_order": before_order,
        "after_order": after_order,
        "actor": str(plan.get("actor") or "$derive-improvement-task"),
    }


def next_item(data: dict[str, Any]) -> dict[str, Any] | None:
    current = data.get("current_item_id")
    items = sorted_items(data)
    if current:
        for item in items:
            if item.get("item_id") == current and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
                return item
    for item in items:
        if item.get("status") in {"planned", "inserted", "reordered"}:
            return item
    return None


def _require_packet_task(packet: dict[str, Any], expected_task_id: str, label: str) -> None:
    observed = str(packet_field(packet, "task_id") or "").strip()
    if not observed or observed != expected_task_id:
        raise SystemExit(f"{label} must be bound to validated_task_id={expected_task_id}.")


def _require_packet_not_blocked(packet: dict[str, Any], label: str) -> None:
    if isinstance(packet.get("result"), dict):
        envelope_status = str(packet.get("status") or "").strip().lower()
        if envelope_status not in {"ok", "pass", "passed"}:
            raise SystemExit(f"{label} result-contract envelope must have status ok/pass.")
        envelope_findings = packet.get("findings")
        if not isinstance(envelope_findings, list):
            raise SystemExit(f"{label} result-contract envelope requires an explicit findings list.")
    else:
        raw_status = str(packet.get("status") or "").strip().lower()
        if raw_status in {"block", "blocked", "error", "failed", "invalid"}:
            raise SystemExit(f"{label} carries a blocking status.")
        envelope_findings = packet.get("findings", [])
        if not isinstance(envelope_findings, list):
            raise SystemExit(f"{label} findings must be a JSON list when present.")
    findings_sets = [envelope_findings]
    payload = packet.get("result")
    if isinstance(payload, dict) and "findings" in payload:
        payload_findings = payload.get("findings")
        if not isinstance(payload_findings, list):
            raise SystemExit(f"{label} nested findings must be a JSON list.")
        findings_sets.append(payload_findings)
    for findings in findings_sets:
        if any(
            isinstance(finding, dict)
            and str(finding.get("severity") or finding.get("status") or "").strip().lower()
            in {"block", "blocked", "error", "failed", "high", "critical"}
            for finding in findings
        ):
            raise SystemExit(f"{label} contains a blocking finding.")


def _require_empty_packet_blockers(packet: dict[str, Any], label: str) -> None:
    blockers = packet_field(packet, "blockers")
    if not isinstance(blockers, list) or blockers:
        raise SystemExit(f"{label} must contain an explicit empty blockers list.")


def _issue_identifier_present(packet: dict[str, Any]) -> bool:
    for key in ("issue_id", "issue_ids", "issue_path", "issue_paths", "issue_url", "issue_urls"):
        if non_empty(packet_field(packet, key)):
            return True
    return False


def validate_promotion_provenance(
    root: Path,
    plan: dict[str, Any],
    validated_task_id: str,
    declared_validation_verdict: str,
) -> dict[str, Any]:
    run_path, run_packet, run_digest = load_bound_packet(
        root,
        plan.get("run_report_path"),
        plan.get("run_report_sha256"),
        "Promotion run report",
    )
    if str(packet_field(run_packet, "step") or "").strip() != "run":
        raise SystemExit("Promotion run report must declare step=run.")
    _require_packet_not_blocked(run_packet, "Promotion run report")
    _require_packet_task(run_packet, validated_task_id, "Promotion run report")
    _require_empty_packet_blockers(run_packet, "Promotion run report")
    execution_status = str(packet_field(run_packet, "execution_status") or "").strip().lower()
    if execution_status not in PROMOTION_TERMINAL_EXECUTION_STATUSES:
        raise SystemExit("Promotion requires a terminal run report with no pending execution.")
    if packet_field(run_packet, "long_run_branch") is True:
        long_run_role = str(packet_field(run_packet, "long_run_role") or "").strip().lower()
        if long_run_role not in {"harvest", "finalize"}:
            raise SystemExit("Promotion cannot advance while a long-running execution remains at launch or monitor state.")
    run_evidence = verify_evidence_files(root, packet_field(run_packet, "evidence_paths"), "Run report evidence_paths")

    validation_path, validation_packet, validation_digest = load_bound_packet(
        root,
        plan.get("validation_report_path"),
        plan.get("validation_report_sha256"),
        "Promotion validation report",
    )
    if str(packet_field(validation_packet, "step") or "").strip() != "validate":
        raise SystemExit("Promotion validation report must declare step=validate.")
    _require_packet_not_blocked(validation_packet, "Promotion validation report")
    _require_packet_task(validation_packet, validated_task_id, "Promotion validation report")
    packet_verdict = str(packet_field(validation_packet, "validation_verdict") or "").strip().lower()
    if packet_verdict not in PROMOTION_VALIDATION_VERDICTS:
        raise SystemExit("Promotion validation report must carry a complete/pass verdict.")
    if declared_validation_verdict not in PROMOTION_VALIDATION_VERDICTS:
        raise SystemExit("Promotion validation_verdict must be complete, pass, or passed.")
    _require_empty_packet_blockers(validation_packet, "Promotion validation report")
    validation_packet_evidence = verify_evidence_files(
        root,
        packet_field(validation_packet, "evidence_paths"),
        "Validation report evidence_paths",
    )
    declared_validation_evidence = verify_evidence_files(
        root,
        plan.get("validation_evidence_paths"),
        "Promotion validation_evidence_paths",
    )
    validation_report_relative = rel_path(root, validation_path)
    if validation_report_relative not in declared_validation_evidence:
        raise SystemExit("Promotion validation_evidence_paths must include validation_report_path.")

    issue_path, issue_packet, issue_digest = load_bound_packet(
        root,
        plan.get("issue_packet_path"),
        plan.get("issue_packet_sha256"),
        "Promotion issue packet",
    )
    if str(packet_field(issue_packet, "step") or "").strip() != "issue":
        raise SystemExit("Promotion issue packet must declare step=issue.")
    _require_packet_not_blocked(issue_packet, "Promotion issue packet")
    _require_packet_task(issue_packet, validated_task_id, "Promotion issue packet")
    _require_empty_packet_blockers(issue_packet, "Promotion issue packet")
    issue_status = str(packet_field(issue_packet, "issue_status") or "").strip().lower()
    if issue_status not in ISSUE_NOOP_STATUSES | ISSUE_MUTATION_STATUSES:
        raise SystemExit("Promotion issue packet must record a completed issue reconciliation or an explicit no-op.")
    issue_provenance = packet_field(issue_packet, "issue_provenance")
    if not isinstance(issue_provenance, dict) or str(issue_provenance.get("source_task_id") or "").strip() != validated_task_id:
        raise SystemExit("Promotion issue packet provenance must identify the validated task.")
    provenance_report_value = str(issue_provenance.get("validation_report_path") or "").strip()
    provenance_report = bounded_workspace_file(root, provenance_report_value, "Issue validation_report_path")
    if provenance_report != validation_path:
        raise SystemExit("Promotion issue packet provenance must cite the exact bound validation report.")
    if issue_status in ISSUE_NOOP_STATUSES:
        if not non_empty(packet_field(issue_packet, "issue_skipped_reason")):
            raise SystemExit("Promotion issue no-op requires issue_skipped_reason.")
    elif not _issue_identifier_present(issue_packet):
        raise SystemExit("Promotion issue reconciliation must identify the durable issue record it handled.")
    issue_evidence = verify_evidence_files(root, packet_field(issue_packet, "evidence_paths"), "Issue packet evidence_paths")

    return {
        "execution_status": execution_status,
        "run_report_path": rel_path(root, run_path),
        "run_report_sha256": run_digest,
        "run_evidence_paths": run_evidence,
        "validation_report_path": validation_report_relative,
        "validation_report_sha256": validation_digest,
        "validation_packet_evidence_paths": validation_packet_evidence,
        "validation_evidence_paths": declared_validation_evidence,
        "issue_packet_path": rel_path(root, issue_path),
        "issue_packet_sha256": issue_digest,
        "issue_status": issue_status,
        "issue_evidence_paths": issue_evidence,
    }


def validate_initial_selection_provenance(
    root: Path,
    path: Path,
    data: dict[str, Any],
    plan: dict[str, Any],
    *,
    item_id: str,
    task_id: str,
    task_digest: str,
    promotion_origin: str,
) -> dict[str, Any]:
    """Validate first-item bootstrap/authority provenance in the promotion transaction."""

    if promotion_origin not in {"bootstrap_initial_selection", "authorized_initial_selection"}:
        raise SystemExit("Initial selection requires a bootstrap or authorized promotion origin.")
    ordered = sorted_items(data)
    if not ordered or str(ordered[0].get("item_id") or "") != item_id or ordered[0].get("order") != 1:
        raise SystemExit("Initial selection origin is valid only for the first canonical pack item.")
    if any(
        isinstance(item, dict) and item.get("status") in {"promoted", "in_progress", "consumed"}
        for item in data.get("items", [])
    ):
        raise SystemExit("Initial selection origin cannot be reused after any pack item was promoted or consumed.")
    prior_actions = {
        str(item.get("action") or "")
        for item in data.get("mutation_log", [])
        if isinstance(item, dict) and item.get("action")
    }
    if prior_actions - {"create"}:
        raise SystemExit("Initial selection must bind to the unmodified pack-creation snapshot.")

    receipt = plan.get("initial_selection_receipt")
    if not isinstance(receipt, dict):
        raise SystemExit("Initial selection requires `initial_selection_receipt` in the promotion transaction.")
    if str(receipt.get("initial_item_id") or "") != item_id:
        raise SystemExit("Initial selection receipt item identity differs from the selected first item.")
    verified = validate_initial_selection_receipt(
        root,
        path,
        data,
        receipt,
        task_id=task_id,
        task_digest=task_digest,
        operation="promote",
        require_mutation_binding=False,
    )
    receipt_digest = sha256_bytes(
        json.dumps(verified, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return {
        "promotion_origin": promotion_origin,
        "initial_selection_receipt": verified,
        "initial_selection_receipt_ref": f"inline:sha256:{receipt_digest}",
        "predecessor_completion_receipt_ref": None,
    }


def consume_in_flight_for_atomic_promotion(
    root: Path,
    data: dict[str, Any],
    completion_plan: dict[str, Any],
    *,
    require_current_verdicts: bool,
) -> str:
    """Consume exactly one promoted item in memory before promoting its successor."""

    in_flight = active_in_flight_items(data)
    if len(in_flight) != 1:
        raise SystemExit("Atomic consume-and-promote requires exactly one in-flight pack item.")
    item = in_flight[0]
    promotion = item.get("promotion")
    if not isinstance(promotion, dict):
        raise SystemExit("Atomic consume-and-promote requires preserved promotion provenance.")
    completed_task_id = str(promotion.get("task_id") or "").strip()
    declared_task_id = str(completion_plan.get("task_id") or completion_plan.get("validated_task_id") or "").strip()
    if not completed_task_id or declared_task_id != completed_task_id:
        raise SystemExit("Atomic completion task identity must match the in-flight promotion.")
    validation_verdict = str(completion_plan.get("validation_verdict") or "").strip().lower()
    completion_provenance = validate_promotion_provenance(
        root,
        completion_plan,
        completed_task_id,
        validation_verdict,
    )
    item["completion"] = {
        "completed_task_id": completed_task_id,
        "completed_at": now_iso(),
        "validation_verdict": validation_verdict,
        "completion_evidence_paths": verify_evidence_files(
            root,
            completion_plan.get("evidence_paths"),
            "Atomic completion evidence_paths",
        ),
        **completion_provenance,
    }
    item["status"] = "consumed"
    result = item.setdefault("result", {})
    result["validation_verdict"] = validation_verdict
    for field in (
        "progress_verdict",
        "progress_kind",
        "semantic_signature",
        "blocker_signature",
    ):
        if completion_plan.get(field) is not None:
            result[field] = completion_plan.get(field)
    preserve_verdict_axes(result, completion_plan, require_current=require_current_verdicts)
    data.setdefault("mutation_log", []).append(
        {
            "timestamp": now_iso(),
            "action": "mark_consumed",
            "reason": completion_plan.get("reason") or "atomic predecessor completion",
            "item_id": item.get("item_id"),
            "actor": "$derive-improvement-task",
            "atomic_with_next_promotion": True,
        }
    )
    refresh_current_item(data)
    return completed_task_id


def render_markdown(root: Path, path: Path, data: dict[str, Any], language: str) -> str:
    ko = language.lower().startswith("ko")
    title = "Task Pack" if not ko else "Task Pack"
    labels = {
        "status": "Status" if not ko else "상태",
        "goal": "Goal" if not ko else "목표",
        "current": "Current Item" if not ko else "현재 item",
        "terminal": "Terminal Blocker" if not ko else "terminal blocker",
        "items": "Items" if not ko else "Items",
        "mutations": "Mutation Log" if not ko else "Mutation Log",
    }
    lines = [
        f"# {title}: {data.get('pack_id', path.stem)}",
        "",
        f"- {labels['status']}: {data.get('status')}",
        f"- {labels['goal']}: {data.get('goal')}",
        f"- {labels['current']}: {data.get('current_item_id') or 'none'}",
        f"- JSON: `{rel_path(root, path)}`",
        "",
        f"## {labels['items']}",
        "",
    ]
    for item in sorted_items(data):
        scope_records, _ = scope_fidelity_records(item)
        scope_summary = "none"
        if scope_records:
            parts = []
            for record in scope_records:
                directive_id = str(record.get("directive_id") or "unknown")
                narrowed = "narrowed" if truthy(record.get("narrowed")) else "full"
                residual = str(record.get("residual_item_id") or "none")
                parts.append(f"{directive_id}:{narrowed}:residual={residual}")
            scope_summary = "; ".join(parts)
        lines.extend(
            [
                f"### {item.get('order')}. {item.get('title')}",
                "",
                f"- item_id: `{item.get('item_id')}`",
                f"- status: `{item.get('status')}`",
                f"- progress_target: `{item.get('progress_target')}`",
                f"- progress_kind_expected: `{item.get('progress_kind_expected') or 'none'}`",
                f"- item_kind: `{item.get('item_kind') or 'none'}`",
                f"- validation_profile: `{item.get('validation_profile')}`",
                f"- semantic_signature_expected: `{item.get('semantic_signature_expected') or 'none'}`",
                f"- positive_input_delta_required: `{item.get('positive_input_delta_required', False)}`",
                f"- required_new_input_kinds: {', '.join(str(value) for value in item.get('required_new_input_kinds', [])) or 'none'}",
                f"- scope_fidelity: {scope_summary}",
                "",
                str(item.get("objective") or "").strip(),
                "",
            ]
        )
    if data.get("terminal_blocker"):
        lines.extend([f"## {labels['terminal']}", "", "```json", json.dumps(data["terminal_blocker"], ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
    if data.get("mutation_log"):
        lines.extend([f"## {labels['mutations']}", ""])
        for mutation in data.get("mutation_log", []):
            if isinstance(mutation, dict):
                lines.append(f"- {mutation.get('timestamp')}: {mutation.get('action')} - {mutation.get('reason')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_path(path: Path) -> Path:
    return path.with_suffix(".md")


def bounded_render_path(root: Path, path: Path) -> Path:
    return _require_within(render_path(path), pack_dir(root), "Task pack Markdown render path")


def write_render(root: Path, path: Path, data: dict[str, Any], language: str) -> Path:
    output = bounded_render_path(root, path)
    write_bytes_atomic(output, render_markdown(root, path, data, language).encode("utf-8"))
    return output


def command_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root, create=False):
        return _command_status_locked(root)


def _command_status_locked(root: Path) -> int:
    store_findings = task_pack_store_findings(root)
    active = active_pack_candidates(root)
    path, data = active[0] if len(active) == 1 else (None, None)
    active_refs = [rel_path(root, candidate) for candidate, _body in active]
    if store_findings:
        output = {
            "status": "block",
            "active_pack": rel_path(root, path) if path else None,
            "active_pack_count": len(active),
            "active_pack_refs": active_refs,
            "pack_count": len(pack_paths(root)),
            "findings": store_findings,
        }
    if not path or not data:
        if not store_findings:
            output = {
                "status": "not_applicable",
                "active_pack": None,
                "active_pack_count": 0,
                "active_pack_refs": [],
                "pack_count": len(pack_paths(root)),
                "findings": [],
            }
    elif not store_findings:
        findings = validate_pack(data, path)
        in_flight = active_in_flight_items(data)
        item = None if in_flight else next_item(data)
        output = {
            "status": status_from_findings(findings),
            "active_pack": rel_path(root, path),
            "render_path": rel_path(root, bounded_render_path(root, path)) if bounded_render_path(root, path).exists() else None,
            "pack_id": data.get("pack_id"),
            "pack_status": data.get("status"),
            "goal": data.get("goal"),
            "current_item_id": data.get("current_item_id"),
            "next_item": item,
            "queue_disposition": "in_flight" if in_flight else "ready" if item else "terminal_candidate",
            "in_flight_item": in_flight[0] if len(in_flight) == 1 else None,
            "planned_item_count": sum(1 for item_data in data.get("items", []) if isinstance(item_data, dict) and item_data.get("status") in {"planned", "inserted", "reordered"}),
            "terminal_blocker": data.get("terminal_blocker"),
            "findings": findings,
            "pack_count": len(pack_paths(root)),
            "active_pack_count": 1,
            "active_pack_refs": active_refs,
        }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] not in {"block"} else 2


def command_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root, create=False):
        return _command_validate_locked(root, args)


def _command_validate_locked(root: Path, args: argparse.Namespace) -> int:
    paths = [resolve_pack_path(root, args.pack)] if args.pack else pack_paths(root)
    results = []
    store_findings = task_pack_store_findings(root)
    status = status_from_findings(store_findings)
    for path in paths:
        data = load_json(path)
        findings = validate_pack(data, path)
        result_status = status_from_findings(findings)
        if result_status == "block":
            status = "block"
        elif result_status == "warn" and status == "ok":
            status = "warn"
        results.append({"path": rel_path(root, path), "status": result_status, "findings": findings})
    strict = bool(getattr(args, "strict_findings", False))
    output = {
        "status": status,
        "strict_findings": strict,
        "store_findings": store_findings,
        "results": results,
        "pack_count": len(results),
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 2 if status == "block" or (strict and status != "ok") else 0


def capability_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "helper": "task_pack_queue",
        "pack_schema_versions": [1],
        "actions": [
            "create_pack",
            "replace_pack",
            "promote_next_item",
            "normalize_initial_selection_provenance",
            "insert_items",
            "reorder_items",
            "skip_items",
            "supersede_pack",
            "terminal_blocked",
        ],
        "canonical_progress_targets": sorted(PROGRESS_TARGETS),
        "canonical_progress_kinds": sorted(PROGRESS_KINDS),
        "verdict_axes": list(VERDICT_AXES),
        "item_kind": {
            "supported": True,
            "required": False,
            "vocabulary": "open",
            "syntax": "bounded_path_safe_token",
            "authoritative_for_progress": False,
        },
        "publication": {
            "create_findings_policy": "clean",
            "replace_successor_findings_policy": "clean",
            "max_active_packs": 1,
            "optional_initial_selection": True,
            "prospective_task_preflight": "hash_bound_workspace_staging_ref",
            "replacement_recovery": "fail_closed_forward_complete",
            "replacement_plan_binding": "content_addressed_plan_and_target_manifest",
            "replacement_receipt_supply": "exact_durable_receipt_with_ref_and_sha256",
            "live_predecessor_retirement": "explicit_reason_and_hash_bound_evidence",
            "atomic_scope": "task_pack_store_and_helper_owned_evidence",
            "task_md_in_atomic_scope": False,
        },
        "size_policy": {
            "new_sequence_min": 2,
            "new_sequence_max": 5,
            "replacement_max_new_items": 5,
            "replacement_over_five_requires_carry_forward_contract": True,
        },
    }


def publication_findings(
    data: dict[str, Any],
    path: Path,
    *,
    check_size: bool,
    prospective_task_digests: set[str] | None = None,
) -> list[dict[str, Any]]:
    findings = validate_pack(data, path, prospective_task_digests=prospective_task_digests)
    if check_size:
        items = data.get("items") if isinstance(data.get("items"), list) else []
        if not 2 <= len(items) <= 5:
            findings.append(
                {
                    "severity": "block",
                    "code": "new_pack_item_count_out_of_bounds",
                    "message": "A newly derived pack must contain 2-5 items; larger replacements require exact carry-forward binding.",
                    "evidence": {"item_count": len(items)},
                }
            )
    if findings and not any(item.get("code") == "publication_findings_not_clean" for item in findings):
        findings.append(
            {
                "severity": "block",
                "code": "publication_findings_not_clean",
                "message": "New task-pack publication requires findings=[].",
                "evidence": {"finding_codes": [str(item.get("code")) for item in findings]},
            }
        )
    return findings


def command_capabilities(_args: argparse.Namespace) -> int:
    json.dump(capability_contract(), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_recover_replacement(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root):
        pending = task_pack_replacement.pending_transaction_ids(root)
        if len(pending) > 1:
            raise SystemExit("Multiple pending task-pack replacements require manual integrity review.")
        receipts = [
            task_pack_replacement.publish_transaction(
                root,
                transaction_id,
                postcondition=lambda prepare: replacement_postcondition(root, prepare),
            )
            for transaction_id in pending
        ]
    output = {
        "status": "ok",
        "recovered_count": len(receipts),
        "receipts": receipts,
        "remaining_pending_transaction_ids": task_pack_replacement.pending_transaction_ids(root),
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_render(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root):
        store_findings = task_pack_store_findings(root)
        if store_findings:
            output = {"status": "block", "rendered": [], "findings": store_findings}
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2
        paths = [resolve_pack_path(root, args.pack)] if args.pack else pack_paths(root)
        rendered = []
        for path in paths:
            data = load_json(path)
            findings = validate_pack(data, path)
            if any(item.get("severity") == "block" for item in findings):
                rendered.append({"path": rel_path(root, path), "status": "block", "findings": findings})
                continue
            output_path = write_render(root, path, data, args.language)
            rendered.append({"path": rel_path(root, path), "status": "rendered", "render_path": rel_path(root, output_path), "findings": findings})
    output = {"status": "block" if any(item["status"] == "block" for item in rendered) else "ok", "rendered": rendered}
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] != "block" else 2


def command_next(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root, create=False):
        return _command_next_locked(root)


def _command_next_locked(root: Path) -> int:
    path, data = active_pack(root)
    if not path or not data:
        output = {"status": "not_applicable", "next_item": None}
    else:
        in_flight = active_in_flight_items(data)
        item = None if in_flight else next_item(data)
        output = {
            "status": "in_flight" if in_flight else "ok" if item else "terminal_candidate",
            "pack_path": rel_path(root, path),
            "pack_id": data.get("pack_id"),
            "next_item": item,
            "in_flight_item": in_flight[0] if len(in_flight) == 1 else None,
            "terminal_blocker": data.get("terminal_blocker"),
        }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def apply_initial_selection_to_new_pack(
    root: Path,
    path: Path,
    pack_data: dict[str, Any],
    initial_selection: dict[str, Any] | None,
    durable_creation: dict[str, Any],
    *,
    check_size: bool,
    dry_run: bool = False,
) -> tuple[bool, list[dict[str, Any]]]:
    if not isinstance(initial_selection, dict):
        return False, publication_findings(pack_data, path, check_size=check_size)
    pack_id = str(pack_data.get("pack_id") or "")
    item_id = str(initial_selection.get("item_id") or "").strip()
    task_id = str(initial_selection.get("task_id") or "").strip()
    task_path_value = str(initial_selection.get("task_path") or "task.md")
    origin = str(initial_selection.get("promotion_origin") or "bootstrap_initial_selection")
    if origin not in {"bootstrap_initial_selection", "authorized_initial_selection"}:
        raise SystemExit("Create/replace initial_selection requires an initial promotion origin.")
    target = next(
        (
            item
            for item in pack_data.get("items", [])
            if isinstance(item, dict) and str(item.get("item_id") or "") == item_id
        ),
        None,
    )
    ordered = sorted_items(pack_data)
    if target is None or not ordered or target is not ordered[0] or target.get("order") != 1:
        raise SystemExit("Create/replace initial_selection must target the first canonical pack item.")
    if target.get("status") != "planned":
        raise SystemExit("Create/replace initial_selection requires a planned first item.")
    task_path = bounded_workspace_path(root, task_path_value, "Create/replace initial task_path")
    prospective_ref = str(initial_selection.get("prospective_task_ref") or "").strip()
    prospective_digest = str(initial_selection.get("prospective_task_sha256") or "").strip()
    prospective_path: Path | None = None
    prospective_bytes: bytes | None = None
    if prospective_ref or prospective_digest:
        prospective_path = bounded_workspace_file(
            root,
            prospective_ref,
            "Create/replace prospective_task_ref",
        )
        require_file_digest(
            prospective_path,
            prospective_digest,
            "Create/replace prospective task",
        )
        prospective_bytes = prospective_path.read_bytes()
    if dry_run and prospective_bytes is not None:
        task_bytes = prospective_bytes
        task_digest = sha256_bytes(task_bytes)
    elif task_path.is_file():
        task_bytes = task_path.read_bytes()
        task_digest = sha256_bytes(task_bytes)
        if prospective_bytes is not None and task_bytes != prospective_bytes:
            raise SystemExit("Canonical task bytes differ from the preflight prospective task.")
    else:
        raise SystemExit(
            "Create/replace initial task_path is missing; dry-run requires a hash-bound prospective_task_ref."
        )
    snapshot_directory = _require_within(
        pack_dir(root) / "task_snapshots" / pack_id,
        pack_dir(root),
        "Create/replace initial task snapshot directory",
    )
    snapshot_name = f"{item_id[:48]}-{task_id[:48]}-{task_digest[:16]}.md"
    task_snapshot_path = _require_within(
        snapshot_directory / snapshot_name,
        pack_dir(root),
        "Create/replace initial task snapshot path",
    )
    write_content_addressed_file(task_snapshot_path, task_bytes, "Create/replace initial task snapshot")
    supplied_receipt = initial_selection.get("initial_selection_receipt")
    if not isinstance(supplied_receipt, dict):
        raise SystemExit("Create/replace initial_selection requires initial_selection_receipt.")
    if supplied_receipt.get("task_snapshot_ref") != rel_path(root, task_snapshot_path):
        raise SystemExit("Create/replace initial-selection receipt references a different task snapshot.")
    if supplied_receipt.get("pack_creation_snapshot_ref") != durable_creation.get("creation_snapshot_ref"):
        raise SystemExit("Create/replace initial-selection receipt references a different creation snapshot.")
    verified = validate_initial_selection_receipt(
        root,
        path,
        pack_data,
        supplied_receipt,
        task_id=task_id,
        task_digest=task_digest,
        operation="promote",
        require_mutation_binding=False,
    )
    inline_digest = sha256_bytes(
        json.dumps(verified, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    target["status"] = "promoted"
    target["promotion"] = {
        "task_id": task_id,
        "task_path": rel_path(root, task_path),
        "task_sha256": task_digest,
        "task_snapshot_path": rel_path(root, task_snapshot_path),
        "promoted_at": supplied_receipt.get("created_at"),
        "mutation_evidence_paths": verify_evidence_files(
            root,
            initial_selection.get("evidence_paths"),
            "Create/replace initial-selection evidence_paths",
        )
        if initial_selection.get("evidence_paths")
        else [],
        "promotion_origin": origin,
        "initial_selection_receipt": verified,
        "initial_selection_receipt_ref": f"inline:sha256:{inline_digest}",
        "predecessor_completion_receipt_ref": None,
    }
    promote_entry = mutation_entry("promote", initial_selection, item_order(pack_data), item_order(pack_data))
    promote_entry.update(
        {
            "timestamp": supplied_receipt.get("created_at"),
            "item_id": item_id,
            "task_id": task_id,
            "validated_task_id": None,
            "promotion_origin": origin,
            "before_pack_sha256": durable_creation.get("creation_snapshot_canonical_sha256"),
        }
    )
    pack_data.setdefault("mutation_log", []).append(promote_entry)
    refresh_current_item(pack_data)
    allowed_prospective = {task_digest} if dry_run and prospective_bytes is not None else None
    return True, publication_findings(
        pack_data,
        path,
        check_size=check_size,
        prospective_task_digests=allowed_prospective,
    )


def item_planning_contract(item: dict[str, Any]) -> dict[str, Any]:
    lifecycle_fields = {"order", "status", "promotion", "completion", "result"}
    return {
        str(key): copy.deepcopy(value)
        for key, value in sorted(item.items(), key=lambda pair: str(pair[0]))
        if key not in lifecycle_fields
    }


def item_planning_contract_sha256(item: dict[str, Any]) -> str:
    payload = json.dumps(item_planning_contract(item), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return sha256_bytes(payload.encode("utf-8"))


def validate_retired_items_contract(
    root: Path,
    retired_items: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    if not isinstance(retired_items, list) or not all(isinstance(value, dict) for value in retired_items):
        return (
            [
                {
                    "severity": "block",
                    "code": "replacement_retired_items_invalid",
                    "message": "Replacement contract retired_items must be a list of disposition objects.",
                }
            ],
            [],
        )
    retired_ids: list[str] = []
    for retired in retired_items:
        item_id = str(retired.get("item_id") or "")
        reason = str(retired.get("reason") or "").strip()
        evidence = retired.get("evidence")
        if not item_id or not reason or len(reason) > 500 or not isinstance(evidence, list) or not evidence:
            findings.append(
                {
                    "severity": "block",
                    "code": "replacement_retired_item_incomplete",
                    "message": "Each retired predecessor item requires item_id, a bounded reason, and non-empty hash-bound evidence.",
                    "evidence": {"item_id": item_id or None},
                }
            )
            continue
        for evidence_item in evidence:
            try:
                if not isinstance(evidence_item, dict):
                    raise SystemExit("Retirement evidence entry must be an object.")
                evidence_path = bounded_workspace_file(
                    root,
                    evidence_item.get("path"),
                    f"Replacement retired item {item_id} evidence",
                )
                try:
                    evidence_path.relative_to(pack_dir(root).resolve())
                except ValueError:
                    pass
                else:
                    raise SystemExit(
                        "Retirement evidence must remain outside the mutable task-pack transaction store."
                    )
                require_file_digest(
                    evidence_path,
                    evidence_item.get("sha256"),
                    f"Replacement retired item {item_id} evidence",
                )
            except SystemExit as exc:
                findings.append(
                    {
                        "severity": "block",
                        "code": "replacement_retired_item_evidence_invalid",
                        "message": str(exc),
                        "evidence": {"item_id": item_id},
                    }
                )
        retired_ids.append(item_id)
    return findings, retired_ids


def validate_carry_forward_contract(
    root: Path,
    predecessor_path: Path,
    predecessor: dict[str, Any],
    successor: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    findings: list[dict[str, Any]] = []
    bindings: list[dict[str, str]] = []

    def add(code: str, message: str, evidence: Any = None) -> None:
        finding: dict[str, Any] = {"severity": "block", "code": code, "message": message}
        if evidence is not None:
            finding["evidence"] = evidence
        findings.append(finding)

    contract = successor.get("replacement_contract")
    if not isinstance(contract, dict) or contract.get("schema_version") != 1:
        add("replacement_contract_missing", "Replacement successor requires replacement_contract schema version 1.")
        return findings, bindings
    expected_ref = rel_path(root, predecessor_path)
    if contract.get("predecessor_pack_ref") != expected_ref:
        add("replacement_predecessor_ref_mismatch", "Replacement contract names a different predecessor pack.")
    if contract.get("predecessor_pack_file_sha256") != sha256_file(predecessor_path):
        add("replacement_predecessor_file_sha_mismatch", "Replacement contract predecessor file digest is stale.")
    if contract.get("predecessor_pack_canonical_sha256") != canonical_pack_sha256(predecessor):
        add("replacement_predecessor_canonical_sha_mismatch", "Replacement contract predecessor canonical digest is stale.")
    new_ids = contract.get("new_item_ids")
    carried_ids = contract.get("carried_forward_item_ids")
    retired_items = contract.get("retired_items", [])
    if not isinstance(new_ids, list) or not all(isinstance(value, str) and value for value in new_ids):
        add("replacement_new_item_ids_invalid", "Replacement contract requires an explicit new_item_ids list.")
        new_ids = []
    if not isinstance(carried_ids, list) or not all(isinstance(value, str) and value for value in carried_ids):
        add("replacement_carried_item_ids_invalid", "Replacement contract requires an explicit carried_forward_item_ids list.")
        carried_ids = []
    new_ids = [str(value) for value in new_ids]
    carried_ids = [str(value) for value in carried_ids]
    retired_findings, retired_ids = validate_retired_items_contract(root, retired_items)
    findings.extend(retired_findings)
    if len(set(new_ids)) != len(new_ids) or len(set(carried_ids)) != len(carried_ids) or set(new_ids) & set(carried_ids):
        add("replacement_item_partition_invalid", "New and carried-forward item IDs must be unique and disjoint.")
    if len(set(retired_ids)) != len(retired_ids) or set(retired_ids) & (set(new_ids) | set(carried_ids)):
        add("replacement_retired_partition_invalid", "Retired predecessor IDs must be unique and disjoint from successor items.")
    successor_ids = item_order(successor)
    if set(successor_ids) != set(new_ids) | set(carried_ids):
        add(
            "replacement_item_partition_incomplete",
            "Replacement new/carried item IDs must partition every successor item.",
            {"successor_item_ids": successor_ids, "new_item_ids": new_ids, "carried_forward_item_ids": carried_ids},
        )
    if len(new_ids) > 5:
        add("replacement_new_item_count_exceeded", "Replacement may introduce at most five newly derived items.")
    if len(successor_ids) > 5 and not carried_ids:
        add("replacement_large_pack_without_carry_forward", "A replacement over five total items requires exact carry-forward items.")

    predecessor_items = {
        str(item.get("item_id")): item
        for item in sorted_items(predecessor)
        if isinstance(item, dict) and item.get("item_id")
    }
    successor_items = {
        str(item.get("item_id")): item
        for item in sorted_items(successor)
        if isinstance(item, dict) and item.get("item_id")
    }
    predecessor_ids = set(predecessor_items)
    successor_id_set = set(successor_items)
    for successor_item_id, successor_item in successor_items.items():
        dependencies = successor_item.get("dependencies")
        if not isinstance(dependencies, list):
            continue
        for dependency in dependencies:
            dependency_id = str(dependency or "")
            if not dependency_id or dependency_id not in predecessor_items or dependency_id in successor_id_set:
                continue
            dependency_item = predecessor_items[dependency_id]
            completion = dependency_item.get("completion")
            if dependency_item.get("status") == "consumed" and isinstance(completion, dict):
                continue
            add(
                "replacement_dependency_target_removed",
                "Successor dependency names a predecessor item that is neither present nor completed with preserved evidence.",
                {"item_id": successor_item_id, "dependency_item_id": dependency_id},
            )
    if set(new_ids) & predecessor_ids:
        add(
            "replacement_predecessor_reclassified_as_new",
            "An existing predecessor item cannot be reclassified as newly derived; carry it exactly or retire it explicitly.",
            {"item_ids": sorted(set(new_ids) & predecessor_ids)},
        )
    unknown_retired = set(retired_ids) - predecessor_ids
    if unknown_retired:
        add(
            "replacement_retired_item_unknown",
            "retired_items may name only predecessor items.",
            {"item_ids": sorted(unknown_retired)},
        )
    live_predecessor_ids = {
        item_id
        for item_id, item in predecessor_items.items()
        if item.get("status") in OPEN_RESIDUAL_STATUSES
    }
    unaccounted_live = live_predecessor_ids - set(carried_ids) - set(retired_ids)
    if unaccounted_live:
        add(
            "replacement_live_predecessor_item_unaccounted",
            "Every nonterminal predecessor item must be carried forward exactly or retired with evidence.",
            {"item_ids": sorted(unaccounted_live)},
        )
    predecessor_relative = [item_id for item_id in item_order(predecessor) if item_id in set(carried_ids)]
    successor_relative = [item_id for item_id in successor_ids if item_id in set(carried_ids)]
    if predecessor_relative != carried_ids or successor_relative != carried_ids:
        add(
            "replacement_carried_order_changed",
            "Carried-forward items must retain predecessor-relative order.",
            {"declared": carried_ids, "predecessor": predecessor_relative, "successor": successor_relative},
        )
    for item_id in carried_ids:
        old_item = predecessor_items.get(item_id)
        new_item = successor_items.get(item_id)
        if old_item is None or new_item is None:
            add("replacement_carried_item_missing", "A declared carried-forward item is missing.", {"item_id": item_id})
            continue
        old_digest = item_planning_contract_sha256(old_item)
        new_digest = item_planning_contract_sha256(new_item)
        bindings.append(
            {
                "item_id": item_id,
                "predecessor_planning_sha256": old_digest,
                "successor_planning_sha256": new_digest,
            }
        )
        if old_digest != new_digest:
            add(
                "replacement_carried_planning_contract_changed",
                "Carried-forward planning fields changed; treat the item as newly derived or restore the exact contract.",
                {"item_id": item_id, "predecessor_sha256": old_digest, "successor_sha256": new_digest},
            )
    return findings, bindings


def replacement_plan_fingerprint(plan: dict[str, Any]) -> str:
    return sha256_bytes(json_bytes(plan))


def replacement_plan_snapshot_path(root: Path, plan_fingerprint: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", plan_fingerprint):
        raise SystemExit("Replacement plan fingerprint is invalid.")
    return _require_within(
        pack_dir(root) / "replacement_plan_snapshots" / f"{plan_fingerprint}.json",
        pack_dir(root),
        "Replacement plan snapshot path",
    )


def pack_planning_contract(pack: dict[str, Any]) -> dict[str, Any]:
    lifecycle_fields = {
        "status",
        "current_item_id",
        "mutation_log",
        "created_at",
        "updated_at",
        "terminal_blocker",
    }
    contract = {
        str(key): copy.deepcopy(value)
        for key, value in sorted(pack.items(), key=lambda pair: str(pair[0]))
        if key not in lifecycle_fields and key != "items"
    }
    contract["items"] = [
        {
            str(key): copy.deepcopy(value)
            for key, value in sorted(item.items(), key=lambda pair: str(pair[0]))
            if key not in {"status", "promotion", "completion", "result"}
        }
        for item in sorted_items(pack)
    ]
    return contract


def validate_durable_creation_evidence(
    root: Path,
    durable_creation: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(durable_creation, dict):
        raise SystemExit("Replacement creation evidence metadata is missing.")
    snapshot_path = bounded_workspace_file(
        root,
        durable_creation.get("creation_snapshot_ref"),
        "Replacement creation snapshot",
    )
    _require_within(snapshot_path, creation_snapshot_dir(root), "Replacement creation snapshot")
    require_file_digest(
        snapshot_path,
        durable_creation.get("creation_snapshot_file_sha256"),
        "Replacement creation snapshot",
    )
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("Replacement creation snapshot is not valid JSON.") from exc
    if not isinstance(snapshot, dict):
        raise SystemExit("Replacement creation snapshot must be a JSON object.")
    if canonical_pack_sha256(snapshot) != durable_creation.get("creation_snapshot_canonical_sha256"):
        raise SystemExit("Replacement creation snapshot canonical digest is inconsistent.")

    receipt_path = bounded_workspace_file(
        root,
        durable_creation.get("creation_receipt_ref"),
        "Replacement creation receipt",
    )
    _require_within(receipt_path, creation_receipt_dir(root), "Replacement creation receipt")
    require_file_digest(
        receipt_path,
        durable_creation.get("creation_receipt_sha256"),
        "Replacement creation receipt",
    )
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("Replacement creation receipt is not valid JSON.") from exc
    expected_receipt = {
        key: value
        for key, value in durable_creation.items()
        if key not in {"creation_receipt_ref", "creation_receipt_sha256"}
    }
    if receipt != expected_receipt:
        raise SystemExit("Replacement creation receipt does not exactly bind the creation snapshot.")
    return snapshot, receipt


def validate_successor_creation_transition(
    successor: dict[str, Any],
    creation_snapshot: dict[str, Any],
    *,
    initial_selection_applied: bool,
) -> None:
    if pack_planning_contract(successor) != pack_planning_contract(creation_snapshot):
        raise SystemExit("Replacement successor planning contract drifted from its creation snapshot.")
    if not initial_selection_applied:
        if canonical_pack_sha256(successor) != canonical_pack_sha256(creation_snapshot):
            raise SystemExit("Replacement successor state drifted from its unselected creation snapshot.")
        return
    before_items = sorted_items(creation_snapshot)
    after_items = sorted_items(successor)
    if not before_items or any(item.get("status") != "planned" for item in before_items):
        raise SystemExit("Replacement initial selection requires an all-planned creation snapshot.")
    if [item.get("item_id") for item in before_items] != [item.get("item_id") for item in after_items]:
        raise SystemExit("Replacement initial selection changed successor item identity or order.")
    if after_items[0].get("status") != "promoted" or any(
        item.get("status") != "planned" for item in after_items[1:]
    ):
        raise SystemExit("Replacement initial selection must promote only the first planned item.")
    expected_current = after_items[1].get("item_id") if len(after_items) > 1 else None
    if successor.get("current_item_id") != expected_current:
        raise SystemExit("Replacement initial selection current item is inconsistent.")
    before_log = creation_snapshot.get("mutation_log")
    after_log = successor.get("mutation_log")
    if (
        not isinstance(before_log, list)
        or not isinstance(after_log, list)
        or len(after_log) != len(before_log) + 1
        or after_log[:-1] != before_log
        or not isinstance(after_log[-1], dict)
        or after_log[-1].get("action") != "promote"
    ):
        raise SystemExit("Replacement initial selection mutation history is inconsistent.")


def replacement_postcondition(root: Path, prepare: dict[str, Any]) -> dict[str, Any]:
    metadata = prepare.get("metadata") if isinstance(prepare.get("metadata"), dict) else {}
    predecessor_ref = str(metadata.get("predecessor_pack_ref") or "")
    successor_ref = str(metadata.get("successor_pack_ref") or "")
    predecessor_path = resolve_pack_path(root, predecessor_ref)
    successor_path = resolve_pack_path(root, successor_ref)
    predecessor = load_json(predecessor_path)
    successor = load_json(successor_path)
    creation_snapshot, creation_receipt = validate_durable_creation_evidence(
        root,
        metadata.get("creation_snapshot") if isinstance(metadata.get("creation_snapshot"), dict) else {},
    )
    plan_path = bounded_workspace_file(root, metadata.get("plan_snapshot_ref"), "Replacement plan snapshot")
    try:
        bound_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit("Replacement plan snapshot is not valid JSON.") from exc
    if not isinstance(bound_plan, dict) or replacement_plan_fingerprint(bound_plan) != metadata.get("plan_fingerprint"):
        raise SystemExit("Replacement plan snapshot fingerprint is inconsistent.")
    planned_successor = bound_plan.get("pack") if isinstance(bound_plan.get("pack"), dict) else {}
    if pack_planning_contract(planned_successor) != pack_planning_contract(creation_snapshot):
        raise SystemExit("Replacement creation snapshot is not bound to the exact input plan.")
    validate_successor_creation_transition(
        successor,
        creation_snapshot,
        initial_selection_applied=metadata.get("initial_selection_applied") is True,
    )
    replacement_contract = successor.get("replacement_contract")
    retired_findings, _retired_ids = validate_retired_items_contract(
        root,
        replacement_contract.get("retired_items", []) if isinstance(replacement_contract, dict) else None,
    )
    if retired_findings:
        raise SystemExit("Replacement retired-item evidence no longer validates.")
    if predecessor.get("status") != "superseded":
        raise SystemExit("Replacement postcondition requires a superseded predecessor.")
    predecessor_blocks = [item for item in validate_pack(predecessor, predecessor_path) if item.get("severity") == "block"]
    successor_findings = validate_pack(successor, successor_path)
    if predecessor_blocks or successor_findings:
        raise SystemExit("Replacement postcondition pack validation failed.")
    if canonical_pack_sha256(predecessor) != metadata.get("predecessor_after_canonical_sha256"):
        raise SystemExit("Replacement predecessor canonical state differs from the prepared transaction.")
    if canonical_pack_sha256(successor) != metadata.get("successor_after_canonical_sha256"):
        raise SystemExit("Replacement successor canonical state differs from the prepared transaction.")
    active = active_pack_candidates(root)
    active_refs = [rel_path(root, path) for path, _data in active]
    if active_refs != [successor_ref]:
        raise SystemExit("Replacement postcondition requires exactly the successor pack to be active.")
    return {
        "active_pack_count": 1,
        "active_pack_refs": active_refs,
        "predecessor_status": predecessor.get("status"),
        "successor_status": successor.get("status"),
        "creation_snapshot_ref": metadata["creation_snapshot"]["creation_snapshot_ref"],
        "creation_snapshot_sha256": metadata["creation_snapshot"]["creation_snapshot_file_sha256"],
        "creation_receipt_ref": metadata["creation_snapshot"]["creation_receipt_ref"],
        "creation_receipt_sha256": metadata["creation_snapshot"]["creation_receipt_sha256"],
        "creation_receipt_kind": creation_receipt.get("receipt_kind"),
    }


def validate_replacement_receipt(
    root: Path,
    plan: dict[str, Any],
    receipt: dict[str, Any] | None,
    *,
    current_pack_path: str | None = None,
    current_render_path: str | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    def add(code: str, message: str, evidence: Any = None) -> None:
        finding: dict[str, Any] = {"severity": "block", "code": code, "message": message}
        if evidence is not None:
            finding["evidence"] = evidence
        findings.append(finding)

    if not isinstance(receipt, dict):
        add("replacement_receipt_missing", "replace_pack requires a committed replacement receipt.")
        return {"status": "block", "findings": findings}
    transaction_id = str(receipt.get("transaction_id") or "")
    try:
        verified = task_pack_replacement.validate_completed_transaction(root, transaction_id)
    except SystemExit as exc:
        add("replacement_receipt_invalid", str(exc))
        return {"status": "block", "findings": findings}
    if receipt != verified:
        add(
            "replacement_supplied_receipt_incomplete",
            "Supplied replacement receipt must exactly match the durable validated receipt, including its ref and digest.",
        )
    expected_fingerprint = replacement_plan_fingerprint(plan)
    if verified.get("plan_fingerprint") != expected_fingerprint:
        add(
            "replacement_plan_fingerprint_mismatch",
            "Replacement receipt is bound to a different plan.",
            {"expected": expected_fingerprint, "actual": verified.get("plan_fingerprint")},
        )
    try:
        prepare = task_pack_replacement.load_prepare(root, transaction_id)[0]
        metadata = prepare.get("metadata") if isinstance(prepare.get("metadata"), dict) else {}
        target_refs = {
            str(target.get("role")): str(target.get("target_ref"))
            for target in prepare.get("targets", [])
            if isinstance(target, dict)
        }
        if current_pack_path is not None and current_pack_path != metadata.get("successor_pack_ref"):
            add(
                "replacement_current_pack_path_mismatch",
                "Result task_pack_path does not identify the committed replacement successor.",
                {"expected": metadata.get("successor_pack_ref"), "actual": current_pack_path},
            )
        if current_render_path is not None and current_render_path != target_refs.get("successor_render"):
            add(
                "replacement_current_render_path_mismatch",
                "Result task_pack_render_path does not identify the committed successor render target.",
                {"expected": target_refs.get("successor_render"), "actual": current_render_path},
            )
        actual_postcondition = replacement_postcondition(root, prepare)
        if verified.get("postcondition") != actual_postcondition:
            add(
                "replacement_postcondition_receipt_mismatch",
                "Replacement receipt postcondition does not match the current verified state.",
                {"recorded": verified.get("postcondition"), "actual": actual_postcondition},
            )
    except SystemExit as exc:
        add("replacement_postcondition_invalid", str(exc))
    return {"status": "block" if findings else "ok", "findings": findings, "receipt": verified}


def normalize_action(action: str) -> str:
    normalized = action.strip().lower()
    mapping = {
        "insert_items": "insert",
        "insert_item": "insert",
        "reorder_items": "reorder",
        "skip_items": "skip",
        "exclude_items": "skip",
        "supersede_pack": "supersede",
        "terminal_blocked": "terminal_block",
        "terminal_block": "terminal_block",
        "create_pack": "create",
        "replace_pack": "replace",
        "promote_next_item": "promote",
        "normalize_initial_selection_provenance": "normalize_initial_selection_provenance",
    }
    return mapping.get(normalized, normalized)


def command_apply_mutation(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(
        root,
        create=not bool(getattr(args, "dry_run", False)),
    ), content_addressed_write_transaction() as evidence_transaction:
        result = _command_apply_mutation_locked(args, root)
        if result == 0 and not getattr(args, "dry_run", False):
            evidence_transaction.commit()
        return result


def _command_apply_mutation_locked(args: argparse.Namespace, root: Path) -> int:
    plan = load_plan(args.plan)
    action = normalize_action(args.action or str(plan.get("action") or plan.get("pack_disposition") or ""))
    if action not in {
        "insert",
        "reorder",
        "skip",
        "supersede",
        "terminal_block",
        "create",
        "replace",
        "promote",
        "normalize_initial_selection_provenance",
    }:
        raise SystemExit(
            "Mutation action must be create, replace, promote, normalize_initial_selection_provenance, insert, reorder, skip, supersede, or terminal_block."
        )

    pending = task_pack_replacement.pending_transaction_ids(root)
    if pending and action != "replace":
        raise SystemExit("A prepared task-pack replacement must be recovered before another mutation.")

    if action == "replace":
        forbidden_plan_keys = _forbidden_receipt_key_paths(plan)
        if forbidden_plan_keys:
            raise SystemExit(
                "Replacement plan snapshots must be body-safe; replace raw/sensitive fields with opaque evidence IDs and hashes: "
                + ", ".join(forbidden_plan_keys)
            )
        plan_fingerprint = replacement_plan_fingerprint(plan)
        completed = task_pack_replacement.completed_transaction_ids_for_plan(root, plan_fingerprint)
        if len(completed) > 1:
            raise SystemExit("Replacement plan is bound to multiple committed transactions.")
        if completed:
            transaction_id = completed[0]
            receipt = task_pack_replacement.validate_completed_transaction(root, transaction_id)
            validation = validate_replacement_receipt(root, plan, receipt)
            if validation.get("status") != "ok":
                raise SystemExit("Completed replacement replay failed receipt validation.")
            output = {
                "status": "no_op",
                "action": "replace",
                "transaction_id": transaction_id,
                "pack_mutation_receipt": receipt,
                "pack_transition_verdict": {"status": "pass", "evidence_ref": receipt.get("receipt_ref")},
                "findings": [],
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 0
        if pending:
            pending_for_plan = task_pack_replacement.pending_transaction_ids_for_plan(root, plan_fingerprint)
            if len(pending_for_plan) != 1 or pending != pending_for_plan:
                raise SystemExit("A different prepared task-pack replacement must be recovered first.")
            transaction_id = pending_for_plan[0]
            if getattr(args, "dry_run", False):
                output = {
                    "status": "block",
                    "action": "replace",
                    "transaction_id": transaction_id,
                    "recovery_required": True,
                    "pack_transition_verdict": {
                        "status": "blocked",
                        "evidence_ref": rel_path(
                            root,
                            task_pack_replacement.prepare_path(root, transaction_id),
                        ),
                    },
                    "findings": [
                        {
                            "severity": "block",
                            "code": "replacement_transaction_pending",
                            "message": "Dry-run never recovers a prepared replacement; run recover-replacement explicitly.",
                        }
                    ],
                }
                json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
                sys.stdout.write("\n")
                return 2
            receipt = task_pack_replacement.publish_transaction(
                root,
                transaction_id,
                postcondition=lambda prepare: replacement_postcondition(root, prepare),
            )
            validation = validate_replacement_receipt(root, plan, receipt)
            if validation.get("status") != "ok":
                raise SystemExit("Recovered replacement journal failed exact receipt validation.")
            output = {
                "status": "recovered",
                "action": "replace",
                "transaction_id": transaction_id,
                "pack_mutation_receipt": receipt,
                "pack_transition_verdict": {"status": "pass", "evidence_ref": receipt.get("receipt_ref")},
                "findings": [],
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 0

        store_findings = task_pack_store_findings(root)
        if store_findings:
            raise SystemExit(store_findings[0]["message"])
        active = active_pack_candidates(root)
        if len(active) != 1:
            raise SystemExit("replace_pack requires exactly one active predecessor pack.")
        predecessor_path_value = plan.get("pack_path") or _coherence_value(plan, "canonical_pack_ref", "pack_path")
        predecessor_path = resolve_pack_path(root, str(predecessor_path_value))
        if predecessor_path != active[0][0]:
            raise SystemExit("replace_pack predecessor is not the unique active pack.")
        predecessor = load_json(predecessor_path)
        coherence = validate_pack_coherence_contract(root, plan, require_declared=True)
        if coherence.get("status") == "block":
            output = {
                "status": "block",
                "action": "replace",
                "pack_path": rel_path(root, predecessor_path),
                "pack_transition_verdict": {"status": "blocked", "evidence_ref": rel_path(root, predecessor_path)},
                "findings": coherence.get("findings", []),
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2

        successor = copy.deepcopy(plan.get("pack") if isinstance(plan.get("pack"), dict) else {})
        required_successor_fields = {
            "schema_version",
            "pack_id",
            "status",
            "language",
            "goal",
            "current_item_id",
            "created_at",
            "updated_at",
            "items",
            "mutation_log",
            "replacement_contract",
        }
        missing_successor_fields = sorted(required_successor_fields - set(successor))
        if missing_successor_fields:
            raise SystemExit(
                "replace_pack successor requires an exact deterministic body; missing: "
                + ", ".join(missing_successor_fields)
            )
        successor_id = str(successor.get("pack_id") or "").strip()
        if not PACK_ID_PATTERN.fullmatch(successor_id):
            raise SystemExit("replace_pack successor requires a path-safe pack_id token.")
        successor_path = resolve_pack_path(root, f".task/task_pack/{successor_id}.json", must_exist=False)
        if successor_path.exists() or successor_path == predecessor_path:
            raise SystemExit("replace_pack successor path must be absent and distinct from the predecessor.")
        predecessor_render_path = bounded_render_path(root, predecessor_path)
        successor_render_path = bounded_render_path(root, successor_path)
        if args.render and successor_render_path.exists():
            raise SystemExit("replace_pack successor Markdown render path must be absent before publication.")
        successor.setdefault("schema_version", 1)
        successor.setdefault("status", "active")
        successor.setdefault("language", args.language)
        if not non_empty(successor.get("created_at")) or not non_empty(successor.get("updated_at")):
            raise SystemExit("replace_pack successor requires explicit deterministic created_at and updated_at values.")
        parse_rfc3339(successor.get("created_at"), "replace_pack successor created_at")
        parse_rfc3339(successor.get("updated_at"), "replace_pack successor updated_at")
        successor.setdefault("mutation_log", [])
        successor.setdefault("terminal_blocker", None)
        if successor.get("status") != "active":
            raise SystemExit("replace_pack successor must be active.")
        if not successor.get("current_item_id") and isinstance(successor.get("items"), list) and successor["items"]:
            successor["current_item_id"] = sorted(successor["items"], key=lambda item: item.get("order", 0))[0].get("item_id")
        create_entry = mutation_entry("create", plan, [], item_order(successor))
        initial_selection = plan.get("initial_selection")
        create_entry["timestamp"] = str(successor["created_at"])
        create_entry["predecessor_pack_ref"] = rel_path(root, predecessor_path)
        successor.setdefault("mutation_log", []).append(create_entry)
        successor_findings = publication_findings(successor, successor_path, check_size=False)
        if successor_findings:
            output = {
                "status": "block",
                "action": "replace",
                "pack_path": rel_path(root, successor_path),
                "pack_transition_verdict": {"status": "blocked", "evidence_ref": rel_path(root, successor_path)},
                "findings": successor_findings,
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2
        durable_creation = persist_creation_snapshot(root, successor_path, successor)
        initial_selection_applied, successor_findings = apply_initial_selection_to_new_pack(
            root,
            successor_path,
            successor,
            initial_selection if isinstance(initial_selection, dict) else None,
            durable_creation,
            check_size=False,
            dry_run=bool(getattr(args, "dry_run", False)),
        )
        carry_findings, carry_bindings = validate_carry_forward_contract(
            root,
            predecessor_path,
            predecessor,
            successor,
        )
        successor_findings.extend(carry_findings)
        if successor_findings:
            output = {
                "status": "block",
                "action": "replace",
                "pack_path": rel_path(root, successor_path),
                "pack_transition_verdict": {"status": "blocked", "evidence_ref": rel_path(root, successor_path)},
                "findings": successor_findings,
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2

        predecessor_after = copy.deepcopy(predecessor)
        predecessor_after["status"] = "superseded"
        for item in predecessor_after.get("items", []):
            if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
                item["status"] = "superseded"
        supersede_entry = mutation_entry(
            "supersede",
            plan,
            item_order(predecessor_after),
            item_order(predecessor_after),
        )
        supersede_entry["replacement_plan_fingerprint"] = plan_fingerprint
        supersede_entry["successor_pack_ref"] = rel_path(root, successor_path)
        predecessor_after.setdefault("mutation_log", []).append(supersede_entry)
        refresh_current_item(predecessor_after)
        transaction_time = str(successor["updated_at"])
        supersede_entry["timestamp"] = transaction_time
        predecessor_after["updated_at"] = transaction_time
        predecessor_blocks = [
            finding
            for finding in validate_pack(predecessor_after, predecessor_path)
            if finding.get("severity") == "block"
        ]
        if predecessor_blocks:
            output = {
                "status": "block",
                "action": "replace",
                "pack_path": rel_path(root, predecessor_path),
                "pack_transition_verdict": {"status": "blocked", "evidence_ref": rel_path(root, predecessor_path)},
                "findings": predecessor_blocks,
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2

        predecessor_after_bytes = json_bytes(predecessor_after)
        successor_after_bytes = json_bytes(successor)
        targets = [
            {
                "role": "predecessor_pack",
                "target_ref": rel_path(root, predecessor_path),
                "before_sha256": sha256_file(predecessor_path),
                "after_bytes": predecessor_after_bytes,
            },
            {
                "role": "successor_pack",
                "target_ref": rel_path(root, successor_path),
                "before_sha256": None,
                "after_bytes": successor_after_bytes,
            },
        ]
        if args.render:
            targets.extend(
                [
                    {
                        "role": "predecessor_render",
                        "target_ref": rel_path(root, predecessor_render_path),
                        "before_sha256": sha256_optional_file(predecessor_render_path),
                        "after_bytes": render_markdown(root, predecessor_path, predecessor_after, args.language).encode("utf-8"),
                    },
                    {
                        "role": "successor_render",
                        "target_ref": rel_path(root, successor_render_path),
                        "before_sha256": None,
                        "after_bytes": render_markdown(root, successor_path, successor, args.language).encode("utf-8"),
                    },
                ]
            )
        plan_snapshot_path = replacement_plan_snapshot_path(root, plan_fingerprint)
        metadata = {
            "plan_fingerprint": plan_fingerprint,
            "plan_snapshot_ref": rel_path(root, plan_snapshot_path),
            "plan_snapshot_sha256": plan_fingerprint,
            "predecessor_pack_ref": rel_path(root, predecessor_path),
            "predecessor_before_canonical_sha256": canonical_pack_sha256(predecessor),
            "predecessor_after_canonical_sha256": canonical_pack_sha256(predecessor_after),
            "successor_pack_ref": rel_path(root, successor_path),
            "successor_after_canonical_sha256": canonical_pack_sha256(successor),
            "creation_snapshot": durable_creation,
            "initial_selection_applied": initial_selection_applied,
            "carry_forward_bindings": carry_bindings,
        }
        transaction_id = task_pack_replacement.transaction_id_for_targets(metadata, targets)
        if getattr(args, "dry_run", False):
            output = {
                "status": "dry_run",
                "action": "replace",
                "transaction_id": transaction_id,
                "predecessor_pack_ref": rel_path(root, predecessor_path),
                "predecessor_before_sha256": sha256_file(predecessor_path),
                "predecessor_after_sha256": sha256_bytes(predecessor_after_bytes),
                "successor_pack_ref": rel_path(root, successor_path),
                "successor_after_sha256": sha256_bytes(successor_after_bytes),
                "successor_after_canonical_sha256": canonical_pack_sha256(successor),
                "plan_snapshot_ref": rel_path(root, plan_snapshot_path),
                "plan_snapshot_sha256": plan_fingerprint,
                "creation_snapshot": durable_creation,
                "initial_selection_applied": initial_selection_applied,
                "carry_forward_bindings": carry_bindings,
                "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, successor_path)},
                "findings": [],
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 0

        write_content_addressed_file(plan_snapshot_path, json_bytes(plan), "Replacement plan snapshot")
        prepare_info = task_pack_replacement.prepare_transaction(
            root,
            targets=targets,
            metadata=metadata,
        )
        if prepare_info.get("transaction_id") != transaction_id:
            raise SystemExit("Replacement prepare transaction identity changed during publication.")
        prepare_path = root / str(prepare_info["prepare_ref"])
        guard_content_addressed_consumer(prepare_path, canonical_pack_sha256(prepare_info["prepare"]))
        receipt = task_pack_replacement.publish_transaction(
            root,
            transaction_id,
            postcondition=lambda prepare: replacement_postcondition(root, prepare),
        )
        output = {
            "status": "ok",
            "action": "replace",
            "transaction_id": transaction_id,
            "predecessor_pack_ref": rel_path(root, predecessor_path),
            "successor_pack_ref": rel_path(root, successor_path),
            "render_path": rel_path(root, successor_render_path) if args.render else None,
            "creation_snapshot": durable_creation,
            "initial_selection_applied": initial_selection_applied,
            "carry_forward_bindings": carry_bindings,
            "pack_mutation_receipt": receipt,
            "pack_transition_verdict": {"status": "pass", "evidence_ref": receipt.get("receipt_ref")},
            "findings": [],
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    if action == "create":
        store_findings = task_pack_store_findings(root)
        if store_findings:
            raise SystemExit(store_findings[0]["message"])
        if active_pack_candidates(root):
            raise SystemExit("Create mutation requires no active task pack; use replace_pack for an active predecessor.")
        pack_data = copy.deepcopy(plan.get("pack") if isinstance(plan.get("pack"), dict) else plan)
        initial_selection = plan.get("initial_selection")
        pack_id = str(pack_data.get("pack_id") or "").strip()
        if not PACK_ID_PATTERN.fullmatch(pack_id):
            raise SystemExit("Create mutation requires a path-safe `pack_id` token of at most 128 characters.")
        path = resolve_pack_path(root, f".task/task_pack/{pack_id}.json", must_exist=False)
        if path.exists():
            raise SystemExit(f"Task pack already exists: {rel_path(root, path)}")
        pack_data.setdefault("schema_version", 1)
        pack_data.setdefault("status", "active")
        pack_data.setdefault("language", args.language)
        pack_data.setdefault("created_at", now_iso())
        pack_data.setdefault("updated_at", now_iso())
        pack_data.setdefault("mutation_log", [])
        pack_data.setdefault("terminal_blocker", None)
        if not pack_data.get("current_item_id") and isinstance(pack_data.get("items"), list) and pack_data["items"]:
            pack_data["current_item_id"] = sorted(pack_data["items"], key=lambda item: item.get("order", 0))[0].get("item_id")
        create_entry = mutation_entry("create", plan, [], item_order(pack_data))
        if isinstance(initial_selection, dict):
            create_entry["timestamp"] = str(pack_data.get("created_at") or create_entry["timestamp"])
        pack_data.setdefault("mutation_log", []).append(create_entry)
        findings = publication_findings(pack_data, path, check_size=True)
        if findings:
            output = {
                "status": "block",
                "pack_path": rel_path(root, path),
                "pack_transition_verdict": {"status": "blocked", "evidence_ref": rel_path(root, path)},
                "findings": findings,
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2
        durable_creation = persist_creation_snapshot(root, path, pack_data)
        initial_selection_applied, findings = apply_initial_selection_to_new_pack(
            root,
            path,
            pack_data,
            initial_selection if isinstance(initial_selection, dict) else None,
            durable_creation,
            check_size=True,
            dry_run=bool(getattr(args, "dry_run", False)),
        )
        if findings:
            raise SystemExit(
                "Create initial-selection transaction failed final validation: "
                + "; ".join(str(item.get("code")) for item in findings)
            )
        if getattr(args, "dry_run", False):
            output = {
                "status": "dry_run",
                "action": "create",
                "pack_path": rel_path(root, path),
                "pack_id": pack_data.get("pack_id"),
                "proposed_after_pack_sha256": canonical_pack_sha256(pack_data),
                "current_item_id": pack_data.get("current_item_id"),
                "creation_snapshot": durable_creation,
                "initial_selection_applied": initial_selection_applied,
                "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, path)},
                "findings": findings,
            }
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 0
        guard_content_addressed_consumer(path, canonical_pack_sha256(pack_data))
        write_json(path, pack_data)
        render_output_path = None
        if args.render:
            render_output_path = write_render(root, path, pack_data, args.language)
        create_hash = canonical_pack_sha256(pack_data)
        create_receipt = {
            "schema_version": PACK_COHERENCE_VERSION,
            "canonical_pack_ref": rel_path(root, path),
            "before_pack_sha256": None,
            "after_pack_sha256": create_hash,
            "actual_before_item_ids": [],
            "actual_before_order": [],
            "actual_before_current_item": None,
            "actual_after_item_ids": item_order(pack_data),
            "actual_after_order": item_order(pack_data),
            "actual_after_current_item": pack_data.get("current_item_id"),
            "mutation_kind": "create",
            "legacy_normalized": False,
        }
        output = {
            "status": "ok",
            "action": "create",
            "pack_path": rel_path(root, path),
            "render_path": rel_path(root, render_output_path) if render_output_path else None,
            "pack_id": pack_data.get("pack_id"),
            "pack_coherence": {
                "schema_version": PACK_COHERENCE_VERSION,
                "canonical_pack_ref": rel_path(root, path),
                "before_pack_sha256": None,
                "after_pack_sha256": create_hash,
                "actual_after_item_ids": item_order(pack_data),
                "actual_after_order": item_order(pack_data),
                "actual_after_current_item": pack_data.get("current_item_id"),
                "mutation_kind": "create",
            },
            "pack_mutation_receipt": create_receipt,
            "creation_snapshot": durable_creation,
            "initial_selection_applied": initial_selection_applied,
            "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, path)},
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    pack_path_value = plan.get("pack_path") or args.pack
    path = resolve_pack_path(root, str(pack_path_value)) if pack_path_value else active_pack(root)[0]
    if path is None:
        raise SystemExit("No active task pack found.")
    data = load_json(path)
    before_order = item_order(data)
    if action == "normalize_initial_selection_provenance":
        supplied_receipt = plan.get("initial_selection_receipt")
        if isinstance(supplied_receipt, dict):
            replay_item_id = str(supplied_receipt.get("initial_item_id") or plan.get("item_id") or "").strip()
            replay_target = next(
                (
                    item
                    for item in data.get("items", [])
                    if isinstance(item, dict) and str(item.get("item_id") or "") == replay_item_id
                ),
                None,
            )
            replay_promotion = (
                replay_target.get("promotion")
                if isinstance(replay_target, dict) and isinstance(replay_target.get("promotion"), dict)
                else {}
            )
            replay_normalization = replay_promotion.get("provenance_normalization")
            if isinstance(replay_normalization, dict):
                if replay_promotion.get("initial_selection_receipt") != supplied_receipt:
                    raise SystemExit("Initial-selection provenance is already normalized with a conflicting receipt.")
                replay_findings = validate_pack(data, path)
                blocking = [finding for finding in replay_findings if finding.get("severity") == "block"]
                if blocking:
                    raise SystemExit(
                        "Stored initial-selection normalization no longer validates: "
                        + "; ".join(str(finding.get("code")) for finding in blocking)
                    )
                output = {
                    "status": "already_normalized",
                    "action": action,
                    "pack_path": rel_path(root, path),
                    "pack_id": data.get("pack_id"),
                    "current_item_id": data.get("current_item_id"),
                    "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, path)},
                    "historical_authority_verdict": replay_normalization.get("historical_authority_verdict"),
                }
                json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
                sys.stdout.write("\n")
                return 0
    coherence_result = validate_pack_coherence_contract(root, plan, require_declared=True)
    if coherence_result["status"] == "block":
        output = {
            "status": "block",
            "action": action,
            "pack_path": rel_path(root, path),
            "pack_transition_verdict": {
                "status": "blocked",
                "evidence_ref": rel_path(root, path),
            },
            "findings": coherence_result["findings"],
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    coherence = dict(coherence_result["pack_coherence"] or {})
    items = data.get("items")
    if not isinstance(items, list):
        raise SystemExit("Task pack has invalid `items`.")

    if action == "promote":
        item_id = str(plan.get("item_id") or data.get("current_item_id") or "").strip()
        task_id = str(plan.get("task_id") or "").strip()
        task_path_value = str(plan.get("task_path") or "task.md").strip()
        validated_task_id = str(plan.get("validated_task_id") or "").strip()
        validation_verdict = str(plan.get("validation_verdict") or "").strip().lower()
        promotion_origin = str(plan.get("promotion_origin") or "predecessor_completion").strip().lower()
        if promotion_origin not in PROMOTION_ORIGINS:
            raise SystemExit("Promotion origin must be predecessor_completion, bootstrap_initial_selection, or authorized_initial_selection.")
        if not item_id or not task_id:
            raise SystemExit("Promotion requires `item_id` and `task_id`.")
        if promotion_origin == "predecessor_completion" and not validated_task_id:
            raise SystemExit("Predecessor promotion requires `validated_task_id`.")
        if not PACK_ID_PATTERN.fullmatch(task_id) or (
            validated_task_id and not PACK_ID_PATTERN.fullmatch(validated_task_id)
        ):
            raise SystemExit("Promotion task identifiers must be path-safe tokens of at most 128 characters.")
        in_flight = [str(item.get("item_id") or "") for item in active_in_flight_items(data)]
        atomic_completion = plan.get("consume_current_item")
        if in_flight and isinstance(atomic_completion, dict):
            completed_task_id = consume_in_flight_for_atomic_promotion(
                root,
                data,
                atomic_completion,
                require_current_verdicts=coherence.get("contract_version") == PACK_COHERENCE_VERSION,
            )
            if promotion_origin != "predecessor_completion" or validated_task_id != completed_task_id:
                raise SystemExit("Atomic successor promotion must use the consumed task as predecessor provenance.")
            in_flight = [str(item.get("item_id") or "") for item in active_in_flight_items(data)]
        if in_flight:
            raise SystemExit(f"Promotion requires the existing in-flight item to be consumed or closed first: {', '.join(in_flight)}")
        if promotion_origin == "predecessor_completion":
            mutation_evidence = verify_evidence_files(root, plan.get("evidence_paths"), "Promotion mutation evidence_paths")
        else:
            mutation_evidence = (
                verify_evidence_files(root, plan.get("evidence_paths"), "Promotion mutation evidence_paths")
                if plan.get("evidence_paths")
                else []
            )
        task_path = bounded_workspace_file(root, task_path_value, "Promotion task_path")
        task_digest = sha256_file(task_path)
        target = next((item for item in items if isinstance(item, dict) and str(item.get("item_id")) == item_id), None)
        if target is None:
            raise SystemExit(f"Unknown task pack item: {item_id}")
        expected = next_item(data)
        if expected is None or str(expected.get("item_id")) != item_id:
            raise SystemExit("promote_next_item may promote only the queue's current next item.")
        if target.get("status") not in {"planned", "inserted", "reordered", "blocked"}:
            raise SystemExit(f"Task pack item is not promotable from status {target.get('status')}: {item_id}")
        if truthy(target.get("acceptance_diluted")) or truthy(
            target.get("result", {}).get("acceptance_diluted") if isinstance(target.get("result"), dict) else False
        ):
            raise SystemExit("A task pack item with acceptance_diluted=true cannot be promoted.")
        snapshot_directory = _require_within(
            pack_dir(root) / "task_snapshots" / str(data.get("pack_id")),
            pack_dir(root),
            "Promotion task snapshot directory",
        )
        snapshot_name = f"{item_id[:48]}-{task_id[:48]}-{task_digest[:16]}.md"
        task_snapshot_path = _require_within(snapshot_directory / snapshot_name, pack_dir(root), "Promotion task snapshot path")
        write_content_addressed_file(task_snapshot_path, task_path.read_bytes(), "Promotion task snapshot")
        if promotion_origin != "predecessor_completion":
            supplied_receipt = plan.get("initial_selection_receipt")
            if not isinstance(supplied_receipt, dict):
                raise SystemExit("Initial selection requires `initial_selection_receipt`.")
            if supplied_receipt.get("task_snapshot_ref") != rel_path(root, task_snapshot_path):
                raise SystemExit("Initial selection receipt must reference the deterministic task snapshot.")
        if promotion_origin == "predecessor_completion":
            provenance_plan = {**(atomic_completion if isinstance(atomic_completion, dict) else {}), **plan}
            provenance = {
                "promotion_origin": promotion_origin,
                "initial_selection_receipt": None,
                "initial_selection_receipt_ref": None,
                **validate_promotion_provenance(root, provenance_plan, validated_task_id, validation_verdict),
            }
            provenance["predecessor_completion_receipt_ref"] = provenance.get("validation_report_path")
        else:
            provenance = validate_initial_selection_provenance(
                root,
                path,
                data,
                plan,
                item_id=item_id,
                task_id=task_id,
                task_digest=task_digest,
                promotion_origin=promotion_origin,
            )
        target["status"] = "promoted"
        target["promotion"] = {
            "task_id": task_id,
            "task_path": rel_path(root, task_path),
            "task_sha256": task_digest,
            "task_snapshot_path": rel_path(root, task_snapshot_path),
            "promoted_at": now_iso(),
            "mutation_evidence_paths": mutation_evidence,
            **provenance,
        }
        if promotion_origin == "predecessor_completion":
            target["promotion"].update(
                {
                    "validated_task_id": validated_task_id,
                    "validation_verdict": validation_verdict,
                }
            )
        entry = mutation_entry("promote", plan, before_order, item_order(data))
        entry.update(
            {
                "item_id": item_id,
                "task_id": task_id,
                "validated_task_id": validated_task_id or None,
                "promotion_origin": promotion_origin,
                "before_pack_sha256": coherence.get("before_pack_sha256"),
            }
        )
        data.setdefault("mutation_log", []).append(entry)

    elif action == "normalize_initial_selection_provenance":
        receipt = plan.get("initial_selection_receipt")
        if not isinstance(receipt, dict):
            raise SystemExit("Initial-selection normalization requires `initial_selection_receipt`.")
        item_id = str(receipt.get("initial_item_id") or plan.get("item_id") or "").strip()
        target = next(
            (item for item in items if isinstance(item, dict) and str(item.get("item_id") or "") == item_id),
            None,
        )
        if target is None:
            raise SystemExit("Initial-selection normalization references an unknown pack item.")
        promotion = target.get("promotion")
        if not isinstance(promotion, dict):
            raise SystemExit("Initial-selection normalization requires preserved promotion provenance.")
        if target.get("status") not in {"promoted", "in_progress", "consumed"}:
            raise SystemExit("Only an already-selected initial item can be normalized.")
        task_id = str(promotion.get("task_id") or "")
        task_digest = _required_sha256(promotion.get("task_sha256"), "Initial promotion task_sha256")
        existing_normalization = promotion.get("provenance_normalization")
        if isinstance(existing_normalization, dict):
            existing_receipt = promotion.get("initial_selection_receipt")
            if existing_receipt == receipt:
                output = {
                    "status": "already_normalized",
                    "action": action,
                    "pack_path": rel_path(root, path),
                    "pack_id": data.get("pack_id"),
                    "current_item_id": data.get("current_item_id"),
                    "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, path)},
                    "historical_authority_verdict": existing_normalization.get("historical_authority_verdict"),
                }
                json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
                sys.stdout.write("\n")
                return 0
            raise SystemExit("Initial-selection provenance is already normalized with a conflicting receipt.")

        before_current = data.get("current_item_id")
        before_item_order = item_order(data)
        before_item_states = [
            {
                "item_id": item.get("item_id"),
                "order": item.get("order"),
                "status": item.get("status"),
                "acceptance": copy.deepcopy(item.get("acceptance")),
                "result": copy.deepcopy(item.get("result")),
                "completion": copy.deepcopy(item.get("completion")),
            }
            for item in items
            if isinstance(item, dict)
        ]
        before_other_items = [copy.deepcopy(item) for item in items if item is not target]
        before_promotion = copy.deepcopy(promotion)
        verified = validate_initial_selection_receipt(
            root,
            path,
            data,
            receipt,
            task_id=task_id,
            task_digest=task_digest,
            operation=action,
            require_mutation_binding=False,
        )
        promotion_origin = str(plan.get("promotion_origin") or "bootstrap_initial_selection")
        if promotion_origin not in {"bootstrap_initial_selection", "authorized_initial_selection"}:
            raise SystemExit("Normalized initial selection requires an initial promotion origin.")
        inline_digest = sha256_bytes(
            json.dumps(verified, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        promotion.update(
            {
                "promotion_origin": promotion_origin,
                "initial_selection_receipt": verified,
                "initial_selection_receipt_ref": f"inline:sha256:{inline_digest}",
                "predecessor_completion_receipt_ref": None,
                "provenance_normalization": {
                    "schema_version": 1,
                    "mode": "legacy_initial_selection",
                    "normalized_at": now_iso(),
                    "authority_mode": verified.get("authority_mode"),
                    "historical_selection_authority_status": verified.get(
                        "historical_selection_authority_status"
                    ),
                    "historical_authority_verdict": "partial"
                    if verified.get("authority_mode") == "current_ratification"
                    else "pass",
                    "normalization_authority_status": "allowed_now",
                    "retroactive_claim_allowed": False,
                },
            }
        )
        entry = mutation_entry(action, plan, before_order, before_order)
        entry.update(
            {
                "item_id": item_id,
                "task_id": task_id,
                "before_pack_sha256": coherence.get("before_pack_sha256"),
                "creation_snapshot_sha256": verified.get("pack_creation_snapshot_sha256"),
                "authority_receipt_ref": verified.get("authority_receipt_ref"),
                "authority_receipt_sha256": verified.get("authority_receipt_sha256"),
                "authority_mode": verified.get("authority_mode"),
                "historical_selection_authority_status": verified.get(
                    "historical_selection_authority_status"
                ),
            }
        )
        data.setdefault("mutation_log", []).append(entry)

        if data.get("current_item_id") != before_current or item_order(data) != before_item_order:
            raise SystemExit("Initial-selection normalization changed current item or pack order.")
        after_item_states = [
            {
                "item_id": item.get("item_id"),
                "order": item.get("order"),
                "status": item.get("status"),
                "acceptance": item.get("acceptance"),
                "result": item.get("result"),
                "completion": item.get("completion"),
            }
            for item in items
            if isinstance(item, dict)
        ]
        if after_item_states != before_item_states:
            raise SystemExit("Initial-selection normalization changed protected item lifecycle fields.")
        if [item for item in items if item is not target] != before_other_items:
            raise SystemExit("Initial-selection normalization changed another pack item.")
        for key, value in before_promotion.items():
            if promotion.get(key) != value:
                raise SystemExit(f"Initial-selection normalization rewrote existing promotion field: {key}")

    elif action == "insert":
        new_items = plan.get("items") or plan.get("insert_items")
        if not isinstance(new_items, list) or not new_items:
            raise SystemExit("Insert mutation requires non-empty `items`.")
        existing_ids = {str(item.get("item_id")) for item in items if isinstance(item, dict)}
        for item in new_items:
            if not isinstance(item, dict):
                raise SystemExit("Inserted items must be JSON objects.")
            item_id = str(item.get("item_id") or "").strip()
            if not item_id or item_id in existing_ids:
                raise SystemExit(f"Inserted item_id is empty or duplicated: {item_id}")
            item.setdefault("status", "inserted")
            item.setdefault("dependencies", [])
            item.setdefault("source_evidence", evidence_paths_from(plan))
            item.setdefault("promotion", {"task_id": None, "task_path": None, "promoted_at": None})
            item.setdefault("result", {"validation_verdict": None, "progress_verdict": None, "progress_kind": None, "semantic_signature": None, "blocker_signature": None})
            existing_ids.add(item_id)
        insert_before = plan.get("insert_before_item_id") or data.get("current_item_id")
        rebuilt: list[dict[str, Any]] = []
        inserted = False
        for item in sorted_items(data):
            if insert_before and item.get("item_id") == insert_before:
                rebuilt.extend(new_items)
                inserted = True
            rebuilt.append(item)
        if not inserted:
            rebuilt.extend(new_items)
        data["items"] = rebuilt
        renumber_items(data)
        data.setdefault("mutation_log", []).append(mutation_entry("insert", plan, before_order, item_order(data)))

    elif action == "reorder":
        requested = plan.get("item_order") or plan.get("order")
        if not isinstance(requested, list) or not requested:
            raise SystemExit("Reorder mutation requires full `item_order` list.")
        requested_ids = [str(item) for item in requested]
        current_ids = item_order(data)
        if set(requested_ids) != set(current_ids) or len(requested_ids) != len(current_ids):
            raise SystemExit("Reorder mutation must name every existing item exactly once.")
        if requested_ids == current_ids:
            raise SystemExit("Reorder mutation is a no-op; canonical item order is unchanged.")
        by_id = {str(item.get("item_id")): item for item in items if isinstance(item, dict)}
        data["items"] = [by_id[item_id] for item_id in requested_ids]
        for item in data["items"]:
            if item.get("status") == "planned":
                item["status"] = "reordered"
        renumber_items(data)
        data.setdefault("mutation_log", []).append(mutation_entry("reorder", plan, before_order, item_order(data)))

    elif action == "skip":
        item_ids = plan.get("item_ids") or plan.get("skip_item_ids") or plan.get("exclude_item_ids")
        if not isinstance(item_ids, list) or not item_ids:
            raise SystemExit("Skip mutation requires non-empty `item_ids`.")
        targets = {str(item_id) for item_id in item_ids}
        found: set[str] = set()
        for item in items:
            if isinstance(item, dict) and str(item.get("item_id")) in targets:
                item["status"] = "skipped"
                result = item.setdefault("result", {})
                result["skip_reason"] = plan.get("reason")
                result["evidence_paths"] = evidence_paths_from(plan)
                found.add(str(item.get("item_id")))
        missing = sorted(targets - found)
        if missing:
            raise SystemExit(f"Unknown task pack item(s): {', '.join(missing)}")
        data.setdefault("mutation_log", []).append(mutation_entry("skip", plan, before_order, item_order(data)))

    elif action == "supersede":
        data["status"] = "superseded"
        for item in items:
            if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
                item["status"] = "superseded"
        data.setdefault("mutation_log", []).append(mutation_entry("supersede", plan, before_order, item_order(data)))

    elif action == "terminal_block":
        terminal = plan.get("terminal_blocker")
        if not isinstance(terminal, dict):
            raise SystemExit("terminal_block mutation requires `terminal_blocker` object.")
        data["status"] = "terminal_blocked"
        data["terminal_blocker"] = terminal
        current = data.get("current_item_id")
        for item in items:
            if isinstance(item, dict) and (not current or item.get("item_id") == current) and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
                item["status"] = "terminal_blocked"
                break
        data.setdefault("mutation_log", []).append(mutation_entry("terminal_block", plan, before_order, item_order(data)))

    if action != "normalize_initial_selection_provenance":
        refresh_current_item(data)
    actual_after_ids = item_order(data)
    proposed_after_ids = coherence.get("proposed_after_item_ids")
    proposed_after_order = coherence.get("proposed_after_order")
    coherence_findings: list[dict[str, Any]] = []
    if isinstance(proposed_after_ids, list) and [str(item) for item in proposed_after_ids] != actual_after_ids:
        coherence_findings.append(
            {
                "severity": "block",
                "code": "proposed_after_item_ids_mismatch",
                "message": "Actual pack item IDs do not match the declared post-mutation state.",
                "evidence": {"declared": proposed_after_ids, "actual": actual_after_ids},
            }
        )
    if isinstance(proposed_after_order, list) and [str(item) for item in proposed_after_order] != actual_after_ids:
        coherence_findings.append(
            {
                "severity": "block",
                "code": "proposed_after_order_mismatch",
                "message": "Actual pack order does not match the declared post-mutation order.",
                "evidence": {"declared": proposed_after_order, "actual": actual_after_ids},
            }
        )
    after_pack_sha256 = canonical_pack_sha256(data)
    if (
        coherence.get("contract_version") == PACK_COHERENCE_VERSION
        and coherence.get("before_pack_sha256") == after_pack_sha256
    ):
        coherence_findings.append(
            {
                "severity": "block",
                "code": "pack_mutation_noop",
                "message": "Current pack mutation did not change the canonical pack body.",
                "evidence": {"mutation_kind": action, "canonical_pack_sha256": after_pack_sha256},
            }
        )
    declared_after_hash = _coherence_value(plan, "after_pack_sha256")
    if declared_after_hash:
        normalized_after_hash = str(declared_after_hash).removeprefix("sha256:").lower()
        if normalized_after_hash != after_pack_sha256:
            coherence_findings.append(
                {
                    "severity": "block",
                    "code": "declared_after_pack_sha256_mismatch",
                    "message": "Declared post-mutation pack hash does not match the canonical resulting state.",
                    "evidence": {"declared": normalized_after_hash, "actual": after_pack_sha256},
                }
            )
    findings = validate_pack(data, path)
    findings.extend(coherence_findings)
    if any(item.get("severity") == "block" for item in findings):
        output = {
            "status": "block",
            "action": action,
            "pack_path": rel_path(root, path),
            "pack_transition_verdict": {"status": "blocked", "evidence_ref": rel_path(root, path)},
            "findings": findings,
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    if getattr(args, "dry_run", False):
        output = {
            "status": "dry_run",
            "action": action,
            "pack_path": rel_path(root, path),
            "pack_id": data.get("pack_id"),
            "before_pack_sha256": coherence.get("before_pack_sha256"),
            "proposed_after_pack_sha256": canonical_pack_sha256(data),
            "current_item_id": data.get("current_item_id"),
            "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, path)},
            "findings": findings,
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0
    guard_content_addressed_consumer(path, canonical_pack_sha256(data))
    write_json(path, data)
    mutation_receipt = {
        "schema_version": PACK_COHERENCE_VERSION,
        "canonical_pack_ref": rel_path(root, path),
        "before_pack_sha256": coherence.get("before_pack_sha256"),
        "after_pack_sha256": canonical_pack_sha256(data),
        "actual_before_item_ids": coherence.get("actual_before_item_ids"),
        "actual_before_order": coherence.get("actual_before_order"),
        "actual_before_current_item": coherence.get("actual_current_item"),
        "actual_after_item_ids": item_order(data),
        "actual_after_order": item_order(data),
        "actual_after_current_item": data.get("current_item_id"),
        "mutation_kind": action,
        "legacy_normalized": bool(coherence.get("legacy_normalized"))
        or action == "normalize_initial_selection_provenance",
    }
    render_output_path = None
    if args.render:
        render_output_path = write_render(root, path, data, args.language)
    output = {
        "status": "ok",
        "action": action,
        "pack_path": rel_path(root, path),
        "render_path": rel_path(root, render_output_path) if render_output_path else None,
        "pack_id": data.get("pack_id"),
        "pack_status": data.get("status"),
        "current_item_id": data.get("current_item_id"),
        "before_order": before_order,
        "after_order": item_order(data),
        "pack_coherence": coherence,
        "pack_mutation_receipt": mutation_receipt,
        "pack_transition_verdict": {
            "status": "pass",
            "evidence_ref": rel_path(root, path),
        },
        "findings": findings,
    }
    if action == "normalize_initial_selection_provenance":
        first_receipt = next(
            (
                item.get("promotion", {}).get("provenance_normalization")
                for item in sorted_items(data)
                if isinstance(item.get("promotion"), dict)
                and isinstance(item.get("promotion", {}).get("provenance_normalization"), dict)
            ),
            {},
        )
        output["normalization_authority_status"] = first_receipt.get("normalization_authority_status")
        output["historical_authority_verdict"] = first_receipt.get("historical_authority_verdict")
        output["semantic_progress"] = False
        output["progress_kind"] = "governance_only"
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_mark_consumed(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    with pack_mutation_lock(root):
        return _command_mark_consumed_locked(args, root)


def _command_mark_consumed_locked(args: argparse.Namespace, root: Path) -> int:
    store_findings = task_pack_store_findings(root)
    if store_findings:
        raise SystemExit(store_findings[0]["message"])
    path = resolve_pack_path(root, args.pack) if args.pack else active_pack(root)[0]
    if path is None:
        raise SystemExit("No active task pack found.")
    data = load_json(path)
    coherence_payload = load_plan(args.pack_coherence_json) if args.pack_coherence_json else {}
    coherence_plan = dict(coherence_payload) if "pack_coherence" in coherence_payload else {"pack_coherence": coherence_payload}
    coherence_plan.update(
        {
            "action": "mark_consumed",
            "pack_path": rel_path(root, path),
        }
    )
    coherence_result = validate_pack_coherence_contract(root, coherence_plan, require_declared=True)
    if coherence_result["status"] == "block":
        output = {
            "status": "block",
            "pack_path": rel_path(root, path),
            "pack_transition_verdict": {"status": "blocked", "evidence_ref": rel_path(root, path)},
            "findings": coherence_result["findings"],
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    coherence = dict(coherence_result["pack_coherence"] or {})
    verdict_payload = load_plan(args.verdict_axes_json) if args.verdict_axes_json else {}
    found = False
    for item in data.get("items", []):
        if isinstance(item, dict) and item.get("item_id") == args.item_id:
            if item.get("status") not in {"promoted", "in_progress"}:
                raise SystemExit("mark-consumed requires an item previously promoted through verified provenance.")
            promotion = item.get("promotion")
            if not isinstance(promotion, dict):
                raise SystemExit("mark-consumed requires preserved promotion provenance.")
            completed_task_id = str(promotion.get("task_id") or "").strip()
            if args.task_id and args.task_id != completed_task_id:
                raise SystemExit("mark-consumed task_id must match the promoted task identity.")
            if args.task_path:
                supplied_task_path = bounded_workspace_file(root, args.task_path, "mark-consumed task_path")
                promoted_task_path = bounded_workspace_file(root, promotion.get("task_path"), "Promotion task_path")
                if supplied_task_path != promoted_task_path:
                    raise SystemExit("mark-consumed task_path must match the promoted task path.")
            completion_evidence = list(args.completion_evidence_path or [])
            completion_plan = {
                "run_report_path": args.run_report_path,
                "run_report_sha256": args.run_report_sha256,
                "validation_report_path": args.validation_report_path,
                "validation_report_sha256": args.validation_report_sha256,
                "validation_evidence_paths": list(args.validation_evidence_path or []),
                "issue_packet_path": args.issue_packet_path,
                "issue_packet_sha256": args.issue_packet_sha256,
                "evidence_paths": completion_evidence,
            }
            completion_provenance = validate_promotion_provenance(
                root,
                completion_plan,
                completed_task_id,
                str(args.validation_verdict or "").strip().lower(),
            )
            item["completion"] = {
                "completed_task_id": completed_task_id,
                "completed_at": now_iso(),
                "validation_verdict": str(args.validation_verdict or "").strip().lower(),
                "completion_evidence_paths": verify_evidence_files(
                    root,
                    completion_evidence,
                    "Completion evidence_paths",
                ),
                **completion_provenance,
            }
            item["status"] = "consumed"
            result = item.setdefault("result", {})
            for key, value in (
                ("validation_verdict", args.validation_verdict),
                ("progress_verdict", args.progress_verdict),
                ("progress_kind", args.progress_kind),
                ("semantic_signature", args.semantic_signature),
                ("blocker_signature", args.blocker_signature),
            ):
                if value:
                    result[key] = value
            preserve_verdict_axes(
                result,
                verdict_payload,
                require_current=coherence.get("contract_version") == PACK_COHERENCE_VERSION,
            )
            if args.has_supplied_input_delta:
                gate = result.setdefault("positive_input_delta_gate", {})
                gate["has_supplied_input_delta"] = True
            if args.supplied_input_artifact_path:
                gate = result.setdefault("positive_input_delta_gate", {})
                paths = gate.setdefault("supplied_input_artifact_paths", [])
                for supplied_path in args.supplied_input_artifact_path:
                    if supplied_path not in paths:
                        paths.append(supplied_path)
            if (
                args.acceptance_target_met
                or args.acceptance_diluted
                or args.explicit_descope_decision
                or args.acceptance_provenance_evidence_path
                or args.residual_item_id
            ):
                gate = result.setdefault("acceptance_provenance_gate", {})
                if args.acceptance_target_met:
                    gate["target_met"] = True
                if args.acceptance_diluted:
                    gate["acceptance_diluted"] = True
                if args.explicit_descope_decision:
                    gate["explicit_descope_decision"] = True
                if args.residual_item_id:
                    gate["residual_item_id"] = args.residual_item_id
                if args.acceptance_provenance_evidence_path:
                    paths = gate.setdefault("evidence_paths", [])
                    for evidence_path in args.acceptance_provenance_evidence_path:
                        if evidence_path not in paths:
                            paths.append(evidence_path)
            if args.required_verifier or args.acceptance_verifier_status or args.acceptance_verifier_evidence_path:
                gate = result.setdefault("acceptance_verifier_gate", {})
                if args.required_verifier:
                    gate["required_verifier"] = args.required_verifier
                    gate["verifier_required"] = True
                if args.acceptance_verifier_status:
                    gate["evaluation_status"] = args.acceptance_verifier_status
                    gate["acceptance_verifier_not_evaluated"] = args.acceptance_verifier_status == "not_evaluated"
                    gate["unverifiable_acceptance_contract"] = args.acceptance_verifier_status == "not_evaluated"
                if args.acceptance_verifier_evidence_path:
                    paths = gate.setdefault("evidence_paths", [])
                    for evidence_path in args.acceptance_verifier_evidence_path:
                        if evidence_path not in paths:
                            paths.append(evidence_path)
            if args.required_gate_hook or args.gate_hook_status:
                gate = result.setdefault("acceptance_verifier_gate", {})
                if args.required_gate_hook:
                    hooks = gate.setdefault("required_gate_hooks", [])
                    for hook in args.required_gate_hook:
                        if hook not in hooks:
                            hooks.append(hook)
                if args.gate_hook_status:
                    gate["gate_hook_status"] = args.gate_hook_status
                    if args.gate_hook_status in {"not_supplied", "absent", "fail_quiet", "not_evaluated"}:
                        gate["unverifiable_acceptance_contract"] = True
            if args.pass_with_unobserved_axes or args.unobserved_goal_axis:
                gate = result.setdefault("goal_axis_completeness_gate", {})
                if args.pass_with_unobserved_axes:
                    gate["pass_with_unobserved_axes"] = True
                if args.unobserved_goal_axis:
                    axes = gate.setdefault("unobserved_goal_axes", [])
                    for axis in args.unobserved_goal_axis:
                        if axis not in axes:
                            axes.append(axis)
            if (
                args.independently_verified_field
                or args.producer_attested_field
                or args.independent_source_separation_status
                or args.independently_verified_downgraded_field
                or args.verification_input_path
                or args.verified_artifact_path
            ):
                gate = result.setdefault("evidence_provenance_gate", {})
                if args.independently_verified_field:
                    fields = gate.setdefault("independently_verified_fields", [])
                    for field in args.independently_verified_field:
                        if field not in fields:
                            fields.append(field)
                if args.producer_attested_field:
                    fields = gate.setdefault("producer_attested_fields", [])
                    for field in args.producer_attested_field:
                        if field not in fields:
                            fields.append(field)
                if args.independent_source_separation_status:
                    gate["independent_source_separation_status"] = args.independent_source_separation_status
                if args.independently_verified_downgraded_field:
                    fields = gate.setdefault("independently_verified_downgraded_fields", [])
                    for field in args.independently_verified_downgraded_field:
                        if field not in fields:
                            fields.append(field)
                if args.verification_input_path:
                    paths = gate.setdefault("verification_input_paths", [])
                    for path_value in args.verification_input_path:
                        if path_value not in paths:
                            paths.append(path_value)
                if args.verified_artifact_path:
                    paths = gate.setdefault("verified_artifact_paths", [])
                    for path_value in args.verified_artifact_path:
                        if path_value not in paths:
                            paths.append(path_value)
            if args.generation_dependent_count_key or args.effective_count_key:
                gate = result.setdefault("count_key_hygiene_gate", {})
                if args.generation_dependent_count_key:
                    gate["generation_dependent_count_key"] = True
                    gate["count_key_trace_only"] = True
                if args.effective_count_key:
                    gate["effective_count_key"] = args.effective_count_key
            if args.envelope_thaw_item_required or args.envelope_thaw_item or args.thaw_condition or args.thaw_schedule:
                gate = result.setdefault("acceptance_reachability_gate", {})
                if args.envelope_thaw_item_required:
                    gate["envelope_thaw_item_required"] = True
                if args.envelope_thaw_item:
                    gate["envelope_thaw_item"] = args.envelope_thaw_item
                if args.thaw_condition:
                    gate["thaw_condition"] = args.thaw_condition
                if args.thaw_schedule:
                    gate["thaw_schedule"] = args.thaw_schedule
            if args.instrumentation_supply_required or args.diagnostics_unavailable_streak is not None or args.existing_diagnostics_sufficient:
                gate = result.setdefault("diagnostics_unavailable_gate", {})
                if args.instrumentation_supply_required:
                    gate["instrumentation_supply_required"] = True
                if args.diagnostics_unavailable_streak is not None:
                    gate["diagnostics_unavailable_streak"] = args.diagnostics_unavailable_streak
                if args.existing_diagnostics_sufficient:
                    result["existing_diagnostics_sufficient"] = True
            if (
                args.cycle_fixed_cost is not None
                or args.marginal_value_per_cycle_cost is not None
                or args.residual_gap_cost_below_policy
                or args.marginal_repair_higher_value
            ):
                policy = result.setdefault("residual_gap_cost_policy", {})
                if args.cycle_fixed_cost is not None:
                    policy["cycle_fixed_cost"] = args.cycle_fixed_cost
                if args.marginal_value_per_cycle_cost is not None:
                    policy["marginal_value_per_cycle_cost"] = args.marginal_value_per_cycle_cost
                if args.residual_gap_cost_below_policy:
                    policy["below_policy"] = True
                if args.marginal_repair_higher_value:
                    policy["marginal_repair_higher_value"] = True
            found = True
            break
    if not found:
        raise SystemExit(f"Unknown task pack item: {args.item_id}")
    remaining = [item for item in data.get("items", []) if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered"}]
    data["current_item_id"] = remaining[0].get("item_id") if remaining else None
    if not remaining and data.get("status") == "active":
        data["status"] = "completed"
    data.setdefault("mutation_log", []).append(
        {
            "timestamp": now_iso(),
            "action": "mark_consumed",
            "reason": args.reason or "pack item consumed by completed task",
            "item_id": args.item_id,
            "actor": "$derive-improvement-task",
        }
    )
    actual_after_ids = item_order(data)
    coherence_findings: list[dict[str, Any]] = []
    for key, actual_value in (
        ("proposed_after_item_ids", actual_after_ids),
        ("proposed_after_order", actual_after_ids),
    ):
        declared = coherence.get(key)
        if isinstance(declared, list) and [str(item) for item in declared] != actual_value:
            coherence_findings.append(
                {
                    "severity": "block",
                    "code": f"{key}_mismatch",
                    "message": "Consumed pack state does not match the declared post-mutation state.",
                    "evidence": {"declared": declared, "actual": actual_value},
                }
            )
    after_pack_sha256 = canonical_pack_sha256(data)
    if (
        coherence.get("contract_version") == PACK_COHERENCE_VERSION
        and coherence.get("before_pack_sha256") == after_pack_sha256
    ):
        coherence_findings.append(
            {
                "severity": "block",
                "code": "pack_mutation_noop",
                "message": "mark_consumed did not change the canonical pack body.",
            }
        )
    findings = validate_pack(data, path)
    findings.extend(coherence_findings)
    if any(item.get("severity") == "block" for item in findings):
        output = {
            "status": "block",
            "pack_path": rel_path(root, path),
            "pack_id": data.get("pack_id"),
            "pack_transition_verdict": {"status": "blocked", "evidence_ref": rel_path(root, path)},
            "findings": findings,
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    write_json(path, data)
    if args.render:
        write_render(root, path, data, args.language)
    mutation_receipt = {
        "schema_version": PACK_COHERENCE_VERSION,
        "canonical_pack_ref": rel_path(root, path),
        "before_pack_sha256": coherence.get("before_pack_sha256"),
        "after_pack_sha256": after_pack_sha256,
        "actual_before_item_ids": coherence.get("actual_before_item_ids"),
        "actual_before_order": coherence.get("actual_before_order"),
        "actual_before_current_item": coherence.get("actual_current_item"),
        "actual_after_item_ids": actual_after_ids,
        "actual_after_order": actual_after_ids,
        "actual_after_current_item": data.get("current_item_id"),
        "mutation_kind": "mark_consumed",
        "legacy_normalized": bool(coherence.get("legacy_normalized")),
    }
    output = {
        "status": "ok",
        "pack_path": rel_path(root, path),
        "pack_id": data.get("pack_id"),
        "current_item_id": data.get("current_item_id"),
        "pack_coherence": coherence,
        "pack_mutation_receipt": mutation_receipt,
        "pack_transition_verdict": {"status": "pass", "evidence_ref": rel_path(root, path)},
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect and render orchestrate-task-cycle task pack queues.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    status_p = sub.add_parser("status")
    status_p.add_argument("--format", choices=("json",), default="json")
    status_p.set_defaults(func=command_status)

    capabilities_p = sub.add_parser("capabilities", help="Print the deterministic task-pack schema and helper capability contract.")
    capabilities_p.set_defaults(func=command_capabilities)

    validate_p = sub.add_parser("validate")
    validate_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to all packs.")
    validate_p.add_argument("--strict-findings", action="store_true", help="Exit nonzero when validation emits any finding, including warnings.")
    validate_p.set_defaults(func=command_validate)

    recover_p = sub.add_parser("recover-replacement", help="Forward-complete prepared task-pack replacement transactions.")
    recover_p.set_defaults(func=command_recover_replacement)

    render_p = sub.add_parser("render")
    render_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to all packs.")
    render_p.add_argument("--language", default="ko", help="Markdown render language label.")
    render_p.set_defaults(func=command_render)

    next_p = sub.add_parser("next")
    next_p.set_defaults(func=command_next)

    consumed_p = sub.add_parser("mark-consumed")
    consumed_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to active pack.")
    consumed_p.add_argument("--pack-coherence-json", help="Inline JSON or path containing versioned canonical before/after pack coherence fields.")
    consumed_p.add_argument("--verdict-axes-json", help="Inline JSON or path containing verdict_contract_version and all six lifecycle verdict axes.")
    consumed_p.add_argument("--item-id", required=True)
    consumed_p.add_argument("--task-id")
    consumed_p.add_argument("--task-path")
    consumed_p.add_argument("--validation-verdict")
    consumed_p.add_argument("--run-report-path")
    consumed_p.add_argument("--run-report-sha256")
    consumed_p.add_argument("--validation-report-path")
    consumed_p.add_argument("--validation-report-sha256")
    consumed_p.add_argument("--validation-evidence-path", action="append")
    consumed_p.add_argument("--issue-packet-path")
    consumed_p.add_argument("--issue-packet-sha256")
    consumed_p.add_argument("--completion-evidence-path", action="append")
    consumed_p.add_argument("--progress-verdict")
    consumed_p.add_argument("--progress-kind")
    consumed_p.add_argument("--semantic-signature")
    consumed_p.add_argument("--blocker-signature")
    consumed_p.add_argument("--has-supplied-input-delta", action="store_true")
    consumed_p.add_argument("--supplied-input-artifact-path", action="append")
    consumed_p.add_argument("--acceptance-target-met", action="store_true")
    consumed_p.add_argument("--acceptance-diluted", action="store_true")
    consumed_p.add_argument("--explicit-descope-decision", action="store_true")
    consumed_p.add_argument("--residual-item-id")
    consumed_p.add_argument("--acceptance-provenance-evidence-path", action="append")
    consumed_p.add_argument("--required-verifier")
    consumed_p.add_argument("--acceptance-verifier-status", choices=["pass", "fail", "not_evaluated"])
    consumed_p.add_argument("--acceptance-verifier-evidence-path", action="append")
    consumed_p.add_argument("--required-gate-hook", action="append")
    consumed_p.add_argument("--gate-hook-status", choices=["pass", "supplied", "present", "not_supplied", "absent", "fail_quiet", "not_evaluated"])
    consumed_p.add_argument("--pass-with-unobserved-axes", action="store_true")
    consumed_p.add_argument("--unobserved-goal-axis", action="append")
    consumed_p.add_argument("--independently-verified-field", action="append")
    consumed_p.add_argument("--producer-attested-field", action="append")
    consumed_p.add_argument("--independent-source-separation-status", choices=["pass", "missing", "overlap", "blocked", "self_grounded"])
    consumed_p.add_argument("--independently-verified-downgraded-field", action="append")
    consumed_p.add_argument("--verification-input-path", action="append")
    consumed_p.add_argument("--verified-artifact-path", action="append")
    consumed_p.add_argument("--generation-dependent-count-key", action="store_true")
    consumed_p.add_argument("--effective-count-key")
    consumed_p.add_argument("--envelope-thaw-item-required", action="store_true")
    consumed_p.add_argument("--envelope-thaw-item")
    consumed_p.add_argument("--thaw-condition")
    consumed_p.add_argument("--thaw-schedule")
    consumed_p.add_argument("--instrumentation-supply-required", action="store_true")
    consumed_p.add_argument("--diagnostics-unavailable-streak")
    consumed_p.add_argument("--existing-diagnostics-sufficient", action="store_true")
    consumed_p.add_argument("--cycle-fixed-cost")
    consumed_p.add_argument("--marginal-value-per-cycle-cost")
    consumed_p.add_argument("--residual-gap-cost-below-policy", action="store_true")
    consumed_p.add_argument("--marginal-repair-higher-value", action="store_true")
    consumed_p.add_argument("--reason")
    consumed_p.add_argument("--language", default="ko")
    consumed_p.add_argument("--render", action="store_true")
    consumed_p.set_defaults(func=command_mark_consumed)

    mutate_p = sub.add_parser(
        "apply-mutation",
        description=(
            "Apply create, replace, promote, normalize_initial_selection_provenance, insert, reorder, "
            "skip, supersede, or terminal_block from a JSON plan."
        ),
        epilog=(
            "Initial-selection schemas and end-to-end examples: "
            "orchestrate-task-cycle/references/initial-selection-provenance.md"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mutate_p.add_argument("--plan", required=True, help="Mutation plan JSON path, inline JSON, or '-' for stdin.")
    mutate_p.add_argument("--action", help="Override action from the plan.")
    mutate_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to active pack or plan.pack_path.")
    mutate_p.add_argument("--language", default="ko")
    mutate_p.add_argument("--render", action="store_true")
    mutate_p.add_argument("--dry-run", action="store_true", help="Validate and render the proposed in-memory state without writing the canonical pack.")
    mutate_p.set_defaults(func=command_apply_mutation)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
