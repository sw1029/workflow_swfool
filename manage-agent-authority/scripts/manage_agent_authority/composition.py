from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT
from .artifact_store import load_grant
from .artifact_store import verify_binding
from .canonical import parse_time
from .canonical import read_object
from .canonical import resolve_workspace_path
from .canonical import sha256_file
from .canonical import write_immutable_json
from .contracts import risk_value
from .contracts import reservation_units
from .root_grant_request_binding import root_grant_request_binding_covers
from .contracts import cardinality_covers
from .contracts import rank_value
from .source_approval import load_source_approval
from .producer_capability import _require_authority_producer_capability


COMPOSITION_KEYS = {
    "schema_version",
    "artifact_kind",
    "composition_id",
    "request_sha256",
    "grant_ids",
    "source_approval",
    "created_at",
    "idempotency_key",
}


def validate_composition(value: dict[str, Any]) -> dict[str, Any]:
    extra = sorted(set(value) - COMPOSITION_KEYS)
    missing = sorted(COMPOSITION_KEYS - set(value))
    if extra or missing:
        raise SystemExit(f"Composition receipt has unknown={extra} missing={missing}.")
    if (
        value["schema_version"] != 2
        or value["artifact_kind"] != "authority_grant_composition"
    ):
        raise SystemExit(
            "Composition requires schema_version=2 and artifact_kind=authority_grant_composition."
        )
    grant_ids = value["grant_ids"]
    if not isinstance(grant_ids, list) or len(grant_ids) < 2:
        raise SystemExit("Composition requires at least two grant IDs.")
    normalized_ids = sorted(set(str(item) for item in grant_ids))
    if normalized_ids != grant_ids:
        raise SystemExit("Composition grant IDs must be sorted and unique.")
    source = value["source_approval"]
    if not isinstance(source, dict) or set(source) != {"ref", "sha256"}:
        raise SystemExit("Composition source_approval must contain ref and sha256.")
    return {
        "schema_version": 2,
        "artifact_kind": "authority_grant_composition",
        "composition_id": str(value["composition_id"]),
        "request_sha256": str(value["request_sha256"]),
        "grant_ids": normalized_ids,
        "source_approval": {"ref": str(source["ref"]), "sha256": str(source["sha256"])},
        "created_at": parse_time(
            value["created_at"], "composition.created_at"
        ).isoformat(),
        "idempotency_key": str(value["idempotency_key"]),
    }


def create_composition(root: Path, raw: dict[str, Any]) -> dict[str, Any]:
    """Read one exact existing composition; never publish prospective bytes."""

    root = root.resolve()
    composition = validate_composition(raw)
    path = (
        root
        / AUTHORIZATION_ROOT
        / "compositions"
        / f"{composition['composition_id']}.json"
    )
    if not path.is_file():
        raise SystemExit(
            "Raw create_composition is sealed to exact historical replay; "
            "prospective writes require the composition intent compiler."
        )
    existing = validate_composition(read_object(path, "authority composition"))
    if existing != composition:
        raise SystemExit("Historical composition replay differs from registered bytes.")
    return {
        "composition": existing,
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }


def _create_compiled_composition(
    root: Path,
    raw: dict[str, Any],
    *,
    producer_capability: object,
) -> dict[str, Any]:
    _require_authority_producer_capability(producer_capability)
    root = root.resolve()
    composition = validate_composition(raw)
    source_path = verify_binding(
        root, composition["source_approval"], "composition source_approval"
    )
    approval = load_source_approval(source_path)
    if "authority.grant.compose" not in approval["capabilities"]:
        raise SystemExit("Composition source lacks authority.grant.compose.")
    if rank_value(approval["source_rank"]) < rank_value("S3"):
        raise SystemExit("Composition requires at least S3 source approval.")
    if composition["request_sha256"] not in approval["request_digests"]:
        raise SystemExit(
            "Composition source does not bind the exact base request digest."
        )
    if not set(composition["grant_ids"]).issubset(approval["grant_ids"]):
        raise SystemExit("Composition source does not bind every exact grant ID.")
    created = parse_time(composition["created_at"], "composition.created_at")
    if created < parse_time(approval["not_before"], "source approval not_before"):
        raise SystemExit("Composition predates its source approval.")
    if approval["expires_at"] and created >= parse_time(
        approval["expires_at"], "source approval expires_at"
    ):
        raise SystemExit("Composition source approval expired before creation.")
    for grant_id in composition["grant_ids"]:
        grant, _, state = load_grant(root, grant_id)
        if state.get("status") != "active":
            raise SystemExit("Composition may bind only active grants.")
        if rank_value(approval["source_rank"]) < rank_value(grant["issuer_rank"]):
            raise SystemExit(
                "Composition source rank is lower than a composed grant issuer."
            )
    path = (
        root
        / AUTHORIZATION_ROOT
        / "compositions"
        / f"{composition['composition_id']}.json"
    )
    digest = write_immutable_json(path, composition, "authority composition")
    return {
        "composition": composition,
        "ref": path.relative_to(root).as_posix(),
        "sha256": digest,
    }


def load_bound_composition(
    root: Path, binding: dict[str, str], request_sha256: str
) -> dict[str, Any]:
    path = resolve_workspace_path(root, binding["ref"], "composition receipt")
    if sha256_file(path) != binding["sha256"]:
        raise SystemExit("Composition receipt digest mismatch.")
    composition = validate_composition(read_object(path, "composition receipt"))
    if composition["request_sha256"] != request_sha256:
        raise SystemExit(
            "Composition receipt does not bind the exact base request with composition_receipt=null."
        )
    verify_binding(root, composition["source_approval"], "composition source_approval")
    return composition


def composition_covers(
    request: dict[str, Any],
    grant_records: list[tuple[dict[str, Any], str, dict[str, Any]]],
    *,
    at: Any,
    rank_floor_index: int,
    session_id: str,
) -> bool:
    capabilities: set[str] = set()
    operation = {
        key: request[key]
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    }
    for grant, _, state in grant_records:
        if (
            state.get("status") != "active"
            or grant["holder_rank"] != request["actor_rank"]
            or not root_grant_request_binding_covers(grant, request)
        ):
            return False
        if parse_time(grant["not_before"], "grant.not_before") > at:
            return False
        if (
            grant.get("expires_at")
            and parse_time(grant["expires_at"], "grant.expires_at") <= at
        ):
            return False
        issuer_index = int(grant["issuer_rank"][1:])
        if (
            issuer_index < rank_floor_index
            or request["subject"] not in grant["subjects"]
        ):
            return False
        if operation not in grant["operations"] or risk_value(
            request["risk_tier"]
        ) > risk_value(grant["risk_ceiling"]):
            return False
        if not cardinality_covers(
            grant["cardinality"], request["cardinality_requested"]
        ):
            return False
        if grant["session_id"] and grant["session_id"] != session_id:
            return False
        if grant["task_id"] and grant["task_id"] != request["task_id"]:
            return False
        if grant["improvement_id"] and grant["improvement_id"] != request["pack_id"]:
            return False
        if request["decision_class"] not in grant["decision_classes"]:
            return False
        available = state.get("remaining_uses")
        if available is not None and available - state.get(
            "reserved_uses", 0
        ) < reservation_units(request):
            return False
        capabilities.update(grant["capabilities"])
    return set(request["required_capabilities"]).issubset(capabilities)
