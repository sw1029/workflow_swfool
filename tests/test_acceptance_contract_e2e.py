from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
for package_root in (
    ROOT / "normalize-acceptance-and-demo" / "scripts",
    ROOT / "orchestrate-task-cycle" / "scripts",
    ROOT / "record-agent-work-log" / "scripts",
    ROOT / "manage-agent-authority" / "scripts",
    ROOT / "manage-task-state-index" / "scripts",
    ROOT / "manage-external-advice" / "scripts",
    ROOT / "manage-evidence-cache" / "scripts",
    ROOT / "manage-implementation-issues" / "scripts",
    ROOT / "manage-schema-contracts" / "scripts",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from normalize_acceptance_and_demo.acceptance_compiler import (  # noqa: E402
    compile_acceptance,
)
from normalize_acceptance_and_demo.acceptance_contract_registry import (  # noqa: E402
    RICH_ACCEPTANCE_CONTRACT_FIELDS,
    VERIFIER_CONTRACT_FIELDS,
    registry,
)
from normalize_acceptance_and_demo.acceptance_identity import (  # noqa: E402
    AcceptanceIdentityError,
)
from orchestrate_task_cycle.acceptance_contract import (  # noqa: E402
    rich_contract_fields,
    verifier_contract_fields,
)
from orchestrate_task_cycle.cycle_ledger import init_cycle  # noqa: E402
from orchestrate_task_cycle.model_context import project_model_context  # noqa: E402
from orchestrate_task_cycle.result_contract import api as result_contract  # noqa: E402
from orchestrate_task_cycle.stage.artifact_store import load_stage_input  # noqa: E402
from orchestrate_task_cycle.task_pack import api as task_pack_queue  # noqa: E402


PART_K_FIELDS = {
    "adoption_axis_classification",
    "designated_baseline",
    "expectation_anchor",
    "expectation_anchor_missing",
    "expectation_lineage_stale",
    "majority_vote_adoption",
    "measured_but_disqualified",
    "observed_evidence_resolution",
    "parity_axes",
    "parity_axis_status",
    "parity_unverified",
    "provisional_adoption",
    "report_key_divergence",
    "required_evidence_resolution",
    "required_output_classes",
    "resolution_downgrade",
    "surrogate_resolution_basis",
}
PART_L_FIELDS = {
    "acceptance_scale",
    "axis_starved_by_missing_producer",
    "basis_overclaim",
    "current_decision_lane",
    "decision_metadata_revision",
    "gating_axis_producer_map",
    "measurement_artifact_created_at",
    "measurement_run_id",
    "metric_basis_inputs",
    "observed_cycle_throughput",
    "pass_on_stale_lane",
    "portfolio_quota",
    "portfolio_quota_exceeded",
    "portfolio_quota_mode",
    "production_lane_identity",
    "required_new_run_id",
    "required_scale",
    "surface_field_defect_matrix",
    "surface_field_classes",
    "throughput_evidence",
    "unreachable_within_cycle",
    "upstream_contract_changed_since_measurement",
}
PART_M_RICH_FIELDS = {
    "affected_fields",
    "anchor_kind",
    "code_constant_anchor",
    "closed_world_collection_consumption",
    "collection_field",
    "collection_truncated",
    "consumed_reference_cap",
    "contract_conflict",
    "degradable",
    "destructive_disposition_blocked",
    "destructive_disposition_requested",
    "directive_class",
    "directive_id",
    "disposal_proportionality_unchecked",
    "domain_quality",
    "execution_cost_scalar",
    "execution_cost_threshold",
    "failure_check_provenance",
    "full_collection_required",
    "governance_metadata",
    "harvest_contract_preflight",
    "harvest_gate_check_id",
    "harvest_gate_inventory",
    "harvest_gate_mitigation_required",
    "harvest_gate_repair_required",
    "harvest_gate_unaudited",
    "harvest_risk_accepted",
    "high_cost_artifact",
    "lane_incompatible",
    "mutable_global_anchor",
    "partial_flag_field",
    "predicate_output_requirements",
    "predicate_revision_required",
    "producer_directive_revision_required",
    "quarantine_path",
    "quarantine_required",
    "ratio_floor_anchor",
    "reharvest_available",
    "reharvest_before_rerun_required",
    "reharvest_command_id",
    "reharvest_path",
    "reharvest_terminal_blocked",
    "rerun_before_reharvest",
    "runtime_derived_anchor",
    "same_task_contract_repair_required",
    "sample_as_universe_misuse",
    "sample_cap_anchor",
    "sample_consistency_only",
    "sample_limit_field",
    "sampled_flag_field",
    "scale_incompatible",
    "target_run_scale",
    "truncation_flag_aliases",
    "truncation_flag_field",
    "verifier_defect",
}
PART_M_TOP_LEVEL_FIELDS = {
    "producer_directives",
    "validation_predicate_contract",
}
PART_M_DERIVED_FIELDS = {
    "mutually_unsatisfiable_contract",
    "unverifiable_acceptance_contract",
}
GATE_HOOK_FIELDS = {
    "evaluation_status",
    "evidence_paths",
    "gate_hook_status",
    "required_gate_hooks",
    "required_verifier",
    "verifier_required",
}


def _binding(path: Path, value: object) -> dict[str, str]:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "ref": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _unverifiable_draft() -> dict[str, Any]:
    return {
        "acceptance_status": "partial",
        "acceptance_criteria": ["A required live verifier must run."],
        "blockers": ["required_verifier_not_evaluated"],
        "evidence_paths": [],
        "acceptance_contract": {
            "harvest_gate_unaudited": True,
            "closed_world_collection_consumption": True,
            "collection_truncated": True,
            "sample_as_universe_misuse": True,
            "full_collection_required": True,
            "sample_consistency_only": True,
            "parity_axis_status": {"input": "controlled"},
            "acceptance_verifier_contract": {
                "required_verifier": "abstract_live_verifier",
                "verifier_required": True,
                "required_gate_hooks": ["abstract_gate_hook"],
                "gate_hook_status": "not_evaluated",
                "evaluation_status": "not_evaluated",
                "evidence_paths": [],
            },
        },
    }


def _compile_and_stage(tmp_path: Path) -> dict[str, Any]:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    init_cycle(tmp_path, "cycle-1", "task-1", "acceptance contract E2E")
    compiled = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=_binding(tmp_path / "draft.json", _unverifiable_draft()),
    )
    binding = compiled["owner_result_binding"]
    loaded, _exact = load_stage_input(
        tmp_path,
        binding["ref"],
        binding["sha256"],
        cycle_id="cycle-1",
        target="acceptance",
        input_kind="owner_result",
    )
    return loaded["owner_result"]


def _base_item() -> dict[str, Any]:
    return {
        "item_id": "item-001",
        "order": 1,
        "status": "consumed",
        "title": "Verifier-bound item",
        "objective": "Exercise canonical acceptance consumption.",
        "acceptance": ["Meet the original target."],
        "validation_profile": "current_only",
        "progress_target": "advanced",
    }


def test_versioned_registry_is_single_source_for_compiler_and_consumers() -> None:
    value = registry()
    paths = value["canonical_paths"]

    assert PART_K_FIELDS | PART_L_FIELDS | PART_M_RICH_FIELDS <= set(
        paths["rich_acceptance_contract"]
    )
    assert PART_M_TOP_LEVEL_FIELDS <= set(paths["core_top_level"])
    assert PART_M_DERIVED_FIELDS <= set(paths["compiler_derived_top_level"])
    assert GATE_HOOK_FIELDS == set(
        value["nested_contracts"]["acceptance_verifier_contract"]["fields"]
    )
    assert RICH_ACCEPTANCE_CONTRACT_FIELDS == rich_contract_fields()
    assert VERIFIER_CONTRACT_FIELDS == verifier_contract_fields()
    for fields in paths.values():
        assert fields == sorted(fields)
        assert len(fields) == len(set(fields))
    part_m_reference = (
        ROOT
        / "orchestrate-task-cycle"
        / "references"
        / "execution-context-contracts.md"
    ).read_text(encoding="utf-8")
    fields_section = part_m_reference.split("## Fields", 1)[1].split(
        "## M1:", 1
    )[0]
    documented_part_m = set(
        re.findall(r"`([a-z][a-z0-9_]*)`", fields_section)
    )
    registered = (
        set(paths["core_top_level"])
        | set(paths["compiler_derived_top_level"])
        | set(paths["rich_acceptance_contract"])
        | GATE_HOOK_FIELDS
    )
    assert documented_part_m <= registered
    skill = (ROOT / "normalize-acceptance-and-demo" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "acceptance-contract-registry-v1.json" in skill


def test_compiler_rejects_unknown_nested_verifier_field(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    draft = _unverifiable_draft()
    draft["acceptance_contract"]["acceptance_verifier_contract"][
        "invented_verifier_claim"
    ] = True

    with pytest.raises(AcceptanceIdentityError, match="unsupported fields"):
        compile_acceptance(
            tmp_path,
            task_id="task-1",
            task_path="task.md",
            draft_binding=_binding(tmp_path / "draft.json", draft),
        )


def test_minimal_acceptance_keeps_legacy_optional_field_absence(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    draft = {
        "acceptance_status": "normalized",
        "acceptance_criteria": ["The bounded behavior is observable."],
        "blockers": [],
        "evidence_paths": [],
    }
    compiled = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=_binding(tmp_path / "draft.json", draft),
    )
    owner = json.loads(
        (tmp_path / compiled["owner_result_binding"]["ref"]).read_text(
            encoding="utf-8"
        )
    )["result"]

    assert "unverifiable_acceptance_contract" not in owner


@pytest.mark.parametrize(
    "verifier",
    (
        {
            "required_verifier": "abstract_live_verifier",
            "verifier_required": True,
            "evaluation_status": "not_evaluated",
        },
        {
            "required_gate_hooks": ["abstract_gate_hook"],
            "gate_hook_status": "not_evaluated",
            "evaluation_status": "pass",
        },
    ),
)
def test_compiler_independently_derives_unverifiable_required_surfaces(
    tmp_path: Path, verifier: dict[str, Any]
) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    draft = _unverifiable_draft()
    draft["acceptance_contract"]["acceptance_verifier_contract"] = verifier
    compiled = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=_binding(tmp_path / "draft.json", draft),
    )
    owner = json.loads(
        (tmp_path / compiled["owner_result_binding"]["ref"]).read_text(
            encoding="utf-8"
        )
    )["result"]

    assert owner["unverifiable_acceptance_contract"] is True


def test_compile_stage_model_context_and_completion_derive_fail_closed(
    tmp_path: Path,
) -> None:
    owner = _compile_and_stage(tmp_path)
    contract = owner["acceptance_contract"]

    assert owner["unverifiable_acceptance_contract"] is True
    context = {
        "workspace": str(tmp_path),
        "agent_goal": {},
        "task_state": {},
        "external_advice": {},
        "cycle_state": {
            "latest_cycle_id": "cycle-1",
            "current_stage": {
                "event_count": 1,
                "status": "partial",
                "latest_event": {
                    "step": "acceptance",
                    "status": "partial",
                    **owner,
                },
                "steps": {
                    "acceptance": {
                        "step": "acceptance",
                        "status": "partial",
                        **owner,
                    }
                },
            },
        },
    }
    model = project_model_context(
        context, collect_git_worktree_identity=False
    )
    projected = model["cycle"]["steps"]["acceptance"]
    assert projected["acceptance_contract"] == contract
    assert projected["unverifiable_acceptance_contract"] is True

    completion = result_contract.validate(
        "validate",
        {
            "validation_verdict": "complete",
            "acceptance_contract": contract,
        },
        "block",
    )
    assert any(
        finding["code"] == "validate_unverifiable_acceptance_complete"
        for finding in completion["findings"]
    )

    derive = result_contract.validate(
        "derive",
        {
            "derive_mode": "normal",
            "selected_task_kind": "implementation",
            "acceptance_contract": contract,
        },
        "block",
    )
    assert any(
        finding["code"] == "derive_unverifiable_acceptance_unhandled"
        for finding in derive["findings"]
    )


def test_task_pack_consumes_nested_canonical_verifier_contract(
    tmp_path: Path,
) -> None:
    owner = _compile_and_stage(tmp_path)
    item = _base_item()
    item["scope_fidelity"] = {
        "directive_id": "directive-r1",
        "original_target": {
            "metric": "abstract_metric",
            "comparator": ">=",
            "target": 1,
        },
        "item_acceptance": ["Meet the original measurable target."],
        "acceptance_contract": owner["acceptance_contract"],
    }
    item["result"] = {
        "validation_verdict": "complete",
        "acceptance_provenance_gate": {"target_met": True},
    }
    pack = {
        "schema_version": 1,
        "pack_id": "pack-test",
        "status": "active",
        "goal": "Test canonical acceptance consumption.",
        "current_item_id": None,
        "items": [item],
        "mutation_log": [],
    }
    findings = task_pack_queue.validate_pack(pack)

    assert any(
        finding["code"] == "acceptance_verifier_not_passed_item_consumed"
        for finding in findings
    )
    assert any(
        finding["code"] == "required_gate_hook_missing_item_consumed"
        for finding in findings
    )
