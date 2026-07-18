#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from .artifact_store import snapshot_file


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OPERATIONS = {"task_pack.initial_selection", "task_pack.normalize_initial_selection"}
TEMPORALITIES = {
    "contemporaneous_selection_authority",
    "current_ratification",
    "retrospective_evidence_assessment",
}
FORBIDDEN_KEYS = {
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
AUTHORITY_SOURCE_KINDS = {
    "explicit_current_user_instruction",
    "effective_authority_policy",
    "contemporaneous_authority_record",
}
CONTEMPORANEOUS_SOURCE_KINDS = {
    "explicit_current_user_instruction",
    "effective_authority_policy",
    "contemporaneous_authority_record",
}
NORMALIZATION_ALLOWED_EFFECTS = {"append_initial_selection_normalization_provenance"}
INITIAL_SELECTION_ALLOWED_EFFECTS = {"promote_first_pack_item"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_workspace_file(root: Path, value: Any, label: str) -> Path:
    raw = Path(str(value or "").strip())
    if not str(value or "").strip() or raw.is_absolute():
        raise SystemExit(f"{label} must be a workspace-relative file path.")
    candidate = root.resolve()
    for part in raw.parts:
        candidate /= part
        if candidate.is_symlink():
            raise SystemExit(f"{label} must not traverse a symlink component.")
    path = candidate.resolve(strict=False)
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"{label} escapes the workspace.") from exc
    if not path.is_file():
        raise SystemExit(
            f"{label} does not identify an existing regular file: {raw.as_posix()}"
        )
    return path


def parse_time(value: Any, label: str) -> dt.datetime:
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


def forbidden_key_paths(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if str(key).lower() in FORBIDDEN_KEYS:
                found.append(path)
            found.extend(forbidden_key_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(forbidden_key_paths(item, f"{prefix}[{index}]"))
    return found


def required_sha(value: Any, label: str) -> str:
    normalized = str(value or "").removeprefix("sha256:").lower()
    if not SHA256_RE.fullmatch(normalized):
        raise SystemExit(f"{label} must be a full lowercase SHA-256 digest.")
    return normalized


def _validate_subject(
    receipt: dict[str, Any], expected: dict[str, Any] | None
) -> dict[str, Any]:
    subject = receipt.get("subject")
    if not isinstance(subject, dict):
        raise SystemExit("Authority receipt subject must be an object.")
    fields = (
        "pack_ref",
        "pack_creation_snapshot_ref",
        "pack_creation_snapshot_sha256",
        "initial_item_id",
        "initial_order",
        "task_id",
        "task_snapshot_ref",
        "task_snapshot_sha256",
    )
    missing = [field for field in fields if subject.get(field) in (None, "")]
    if missing or subject.get("initial_order") != 1:
        raise SystemExit(
            f"Authority receipt subject is incomplete or not first-order: {', '.join(missing)}"
        )
    required_sha(
        subject.get("pack_creation_snapshot_sha256"),
        "subject.pack_creation_snapshot_sha256",
    )
    required_sha(subject.get("task_snapshot_sha256"), "subject.task_snapshot_sha256")
    if expected is not None and subject != expected:
        raise SystemExit(
            "Authority receipt subject does not match the expected operation subject."
        )
    return subject


def _validate_basis(root: Path, receipt: dict[str, Any], schema: int) -> str:
    basis = receipt.get("authority_basis")
    if not isinstance(basis, dict):
        raise SystemExit("Authority receipt authority_basis must be an object.")
    prefix = "" if schema == 1 else "_snapshot"
    policy_ref = f"policy{prefix}_ref"
    policy_sha = f"policy{prefix}_sha256"
    source_ref = "source_evidence_ref" if schema == 1 else "source_snapshot_ref"
    source_sha = "source_evidence_sha256" if schema == 1 else "source_snapshot_sha256"
    policy_path = resolve_workspace_file(
        root, basis.get(policy_ref), f"authority_basis.{policy_ref}"
    )
    source_path = resolve_workspace_file(
        root, basis.get(source_ref), f"authority_basis.{source_ref}"
    )
    if sha256_file(policy_path) != required_sha(
        basis.get(policy_sha), f"authority_basis.{policy_sha}"
    ):
        label = "policy" if schema == 1 else "policy snapshot"
        raise SystemExit(f"Authority {label} SHA-256 does not match the receipt.")
    if sha256_file(source_path) != required_sha(
        basis.get(source_sha), f"authority_basis.{source_sha}"
    ):
        label = "source-evidence" if schema == 1 else "source snapshot"
        raise SystemExit(f"Authority {label} SHA-256 does not match the receipt.")
    if basis.get("integrity_status") != "verified":
        raise SystemExit("Authority receipt requires verified source integrity.")
    source_kind = str(basis.get("source_kind") or "")
    if (
        source_kind not in AUTHORITY_SOURCE_KINDS
        or not str(basis.get("source_id") or "").strip()
    ):
        raise SystemExit(
            "Authority receipt requires a supported source_kind and opaque source_id."
        )
    return source_kind


def _validate_historical(
    receipt: dict[str, Any],
    temporality: str,
    source_kind: str,
    effective: dt.datetime,
    selected: dt.datetime | None,
) -> dict[str, Any]:
    historical = receipt.get("historical_effect")
    if not isinstance(historical, dict):
        raise SystemExit("Authority receipt historical_effect must be an object.")
    verified_pass = (
        historical.get("historical_selection_authority_status") == "verified"
        and historical.get("historical_authority_verdict") == "pass"
        and historical.get("retroactive_claim_allowed") is False
    )
    if temporality == "current_ratification":
        if source_kind != "explicit_current_user_instruction":
            raise SystemExit(
                "Current ratification requires explicit current user instruction evidence."
            )
        if (
            historical.get("historical_selection_authority_status")
            != "unverifiable_before_ratification"
        ):
            raise SystemExit(
                "Current ratification must preserve unverified historical selection authority."
            )
        if (
            historical.get("historical_authority_verdict") != "partial"
            or historical.get("retroactive_claim_allowed") is not False
        ):
            raise SystemExit(
                "Current ratification cannot claim a historical pass or retroactive authority."
            )
        if selected is not None and effective <= selected:
            raise SystemExit(
                "Current ratification must be effective after the original selection."
            )
    elif temporality == "contemporaneous_selection_authority":
        if source_kind not in CONTEMPORANEOUS_SOURCE_KINDS:
            raise SystemExit(
                "Contemporaneous authority requires a supported contemporaneous source."
            )
        if not verified_pass:
            raise SystemExit(
                "Contemporaneous authority requires a verified historical pass without retroactive claims."
            )
        if selected is not None and effective > selected:
            raise SystemExit(
                "Contemporaneous authority must be effective by the original selection."
            )
    elif temporality == "retrospective_evidence_assessment":
        if (
            receipt.get("operation") != "task_pack.normalize_initial_selection"
            or source_kind != "contemporaneous_authority_record"
        ):
            raise SystemExit(
                "Retrospective assessment may only normalize from a contemporaneous authority record."
            )
        if not verified_pass:
            raise SystemExit(
                "Retrospective assessment requires verified immutable historical authority."
            )
        if selected is not None and effective > selected:
            raise SystemExit(
                "Retrospective evidence must predate or equal the original selection."
            )
    return historical


def _validate_effects(receipt: dict[str, Any]) -> None:
    effects = set(str(item) for item in receipt.get("allowed_effects") or [])
    operation = receipt.get("operation")
    if (
        operation == "task_pack.normalize_initial_selection"
        and effects != NORMALIZATION_ALLOWED_EFFECTS
    ):
        raise SystemExit(
            "Task-pack normalization receipt effects must be provenance-only."
        )
    if (
        operation == "task_pack.initial_selection"
        and effects != INITIAL_SELECTION_ALLOWED_EFFECTS
    ):
        raise SystemExit(
            "Task-pack initial-selection receipt effects must be first-promotion only."
        )


def validate_receipt(
    root: Path,
    receipt: dict[str, Any],
    expected_subject: dict[str, Any] | None = None,
    selected_at: Any | None = None,
) -> dict[str, Any]:
    schema = receipt.get("schema_version")
    if schema not in {1, 2} or receipt.get("receipt_kind") != "operation_authority":
        raise SystemExit(
            "Authority receipt requires schema_version=1|2 and receipt_kind=operation_authority."
        )
    if not str(receipt.get("receipt_id") or "").strip():
        raise SystemExit("Authority receipt requires a stable receipt_id.")
    if (
        receipt.get("operation") not in OPERATIONS
        or receipt.get("decision") != "allowed"
    ):
        raise SystemExit(
            "Authority receipt operation is unsupported or decision is not allowed."
        )
    temporality = str(receipt.get("basis_temporality") or "")
    if temporality not in TEMPORALITIES:
        raise SystemExit("Authority receipt basis_temporality is invalid.")
    issued = parse_time(receipt.get("issued_at"), "issued_at")
    effective = parse_time(receipt.get("effective_at"), "effective_at")
    if effective > issued:
        raise SystemExit("Authority receipt effective_at cannot be after issued_at.")
    selected = (
        parse_time(selected_at, "selected_at") if selected_at is not None else None
    )
    sensitive = forbidden_key_paths(receipt)
    if sensitive:
        raise SystemExit(
            f"Authority receipt contains forbidden sensitive/body keys: {', '.join(sensitive)}"
        )
    subject = _validate_subject(receipt, expected_subject)
    source_kind = _validate_basis(root, receipt, schema)
    historical = _validate_historical(
        receipt, temporality, source_kind, effective, selected
    )
    _validate_effects(receipt)
    return {
        "status": "valid",
        "schema_version": schema,
        "receipt_id": receipt.get("receipt_id"),
        "operation": receipt.get("operation"),
        "basis_temporality": temporality,
        "temporality_binding_status": "verified" if selected else "consumer_required",
        "subject": subject,
        "historical_effect": historical,
    }


def load_json_value(value: str) -> dict[str, Any]:
    try:
        candidate = Path(value)
        is_file = candidate.is_file()
    except OSError:
        is_file = False
    if is_file:
        loaded = json.loads(candidate.read_text(encoding="utf-8"))
    else:
        loaded = json.loads(value)
    if not isinstance(loaded, dict):
        raise SystemExit("JSON input must be an object.")
    return loaded


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def command_issue(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    receipt = load_json_value(args.plan)
    basis = receipt.setdefault("authority_basis", {})
    policy = resolve_workspace_file(
        root, basis.get("policy_ref"), "authority_basis.policy_ref"
    )
    source = resolve_workspace_file(
        root, basis.get("source_evidence_ref"), "authority_basis.source_evidence_ref"
    )
    basis["policy_sha256"] = sha256_file(policy)
    basis["source_evidence_sha256"] = sha256_file(source)
    if receipt.get("schema_version") == 2:
        policy_snapshot = snapshot_file(root, str(basis.get("policy_ref")), "policy")
        source_snapshot = snapshot_file(
            root, str(basis.get("source_evidence_ref")), "source_approval"
        )
        basis["policy_snapshot_ref"] = policy_snapshot["ref"]
        basis["policy_snapshot_sha256"] = policy_snapshot["sha256"]
        basis["source_snapshot_ref"] = source_snapshot["ref"]
        basis["source_snapshot_sha256"] = source_snapshot["sha256"]
    validated = validate_receipt(root, receipt)
    raw_output = Path(args.output)
    if raw_output.is_absolute():
        raise SystemExit("Receipt output must be workspace-relative.")
    output = (root / raw_output).resolve(strict=False)
    boundary = (root / ".task" / "authority_receipts").resolve(strict=False)
    try:
        output.relative_to(boundary)
    except ValueError as exc:
        raise SystemExit(
            "Receipt output must stay under .task/authority_receipts/."
        ) from exc
    if output.suffix != ".json":
        raise SystemExit("Receipt output must be JSON.")
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if existing != receipt:
            raise SystemExit(
                "A conflicting authority receipt already exists at the output path."
            )
    else:
        write_json_atomic(output, receipt)
    result = {
        **validated,
        "receipt_ref": output.relative_to(root).as_posix(),
        "receipt_sha256": sha256_file(output),
    }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = resolve_workspace_file(root, args.receipt, "receipt")
    if args.receipt_sha256 and sha256_file(path) != required_sha(
        args.receipt_sha256, "receipt_sha256"
    ):
        raise SystemExit("Authority receipt SHA-256 does not match.")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    expected = (
        load_json_value(args.expected_subject_json)
        if args.expected_subject_json
        else None
    )
    result = validate_receipt(
        root, receipt, expected, getattr(args, "selected_at", None)
    )
    result.update(
        {
            "receipt_ref": path.relative_to(root).as_posix(),
            "receipt_sha256": sha256_file(path),
        }
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Issue or validate bounded operation authority receipts."
    )
    parser.add_argument("--root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)
    issue = subparsers.add_parser("issue")
    issue.add_argument(
        "--plan", required=True, help="Receipt JSON or a JSON file path."
    )
    issue.add_argument("--output", required=True)
    issue.set_defaults(func=command_issue)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--receipt", required=True)
    validate.add_argument("--receipt-sha256")
    validate.add_argument("--expected-subject-json")
    validate.add_argument(
        "--selected-at",
        help="Original selection RFC3339 time; omit only for structural validation before consumer binding.",
    )
    validate.set_defaults(func=command_validate)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
