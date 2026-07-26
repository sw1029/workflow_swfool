"""Activation evidence and deterministic broker for authority interaction mode."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from . import authority_interaction as interaction
from .artifact_store import _register_compiled_grant, grant_path, verify_binding
from .canonical import authority_lock, object_sha256, parse_time, write_json_atomic
from .contracts import rank_value, validate_grant, validate_request
from .producer_capability import _AUTHORITY_PRODUCER_CAPABILITY
from .root_authority_registry import SIGNATURE_ALGORITHM, load_registry, sha256_bytes
from .root_authorization_evidence import _verify_rsa_signature
from .stable_store import publish_immutable, read_regular


def activation_evidence_unsigned(plan_binding: dict[str, str], plan: dict[str, Any], *, key_id: str, decided_at: str) -> dict[str, Any]:
    identity = sha256_bytes(interaction._json_bytes({"activation_plan": plan_binding, "workspace": plan["workspace"], "key_id": key_id, "decided_at": decided_at}))
    return {"schema_version": 1, "artifact_kind": "authority_interaction_activation_evidence", "audience": "manage-agent-authority/authority-interaction-activation", "issuer": "local-agent-managed-root-authorizer", "activation_id": f"authia-{identity[:24]}", "activation_plan": plan_binding, "approved": True, "decided_at": decided_at, "evidence_id": f"activation-evidence-{identity}"}


def validate_activation_evidence(value: Any, *, root: Path, plan_binding: dict[str, str], plan: dict[str, Any]) -> dict[str, Any]:
    expected = {"schema_version", "artifact_kind", "audience", "issuer", "activation_id", "activation_plan", "approved", "decided_at", "evidence_id", "signature"}
    if not isinstance(value, dict) or set(value) != expected or value.get("schema_version") != 1 or value.get("artifact_kind") != "authority_interaction_activation_evidence" or value.get("audience") != "manage-agent-authority/authority-interaction-activation" or value.get("issuer") != "local-agent-managed-root-authorizer" or value.get("approved") is not True or value.get("activation_plan") != plan_binding:
        raise SystemExit("authority_interaction_evidence_invalid")
    decided = parse_time(value.get("decided_at"), "activation decision time")
    if decided < parse_time(plan["prepared_at"], "activation prepared_at") or decided >= parse_time(plan["expires_at"], "activation expires_at"):
        raise SystemExit("authority_interaction_evidence_expired")
    signature = value.get("signature")
    if not isinstance(signature, dict) or set(signature) != {"algorithm", "key_id", "value_base64"} or signature.get("algorithm") != SIGNATURE_ALGORITHM:
        raise SystemExit("authority_interaction_evidence_invalid")
    loaded = load_registry(interaction.TRUST_ANCHOR_REGISTRY)
    if loaded is None:
        raise SystemExit("authority_interaction_trust_registry_unavailable")
    anchor = loaded[1].get(str(signature["key_id"]))
    if not anchor or anchor.get("status") != "active" or anchor.get("issuer") != "local-agent-managed-root-authorizer":
        raise SystemExit("authority_interaction_key_revoked_or_unknown")
    try:
        encoded = base64.b64decode(str(signature["value_base64"]), validate=True)
    except Exception as exc:
        raise SystemExit("authority_interaction_evidence_invalid") from exc
    unsigned = {key: value[key] for key in expected if key != "signature"}
    if not _verify_rsa_signature(interaction._json_bytes(unsigned), encoded, modulus_hex=anchor["modulus_hex"], exponent=anchor["public_exponent"]):
        raise SystemExit("authority_interaction_evidence_signature_invalid")
    return value


def publish_activation_evidence(root: Path, evidence: dict[str, Any]) -> dict[str, str]:
    root = root.resolve()
    plan_binding = evidence.get("activation_plan") if isinstance(evidence, dict) else None
    if not isinstance(plan_binding, dict):
        raise SystemExit("authority_interaction_evidence_invalid")
    binding, plan = interaction.load_activation_plan(root, plan_binding)
    payload = interaction._json_bytes(interaction.validate_activation_evidence(evidence, root=root, plan_binding=binding, plan=plan))
    path = root / interaction.EVIDENCE_ROOT / f"{hashlib.sha256(payload).hexdigest()}.json"
    publish_immutable(path, payload)
    return interaction._binding(root, path, payload)


def _state_path(root: Path, activation_id: str) -> Path:
    return root / interaction.STATE_ROOT / f"{activation_id}.json"


def _receipt_path(root: Path, activation_id: str) -> Path:
    return root / interaction.MATERIALIZATION_ROOT / activation_id / "receipt.json"


def materialize_activation(root: Path, evidence_binding: dict[str, str]) -> dict[str, Any]:
    root = root.resolve()
    evidence_path = verify_binding(root, evidence_binding, "authority interaction evidence")
    if evidence_path.parent != root / interaction.EVIDENCE_ROOT:
        raise SystemExit("authority_interaction_evidence_binding_invalid")
    try:
        evidence = json.loads((read_regular(evidence_path, label="authority interaction evidence") or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("authority_interaction_evidence_invalid") from exc
    plan_binding, plan = interaction.load_activation_plan(root, evidence["activation_plan"])
    interaction.validate_activation_evidence(evidence, root=root, plan_binding=plan_binding, plan=plan)
    receipt = {"schema_version": 1, "artifact_kind": "authority_interaction_activation_materialization", "activation_id": evidence["activation_id"], "activation_plan": plan_binding, "activation_evidence": evidence_binding, "materialized_at": interaction._utc_now()}
    receipt_path = _receipt_path(root, evidence["activation_id"])
    payload = interaction._json_bytes(receipt)
    with authority_lock(root):
        publish_immutable(receipt_path, payload)
        state_path = _state_path(root, evidence["activation_id"])
        if not state_path.exists():
            write_json_atomic(state_path, {"schema_version": 1, "artifact_kind": "authority_interaction_activation_state", "activation_id": evidence["activation_id"], "child_grants": 0, "total_uses": 0, "uses_by_cardinality": {}, "child_grant_ids": [], "status": "active", "version": 0})
    return {"status": "materialized", "activation_id": evidence["activation_id"], "activation_plan": plan_binding, "activation_evidence": evidence_binding, "receipt": interaction._binding(root, receipt_path, payload)}


def _records(root: Path) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str], dict[str, str]]]:
    records = []
    if not (root / interaction.STATE_ROOT).is_dir():
        return records
    for state_path in sorted((root / interaction.STATE_ROOT).glob("authia-*.json")):
        try:
            state = json.loads((read_regular(state_path, label="authority interaction state") or b"").decode("utf-8"))
            receipt = json.loads((read_regular(_receipt_path(root, state["activation_id"]), label="authority interaction receipt") or b"").decode("utf-8"))
            plan_binding, plan = interaction.load_activation_plan(root, receipt["activation_plan"])
            evidence_path = verify_binding(root, receipt["activation_evidence"], "authority interaction evidence")
            evidence = json.loads((read_regular(evidence_path, label="authority interaction evidence") or b"").decode("utf-8"))
            interaction.validate_activation_evidence(evidence, root=root, plan_binding=plan_binding, plan=plan)
            records.append((state, receipt, plan, receipt["activation_plan"], receipt["activation_evidence"]))
        except (SystemExit, KeyError, TypeError, json.JSONDecodeError):
            continue
    return records


def _current(root: Path, plan: dict[str, Any], *, at: str) -> tuple[bool, str]:
    config, digest, _exists = interaction.load_config()
    if not config["enabled"]:
        return False, "authority_interaction_disabled"
    if digest != plan["config_sha256"]:
        return False, "authority_interaction_config_drift"
    if interaction.workspace_identity(root) != plan["workspace"]:
        return False, "authority_interaction_workspace_drift"
    if interaction.goal_policy_snapshot(root) != plan["goal_policy_snapshot"]:
        return False, "authority_interaction_goal_or_policy_drift"
    if interaction.manifest_bindings() != plan["manifest_bindings"]:
        return False, "authority_interaction_manifest_drift"
    if parse_time(at, "activation evaluation time") >= parse_time(plan["expires_at"], "activation expiry"):
        return False, "authority_interaction_expired"
    mode = interaction.current_mode(config)
    if mode in {"manual", "observe"} or not interaction._mode_at_most(mode, plan["authority_interaction_mode"]) or not interaction._mode_at_most(mode, interaction._runtime_ceiling()):
        return False, "authority_interaction_mode_narrowed"
    return True, "eligible"


def _operation_allowed(request: dict[str, Any], operation: dict[str, Any], profile: dict[str, Any]) -> bool:
    key = (request["skill_id"], request["operation_id"], request["operation_version"])
    allowed = set().union(*(interaction.OPERATION_REGISTRY[group] for group in profile["operation_groups"]))
    return key in allowed and request["operation_id"] not in interaction.ALWAYS_DENY_OPERATION_IDS and request["mutation_class"] == "local_mutation" and request["mutation_class"] in profile["mutation_classes"] and request["risk_tier"] != "R3" and interaction.RISK_ORDER[request["risk_tier"]] <= interaction.RISK_ORDER[profile["max_risk"]] and request["decision_class"] not in {"D0", "D1"} and request["decision_class"] in profile["decision_classes"] and request["cardinality_requested"] in profile["cardinalities"] and rank_value(operation["source_rank_floor"]) <= rank_value(profile["max_operation_source_floor"])


def _policy_binding(root: Path) -> dict[str, str]:
    try:
        pointer = json.loads((read_regular(root / ".task/authorization/state/current_policy.json", label="current policy pointer") or b"").decode("utf-8"))
        binding = pointer["policy_snapshot"]
        verify_binding(root, binding, "current policy snapshot")
        return binding
    except (SystemExit, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit("authority_interaction_current_policy_unavailable") from exc


def _budget_key(cardinality: str) -> str | None:
    return {
        "bounded_reusable": "max_bounded_reusable_uses",
        "task_lease": "max_task_lease_uses",
        "improvement_lease": "max_improvement_lease_uses",
    }.get(cardinality)


def _state_allows_child(state: dict[str, Any], plan: dict[str, Any], grant: dict[str, Any]) -> bool:
    if state.get("status") != "active":
        return False
    if grant["grant_id"] in state.get("child_grant_ids", []):
        return True
    if state.get("child_grants", 0) >= plan["limits"]["max_child_grants"] or state.get("total_uses", 0) + grant["max_uses"] > plan["limits"]["max_total_uses"]:
        return False
    key = _budget_key(grant["cardinality"])
    used = state.get("uses_by_cardinality", {})
    return key is None or used.get(grant["cardinality"], 0) + grant["max_uses"] <= plan["limits"][key]


def _updated_state(state: dict[str, Any], grant: dict[str, Any]) -> dict[str, Any]:
    if grant["grant_id"] in state.get("child_grant_ids", []):
        return state
    uses = dict(state.get("uses_by_cardinality", {}))
    uses[grant["cardinality"]] = uses.get(grant["cardinality"], 0) + grant["max_uses"]
    return {**state, "child_grants": state.get("child_grants", 0) + 1, "total_uses": state.get("total_uses", 0) + grant["max_uses"], "uses_by_cardinality": uses, "child_grant_ids": sorted([*state.get("child_grant_ids", []), grant["grant_id"]]), "version": state.get("version", 0) + 1}


def _child_source(root: Path, *, activation_id: str, plan_binding: dict[str, str], evidence_binding: dict[str, str], receipt_binding: dict[str, str], request: dict[str, Any], now: str) -> tuple[dict[str, Any], dict[str, Any]]:
    request_sha = object_sha256(request)
    identity = object_sha256({"activation_id": activation_id, "request_sha256": request_sha})
    grant_id = f"authg-mode-{identity[:19]}"
    child_receipt_ref = (interaction.MATERIALIZATION_ROOT / activation_id / "children" / grant_id / "receipt.json").as_posix()
    operations = [{key: request[key] for key in ("skill_id", "skill_version", "operation_id", "operation_version")}]
    projection = {"grant_id": grant_id, "lineage_id": f"authl-mode-{identity[:18]}", "grant_idempotency_key": f"authgk-mode-{identity[:17]}", "request_sha256": request_sha, "holder_rank": request["actor_rank"], "capabilities": request["required_capabilities"], "subjects": [request["subject"]], "operations": operations, "risk_ceiling": request["risk_tier"], "decision_classes": [request["decision_class"]], "cardinality": request["cardinality_requested"], "max_uses": request["use_budget_requested"], "session_id": None, "task_id": request["task_id"], "improvement_id": request["pack_id"], "policy_snapshot": _policy_binding(root), "activation_materialization_ref": child_receipt_ref}
    source = {"schema_version": 6, "artifact_kind": "authority_source_approval", "approval_id": f"authsrc-mode-{identity[:16]}", "source_kind": "delegated_policy_steward", "source_rank": "S2", "decision_type": "grant_authority", "capabilities": sorted(set(request["required_capabilities"]) | {"authority.grant.issue"}), "subjects": [request["subject"]], "operations": operations, "risk_ceiling": request["risk_tier"], "decision_classes": [request["decision_class"]], "cardinalities": [request["cardinality_requested"]], "max_uses": request["use_budget_requested"], "grant_ids": [grant_id], "request_digests": [request_sha], "lineage_ids": [projection["lineage_id"]], "delegation_binding": plan_binding, "not_before": now, "expires_at": None, "evidence_id": activation_id, "decision_binding": evidence_binding, "decision_trust_class": "host_user_signed_mode_activation_child", "activation_plan": plan_binding, "activation_evidence": evidence_binding, "activation_materialization": receipt_binding, "activation_child": projection}
    source_payload = interaction._json_bytes(source)
    grant = {"schema_version": 4, "artifact_kind": "authority_grant", "grant_id": grant_id, "lineage_id": projection["lineage_id"], "parent_grant_id": None, "issuer_rank": "S2", "holder_rank": request["actor_rank"], "capabilities": request["required_capabilities"], "subjects": [request["subject"]], "operations": operations, "risk_ceiling": request["risk_tier"], "decision_classes": [request["decision_class"]], "cardinality": request["cardinality_requested"], "max_uses": request["use_budget_requested"], "not_before": now, "expires_at": None, "session_id": None, "task_id": request["task_id"], "improvement_id": request["pack_id"], "source_approval": {"ref": (Path(".task/authorization/source_snapshots") / f"source_approval-{hashlib.sha256(source_payload).hexdigest()}.json").as_posix(), "sha256": hashlib.sha256(source_payload).hexdigest()}, "policy_snapshot": projection["policy_snapshot"], "created_at": now, "idempotency_key": projection["grant_idempotency_key"], "request_sha256": request_sha, "activation_materialization_ref": child_receipt_ref}
    return source, grant


def materialize_mode_child(root: Path, request: dict[str, Any], *, evaluated_at: str, skills_root: Path | None = None) -> dict[str, Any] | None:
    """Atomically mint an exact child grant when a current activation allows it."""
    from .operations import load_operation

    root = root.resolve()
    request = validate_request(request)
    operation, _manifest = load_operation(request["skill_id"], request["skill_version"], request["operation_id"], request["operation_version"], skills_root=skills_root)
    if operation is None:
        return None
    for state, _receipt, plan, plan_binding, evidence_binding in _records(root):
        current, _reason = _current(root, plan, at=evaluated_at)
        if state.get("status") != "active" or not current or not _operation_allowed(request, operation, plan["profile"]):
            continue
        now = parse_time(evaluated_at, "mode child materialized_at").isoformat()
        receipt_path = _receipt_path(root, state["activation_id"])
        source, raw_grant = _child_source(root, activation_id=state["activation_id"], plan_binding=plan_binding, evidence_binding=evidence_binding, receipt_binding=interaction._binding(root, receipt_path), request=request, now=now)
        child_receipt = {"schema_version": 1, "artifact_kind": "authority_interaction_child_materialization", "activation_id": state["activation_id"], "activation_plan": plan_binding, "request_sha256": raw_grant["request_sha256"], "source_approval": raw_grant["source_approval"], "grant_id": raw_grant["grant_id"]}
        with authority_lock(root):
            current_state = json.loads((read_regular(_state_path(root, state["activation_id"]), label="authority interaction state") or b"").decode("utf-8"))
            if not _state_allows_child(current_state, plan, raw_grant):
                continue
            publish_immutable(root / raw_grant["source_approval"]["ref"], interaction._json_bytes(source))
            publish_immutable(root / raw_grant["activation_materialization_ref"], interaction._json_bytes(child_receipt))
            registered = _register_compiled_grant(root, validate_grant(raw_grant), producer_capability=_AUTHORITY_PRODUCER_CAPABILITY)
            updated = _updated_state(current_state, raw_grant)
            if updated != current_state:
                write_json_atomic(_state_path(root, state["activation_id"]), updated)
        return {"status": "materialized", "activation_id": state["activation_id"], "grant_id": registered["grant"]["grant_id"], "grant_binding": {"ref": grant_path(root, registered["grant"]["grant_id"]).relative_to(root).as_posix(), "sha256": registered["grant_sha256"]}}
    return None


def validate_mode_child_source(root: Path, source: dict[str, Any], grant: dict[str, Any]) -> None:
    if source.get("schema_version") != 6 or grant.get("schema_version") != 4 or not isinstance(source.get("activation_child"), dict):
        raise SystemExit("authority_interaction_child_schema_invalid")
    projected = {"grant_id": "grant_id", "lineage_id": "lineage_id", "grant_idempotency_key": "idempotency_key", "request_sha256": "request_sha256", "holder_rank": "holder_rank", "capabilities": "capabilities", "subjects": "subjects", "operations": "operations", "risk_ceiling": "risk_ceiling", "decision_classes": "decision_classes", "cardinality": "cardinality", "max_uses": "max_uses", "session_id": "session_id", "task_id": "task_id", "improvement_id": "improvement_id", "policy_snapshot": "policy_snapshot", "activation_materialization_ref": "activation_materialization_ref"}
    child = source["activation_child"]
    if any(child.get(key) != grant.get(grant_key) for key, grant_key in projected.items()) or grant.get("parent_grant_id") is not None or grant.get("issuer_rank") != "S2" or grant.get("not_before") != source.get("not_before") or grant.get("created_at") != source.get("not_before"):
        raise SystemExit("authority_interaction_child_projection_mismatch")
    plan_binding, plan = interaction.load_activation_plan(root, source["activation_plan"])
    if plan_binding != source["delegation_binding"]:
        raise SystemExit("authority_interaction_child_plan_binding_invalid")
    evidence = json.loads((read_regular(verify_binding(root, source["activation_evidence"], "authority interaction activation evidence"), label="authority interaction activation evidence") or b"").decode("utf-8"))
    interaction.validate_activation_evidence(evidence, root=root, plan_binding=plan_binding, plan=plan)
    receipt = json.loads((read_regular(verify_binding(root, source["activation_materialization"], "authority interaction activation materialization"), label="authority interaction activation materialization") or b"").decode("utf-8"))
    try:
        child_receipt = json.loads((read_regular(root / grant["activation_materialization_ref"], label="authority interaction child receipt") or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("authority_interaction_child_receipt_invalid") from exc
    if receipt.get("activation_id") != evidence.get("activation_id") or receipt.get("activation_plan") != plan_binding or receipt.get("activation_evidence") != source["activation_evidence"] or child_receipt != {"schema_version": 1, "artifact_kind": "authority_interaction_child_materialization", "activation_id": evidence["activation_id"], "activation_plan": plan_binding, "request_sha256": grant["request_sha256"], "source_approval": grant["source_approval"], "grant_id": grant["grant_id"]}:
        raise SystemExit("authority_interaction_materialization_binding_invalid")
    valid, reason = _current(root, plan, at=grant["created_at"])
    if not valid:
        raise SystemExit(reason)


def activation_child_eligible(root: Path, grant: dict[str, Any], *, at: Any, skills_root: Path | None = None) -> bool:
    if grant.get("schema_version") != 4:
        return True
    try:
        source = json.loads((read_regular(verify_binding(root, grant["source_approval"], "mode child source approval"), label="mode child source approval") or b"").decode("utf-8"))
        if source.get("schema_version") != 6 or source.get("activation_child", {}).get("grant_id") != grant.get("grant_id"):
            return False
        plan_binding, plan = interaction.load_activation_plan(root, source["activation_plan"])
        evidence = json.loads((read_regular(verify_binding(root, source["activation_evidence"], "mode activation evidence"), label="mode activation evidence") or b"").decode("utf-8"))
        interaction.validate_activation_evidence(evidence, root=root, plan_binding=plan_binding, plan=plan)
        valid, _reason = _current(root, plan, at=parse_time(at, "mode child eligibility").isoformat())
        state = json.loads((read_regular(_state_path(root, evidence["activation_id"]), label="authority interaction state") or b"").decode("utf-8"))
        return valid and state.get("status") == "active" and grant["grant_id"] in state.get("child_grant_ids", [])
    except (SystemExit, KeyError, TypeError, json.JSONDecodeError):
        return False


def status(root: Path, *, at: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    config, digest, exists = interaction.load_config()
    rows = []
    for state, _receipt, plan, plan_binding, evidence_binding in _records(root):
        valid, reason = _current(root, plan, at=at or interaction._utc_now())
        rows.append({"activation_id": state.get("activation_id"), "status": state.get("status"), "eligible": valid, "reason_code": reason, "activation_plan": plan_binding, "activation_evidence": evidence_binding, "expires_at": plan.get("expires_at"), "child_grants": state.get("child_grants"), "total_uses": state.get("total_uses")})
    return {"schema_version": 1, "status": "ok", "config_present": exists, "config_sha256": digest, "enabled": config["enabled"], "authority_interaction_mode": interaction.current_mode(config), "runtime_ceiling": interaction._runtime_ceiling(), "last_attempt": interaction.last_attempt(), "activations": rows}
