from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical import parse_time
from .canonical import resolve_workspace_path
from .canonical import sha256_file
from .contracts import CARDINALITIES
from .contracts import DECISION_CLASSES
from .contracts import RISK_TIERS
from .contracts import rank_value
from .contracts import risk_value
from .contracts import validate_subject


SOURCE_KINDS = {
    "platform_session_ceiling": "S4",
    "explicit_user_instruction": "S3",
    "delegated_policy_steward": "S2",
    "cycle_coordination_grant": "S1",
}
APPROVAL_KEYS = {
    "schema_version",
    "artifact_kind",
    "approval_id",
    "source_kind",
    "source_rank",
    "decision_type",
    "capabilities",
    "subjects",
    "operations",
    "risk_ceiling",
    "decision_classes",
    "cardinalities",
    "max_uses",
    "grant_ids",
    "request_digests",
    "lineage_ids",
    "delegation_binding",
    "not_before",
    "expires_at",
    "evidence_id",
    "integrity_status",
}
OPERATION_KEYS = {"skill_id", "skill_version", "operation_id", "operation_version"}


def _unique_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SystemExit(f"{label} must be a non-empty list.")
    normalized = sorted(set(str(item) for item in value))
    if len(normalized) != len(value) or any(
        not item or "*" in item for item in normalized
    ):
        raise SystemExit(f"{label} must contain unique exact values without wildcards.")
    return normalized


def _digests(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SystemExit("source approval request_digests must be a list.")
    normalized = sorted(set(str(item) for item in value))
    if len(normalized) != len(value) or any(
        len(item) != 64 or any(char not in "0123456789abcdef" for char in item)
        for item in normalized
    ):
        raise SystemExit(
            "source approval request_digests must be unique SHA-256 values."
        )
    return normalized


def _operations(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise SystemExit("source approval operations must be non-empty.")
    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != OPERATION_KEYS:
            raise SystemExit(f"source approval operations[{index}] is not closed.")
        operation = {key: str(item[key] or "") for key in sorted(OPERATION_KEYS)}
        if any(not field or "*" in field for field in operation.values()):
            raise SystemExit(
                "source approval operations must be exact without wildcards."
            )
        normalized.append(operation)
    if len({tuple(item.values()) for item in normalized}) != len(normalized):
        raise SystemExit("source approval operations must be unique.")
    return sorted(normalized, key=lambda item: tuple(item.values()))


def _delegation_binding(value: Any, required: bool) -> dict[str, str] | None:
    if value is None:
        if required:
            raise SystemExit("Delegated source approval requires delegation_binding.")
        return None
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise SystemExit("delegation_binding must contain exact ref and sha256.")
    ref = str(value["ref"] or "").strip()
    digest = str(value["sha256"] or "")
    if not ref or Path(ref).is_absolute() or "*" in ref or ".." in Path(ref).parts:
        raise SystemExit("delegation_binding.ref must be workspace-relative and exact.")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise SystemExit("delegation_binding.sha256 must be a lowercase SHA-256.")
    return {"ref": ref, "sha256": digest}


def validate_source_approval(value: dict[str, Any]) -> dict[str, Any]:
    extra = sorted(set(value) - APPROVAL_KEYS)
    missing = sorted(APPROVAL_KEYS - set(value))
    if extra or missing:
        raise SystemExit(f"Source approval has unknown={extra} missing={missing}.")
    if (
        value["schema_version"] != 2
        or value["artifact_kind"] != "authority_source_approval"
    ):
        raise SystemExit(
            "Source approval requires schema_version=2 and artifact_kind=authority_source_approval."
        )
    source_kind = str(value["source_kind"])
    source_rank = str(value["source_rank"])
    if SOURCE_KINDS.get(source_kind) != source_rank:
        raise SystemExit(
            "Source approval kind and rank do not match the closed source hierarchy."
        )
    if value["decision_type"] != "grant_authority":
        raise SystemExit(
            "Source approval cannot substitute for another typed decision."
        )
    if value["integrity_status"] != "verified":
        raise SystemExit("Source approval integrity must be verified.")
    decisions = _unique_strings(
        value["decision_classes"], "source approval decision_classes"
    )
    cardinalities = _unique_strings(
        value["cardinalities"], "source approval cardinalities"
    )
    if any(item not in DECISION_CLASSES for item in decisions):
        raise SystemExit("Source approval contains an unknown decision class.")
    if any(item not in CARDINALITIES for item in cardinalities):
        raise SystemExit("Source approval contains an unknown cardinality.")
    risk = str(value["risk_ceiling"])
    if risk not in RISK_TIERS:
        raise SystemExit("Source approval risk ceiling is invalid.")
    max_uses = value["max_uses"]
    if max_uses is not None and (
        not isinstance(max_uses, int) or isinstance(max_uses, bool) or max_uses < 1
    ):
        raise SystemExit("Source approval max_uses must be null or positive.")
    subjects = value["subjects"]
    if not isinstance(subjects, list) or not subjects:
        raise SystemExit("Source approval subjects must be non-empty.")
    return {
        "schema_version": 2,
        "artifact_kind": "authority_source_approval",
        "approval_id": str(value["approval_id"]),
        "source_kind": source_kind,
        "source_rank": source_rank,
        "decision_type": "grant_authority",
        "capabilities": _unique_strings(
            value["capabilities"], "source approval capabilities"
        ),
        "subjects": [
            validate_subject(item, f"source approval subjects[{index}]")
            for index, item in enumerate(subjects)
        ],
        "operations": _operations(value["operations"]),
        "risk_ceiling": risk,
        "decision_classes": decisions,
        "cardinalities": cardinalities,
        "max_uses": max_uses,
        "grant_ids": _unique_strings(value["grant_ids"], "source approval grant_ids"),
        "request_digests": _digests(value["request_digests"]),
        "lineage_ids": _unique_strings(
            value["lineage_ids"], "source approval lineage_ids"
        ),
        "delegation_binding": _delegation_binding(
            value["delegation_binding"], source_rank in {"S1", "S2"}
        ),
        "not_before": parse_time(
            value["not_before"], "source approval not_before"
        ).isoformat(),
        "expires_at": parse_time(
            value["expires_at"], "source approval expires_at"
        ).isoformat()
        if value["expires_at"]
        else None,
        "evidence_id": str(value["evidence_id"]),
        "integrity_status": "verified",
    }


def load_source_approval(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"Source approval must be closed JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit("Source approval must be a JSON object.")
    return validate_source_approval(value)


def _scope_set(items: list[dict[str, Any]]) -> set[tuple[str, ...]]:
    return {tuple(str(item[key]) for key in sorted(item)) for item in items}


def _validate_delegated_subset(
    approval: dict[str, Any], parent: dict[str, Any]
) -> None:
    if rank_value(parent["source_rank"]) <= rank_value(approval["source_rank"]):
        raise SystemExit(
            "Delegated source approval must bind a strictly higher-rank source approval."
        )
    subset_fields = (
        "capabilities",
        "decision_classes",
        "cardinalities",
        "grant_ids",
        "request_digests",
        "lineage_ids",
    )
    for field in subset_fields:
        if not set(approval[field]).issubset(parent[field]):
            raise SystemExit(
                f"Delegated source approval {field} exceeds its higher-rank source."
            )
    for field in ("subjects", "operations"):
        if not _scope_set(approval[field]).issubset(_scope_set(parent[field])):
            raise SystemExit(
                f"Delegated source approval {field} exceeds its higher-rank source."
            )
    if risk_value(approval["risk_ceiling"]) > risk_value(parent["risk_ceiling"]):
        raise SystemExit(
            "Delegated source approval risk ceiling exceeds its higher-rank source."
        )
    if parent["max_uses"] is not None and (
        approval["max_uses"] is None or approval["max_uses"] > parent["max_uses"]
    ):
        raise SystemExit(
            "Delegated source approval use budget exceeds its higher-rank source."
        )
    if parse_time(approval["not_before"], "delegated source not_before") < parse_time(
        parent["not_before"], "higher-rank source not_before"
    ):
        raise SystemExit(
            "Delegated source approval begins before its higher-rank source."
        )
    parent_expiry = parent["expires_at"]
    approval_expiry = approval["expires_at"]
    if parent_expiry and (
        not approval_expiry
        or parse_time(approval_expiry, "delegated source expires_at")
        > parse_time(parent_expiry, "higher-rank source expires_at")
    ):
        raise SystemExit("Delegated source approval outlives its higher-rank source.")


def validate_delegation_lineage(
    root: Path, approval: dict[str, Any], *, effective_at: str
) -> None:
    """Prove every S1/S2 approval narrows an immutable higher-rank source."""
    now = parse_time(effective_at, "delegated source effective_at")
    current = approval
    seen_approvals: set[str] = set()
    seen_bindings: set[tuple[str, str]] = set()
    while True:
        approval_id = current["approval_id"]
        if approval_id in seen_approvals:
            raise SystemExit("Delegated source approval lineage is circular.")
        seen_approvals.add(approval_id)
        if now < parse_time(current["not_before"], "source approval not_before"):
            raise SystemExit("Delegated source approval lineage is not yet effective.")
        if current["expires_at"] and now >= parse_time(
            current["expires_at"], "source approval expires_at"
        ):
            raise SystemExit("Delegated source approval lineage has expired.")
        if current["source_rank"] in {"S3", "S4"}:
            return

        binding = current["delegation_binding"]
        if binding is None:
            raise SystemExit(
                "S1/S2 source approval lacks its higher-rank delegation binding."
            )
        binding_identity = (binding["ref"], binding["sha256"])
        if binding_identity in seen_bindings:
            raise SystemExit("Delegated source approval lineage is circular.")
        seen_bindings.add(binding_identity)
        parent_path = resolve_workspace_path(root, binding["ref"], "delegation_binding")
        if sha256_file(parent_path) != binding["sha256"]:
            raise SystemExit("Delegation binding digest mismatch.")
        parent = load_source_approval(parent_path)
        _validate_delegated_subset(current, parent)
        current = parent


def validate_for_grant(
    root: Path, approval: dict[str, Any], grant: dict[str, Any]
) -> None:
    if "authority.grant.issue" not in approval["capabilities"]:
        raise SystemExit("Source approval lacks authority.grant.issue.")
    if approval["source_rank"] != grant["issuer_rank"]:
        raise SystemExit("Grant issuer_rank must equal its source approval rank.")
    if grant["grant_id"] not in approval["grant_ids"]:
        raise SystemExit("Source approval does not bind this exact grant ID.")
    if grant["lineage_id"] not in approval["lineage_ids"]:
        raise SystemExit("Source approval does not bind this exact grant lineage.")
    if not set(grant["capabilities"]).issubset(approval["capabilities"]):
        raise SystemExit("Grant capabilities exceed its source approval.")
    if not {tuple(item.values()) for item in grant["subjects"]}.issubset(
        {tuple(item.values()) for item in approval["subjects"]}
    ):
        raise SystemExit("Grant subjects exceed its source approval.")
    if not {tuple(item.values()) for item in grant["operations"]}.issubset(
        {tuple(item.values()) for item in approval["operations"]}
    ):
        raise SystemExit("Grant operations exceed its source approval.")
    if risk_value(grant["risk_ceiling"]) > risk_value(approval["risk_ceiling"]):
        raise SystemExit("Grant risk ceiling exceeds its source approval.")
    if not set(grant["decision_classes"]).issubset(approval["decision_classes"]):
        raise SystemExit("Grant decision classes exceed its source approval.")
    if grant["cardinality"] not in approval["cardinalities"]:
        raise SystemExit("Grant cardinality exceeds its source approval.")
    if approval["max_uses"] is not None and (
        grant["max_uses"] is None or grant["max_uses"] > approval["max_uses"]
    ):
        raise SystemExit("Grant use budget exceeds its source approval.")
    if parse_time(grant["not_before"], "grant.not_before") < parse_time(
        approval["not_before"], "source approval not_before"
    ):
        raise SystemExit("Grant begins before its source approval.")
    created = parse_time(grant["created_at"], "grant.created_at")
    if created < parse_time(approval["not_before"], "source approval not_before"):
        raise SystemExit("Grant creation predates its source approval.")
    if approval["expires_at"] and created >= parse_time(
        approval["expires_at"], "source approval expires_at"
    ):
        raise SystemExit("Grant was created after its source approval expired.")
    if approval["expires_at"] and (
        not grant["expires_at"]
        or parse_time(grant["expires_at"], "grant.expires_at")
        > parse_time(approval["expires_at"], "source approval expires_at")
    ):
        raise SystemExit("Grant outlives its source approval.")
    validate_delegation_lineage(root, approval, effective_at=grant["created_at"])


def validate_for_transition(
    root: Path, approval: dict[str, Any], grant: dict[str, Any], at: str
) -> None:
    now = parse_time(at, "transition time")
    validate_delegation_lineage(root, approval, effective_at=at)
    if "authority.grant.transition" not in approval["capabilities"]:
        raise SystemExit("Source approval lacks authority.grant.transition.")
    if grant["grant_id"] not in approval["grant_ids"]:
        raise SystemExit("Transition approval does not bind the exact grant ID.")
    if grant["lineage_id"] not in approval["lineage_ids"]:
        raise SystemExit("Transition approval does not bind the exact grant lineage.")
    source_rank = rank_value(approval["source_rank"])
    if source_rank <= rank_value(grant["holder_rank"]):
        raise SystemExit("Transition source rank must be above the target holder rank.")
    if source_rank < rank_value(grant["issuer_rank"]):
        binding = approval["delegation_binding"]
        if binding is None:
            raise SystemExit(
                "Lower-than-issuer transition requires delegation lineage evidence."
            )
        parent_path = resolve_workspace_path(
            root, binding["ref"], "transition delegation_binding"
        )
        if sha256_file(parent_path) != binding["sha256"]:
            raise SystemExit("Transition delegation binding digest mismatch.")
        parent = load_source_approval(parent_path)
        if rank_value(parent["source_rank"]) <= source_rank:
            raise SystemExit("Transition delegation source rank is not higher.")
        if (
            "authority.grant.transition" not in parent["capabilities"]
            or grant["grant_id"] not in parent["grant_ids"]
            or grant["lineage_id"] not in parent["lineage_ids"]
        ):
            raise SystemExit("Transition delegation lineage does not cover the target.")
        if now < parse_time(parent["not_before"], "delegation source not_before"):
            raise SystemExit("Transition delegation source is not yet effective.")
        if parent["expires_at"] and now >= parse_time(
            parent["expires_at"], "delegation source expires_at"
        ):
            raise SystemExit("Transition delegation source has expired.")
    if now < parse_time(approval["not_before"], "source approval not_before"):
        raise SystemExit("Transition approval is not yet effective.")
    if approval["expires_at"] and now >= parse_time(
        approval["expires_at"], "source approval expires_at"
    ):
        raise SystemExit("Transition approval has expired.")
