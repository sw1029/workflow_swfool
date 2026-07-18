from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, TypeVar

from .common import (
    SCHEMA_VERSION,
    WorkflowError,
    expect_keys,
    read_json,
    require,
    sha256_file,
    workspace_file,
    workspace_regular_file,
)
from .owner_plans import verify_owner_plan
from .owner_results import verify_owner_result
from .authority_snapshots import verify_policy_snapshot


SKILLS_ROOT = Path(__file__).resolve().parents[3]
AUTHORITY_SCRIPTS = SKILLS_ROOT / "manage-agent-authority" / "scripts"
if str(AUTHORITY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AUTHORITY_SCRIPTS))

from manage_agent_authority.canonical import object_sha256  # noqa: E402
from manage_agent_authority.contracts import risk_value, validate_request  # noqa: E402
from manage_agent_authority.evaluation_context import (  # noqa: E402
    validate_evaluation_context,
)
from manage_agent_authority.operations import load_operation  # noqa: E402
from manage_agent_authority.projection_io import (  # noqa: E402
    load_bound_json,
    load_grant_artifact,
    validate_reservation_state,
)
from manage_agent_authority.projection_receipts import (  # noqa: E402
    validate_release_receipt,
    validate_use_receipt,
)
from manage_agent_authority.projection_reconciliation import (  # noqa: E402
    validate_reconciliation_evidence,
    validate_reconciliation_receipt,
)
from manage_agent_authority.projection_reservations import (  # noqa: E402
    load_bound_reservation,
)

from .authority_grant import verify_materialized_grant  # noqa: E402
from .authority_materialization import normalize_materialization  # noqa: E402


T = TypeVar("T")
OPERATION_KEYS = {"skill_id", "skill_version", "operation_id", "operation_version"}


def _authority_call(code: str, label: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        message = str(error) or error.__class__.__name__
        raise WorkflowError(code, f"{label} is invalid: {message}") from error


def _manifest_for(operation: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    loaded, binding = _authority_call(
        "invalid_authority_contract",
        "owner operation manifest",
        lambda: load_operation(
            operation["skill_id"], operation["skill_version"],
            operation["operation_id"], operation["operation_version"],
            skills_root=SKILLS_ROOT,
        ),
    )
    require(loaded is not None and binding is not None, "invalid_authority_contract",
            "owner operation is absent from its authority manifest")
    assert loaded is not None and binding is not None
    return loaded, binding


def _manifest_reasons(request: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    mutation_order = {"observe": 0, "local_mutation": 1,
                      "external_mutation": 2, "destructive": 3}
    reversibility_order = {"reversible": 0, "conditionally_reversible": 1,
                           "irreversible": 2}
    reasons = []
    if not set(manifest["required_capabilities"]).issubset(
        request["required_capabilities"]
    ):
        reasons.append("request_understates_manifest_capabilities")
    if risk_value(request["risk_tier"]) < risk_value(manifest["risk_floor"]):
        reasons.append("request_understates_manifest_risk")
    if mutation_order[request["mutation_class"]] < mutation_order[manifest["mutation_class"]]:
        reasons.append("request_understates_manifest_mutation")
    if reversibility_order[request["reversibility"]] < reversibility_order[manifest["reversibility"]]:
        reasons.append("request_overstates_reversibility")
    comparisons = (
        (request["decision_class"], {manifest["decision_class"]}, "decision_class"),
        (request["effect_class"], set(manifest["effect_classes"]), "effect_class"),
        (request["data_class"], set(manifest["data_classes"]), "data_class"),
        (request["subject"]["kind"], set(manifest["subject_kinds"]), "subject_kind"),
    )
    reasons.extend(f"{label}_mismatch" for value, allowed, label in comparisons
                   if value not in allowed)
    return reasons


def normalize_authority(
    owner_skill: str, effect_class: str, plan_binding: dict[str, str], raw: Any,
) -> dict[str, Any]:
    require(isinstance(raw, dict), "invalid_plan", "authority must be an object")
    applicability = raw.get("applicability")
    if applicability == "none":
        expect_keys(raw, {"applicability", "operation"}, set(), "authority")
        operation = raw["operation"]
        require(isinstance(operation, dict), "invalid_plan",
                "authority.operation must be an object")
        expect_keys(operation, OPERATION_KEYS, set(), "authority.operation")
        normalized_operation = {key: str(operation[key]) for key in OPERATION_KEYS}
        require(normalized_operation["skill_id"] == owner_skill,
                "invalid_authority_contract", "authority-free owner skill mismatch")
        manifest, binding = _manifest_for(normalized_operation)
        require(manifest["authority_applicability"] == "none"
                and manifest["authorization_mechanism"] == "none",
                "invalid_authority_contract",
                "authority-free classification is not declared by the owner manifest")
        require(effect_class in manifest["effect_classes"], "invalid_authority_contract",
                "authority-free effect class is absent from the owner manifest")
        return {"applicability": "none", "operation": normalized_operation,
                "operation_manifest": binding}
    require(applicability == "required", "invalid_plan",
            "authority.applicability must be required or none")
    expect_keys(raw, {"applicability", "request", "materialization"}, set(), "authority")
    request = _authority_call(
        "invalid_authority_contract", "authority request",
        lambda: validate_request(raw["request"]),
    )
    require(request["skill_id"] == owner_skill, "invalid_authority_contract",
            "authority request owner skill mismatch")
    require(request["effect_class"] == effect_class, "invalid_authority_contract",
            "authority request effect class mismatch")
    use_budget = request["use_budget_requested"]
    reservation_units = request.get("reservation_units")
    require(request["cardinality_requested"] == "single_use"
            and isinstance(use_budget, int) and not isinstance(use_budget, bool)
            and use_budget == 1
            and isinstance(reservation_units, int)
            and not isinstance(reservation_units, bool)
            and reservation_units == 1,
            "invalid_authority_contract",
            "task-doctor governed effects require one exact single-use reservation unit")
    require(request["subject"]["ref"] == plan_binding["ref"]
            and request["subject"]["digest"] == plan_binding["sha256"],
            "invalid_authority_contract",
            "authority request subject must bind the canonical owner plan")
    operation = {key: request[key] for key in OPERATION_KEYS}
    manifest, manifest_binding = _manifest_for(operation)
    require(manifest["authority_applicability"] == "required"
            and manifest["authorization_mechanism"] == "grant",
            "invalid_authority_contract", "owner operation does not use grant authority")
    reasons = _manifest_reasons(request, manifest)
    require(not reasons, "invalid_authority_contract",
            f"authority request conflicts with manifest: {sorted(reasons)}")
    materialization = normalize_materialization(raw["materialization"], request)
    return {
        "applicability": "required", "request": request,
        "request_sha256": object_sha256(request),
        "operation_manifest": manifest_binding,
        "materialization": materialization,
    }


def verify_operation_plan(
    root: Path, item: dict[str, Any], *, phase: str = "pre_dispatch",
    effect_status: str | None = None,
    dependencies_ready: bool = False,
) -> dict[str, Any]:
    plan_path = workspace_file(root, item["plan_binding"]["ref"],
                               item["plan_binding"]["sha256"],
                               f"{item['operation_id']}.plan_binding")
    require(read_json(plan_path, "invalid_plan_binding") == item["plan"],
            "plan_binding_mismatch",
            f"{item['operation_id']} owner plan object differs from its exact file binding")
    owner_lifecycle = verify_owner_plan(
        root, item["owner_skill"], item["workflow_role"], item["plan"],
        plan_ref=item["plan_binding"]["ref"], phase=phase,
        effect_status=effect_status, dependencies=item["dependencies"],
        dependencies_ready=dependencies_ready,
    )
    authority = item["authority"]
    if authority["applicability"] == "none":
        return owner_lifecycle
    context = _authority_call(
        "invalid_authority_contract", "authority evaluation context",
        lambda: validate_evaluation_context(root, authority["materialization"]["evaluation_context"]),
    )
    require(object_sha256(context) == authority["materialization"]["evaluation_context_sha256"],
            "invalid_authority_contract", "evaluation context digest mismatch")
    verify_policy_snapshot(root, authority["materialization"]["policy_snapshot"])
    return owner_lifecycle


def _reservation_scope(
    root: Path, item: dict[str, Any], binding: dict[str, str],
    *, phase: str = "pre_dispatch", effect_status: str | None = None,
    dependencies_ready: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    verify_operation_plan(
        root, item, phase=phase, effect_status=effect_status,
        dependencies_ready=dependencies_ready,
    )
    require(item["authority"]["applicability"] == "required",
            "invalid_authority_evidence", "authority-free operation cannot bind a reservation")
    reservation, uses, normalized = _authority_call(
        "invalid_authority_evidence", "authority reservation",
        lambda: load_bound_reservation(root, binding, "task-doctor reservation"),
    )
    decision, _, _ = _authority_call(
        "invalid_authority_evidence", "reservation decision",
        lambda: load_bound_json(root, reservation["decision"], "reservation decision"),
    )
    authority = item["authority"]
    require(decision.get("request") == authority["request"]
            and decision.get("request_sha256") == authority["request_sha256"],
            "authority_binding_mismatch",
            "reservation decision binds a different exact authority request")
    require(decision.get("operation_manifest") == authority["operation_manifest"],
            "authority_binding_mismatch",
            "reservation decision binds a different owner operation manifest")
    materialization = authority["materialization"]
    require(decision.get("evaluation_context") == materialization["evaluation_context"]
            and decision.get("evaluation_context_sha256")
            == materialization["evaluation_context_sha256"],
            "authority_binding_mismatch",
            "reservation decision binds a different evaluation context")
    require(decision.get("evaluated_at") == _iso_time(materialization["evaluated_at"]),
            "authority_binding_mismatch", "reservation decision evaluated_at mismatch")
    grant_ids = {entry["grant_id"] for entry in uses}
    require(grant_ids == {materialization["grant_spec"]["grant_id"]},
            "authority_binding_mismatch", "reservation uses a different exact grant")
    grant, _ = _authority_call(
        "invalid_authority_evidence", "reserved authority grant",
        lambda: load_grant_artifact(root, materialization["grant_spec"]["grant_id"]),
    )
    verify_materialized_grant(grant, authority)
    require(reservation["idempotency_key"]
            == materialization["reservation"]["idempotency_key"]
            and reservation["reserved_at"]
            == _iso_time(materialization["reservation"]["reserved_at"]),
            "authority_binding_mismatch", "reservation materialization recipe mismatch")
    return reservation, uses, normalized


def validate_reservation_evidence(
    root: Path, item: dict[str, Any], binding: dict[str, str], *,
    dependencies_ready: bool = False,
) -> dict[str, Any]:
    reservation, _, normalized = _reservation_scope(
        root, item, binding, dependencies_ready=dependencies_ready
    )
    state_ref = (
        ".task/authorization/state/reservations/"
        f"{reservation['reservation_id']}.json"
    )
    state_path = workspace_regular_file(root, state_ref, "reservation_state")
    state = read_json(state_path, "invalid_authority_evidence")
    state = _authority_call(
        "invalid_authority_evidence", "current reservation state",
        lambda: validate_reservation_state(state, reservation["reservation_id"],
                                           "task-doctor reservation state"),
    )
    require(state == {"schema_version": 2,
                      "artifact_kind": "authority_reservation_state",
                      "reservation_id": reservation["reservation_id"],
                      "status": "reserved", "version": 0,
                      "last_event_id": reservation["reservation_id"]},
            "authority_reservation_not_current",
            "reservation is stale, released, consumed, or quarantined")
    return {**normalized, "reservation_id": reservation["reservation_id"],
            "request_sha256": reservation["request_sha256"],
            "state_ref": state_ref,
            "state_sha256": sha256_file(state_path), "state_version": 0,
            "status": "reserved"}


def validate_reservation_binding(
    root: Path, item: dict[str, Any], binding: dict[str, str],
    *, phase: str = "pre_dispatch", effect_status: str | None = None,
) -> dict[str, str]:
    reservation, _, normalized = _reservation_scope(
        root, item, binding, phase=phase, effect_status=effect_status
    )
    return {**normalized, "reservation_id": reservation["reservation_id"],
            "request_sha256": reservation["request_sha256"]}


def _iso_time(value: str) -> str:
    from manage_agent_authority.canonical import parse_time
    return _authority_call(
        "invalid_authority_contract", "task-doctor authority time",
        lambda: parse_time(value, "task-doctor time").isoformat(),
    )


def _binding(value: Any, label: str) -> dict[str, str]:
    require(isinstance(value, dict), "invalid_owner_result", f"{label} must be an object")
    expect_keys(value, {"ref", "sha256"}, set(), label, "invalid_owner_result")
    return {"ref": str(value["ref"]), "sha256": str(value["sha256"])}


def _owner_effect(
    root: Path, journal: dict[str, Any], item: dict[str, Any], value: Any,
) -> tuple[dict[str, str], dict[str, Any]]:
    binding = _binding(value, "owner_result")
    path = workspace_file(root, binding["ref"], binding["sha256"], "owner_result")
    body = read_json(path, "invalid_owner_result")
    expect_keys(body, {"schema_version", "artifact_kind", "workflow_id",
                       "operation_id", "owner_skill", "plan_sha256",
                       "effect_status", "owner_artifact"}, set(),
                "owner effect result", "invalid_owner_result")
    require(body["schema_version"] == SCHEMA_VERSION
            and body["artifact_kind"] == "task_doctor_owner_effect_result",
            "invalid_owner_result", "owner effect result type mismatch")
    require(body["workflow_id"] == journal["workflow_id"]
            and body["operation_id"] == item["operation_id"]
            and body["owner_skill"] == item["owner_skill"]
            and body["plan_sha256"] == item["plan_sha256"],
            "invalid_owner_result", "owner effect result workflow binding mismatch")
    require(body["effect_status"] in {"confirmed_effect", "confirmed_no_effect"},
            "invalid_owner_result", "owner effect status is not settled")
    owner_artifact = _binding(body["owner_artifact"], "owner_artifact")
    workspace_file(root, owner_artifact["ref"], owner_artifact["sha256"], "owner_artifact")
    verify_owner_result(root, item, owner_artifact, body["effect_status"])
    return binding, body


def _current_settled_state(
    root: Path, reservation_id: str, status: str, receipt_id: str,
    receipt: dict[str, Any],
) -> None:
    state_ref = f".task/authorization/state/reservations/{reservation_id}.json"
    path = workspace_regular_file(root, state_ref, "settled_reservation_state")
    state = read_json(path, "invalid_authority_settlement")
    state = _authority_call(
        "invalid_authority_settlement", "settled reservation state",
        lambda: validate_reservation_state(state, reservation_id, "settled reservation state"),
    )
    require(state["status"] == status and state["last_event_id"] == receipt_id,
            "stale_authority_settlement",
            "authority receipt is not the current reservation settlement")
    raw_changes = receipt.get("state_changes")
    require(isinstance(raw_changes, list), "invalid_authority_settlement",
            "authority receipt lacks exact state changes")
    assert isinstance(raw_changes, list)
    changes = raw_changes
    matching = [change for change in changes if isinstance(change, dict)
                and change.get("ref") == state_ref]
    require(len(matching) == 1 and matching[0].get("after") == state,
            "stale_authority_settlement",
            "current reservation state differs from the receipt after-state")


def _receipt(
    root: Path, receipt_binding: dict[str, str], reservation: dict[str, str],
    owner: dict[str, str], effect_status: str,
) -> str:
    path = workspace_file(root, receipt_binding["ref"], receipt_binding["sha256"],
                          "authority_settlement.receipt")
    receipt = read_json(path, "invalid_authority_settlement")
    kind = receipt.get("artifact_kind")
    if kind == "authority_use_receipt":
        _authority_call("invalid_authority_settlement", "authority use receipt",
                        lambda: validate_use_receipt(root, receipt, path))
        require(effect_status == "confirmed_effect"
                and receipt.get("owner_execution_result") == owner,
                "authority_settlement_mismatch",
                "use receipt does not bind the exact confirmed-effect owner result")
        expected_status = "consumed"
    elif kind == "authority_release_receipt":
        _authority_call("invalid_authority_settlement", "authority release receipt",
                        lambda: validate_release_receipt(root, receipt, path))
        require(effect_status == "confirmed_no_effect"
                and receipt.get("effect_status") == "verified_no_effect"
                and receipt.get("release_applied") is True
                and receipt.get("no_effect_evidence") == owner,
                "authority_settlement_mismatch",
                "release receipt does not prove the exact confirmed no-effect result")
        expected_status = "released"
    elif kind == "authority_reconciliation_receipt":
        _authority_call("invalid_authority_settlement", "authority reconciliation receipt",
                        lambda: validate_reconciliation_receipt(root, receipt, path))
        require(receipt.get("outcome") == effect_status,
                "authority_settlement_mismatch", "reconciliation outcome mismatch")
        bound_reservation, _, normalized = _authority_call(
            "invalid_authority_settlement", "reconciliation reservation",
            lambda: load_bound_reservation(root, receipt["reservation"],
                                           "reconciliation reservation"),
        )
        evidence = _authority_call(
            "invalid_authority_settlement", "reconciliation evidence",
            lambda: validate_reconciliation_evidence(
                root, receipt["effect_evidence"], bound_reservation, normalized,
                receipt["outcome"], require_current_subject=False),
        )
        require(evidence.get("owner_result") == owner,
                "authority_settlement_mismatch",
                "reconciliation receipt does not bind the exact owner result")
        expected_status = "consumed" if effect_status == "confirmed_effect" else "released"
    else:
        raise WorkflowError("invalid_authority_settlement",
                            "authority settlement must be a v2 use, release, or reconciliation receipt")
    require(receipt.get("reservation") == reservation,
            "authority_settlement_mismatch", "settlement binds a different reservation")
    _current_settled_state(root, _reservation_id(root, reservation),
                           expected_status, receipt["receipt_id"], receipt)
    return effect_status


def _reservation_id(root: Path, binding: dict[str, str]) -> str:
    reservation, _, _ = _authority_call(
        "invalid_authority_settlement", "settlement reservation",
        lambda: load_bound_reservation(root, binding, "settlement reservation"),
    )
    return reservation["reservation_id"]


def validate_completion(
    root: Path, journal: dict[str, Any], operation_id: str,
    completion_ref: str, completion_sha256: str,
) -> tuple[dict[str, Any], str]:
    path = workspace_file(root, completion_ref, completion_sha256, "owner_completion")
    body = read_json(path, "invalid_owner_result")
    expect_keys(body, {"schema_version", "artifact_kind", "workflow_id",
                       "operation_id", "plan_sha256", "outcome", "owner_result",
                       "authority_settlement"}, set(), "owner completion",
                "invalid_owner_result")
    item = next(entry for entry in journal["plan"]["operations"]
                if entry["operation_id"] == operation_id)
    require(body["schema_version"] == SCHEMA_VERSION
            and body["artifact_kind"] == "task_doctor_owner_completion",
            "invalid_owner_result", "owner completion type mismatch")
    require(body["workflow_id"] == journal["workflow_id"]
            and body["operation_id"] == operation_id
            and body["plan_sha256"] == item["plan_sha256"],
            "invalid_owner_result", "owner completion workflow binding mismatch")
    require(body["outcome"] in {"completed", "confirmed_no_effect"},
            "invalid_owner_result", "owner completion outcome is invalid")
    owner_binding, owner_body = _owner_effect(root, journal, item, body["owner_result"])
    expected_effect = ("confirmed_effect" if body["outcome"] == "completed"
                       else "confirmed_no_effect")
    require(owner_body["effect_status"] == expected_effect,
            "invalid_owner_result", "completion and owner effect outcome differ")
    verify_operation_plan(
        root, item, phase="terminal", effect_status=expected_effect
    )
    settlement = body["authority_settlement"]
    require(isinstance(settlement, dict), "invalid_owner_result",
            "authority_settlement must be an object")
    if item["authority"]["applicability"] == "none":
        expect_keys(settlement, {"status"}, set(), "authority_settlement",
                    "invalid_owner_result")
        require(settlement["status"] == "not_applicable", "invalid_owner_result",
                "authority-free completion requires not_applicable settlement")
    else:
        expect_keys(settlement, {"status", "receipt"}, set(), "authority_settlement",
                    "invalid_owner_result")
        require(settlement["status"] == "settled", "invalid_owner_result",
                "governed completion requires settled authority")
        receipt_binding = _binding(settlement["receipt"], "authority_settlement.receipt")
        receipt_path = workspace_file(root, receipt_binding["ref"],
                                      receipt_binding["sha256"],
                                      "authority_settlement.receipt")
        receipt_body = read_json(receipt_path, "invalid_authority_settlement")
        reservation = receipt_body.get("reservation")
        require(isinstance(reservation, dict), "authority_settlement_mismatch",
                "settlement receipt has no reservation binding")
        reservation = _binding(reservation, "authority_settlement.reservation")
        _reservation_scope(
            root, item, reservation, phase="terminal",
            effect_status=expected_effect,
        )
        state = journal["operation_state"][operation_id]
        resolution = state.get("resolution_evidence") or {}
        if state.get("resolution") in {"ready_to_resume", "projection_repair"}:
            require({key: resolution.get(key) for key in ("ref", "sha256")}
                    == reservation, "authority_settlement_mismatch",
                    "settlement differs from the dispatched reservation")
        _receipt(root, receipt_binding, reservation, owner_binding, expected_effect)
    return body, expected_effect
