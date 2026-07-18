"""Closed, non-retroactive contract for retiring invalid closed task packs."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..authority_boundary import project_authority_packet
from ..authority_artifacts import (
    validate_authority_artifacts,
    validate_authority_verification_binding,
)
from .legacy_retirement_store import (
    SHA256,
    canonical_sha256,
    read_bound_json,
    safe_regular_file,
    sha256_file,
)
from .packet_io import load_json
from .storage import canonical_pack_sha256
from .validation import validate_pack


PLAN_KEYS = {
    "schema_version",
    "artifact_kind",
    "source_pack",
    "task_binding",
    "authority_packet",
    "pre_commit_verification",
    "consume_idempotency_key",
    "prepared_at",
    "reason_code",
}
PACK_BINDING_KEYS = {
    "ref",
    "file_sha256",
    "canonical_pack_sha256",
    "pack_id",
}
TASK_BINDING_KEYS = {"ref", "sha256"}
BINDING_KEYS = {"ref", "sha256"}
CLOSED_PACK_STATUSES = {"completed", "superseded", "terminal_blocked"}
LEGACY_ELIGIBILITY_CONTRACT_VERSION = 1
LEGACY_ELIGIBLE_FINDING_CODES = {
    "closed_pack_has_in_flight_item",
    "closed_pack_has_open_item",
    "completed_pack_has_noncompleted_items",
    "completion_provenance_missing",
    "current_item_not_earliest_ready",
    "cyclic_item_dependency",
    "item_dependency_bypassed",
    "item_dependency_not_topological",
    "multiple_in_flight_pack_items",
    "pack_operational_status_mismatch",
    "promotion_provenance_incomplete",
    "promotion_provenance_invalid",
    "promotion_provenance_missing",
    "self_item_dependency",
}
REASON_CODE = "legacy_closed_contract_migration_nonretroactive"
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
TASK_FIELD = re.compile(
    r"^-\s*(Status|Executable|Task Pack):\s*`?([^`\n]+?)`?\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class RetirementTarget:
    pack_path: Path
    pack: dict[str, Any]
    pack_bytes: bytes
    task_path: Path
    task_bytes: bytes
    blocking_findings: tuple[dict[str, Any], ...]
    finding_codes: tuple[str, ...]
    finding_fingerprint: str


def _closed(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} requires exact fields {sorted(keys)}")
    return value


def _binding(value: Any, label: str) -> dict[str, str]:
    row = _closed(value, BINDING_KEYS, label)
    ref = str(row.get("ref") or "")
    digest = str(row.get("sha256") or "")
    if not ref or not SHA256.fullmatch(digest):
        raise ValueError(f"{label} requires a ref and lowercase SHA-256")
    return {"ref": ref, "sha256": digest}


def _rfc3339(value: Any, label: str) -> str:
    raw = str(value or "")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be RFC3339-compatible") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return raw


def task_fields(body: bytes) -> dict[str, str]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("task.md must be UTF-8") from exc
    values: dict[str, str] = {}
    for key, value in TASK_FIELD.findall(text):
        normalized = key.lower().replace(" ", "_")
        if normalized in values:
            raise ValueError(f"task.md repeats {key}")
        values[normalized] = value.strip().strip("`")
    required = {"status", "executable", "task_pack"}
    if set(values) != required:
        raise ValueError(
            "task.md lacks an exact Status/Executable/Task Pack projection"
        )
    return values


def normalize_plan(value: Any) -> dict[str, Any]:
    plan = _closed(value, PLAN_KEYS, "legacy retirement plan")
    if (
        plan.get("schema_version") != 1
        or plan.get("artifact_kind") != "legacy_task_pack_retirement_plan"
    ):
        raise ValueError("legacy retirement plan schema or kind is invalid")
    source = _closed(plan.get("source_pack"), PACK_BINDING_KEYS, "source_pack")
    source_ref = str(source.get("ref") or "")
    pure = Path(source_ref)
    if (
        pure.is_absolute()
        or pure.parent.as_posix() != ".task/task_pack"
        or pure.suffix != ".json"
    ):
        raise ValueError("source_pack.ref must identify one top-level task-pack JSON")
    file_digest = str(source.get("file_sha256") or "")
    canonical_digest = str(source.get("canonical_pack_sha256") or "")
    pack_id = str(source.get("pack_id") or "")
    if not SHA256.fullmatch(file_digest) or not SHA256.fullmatch(canonical_digest):
        raise ValueError("source_pack requires exact file and canonical SHA-256 values")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", pack_id):
        raise ValueError("source_pack.pack_id must be a bounded opaque ID")
    task = _closed(plan.get("task_binding"), TASK_BINDING_KEYS, "task_binding")
    if task.get("ref") != "task.md" or not SHA256.fullmatch(
        str(task.get("sha256") or "")
    ):
        raise ValueError("task_binding must exactly bind root task.md")
    consume_key = str(plan.get("consume_idempotency_key") or "")
    if not IDEMPOTENCY_KEY.fullmatch(consume_key):
        raise ValueError("consume_idempotency_key must be a bounded opaque key")
    if not consume_key.startswith("task-pack-retire:"):
        raise ValueError("consume_idempotency_key must be operation-specific")
    if plan.get("reason_code") != REASON_CODE:
        raise ValueError("legacy retirement reason_code is not supported")
    prepared_at = _rfc3339(plan.get("prepared_at"), "prepared_at")
    return {
        "schema_version": 1,
        "artifact_kind": "legacy_task_pack_retirement_plan",
        "source_pack": {
            "ref": source_ref,
            "file_sha256": file_digest,
            "canonical_pack_sha256": canonical_digest,
            "pack_id": pack_id,
        },
        "task_binding": {
            "ref": "task.md",
            "sha256": str(task["sha256"]),
        },
        "authority_packet": _binding(plan.get("authority_packet"), "authority_packet"),
        "pre_commit_verification": _binding(
            plan.get("pre_commit_verification"), "pre_commit_verification"
        ),
        "consume_idempotency_key": consume_key,
        "prepared_at": prepared_at,
        "reason_code": REASON_CODE,
    }


def validate_target(root: Path, plan: dict[str, Any]) -> RetirementTarget:
    root = root.resolve(strict=True)
    source = plan["source_pack"]
    pack_path = safe_regular_file(root, source["ref"], "source task pack")
    if pack_path.parent != root / ".task" / "task_pack":
        raise ValueError("source task pack must be a top-level canonical pack")
    pack_bytes = pack_path.read_bytes()
    if sha256_file(pack_path) != source["file_sha256"]:
        raise ValueError("source task-pack bytes drifted from the plan")
    pack = load_json(pack_path)
    if pack.get("pack_id") != source["pack_id"]:
        raise ValueError("source task-pack identity does not match the plan")
    if canonical_pack_sha256(pack) != source["canonical_pack_sha256"]:
        raise ValueError("source task-pack canonical state drifted from the plan")
    declared_status = str(pack.get("status") or "")
    if declared_status not in CLOSED_PACK_STATUSES:
        raise ValueError("only a declared-closed historical pack may be retired")
    blocking = tuple(
        finding
        for finding in validate_pack(pack, pack_path)
        if finding.get("severity") == "block"
    )
    codes = tuple(sorted({str(finding.get("code") or "") for finding in blocking}))
    if not blocking:
        raise ValueError("a clean task pack cannot receive a legacy retirement overlay")
    unknown = sorted(set(codes) - LEGACY_ELIGIBLE_FINDING_CODES)
    if unknown:
        raise ValueError(
            "task pack has blockers outside the legacy eligibility contract: "
            + ", ".join(unknown)
        )
    task_path = safe_regular_file(
        root, "task.md", "current task", expected_ref="task.md"
    )
    task_bytes = task_path.read_bytes()
    if sha256_file(task_path) != plan["task_binding"]["sha256"]:
        raise ValueError("current task bytes drifted from the retirement plan")
    fields = task_fields(task_bytes)
    if fields["status"] not in {"completed", "terminal_wait", "terminal_blocked"}:
        raise ValueError("legacy retirement requires a non-executable terminal task")
    if fields["executable"].lower() != "false" or fields["task_pack"].lower() != "none":
        raise ValueError("current task is still bound to executable task-pack work")
    fingerprint = canonical_sha256(list(blocking))
    return RetirementTarget(
        pack_path=pack_path,
        pack=pack,
        pack_bytes=pack_bytes,
        task_path=task_path,
        task_bytes=task_bytes,
        blocking_findings=blocking,
        finding_codes=codes,
        finding_fingerprint=fingerprint,
    )


def validate_authority_phase(
    root: Path,
    plan: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    _, packet = read_bound_json(
        root, plan["authority_packet"], "orchestrator authority packet"
    )
    projection = project_authority_packet(packet)
    if not projection.valid:
        codes = ", ".join(str(row.get("code")) for row in projection.findings)
        raise ValueError(f"authority packet is invalid: {codes}")
    operation = packet.get("operation_binding") or {}
    decision = packet.get("decision_binding") or {}
    source = plan["source_pack"]
    expected_subject = {
        "kind": "task_pack",
        "ref": source["ref"],
        "digest": source["file_sha256"],
        "revision": source["pack_id"],
    }
    if (
        decision.get("decision") != "allowed"
        or operation.get("skill_id") != "orchestrate-task-cycle"
        or operation.get("skill_version") != "2.0.0"
        or operation.get("operation_id") != "mutate_task_topology"
        or operation.get("operation_version") != "1"
        or operation.get("mutation_class") != "local_mutation"
        or packet.get("subject") != expected_subject
        or (packet.get("scope") or {}).get("pack_id") != source["pack_id"]
    ):
        raise ValueError("authority packet does not authorize this exact source pack")
    current_findings = validate_authority_artifacts(packet, root)
    if current_findings:
        codes = ", ".join(str(row.get("code")) for row in current_findings)
        raise ValueError(f"current authority artifacts are stale: {codes}")
    findings = validate_authority_verification_binding(
        packet,
        plan["pre_commit_verification"],
        root,
        expected_stage="pre_commit",
    )
    if findings:
        codes = ", ".join(str(row.get("code")) for row in findings)
        raise ValueError(f"pre-commit authority verification failed: {codes}")
    _, verification = read_bound_json(
        root,
        plan["pre_commit_verification"],
        "pre-commit authority verification",
        expected_prefix=".task/authorization/verifications",
    )
    return packet, verification


def plan_fingerprint(plan: dict[str, Any]) -> str:
    return canonical_sha256(normalize_plan(plan))


__all__ = (
    "CLOSED_PACK_STATUSES",
    "LEGACY_ELIGIBILITY_CONTRACT_VERSION",
    "LEGACY_ELIGIBLE_FINDING_CODES",
    "REASON_CODE",
    "RetirementTarget",
    "normalize_plan",
    "plan_fingerprint",
    "task_fields",
    "validate_authority_phase",
    "validate_target",
)
