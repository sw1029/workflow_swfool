"""Closed inputs and authority checks for terminal-wait baseline publication."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .authority_artifacts import (
    validate_authority_artifacts,
    validate_authority_verification_binding,
)
from .authority_boundary import project_authority_packet
from .selection_decision_receipt import (
    acknowledgement_binding,
    read_selection_decision_receipt,
)
from .selection_tick_contract import (
    ACKNOWLEDGEMENT_KEYS,
    validate_selection_tick_v2,
)
from .selection_tick_premise import VERIFIED_PREMISE_CONTRACT
from .terminal_wait_baseline_store import (
    SHA256,
    canonical_sha256,
    read_bound_bytes,
    read_bound_json,
)
from .terminal_wait_source_contract import validate_rebased_terminal_source


PLAN_KEYS = {
    "schema_version",
    "artifact_kind",
    "task",
    "source_derive",
    "transition_evidence",
    "selection_baseline",
    "expected_current_snapshot_sha256",
    "authority_subject",
    "authority_packet",
    "pre_commit_verification",
    "consume_idempotency_key",
    "prepared_at",
}
AUTHORITY_SUBJECT_KEYS = {
    "schema_version",
    "artifact_kind",
    "task",
    "source_derive",
    "transition_evidence",
    "selection_baseline",
    "expected_current_snapshot_sha256",
}
BINDING_KEYS = {"ref", "sha256"}
TASK_KEYS = {"task_id", "ref", "sha256"}
OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
TASK_FIELD = re.compile(
    r"^-\s*(Status|Executable):\s*`?([^`\n]+?)`?\s*$",
    re.MULTILINE,
)


def _closed(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} requires exact fields {sorted(keys)}")
    return value


def binding(value: Any, label: str) -> dict[str, str]:
    row = _closed(value, BINDING_KEYS, label)
    ref = row.get("ref")
    digest = row.get("sha256")
    if (
        not isinstance(ref, str)
        or not isinstance(digest, str)
        or not ref
        or len(ref) > 512
        or ref != ref.strip()
        or "\\" in ref
        or "\x00" in ref
        or not SHA256.fullmatch(digest)
    ):
        raise ValueError(f"{label} requires a ref and lowercase SHA-256")
    pure = PurePosixPath(ref)
    if (
        pure.is_absolute()
        or pure.as_posix() != ref
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError(f"{label} requires a normalized workspace-relative ref")
    return {"ref": ref, "sha256": digest}


def _rfc3339(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an RFC3339 string")
    raw = value
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be RFC3339-compatible") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return raw


def _normalize_source_core(value: dict[str, Any]) -> dict[str, Any]:
    task = _closed(value.get("task"), TASK_KEYS, "task")
    task_id = task.get("task_id")
    task_sha256 = task.get("sha256")
    if (
        not isinstance(task_id, str)
        or not OPAQUE_ID.fullmatch(task_id)
        or task.get("ref") != "task.md"
        or not isinstance(task_sha256, str)
        or not SHA256.fullmatch(task_sha256)
    ):
        raise ValueError("task must bind one opaque ID and exact root task.md SHA-256")
    transition = value.get("transition_evidence")
    expected = value.get("expected_current_snapshot_sha256")
    if expected is not None and (
        not isinstance(expected, str) or not SHA256.fullmatch(expected)
    ):
        raise ValueError("expected current snapshot must be null or a SHA-256")
    return {
        "task": {
            "task_id": task_id,
            "ref": "task.md",
            "sha256": task_sha256,
        },
        "source_derive": binding(value.get("source_derive"), "source_derive"),
        "transition_evidence": (
            binding(transition, "transition_evidence")
            if transition is not None
            else None
        ),
        "selection_baseline": binding(
            value.get("selection_baseline"), "selection_baseline"
        ),
        "expected_current_snapshot_sha256": expected,
    }


def normalize_authority_subject(value: Any) -> dict[str, Any]:
    subject = _closed(
        value, AUTHORITY_SUBJECT_KEYS, "terminal-wait baseline authority subject"
    )
    if (
        subject.get("schema_version") != 1
        or subject.get("artifact_kind") != "terminal_wait_baseline_authority_subject"
    ):
        raise ValueError(
            "terminal-wait baseline authority subject schema or kind is invalid"
        )
    return {
        "schema_version": 1,
        "artifact_kind": "terminal_wait_baseline_authority_subject",
        **_normalize_source_core(subject),
    }


def normalize_plan(value: Any) -> dict[str, Any]:
    plan = _closed(value, PLAN_KEYS, "terminal-wait baseline plan")
    if (
        plan.get("schema_version") != 1
        or plan.get("artifact_kind") != "terminal_wait_baseline_plan"
    ):
        raise ValueError("terminal-wait baseline plan schema or kind is invalid")
    core = _normalize_source_core(plan)
    consume_key = plan.get("consume_idempotency_key")
    if not isinstance(consume_key, str):
        raise ValueError("consume idempotency key must be a string")
    if not IDEMPOTENCY_KEY.fullmatch(consume_key) or not consume_key.startswith(
        "terminal-wait-baseline:"
    ):
        raise ValueError("consume idempotency key must be operation-specific")
    return {
        "schema_version": 1,
        "artifact_kind": "terminal_wait_baseline_plan",
        **core,
        "authority_subject": binding(
            plan.get("authority_subject"), "authority_subject"
        ),
        "authority_packet": binding(plan.get("authority_packet"), "authority_packet"),
        "pre_commit_verification": binding(
            plan.get("pre_commit_verification"), "pre_commit_verification"
        ),
        "consume_idempotency_key": consume_key,
        "prepared_at": _rfc3339(plan.get("prepared_at"), "prepared_at"),
    }


def _task_is_terminal(body: bytes) -> None:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("task.md must be UTF-8") from exc
    values: dict[str, str] = {}
    for key, value in TASK_FIELD.findall(text):
        normalized = key.lower()
        if normalized in values:
            raise ValueError(f"task.md repeats {key}")
        values[normalized] = value.strip().strip("`")
    if set(values) != {"status", "executable"}:
        raise ValueError("task.md lacks an exact Status/Executable projection")
    if values["status"] not in {"completed", "terminal_wait", "terminal_blocked"}:
        raise ValueError("terminal-wait baseline requires a terminal task")
    if values["executable"].lower() != "false":
        raise ValueError("terminal-wait baseline requires a non-executable task")


def validate_selection_packet(
    packet: dict[str, Any], *, root: Path | None = None, allow_legacy_v1: bool = False
) -> dict[str, str]:
    if packet.get("format_version") == 2:
        validate_selection_tick_v2(packet)
    packet_id = packet.get("packet_id")
    expected_id = (
        "selection-tick-"
        + canonical_sha256(
            {key: value for key, value in packet.items() if key != "packet_id"}
        )[:32]
    )
    manifest = packet.get("observed_input_manifest_sha256")
    if (
        not isinstance(packet_id, str)
        or not isinstance(manifest, str)
        or packet_id != expected_id
        or packet.get("format_version") not in {1, 2}
        or packet.get("artifact_kind") != "selection_tick"
        or packet.get("status") not in {"baseline_recorded", "no_op"}
        or not SHA256.fullmatch(manifest)
        or packet.get("selection_required") is not False
        or packet.get("agent_fanout_allowed") is not False
        or packet.get("full_cycle_allowed") is not False
        or packet.get("mutation_performed") is not False
        or packet.get("not_goal_truth") is not True
        or packet.get("not_authority") is not True
    ):
        raise ValueError(
            "selection baseline is not a valid read-only terminal-wait packet"
        )
    version = packet.get("format_version")
    if version == 1:
        if not allow_legacy_v1:
            raise ValueError(
                "legacy selection baseline is historical-only and cannot be published"
            )
    elif (
        packet.get("premise_input_contract") != VERIFIED_PREMISE_CONTRACT
        or packet.get("wake_evaluation_rule")
        != "explicit-premise-or-bound-class-change-v1"
        or packet.get("wake_predicate_ids_are_policy_labels") is not True
    ):
        raise ValueError(
            "selection baseline does not enforce verified exact-subject re-entry"
        )
    if packet.get("baseline_rebased") is True:
        acknowledgement = packet.get("selection_acknowledgement_binding")
        if root is None or not isinstance(acknowledgement, dict):
            raise ValueError(
                "rebased selection baseline requires a persisted decision receipt"
            )
        if set(acknowledgement) != ACKNOWLEDGEMENT_KEYS:
            raise ValueError("selection acknowledgement binding schema is invalid")
        receipt_binding = {
            "ref": acknowledgement["selection_receipt_ref"],
            "sha256": acknowledgement["selection_receipt_sha256"],
        }
        try:
            receipt = read_selection_decision_receipt(
                root,
                receipt_binding,
                expected_trigger_binding={
                    "trigger_selection_tick_id": acknowledgement["trigger_tick_id"],
                    "trigger_selection_tick_sha256": acknowledgement[
                        "trigger_tick_sha256"
                    ],
                },
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                "rebased selection baseline decision receipt is invalid"
            ) from exc
        if (
            acknowledgement != acknowledgement_binding(receipt_binding, receipt)
            or packet.get("selection_acknowledgement_status") != "accepted"
            or packet.get("acknowledged_selection_tick_id")
            != acknowledgement["trigger_tick_id"]
        ):
            raise ValueError("rebased selection acknowledgement is inconsistent")
    return {"packet_id": packet_id, "observed_input_manifest_sha256": manifest}


def _validate_source_artifacts(
    root: Path,
    source: dict[str, Any],
    *,
    require_current_task: bool,
    allow_legacy_selection_v1: bool,
) -> tuple[dict[str, Any], dict[str, str]]:
    root = root.resolve(strict=True)
    if require_current_task:
        _, task_body = read_bound_bytes(
            root,
            {"ref": source["task"]["ref"], "sha256": source["task"]["sha256"]},
            "bound terminal task",
        )
        _task_is_terminal(task_body)
    if source["transition_evidence"] is not None:
        _, transition = read_bound_json(
            root, source["transition_evidence"], "transition evidence"
        )
        if not transition:
            raise ValueError("transition evidence cannot be empty")
    _, packet = read_bound_json(
        root, source["selection_baseline"], "selection baseline"
    )
    projection = validate_selection_packet(
        packet,
        root=root,
        allow_legacy_v1=allow_legacy_selection_v1,
    )
    _, derive = read_bound_json(root, source["source_derive"], "source derive result")
    if not derive:
        raise ValueError("source derive result cannot be empty")
    if packet.get("baseline_rebased") is True:
        acknowledgement = packet["selection_acknowledgement_binding"]
        receipt_binding = {
            "ref": acknowledgement["selection_receipt_ref"],
            "sha256": acknowledgement["selection_receipt_sha256"],
        }
        receipt = read_selection_decision_receipt(
            root,
            receipt_binding,
            expected_trigger_binding={
                "trigger_selection_tick_id": acknowledgement["trigger_tick_id"],
                "trigger_selection_tick_sha256": acknowledgement["trigger_tick_sha256"],
            },
        )
        validate_rebased_terminal_source(root, source, derive, packet, receipt)
    return packet, projection


def validate_authority_subject_sources(
    root: Path, subject: dict[str, Any], *, require_current_task: bool = True
) -> tuple[dict[str, Any], dict[str, str]]:
    normalized = normalize_authority_subject(subject)
    return _validate_source_artifacts(
        root,
        normalized,
        require_current_task=require_current_task,
        allow_legacy_selection_v1=False,
    )


def validate_sources(
    root: Path,
    plan: dict[str, Any],
    *,
    require_current_task: bool = True,
    allow_legacy_selection_v1: bool = False,
) -> tuple[dict[str, Any], dict[str, str]]:
    packet, projection = _validate_source_artifacts(
        root,
        plan,
        require_current_task=require_current_task,
        allow_legacy_selection_v1=allow_legacy_selection_v1,
    )
    validate_authority_subject_binding(root, plan)
    return packet, projection


def subject_digest(plan: dict[str, Any]) -> str:
    """Return the exact file digest used by authority subject preflight."""

    normalized = normalize_plan(plan)
    return normalized["authority_subject"]["sha256"]


def authority_subject_body(plan: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_plan(plan)
    return {
        "schema_version": 1,
        "artifact_kind": "terminal_wait_baseline_authority_subject",
        "task": normalized["task"],
        "source_derive": normalized["source_derive"],
        "transition_evidence": normalized["transition_evidence"],
        "selection_baseline": normalized["selection_baseline"],
        "expected_current_snapshot_sha256": normalized[
            "expected_current_snapshot_sha256"
        ],
    }


def authority_subject_revision(subject: dict[str, Any]) -> str:
    normalized = normalize_authority_subject(subject)
    return "twbs-" + canonical_sha256(normalized)[:32]


def validate_authority_subject_binding(
    root: Path, plan: dict[str, Any]
) -> dict[str, str]:
    expected = authority_subject_body(plan)
    subject_binding = plan["authority_subject"]
    digest = subject_binding["sha256"]
    expected_ref = f".task/terminal_wait_baseline/subjects/{digest}.json"
    _, subject = read_bound_json(
        root,
        subject_binding,
        "terminal-wait baseline authority subject",
        expected_prefix=".task/terminal_wait_baseline/subjects",
        expected_ref=expected_ref,
    )
    normalized = normalize_authority_subject(subject)
    if normalized != expected:
        raise ValueError(
            "authority subject does not bind this exact terminal-wait baseline"
        )
    return {
        "kind": "terminal_wait_baseline_binding",
        "ref": expected_ref,
        "digest": digest,
        "revision": authority_subject_revision(normalized),
    }


def validate_authority_phase(
    root: Path, plan: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    _, packet = read_bound_json(root, plan["authority_packet"], "authority packet")
    projection = project_authority_packet(packet)
    if not projection.valid:
        codes = ", ".join(str(row.get("code")) for row in projection.findings)
        raise ValueError(f"authority packet is invalid: {codes}")
    operation = packet.get("operation_binding") or {}
    decision = packet.get("decision_binding") or {}
    task = plan["task"]
    expected_subject = validate_authority_subject_binding(root, plan)
    if (
        decision.get("decision") != "allowed"
        or operation.get("skill_id") != "orchestrate-task-cycle"
        or operation.get("skill_version") != "2.0.0"
        or operation.get("operation_id") != "publish_terminal_wait_baseline_binding"
        or operation.get("operation_version") != "1"
        or operation.get("mutation_class") != "local_mutation"
        or packet.get("subject") != expected_subject
        or (packet.get("scope") or {}).get("task_id") != task["task_id"]
    ):
        raise ValueError(
            "authority packet does not authorize this exact baseline binding"
        )
    findings = validate_authority_artifacts(packet, root)
    if findings:
        codes = ", ".join(str(row.get("code")) for row in findings)
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


__all__ = (
    "authority_subject_body",
    "authority_subject_revision",
    "binding",
    "normalize_authority_subject",
    "normalize_plan",
    "subject_digest",
    "validate_authority_phase",
    "validate_authority_subject_binding",
    "validate_authority_subject_sources",
    "validate_selection_packet",
    "validate_sources",
)
