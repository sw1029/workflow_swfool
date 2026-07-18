from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT
from .canonical import object_sha256, parse_time
from .contracts import IDENTIFIER_RE, risk_value
from .operations import load_operation
from .projection_io import safe_json, safe_owned_directory
from .source_approval import validate_delegation_lineage, validate_source_approval
from .workflow_candidates import GrantRecords, grant_covers_request


def _materialization_candidates(
    root: Path,
    approval: dict[str, Any],
    approval_binding: dict[str, str],
    request: dict[str, Any],
    context: dict[str, Any],
    evaluated_at: Any,
    rank_floor: str,
    grant_records: GrantRecords,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    materializable: list[str] = []
    usable: list[str] = []
    unavailable: list[dict[str, Any]] = []
    for grant_id in approval["grant_ids"]:
        if not IDENTIFIER_RE.fullmatch(grant_id):
            unavailable.append(
                {"grant_id": grant_id, "blocker_codes": ["invalid_grant_id"]}
            )
            continue
        if grant_id not in grant_records:
            grant_path = root / AUTHORIZATION_ROOT / "grants" / f"{grant_id}.json"
            state_path = (
                root
                / AUTHORIZATION_ROOT
                / "state"
                / "grants"
                / f"{grant_id}.json"
            )
            if (
                grant_path.exists()
                or grant_path.is_symlink()
                or state_path.exists()
                or state_path.is_symlink()
            ):
                unavailable.append(
                    {
                        "grant_id": grant_id,
                        "blocker_codes": ["conflicting_or_orphan_grant_projection"],
                    }
                )
            else:
                materializable.append(grant_id)
            continue
        grant, grant_digest, grant_state, state_binding = grant_records[grant_id]
        covers, blocker_codes = grant_covers_request(
            grant_records,
            grant_id,
            request,
            evaluated_at,
            rank_floor=rank_floor,
            session_id=context["session_ceiling"]["evidence_id"],
        )
        if grant["source_approval"] != approval_binding:
            blocker_codes = [*blocker_codes, "source_approval_binding_conflict"]
        if not blocker_codes and covers:
            usable.append(grant_id)
        else:
            unavailable.append(
                {
                    "grant_id": grant_id,
                    "grant_sha256": grant_digest,
                    "state_binding": state_binding,
                    "state_status": grant_state["status"],
                    "blocker_codes": blocker_codes,
                }
            )
    return materializable, usable, unavailable


def source_approvals_covering(
    root: Path,
    request: dict[str, Any],
    request_sha256: str,
    context: dict[str, Any],
    at: str,
    skills_root: Path | None,
    grant_records: GrantRecords,
) -> list[dict[str, Any]]:
    directory = safe_owned_directory(
        root.resolve(),
        AUTHORIZATION_ROOT / "source_snapshots",
        "Authority source snapshot directory",
    )
    if directory is None:
        return []
    now = parse_time(at, "resolve.at")
    operation = {
        key: request[key]
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    }
    operation_contract, _ = load_operation(
        request["skill_id"],
        request["skill_version"],
        request["operation_id"],
        request["operation_version"],
        skills_root=skills_root,
    )
    if operation_contract is None:
        raise SystemExit("Source approval candidate operation identity is unavailable.")
    matches: list[dict[str, Any]] = []
    source_name = re.compile(r"^source_approval-([0-9a-f]{64})\.json$")
    for path in sorted(directory.iterdir()):
        match = source_name.fullmatch(path.name)
        if match is None:
            continue
        if path.is_symlink() or not path.is_file():
            raise SystemExit("Source snapshot candidate must be a regular JSON file.")
        raw_approval, digest = safe_json(root, path, "authority source snapshot")
        if digest != match.group(1):
            raise SystemExit("Source snapshot filename digest does not match its bytes.")
        approval = validate_source_approval(raw_approval)
        if now < parse_time(approval["not_before"], "source not_before"):
            continue
        if approval["expires_at"] and now >= parse_time(
            approval["expires_at"], "source expires_at"
        ):
            continue
        if approval["source_rank"] in {"S1", "S2"}:
            try:
                validate_delegation_lineage(root, approval, effective_at=at)
            except SystemExit:
                continue
        if (
            "authority.grant.issue" not in approval["capabilities"]
            or not set(request["required_capabilities"]).issubset(
                approval["capabilities"]
            )
            or request["subject"] not in approval["subjects"]
            or operation not in approval["operations"]
            or risk_value(request["risk_tier"])
            > risk_value(approval["risk_ceiling"])
            or request["decision_class"] not in approval["decision_classes"]
            or request["cardinality_requested"] not in approval["cardinalities"]
            or (
                approval["max_uses"] is not None
                and approval["max_uses"] < request["use_budget_requested"]
            )
            or (
                approval["request_digests"]
                and request_sha256 not in approval["request_digests"]
            )
        ):
            continue
        approval_binding = {
            "ref": path.relative_to(root).as_posix(),
            "sha256": digest,
        }
        materializable, usable, unavailable = _materialization_candidates(
            root,
            approval,
            approval_binding,
            request,
            context,
            now,
            operation_contract["source_rank_floor"],
            grant_records,
        )
        ready = bool(materializable or usable)
        internal_defect_codes = {
            "conflicting_or_orphan_grant_projection",
            "invalid_grant_id",
        }
        has_internal_defect = any(
            internal_defect_codes.intersection(item["blocker_codes"])
            for item in unavailable
        )
        materialization_status = "ready"
        if not ready:
            materialization_status = (
                "defect" if has_internal_defect else "fresh_authority_required"
            )
        matches.append(
            {
                "approval_id": approval["approval_id"],
                "source_rank": approval["source_rank"],
                **approval_binding,
                "lineage_ids": approval["lineage_ids"],
                "materialization_status": materialization_status,
                "materializable_grant_ids": materializable,
                "usable_grant_ids": usable,
                "unavailable_grants": unavailable,
            }
        )
    return matches


def source_recovery_identity(
    request_sha256: str, approvals: list[dict[str, Any]]
) -> str:
    evidence = [
        {
            "ref": approval["ref"],
            "sha256": approval["sha256"],
            "materialization_status": approval["materialization_status"],
            "unavailable_grants": approval["unavailable_grants"],
        }
        for approval in approvals
    ]
    core = {
        "request_sha256": request_sha256,
        "reason_code": "source_authority_no_usable_or_materializable_grant",
        "source_state_evidence": evidence,
    }
    return f"authrec-{object_sha256(core)[:24]}"


__all__ = ["source_approvals_covering", "source_recovery_identity"]
