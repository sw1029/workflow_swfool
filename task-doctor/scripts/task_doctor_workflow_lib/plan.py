from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .common import (
    FORBIDDEN_EFFECTS,
    GIT_STATES,
    MODES,
    PLAN_KIND,
    RESOLUTIONS,
    SAFE_ID,
    SCHEMA_VERSION,
    SKILL_ID,
    WorkflowError,
    expect_keys,
    require,
    validate_hex,
    validate_nonempty,
)
from .authority import normalize_authority, verify_operation_plan
from .authority_basis import verify_declared_basis


ROLE_BY_OPERATION = {
    ("task-doctor", "mutate_task_scope"): "task_scope_transition",
    ("manage-external-advice", "mutate_advice_lifecycle"): "external_advice_intake",
    ("manage-task-state-index", "mutate_task_state_index"): "task_index_transition",
}


def _header(
    raw: dict[str, Any],
) -> tuple[int, str, int, list[str], list[str], str]:
    expect_keys(
        raw,
        {
            "schema_version", "execution_mode", "complete_effect_inventory",
            "max_user_approval_interactions", "authorized_local_effects",
            "excluded_effects", "git_finalization", "task_index_transition",
            "operations",
        },
        {"authorization_basis", "reporting"},
        "workflow plan",
    )
    plan_schema_version = raw["schema_version"]
    require(plan_schema_version in {SCHEMA_VERSION, 2}, "invalid_plan",
            "schema_version must be 1 or 2")
    mode = raw["execution_mode"]
    require(mode in MODES, "invalid_plan", f"unsupported execution_mode: {mode}")
    require(raw["complete_effect_inventory"] is True, "plan_incomplete",
            "complete_effect_inventory must be true before any workflow mutation",
            next_action="prepare_all_required_effects")
    maximum = raw["max_user_approval_interactions"]
    require(isinstance(maximum, int) and not isinstance(maximum, bool),
            "invalid_plan", "max_user_approval_interactions must be an integer")
    expected = 0 if mode == "execute_with_declared_authorization" else 1
    require(maximum == expected, "invalid_plan",
            f"{mode} requires max_user_approval_interactions={expected}")
    authorized = raw["authorized_local_effects"]
    excluded = raw["excluded_effects"]
    for value, label in ((authorized, "authorized_local_effects"),
                         (excluded, "excluded_effects")):
        require(isinstance(value, list)
                and all(isinstance(item, str) and item for item in value),
                "invalid_plan", f"{label} must be a string list")
        require(len(value) == len(set(value)), "invalid_plan",
                f"{label} contains duplicates")
    require(FORBIDDEN_EFFECTS <= set(excluded), "invalid_plan",
            "excluded_effects must preserve the task-doctor safety boundary")
    git_state = raw["git_finalization"]
    require(git_state in GIT_STATES, "invalid_plan",
            f"unsupported git_finalization: {git_state}")
    return plan_schema_version, mode, maximum, authorized, excluded, git_state


def _operation(
    item: Any, index: int, mode: str, plan_schema_version: int,
) -> dict[str, Any]:
    require(isinstance(item, dict), "invalid_plan",
            f"operations[{index}] must be an object")
    expect_keys(
        item,
        {"operation_id", "workflow_role", "owner_skill", "effect_class",
         "effect_summary", "required", "dependencies", "plan", "plan_binding",
         "authority"},
        {"initial_resolution"},
        f"operations[{index}]",
    )
    operation_id = validate_nonempty(item["operation_id"], "operation_id")
    require(SAFE_ID.fullmatch(operation_id) is not None, "invalid_plan",
            f"invalid operation_id: {operation_id}")
    owner = validate_nonempty(item["owner_skill"], f"{operation_id}.owner_skill")
    require(SKILL_ID.fullmatch(owner) is not None, "invalid_plan",
            f"invalid owner_skill for {operation_id}: {owner}")
    effect_class = validate_nonempty(item["effect_class"],
                                     f"{operation_id}.effect_class")
    require(SAFE_ID.fullmatch(effect_class) is not None, "invalid_plan",
            f"invalid effect_class for {operation_id}: {effect_class}")
    require(effect_class not in FORBIDDEN_EFFECTS, "forbidden_effect",
            f"task-doctor cannot coordinate effect_class {effect_class}")
    workflow_role = validate_nonempty(item["workflow_role"],
                                      f"{operation_id}.workflow_role")
    require(SAFE_ID.fullmatch(workflow_role) is not None, "invalid_plan",
            f"invalid workflow_role for {operation_id}: {workflow_role}")
    require(isinstance(item["required"], bool), "invalid_plan",
            f"{operation_id}.required must be boolean")
    dependencies = item["dependencies"]
    require(isinstance(dependencies, list)
            and all(isinstance(value, str) and value for value in dependencies),
            "invalid_plan", f"{operation_id}.dependencies must be a string list")
    require(len(dependencies) == len(set(dependencies)), "invalid_plan",
            f"{operation_id}.dependencies contains duplicates")
    require(isinstance(item["plan"], dict) and bool(item["plan"]), "invalid_plan",
            f"{operation_id}.plan must be a non-empty exact owner plan")
    plan_binding = item["plan_binding"]
    require(isinstance(plan_binding, dict), "invalid_plan",
            f"{operation_id}.plan_binding must be an object")
    expect_keys(plan_binding, {"ref", "sha256"}, set(),
                f"{operation_id}.plan_binding")
    validate_nonempty(plan_binding["ref"], f"{operation_id}.plan_binding.ref")
    validate_hex(plan_binding["sha256"], f"{operation_id}.plan_binding.sha256")
    normalized_authority = normalize_authority(
        owner.removeprefix("$"), effect_class, plan_binding, item["authority"],
        plan_schema_version=plan_schema_version,
    )
    authority_free = normalized_authority["applicability"] == "none"
    expected_resolution = (
        "authority_not_applicable" if authority_free else
        "already_covered" if mode == "execute_with_declared_authorization" else
        "needs_user_approval"
    )
    resolution = item.get("initial_resolution", expected_resolution)
    require(resolution in RESOLUTIONS and resolution == expected_resolution,
            "invalid_plan",
            f"{operation_id} initial_resolution must be {expected_resolution}; "
            "live and terminal classifications require journal evidence")
    return {
        "operation_id": operation_id,
        "workflow_role": workflow_role,
        "owner_skill": owner.removeprefix("$"),
        "effect_class": effect_class,
        "effect_summary": validate_nonempty(item["effect_summary"],
                                            f"{operation_id}.effect_summary"),
        "required": item["required"],
        "dependencies": list(dependencies),
        "plan": copy.deepcopy(item["plan"]),
        "plan_sha256": plan_binding["sha256"],
        "plan_binding": copy.deepcopy(plan_binding),
        "authority": normalized_authority,
        "initial_resolution": resolution,
    }


def _validate_operations(operations: list[dict[str, Any]], excluded: list[str]) -> None:
    identifiers = [item["operation_id"] for item in operations]
    require(len(identifiers) == len(set(identifiers)), "invalid_plan",
            "operation_id values must be unique")
    position = {value: index for index, value in enumerate(identifiers)}
    for item in operations:
        require(item["effect_class"] not in set(excluded), "invalid_plan",
                f"effect_class {item['effect_class']} is both planned and excluded")
        for dependency in item["dependencies"]:
            require(dependency in position, "invalid_plan",
                    f"operation {item['operation_id']} has unknown dependency {dependency}")
            require(position[dependency] < position[item["operation_id"]], "invalid_plan",
                    "operations must be topologically ordered; "
                    f"{item['operation_id']} precedes dependency {dependency}")


def _validate_index(raw: dict[str, Any], operations: list[dict[str, Any]]) -> None:
    transition = raw["task_index_transition"]
    require(isinstance(transition, dict), "invalid_plan",
            "task_index_transition must be an object")
    status = transition.get("status")
    require(status in {"planned", "not_applicable"}, "invalid_plan",
            "task_index_transition.status must be planned or not_applicable")
    index_operations = [item for item in operations
                        if item["workflow_role"] == "task_index_transition"]
    task_operations = [item for item in operations
                       if item["workflow_role"] == "task_scope_transition"]
    if status == "not_applicable":
        expect_keys(transition, {"status", "reason"}, set(), "task_index_transition")
        validate_nonempty(transition["reason"], "task_index_transition.reason")
        require(not index_operations, "invalid_plan",
                "not_applicable task-index transition cannot include an index operation")
        require(not task_operations, "invalid_plan",
                "task scope changes require one final task-index transition")
        return
    expect_keys(transition, {"status", "operation_id"}, set(), "task_index_transition")
    require(len(index_operations) == 1, "invalid_plan",
            "planned task-index reconciliation requires exactly one operation")
    index_operation = index_operations[0]
    require(transition["operation_id"] == index_operation["operation_id"],
            "invalid_plan", "task_index_transition operation_id does not match")
    require(index_operation["plan"].get("plan_kind") == "task_state_transition_plan",
            "invalid_plan",
            "task-index owner plan must be an exact task_state_transition_plan")
    require(isinstance(index_operation["plan"].get("events"), list)
            and index_operation["plan"]["events"], "invalid_plan",
            "task-index owner plan must contain all exact events")
    expected_dependencies = {
        item["operation_id"] for item in operations
        if item["operation_id"] != index_operation["operation_id"]
        and item["workflow_role"] != "git_finalization"
    }
    require(expected_dependencies <= set(index_operation["dependencies"]),
            "plan_incomplete",
            "the single task-index transition must depend on every prior lifecycle effect",
            next_action="consolidate_task_index_transition")


def _validate_git(git_state: str, operations: list[dict[str, Any]]) -> None:
    git_operations = [item for item in operations
                      if item["workflow_role"] == "git_finalization"]
    if git_state != "requested":
        require(not git_operations, "invalid_plan",
                f"git_finalization={git_state} cannot include a Git operation")
        return
    require(len(git_operations) == 1, "invalid_plan",
            "requested Git finalization requires exactly one operation")
    git_operation = git_operations[0]
    require(git_operation["required"] is False, "invalid_plan",
            "Git finalization must remain optional to task publication")
    required_non_git = {
        item["operation_id"] for item in operations
        if item["required"] and item["workflow_role"] != "git_finalization"
    }
    require(required_non_git <= set(git_operation["dependencies"]), "invalid_plan",
            "Git finalization must depend on every required non-Git effect")


def _validate_owner_plan_kinds(operations: list[dict[str, Any]]) -> None:
    for item in operations:
        authority = item["authority"]
        operation = (
            authority["request"] if authority["applicability"] == "required"
            else authority["operation"]
        )
        identity = (operation["skill_id"], operation["operation_id"])
        expected_role = ROLE_BY_OPERATION.get(identity)
        require(expected_role is not None, "invalid_plan",
                "owner operation has no registered closed task-doctor plan/result adapter")
        require(item["workflow_role"] == expected_role, "invalid_plan",
                f"{identity[0]}:{identity[1]} requires workflow_role={expected_role}")
        if item["workflow_role"] == "task_scope_transition":
            require(item["owner_skill"] == "task-doctor"
                    and item["plan"].get("plan_kind") == "task_transition_plan",
                    "invalid_plan",
                    "task scope transitions require a closed task_transition_plan")
        if (item["workflow_role"] == "external_advice_intake"
                and item["owner_skill"] == "manage-external-advice"):
            require(item["plan"].get("plan_kind") == "external_advice_intake_plan",
                    "invalid_plan",
                    "external-advice owner plan must be an exact intake plan")


def _validate_authority_lifecycle_identities(
    operations: list[dict[str, Any]],
) -> None:
    governed = [
        item for item in operations if item["authority"]["applicability"] == "required"
    ]
    fields = {
        "request_id": [item["authority"]["request"]["request_id"] for item in governed],
        "request idempotency key": [
            item["authority"]["request"]["idempotency_key"] for item in governed
        ],
        "grant_id": [
            item["authority"]["materialization"]["grant_spec"]["grant_id"]
            for item in governed
        ],
        "grant idempotency key": [
            item["authority"]["materialization"]["grant_spec"]["idempotency_key"]
            for item in governed
        ],
        "reservation idempotency key": [
            item["authority"]["materialization"]["reservation"]["idempotency_key"]
            for item in governed
        ],
    }
    for label, values in fields.items():
        require(len(values) == len(set(values)), "invalid_authority_contract",
                f"governed operations must have unique {label} values")


def _basis(raw: dict[str, Any], mode: str, effects: set[str], authorized: list[str]) -> Any:
    basis = raw.get("authorization_basis")
    if mode == "execute_with_declared_authorization":
        require(isinstance(basis, dict), "invalid_plan",
                "execute_with_declared_authorization requires authorization_basis")
        require(effects == set(authorized), "undeclared_effect",
                "authorized_local_effects must exactly equal the planned effect inventory",
                next_action="prepare_consolidated_review")
    if basis is not None:
        require(isinstance(basis, dict), "invalid_plan",
                "authorization_basis must be an object")
        expect_keys(basis, {"schema_version", "basis_kind", "approvals"}, set(),
                    "authorization_basis")
        require(basis["schema_version"] == SCHEMA_VERSION
                and basis["basis_kind"] == "task_doctor_declared_authorization",
                "invalid_plan", "authorization_basis type mismatch")
        approvals = basis["approvals"]
        require(isinstance(approvals, list), "invalid_plan",
                "authorization_basis.approvals must be a list")
        normalized = []
        for index, approval in enumerate(approvals):
            require(isinstance(approval, dict), "invalid_plan",
                    f"authorization_basis.approvals[{index}] must be an object")
            expect_keys(approval, {"operation_id", "source_approval"}, set(),
                        f"authorization_basis.approvals[{index}]")
            source = approval["source_approval"]
            require(isinstance(source, dict), "invalid_plan",
                    "source_approval must be a binding")
            expect_keys(source, {"ref", "sha256"}, set(), "source_approval")
            validate_nonempty(source["ref"], "source_approval.ref")
            validate_hex(source["sha256"], "source_approval.sha256")
            normalized.append(copy.deepcopy(approval))
        identifiers = [item["operation_id"] for item in normalized]
        require(len(identifiers) == len(set(identifiers)), "invalid_plan",
                "authorization_basis contains duplicate operation IDs")
        return {"schema_version": SCHEMA_VERSION,
                "basis_kind": "task_doctor_declared_authorization",
                "approvals": normalized}
    return None


def normalize_plan(raw: Any) -> dict[str, Any]:
    require(isinstance(raw, dict), "invalid_plan", "workflow plan must be an object")
    (
        plan_schema_version,
        mode,
        maximum,
        authorized,
        excluded,
        git_state,
    ) = _header(raw)
    operations_raw = raw["operations"]
    require(isinstance(operations_raw, list) and bool(operations_raw), "invalid_plan",
            "operations must be a non-empty list")
    operations = [_operation(item, index, mode, plan_schema_version)
                  for index, item in enumerate(operations_raw)]
    _validate_operations(operations, excluded)
    _validate_index(raw, operations)
    _validate_git(git_state, operations)
    _validate_owner_plan_kinds(operations)
    _validate_authority_lifecycle_identities(operations)
    if mode == "execute_with_declared_authorization":
        require(all(item["initial_resolution"] != "needs_user_approval"
                    for item in operations), "invalid_plan",
                "declared-authorization mode cannot begin with needs_user_approval")
    basis = _basis(raw, mode, {item["effect_class"] for item in operations}, authorized)
    if basis is not None:
        approval_by_operation = {
            item["operation_id"]: copy.deepcopy(item["source_approval"])
            for item in basis["approvals"]
        }
        governed_ids = {
            item["operation_id"] for item in operations
            if item["authority"]["applicability"] == "required"
        }
        require(set(approval_by_operation) == governed_ids,
                "invalid_authorization_basis",
                "declared authorization approvals must exactly equal governed operations")
        for item in operations:
            if item["authority"]["applicability"] == "required":
                source = approval_by_operation.get(item["operation_id"])
                require(source is not None, "invalid_authorization_basis",
                        "declared authorization lacks an operation source snapshot")
                item["authority"]["source_approval"] = source
    reporting = raw.get("reporting", {"detail": "concise", "language": "auto"})
    require(isinstance(reporting, dict), "invalid_plan", "reporting must be an object")
    expect_keys(reporting, {"detail", "language"}, set(), "reporting")
    require(reporting["detail"] == "concise", "invalid_plan",
            "task-doctor default reporting must be concise")
    validate_nonempty(reporting["language"], "reporting.language")
    result = {
        "kind": PLAN_KIND, "schema_version": plan_schema_version,
        "execution_mode": mode, "complete_effect_inventory": True,
        "max_user_approval_interactions": maximum,
        "authorized_local_effects": sorted(set(authorized)),
        "excluded_effects": sorted(set(excluded)),
        "git_finalization": git_state,
        "task_index_transition": copy.deepcopy(raw["task_index_transition"]),
        "operations": operations, "reporting": copy.deepcopy(reporting),
    }
    if basis is not None:
        result["authorization_basis"] = copy.deepcopy(basis)
    return result


def verify_plan_bindings(
    root: Path, plan: dict[str, Any], *, phase: str = "pre_dispatch",
) -> None:
    for item in plan["operations"]:
        verify_operation_plan(
            root, item, phase=phase,
            dependencies_ready=not item["dependencies"],
        )
    verify_declared_basis(root, plan)


def validate_normalized_plan(plan: Any) -> dict[str, Any]:
    """Reconstruct and re-normalize a journal-embedded immutable plan."""

    require(isinstance(plan, dict), "invalid_journal",
            "journal normalized plan must be an object")
    expected_top = {
        "kind", "schema_version", "execution_mode", "complete_effect_inventory",
        "max_user_approval_interactions", "authorized_local_effects",
        "excluded_effects", "git_finalization", "task_index_transition",
        "operations", "reporting",
    }
    expect_keys(plan, expected_top, {"authorization_basis"},
                "journal normalized plan", "invalid_journal")
    operations = plan.get("operations")
    require(isinstance(operations, list), "invalid_journal",
            "journal normalized operations must be a list")
    raw_operations: list[dict[str, Any]] = []
    try:
        for index, item in enumerate(operations):
            require(isinstance(item, dict), "invalid_journal",
                    f"journal normalized operation {index} must be an object")
            expect_keys(
                item,
                {"operation_id", "workflow_role", "owner_skill", "effect_class",
                 "effect_summary", "required", "dependencies", "plan", "plan_sha256",
                 "plan_binding", "authority", "initial_resolution"},
                set(), f"journal normalized operation {index}", "invalid_journal",
            )
            authority = item["authority"]
            require(isinstance(authority, dict), "invalid_journal",
                    "journal normalized authority must be an object")
            if authority.get("applicability") == "none":
                raw_authority = {
                    "applicability": "none", "operation": authority["operation"]
                }
            else:
                materialization = copy.deepcopy(authority["materialization"])
                materialization.pop("evaluation_context_sha256", None)
                raw_authority = {
                    "applicability": "required", "request": authority["request"],
                    "materialization": materialization,
                }
            raw_operations.append({
                key: copy.deepcopy(item[key]) for key in (
                    "operation_id", "workflow_role", "owner_skill", "effect_class",
                    "effect_summary", "required", "dependencies", "plan",
                    "plan_binding", "initial_resolution",
                )
            } | {"authority": copy.deepcopy(raw_authority)})
        raw = {
            key: copy.deepcopy(plan[key]) for key in (
                "schema_version", "execution_mode", "complete_effect_inventory",
                "max_user_approval_interactions", "authorized_local_effects",
                "excluded_effects", "git_finalization", "task_index_transition",
                "reporting",
            )
        }
        raw["operations"] = raw_operations
        if "authorization_basis" in plan:
            raw["authorization_basis"] = copy.deepcopy(plan["authorization_basis"])
        normalized = normalize_plan(raw)
    except WorkflowError as error:
        if error.code == "invalid_journal":
            raise
        raise WorkflowError(
            "invalid_journal",
            f"journal normalized plan violates its semantic contract: {error.message}",
        ) from error
    except (KeyError, TypeError) as error:
        raise WorkflowError(
            "invalid_journal", "journal normalized plan is structurally incomplete"
        ) from error
    require(normalized == plan, "invalid_journal",
            "journal normalized plan is not the canonical normalization result")
    return plan
