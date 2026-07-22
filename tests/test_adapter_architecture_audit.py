from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrate_task_cycle.adapter_architecture import (
    adjudicate_architecture,
    architecture_cache_fingerprint,
    build_adapter_validation_packet,
    build_code_structure_packet,
    compile_architecture_facts,
    validate_semantic_receipt,
)
from orchestrate_task_cycle.adapter_architecture.contracts import (
    SEMANTIC_SCHEMA_REVISION,
    object_sha256,
)
from orchestrate_task_cycle.repo_skill_adapter import (
    registered_adapter_handoff,
    scan_repo_skill_adapters,
)
from orchestrate_task_cycle.stage.native_results import normalize_native_owner_result
from audit_cycle_loopback import adapter_loading


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_v3_adapter(root: Path) -> tuple[Path, Path]:
    skill = root / ".codex/skills/example-workflow-adapter"
    scripts = skill / "scripts"
    scripts.mkdir(parents=True)
    adapter = scripts / "adapter.py"
    helper = scripts / "helper.py"
    adapter.write_text(
        "from helper import normalize\n\n"
        "class Base:\n"
        "    def render(self, value):\n"
        "        return value\n\n"
        "class Child(Base):\n"
        "    def render(self, value):\n"
        "        return normalize(value)\n\n"
        "def quality_vector(value=None):\n"
        "    return {'value': normalize(value)}\n",
        encoding="utf-8",
    )
    helper.write_text(
        "def normalize(value):\n"
        "    return value\n\n"
        "def normalize_again(item):\n"
        "    return item\n",
        encoding="utf-8",
    )
    hooks = skill / "hook-contracts.json"
    convention = skill / "code-convention.json"
    _write_json(
        hooks,
        {
            "schema_version": 1,
            "hooks": [
                {
                    "hook_id": "quality_vector",
                    "input_schema_id": "quality-vector-input-v1",
                    "output_schema_id": "quality-vector-output-v1",
                    "phases": ["loopback_audit"],
                    "consumer_ids": ["audit-cycle-loopback"],
                    "side_effect_class": "read_only",
                    "owner": {
                        "component_id": "adapter",
                        "symbol": "quality_vector",
                    },
                    "fail_policy": "fail_closed",
                    "test_component_ids": [],
                }
            ],
        },
    )
    _write_json(
        convention,
        {
            "schema_version": 1,
            "enforcement": "enforce_all",
            "rollout_policy": {"mode": "enforce_all"},
            "thresholds": {
                "max_module_logical_loc": 8,
                "max_function_logical_loc": 20,
                "max_class_logical_loc": 20,
            },
            "module_dependency_dag": {
                "facade": ["domain"],
                "domain": [],
                "contract": [],
            },
        },
    )
    prefix = ".codex/skills/example-workflow-adapter"
    components = [
        {
            "component_id": "adapter",
            "path": f"{prefix}/scripts/adapter.py",
            "kind": "python_module",
            "role": "facade",
            "required": True,
            "revision_included": True,
            "runtime_included": True,
            "architecture_audit_scope": True,
            "depends_on": ["helper"],
        },
        {
            "component_id": "helper",
            "path": f"{prefix}/scripts/helper.py",
            "kind": "python_module",
            "role": "domain",
            "required": True,
            "revision_included": True,
            "runtime_included": True,
            "architecture_audit_scope": True,
            "depends_on": [],
        },
        {
            "component_id": "hook-contracts",
            "path": f"{prefix}/hook-contracts.json",
            "kind": "contract",
            "role": "contract",
            "required": True,
            "revision_included": True,
            "runtime_included": False,
            "architecture_audit_scope": False,
            "depends_on": [],
        },
        {
            "component_id": "code-convention",
            "path": f"{prefix}/code-convention.json",
            "kind": "contract",
            "role": "contract",
            "required": True,
            "revision_included": True,
            "runtime_included": False,
            "architecture_audit_scope": False,
            "depends_on": [],
        },
    ]
    _write_json(
        skill / "adapter.manifest.json",
        {
            "format_version": 3,
            "adapter_id": "example-workflow-adapter",
            "status": "active",
            "implementation_path": f"{prefix}/scripts/adapter.py",
            "not_goal_truth": True,
            "not_validation_evidence": True,
            "required_consumer_ids": ["audit-cycle-loopback"],
            "hooks": ["quality_vector"],
            "phase_consumers": {
                "loopback_audit": ["audit-cycle-loopback"]
            },
            "phase_hooks": {"loopback_audit": ["quality_vector"]},
            "components": components,
            "runtime_closure": {
                "entry_component_ids": ["adapter"],
                "dynamic_dependency_ids": [],
                "unresolved_local_import_policy": "block",
            },
            "hook_contract_path": f"{prefix}/hook-contracts.json",
            "code_convention_contract_path": f"{prefix}/code-convention.json",
        },
    )
    return adapter, helper


def _row(root: Path) -> dict:
    scan = scan_repo_skill_adapters(root, cycle_id="cycle-v3")
    assert scan["adapter_scan_status"] == "pass", scan["blockers"]
    return scan["repo_skill_adapter_packet"]["adapters"][0]


def _semantic_receipt(row: dict, facts: dict, fact_ids: list[str]) -> dict:
    pressure_by_id = {
        item["fact_id"]: item for item in facts["structural_pressures"]
    }
    cited = [pressure_by_id[fact_id] for fact_id in fact_ids]
    axes = {item["axis"] for item in cited}
    if len(axes) != 1:
        raise ValueError("test semantic receipt requires one cited axis")
    subjects = sorted(
        {
            subject
            for item in cited
            for subject in (item.get("subjects") or [item["subject"]])
        }
    )
    body = {
        "schema_version": 1,
        "artifact_kind": "adapter_architecture_semantic_receipt",
        "semantic_schema_revision": SEMANTIC_SCHEMA_REVISION,
        "adapter_id": row["adapter_id"],
        "adapter_revision_sha256": row["adapter_revision_sha256"],
        "convention_sha256": row["code_convention_contract_sha256"],
        "fact_packet_sha256": facts["fact_packet_sha256"],
        "assessment": {
            "responsibilities": [
                {
                    "component_id": "adapter",
                    "distilled_responsibility": "Expose the stable adapter facade.",
                }
            ],
            "semantic_module_tree": [
                {
                    "module_id": "facades",
                    "distilled_responsibility": "Own compatibility entry points.",
                    "children": [],
                    "source_component_ids": ["adapter"],
                }
            ],
            "findings": [
                {
                    "finding_id": "finding-1",
                    "axis": next(iter(axes)),
                    "subjects": subjects,
                    "evidence_fact_ids": fact_ids,
                    "observation": "The deterministic pressure crosses one responsibility boundary.",
                    "confidence": 0.9,
                    "recommendation": "Move domain calculation behind the facade.",
                }
            ],
            "compatibility_risks": ["Preserve the public hook signature."],
            "design_observations": ["Composition remains simpler than inheritance here."],
        },
    }
    return {**body, "receipt_sha256": object_sha256(body)}


def test_manifest_v3_closes_runtime_components_and_handoff(tmp_path: Path) -> None:
    _write_v3_adapter(tmp_path)
    scan = scan_repo_skill_adapters(tmp_path, cycle_id="cycle-v3")
    row = scan["repo_skill_adapter_packet"]["adapters"][0]

    assert scan["adapter_scan_status"] == "pass"
    assert row["manifest_format_version"] == 3
    assert row["manifest_compatibility_status"] == "v3_closed"
    assert row["runtime_closure"]["component_ids"] == ["adapter", "helper"]
    assert row["runtime_closure"]["internal_import_edges"] == [
        {
            "source_path": ".codex/skills/example-workflow-adapter/scripts/adapter.py",
            "target_path": ".codex/skills/example-workflow-adapter/scripts/helper.py",
        }
    ]
    assert len(row["component_registry_sha256"]) == 64
    assert len(row["adapter_revision_sha256"]) == 64
    handoff = registered_adapter_handoff(
        tmp_path,
        scan,
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )
    assert handoff["status"] == "ready"
    assert handoff["manifest_format_version"] == 3
    assert handoff["authority_granted"] is False


def test_manifest_v3_handoff_detects_transitive_component_drift(tmp_path: Path) -> None:
    _adapter, helper = _write_v3_adapter(tmp_path)
    scan = scan_repo_skill_adapters(tmp_path)
    helper.write_text("def normalize(value):\n    return str(value)\n", encoding="utf-8")

    handoff = registered_adapter_handoff(
        tmp_path,
        scan,
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )

    assert handoff["status"] == "registered_unavailable"
    assert "component:helper" in handoff["stale_components"]
    assert "components" in handoff["stale_components"]
    assert "runtime_closure" in handoff["stale_components"]
    assert "adapter_revision_sha256" in handoff["stale_components"]


def test_loopback_consumer_accepts_v3_scan_and_rejects_closure_drift(
    tmp_path: Path,
) -> None:
    _adapter, helper = _write_v3_adapter(tmp_path)
    scan = scan_repo_skill_adapters(tmp_path)

    ready = adapter_loading.registered_adapter_from_scan(
        tmp_path,
        json.dumps(scan),
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )

    assert ready["status"] == "ready"
    assert ready["adapter_revision_sha256"] == scan[
        "repo_skill_adapter_packet"
    ]["adapters"][0]["adapter_revision_sha256"]

    helper.write_text("def normalize(value):\n    return str(value)\n", encoding="utf-8")
    stale = adapter_loading.registered_adapter_from_scan(
        tmp_path,
        json.dumps(scan),
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )

    assert stale["status"] == "wiring_defect"
    assert stale["error"] == "registered_adapter_scan_stale"


def test_manifest_v3_auto_binds_statically_resolved_local_import(tmp_path: Path) -> None:
    adapter, _helper = _write_v3_adapter(tmp_path)
    secret = adapter.parent / "unregistered.py"
    secret.write_text("VALUE = 1\n", encoding="utf-8")
    adapter.write_text("import unregistered\n", encoding="utf-8")

    scan = scan_repo_skill_adapters(tmp_path)
    row = scan["repo_skill_adapter_packet"]["adapters"][0]
    relative = (
        ".codex/skills/example-workflow-adapter/scripts/unregistered.py"
    )

    assert scan["adapter_scan_status"] == "pass"
    assert row["runtime_closure"]["discovered_transitive_sha256"][relative]
    secret.write_text("VALUE = 2\n", encoding="utf-8")
    handoff = registered_adapter_handoff(
        tmp_path,
        scan,
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )
    assert handoff["status"] == "registered_unavailable"
    assert "runtime_closure" in handoff["stale_components"]
    assert "adapter_revision_sha256" in handoff["stale_components"]


def test_manifest_v3_blocks_unresolved_relative_local_import(
    tmp_path: Path,
) -> None:
    adapter, _helper = _write_v3_adapter(tmp_path)
    adapter.write_text(
        "from .missing_runtime_module import value\n",
        encoding="utf-8",
    )

    scan = scan_repo_skill_adapters(tmp_path)

    assert scan["adapter_scan_status"] == "block"
    assert any(
        error.startswith("runtime_local_import_unresolved:")
        for error in scan["blockers"][0]["errors"]
    )


def test_facts_semantic_receipt_and_adjudicator_keep_final_status_deterministic(
    tmp_path: Path,
) -> None:
    _write_v3_adapter(tmp_path)
    row = _row(tmp_path)
    facts = compile_architecture_facts(tmp_path, row)
    fact_ids = [item["fact_id"] for item in facts["structural_pressures"]]
    assert fact_ids
    assert facts["import_graph"]["strongly_connected_components"]
    assert facts["inheritance"][0]["override_methods"] == ["render"]
    assert facts["normalized_ast_clone_groups"]
    assert facts["raw_source_persisted"] is False
    semantic = validate_semantic_receipt(
        _semantic_receipt(row, facts, [fact_ids[0]]),
        adapter_id=row["adapter_id"],
        adapter_revision_sha256=row["adapter_revision_sha256"],
        convention_sha256=row["code_convention_contract_sha256"],
        fact_packet_sha256=facts["fact_packet_sha256"],
        structural_pressures=facts["structural_pressures"],
    )
    convention = json.loads(
        (tmp_path / row["code_convention_contract_path"]).read_text(encoding="utf-8")
    )
    result = adjudicate_architecture(facts, convention, semantic)

    assert result["adapter_architecture_status"] == "refactor_required"
    assert result["adapter_consumability_status"] == "pass"
    assert result["semantic_corroborated_fact_ids"] == [fact_ids[0]]
    assert result["semantic_cannot_set_final_status"] is True

    invalid = _semantic_receipt(row, facts, [fact_ids[0]])
    invalid["assessment"]["findings"][0]["severity"] = "blocked"
    invalid["receipt_sha256"] = object_sha256(
        {key: value for key, value in invalid.items() if key != "receipt_sha256"}
    )
    with pytest.raises(ValueError, match="forbidden authority/body field"):
        validate_semantic_receipt(
            invalid,
            adapter_id=row["adapter_id"],
            adapter_revision_sha256=row["adapter_revision_sha256"],
            convention_sha256=row["code_convention_contract_sha256"],
            fact_packet_sha256=facts["fact_packet_sha256"],
            structural_pressures=facts["structural_pressures"],
        )


def test_semantic_receipt_rejects_unrelated_axis_and_subjects_without_blockers(
    tmp_path: Path,
) -> None:
    _write_v3_adapter(tmp_path)
    row = _row(tmp_path)
    facts = compile_architecture_facts(tmp_path, row)
    assert facts["blockers"] == []
    convention = json.loads(
        (tmp_path / row["code_convention_contract_path"]).read_text(
            encoding="utf-8"
        )
    )
    assert adjudicate_architecture(facts, convention, None)[
        "adapter_consumability_status"
    ] == "pass"
    pressure = facts["structural_pressures"][0]
    fact_id = pressure["fact_id"]
    pressure_subjects = pressure.get("subjects") or [pressure["subject"]]
    mismatched_axis = _semantic_receipt(row, facts, [fact_id])
    mismatched_axis["assessment"]["findings"][0].update(
        {
            "axis": f"unrelated-{pressure['axis']}",
            "subjects": pressure_subjects,
        }
    )
    mismatched_axis["receipt_sha256"] = object_sha256(
        {
            key: value
            for key, value in mismatched_axis.items()
            if key != "receipt_sha256"
        }
    )

    with pytest.raises(ValueError, match="axis does not match"):
        validate_semantic_receipt(
            mismatched_axis,
            adapter_id=row["adapter_id"],
            adapter_revision_sha256=row["adapter_revision_sha256"],
            convention_sha256=row["code_convention_contract_sha256"],
            fact_packet_sha256=facts["fact_packet_sha256"],
            structural_pressures=facts["structural_pressures"],
        )

    mismatched_subjects = _semantic_receipt(row, facts, [fact_id])
    mismatched_subjects["assessment"]["findings"][0]["subjects"] = [
        "unrelated-subject"
    ]
    mismatched_subjects["receipt_sha256"] = object_sha256(
        {
            key: value
            for key, value in mismatched_subjects.items()
            if key != "receipt_sha256"
        }
    )

    with pytest.raises(ValueError, match="subjects do not match"):
        validate_semantic_receipt(
            mismatched_subjects,
            adapter_id=row["adapter_id"],
            adapter_revision_sha256=row["adapter_revision_sha256"],
            convention_sha256=row["code_convention_contract_sha256"],
            fact_packet_sha256=facts["fact_packet_sha256"],
            structural_pressures=facts["structural_pressures"],
        )


def test_hook_owner_symbol_does_not_resolve_from_another_component(
    tmp_path: Path,
) -> None:
    adapter, helper = _write_v3_adapter(tmp_path)
    adapter.write_text("from helper import quality_vector\n", encoding="utf-8")
    helper.write_text(
        "def quality_vector(value=None):\n"
        "    return {'value': value}\n",
        encoding="utf-8",
    )
    row = _row(tmp_path)

    facts = compile_architecture_facts(tmp_path, row)
    hook = facts["hook_owner_test_mapping"][0]
    convention = json.loads(
        (tmp_path / row["code_convention_contract_path"]).read_text(
            encoding="utf-8"
        )
    )
    result = adjudicate_architecture(facts, convention, None)

    assert hook["owner_component_id"] == "adapter"
    assert hook["owner_component_exists"] is True
    assert hook["owner_symbol_exists"] is False
    assert any(
        item["axis"] == "hook_owner_test_mapping"
        for item in facts["structural_pressures"]
    )
    assert result["adapter_consumability_status"] == "blocked"
    assert result["adapter_architecture_status"] == "blocked"
    assert result["deterministic_blockers"] == [
        {
            "code": "adapter_hook_owner_unresolved",
            "hook_id": "quality_vector",
        }
    ]


@pytest.mark.parametrize(
    "owner_symbol",
    ["Child.render", "facade.Child.render", "adapter.Child.render"],
)
def test_hook_owner_accepts_relative_component_and_module_qualified_nested_symbol(
    tmp_path: Path,
    owner_symbol: str,
) -> None:
    _write_v3_adapter(tmp_path)
    skill = tmp_path / ".codex/skills/example-workflow-adapter"
    manifest_path = skill / "adapter.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["components"][0]["component_id"] = "facade"
    manifest["runtime_closure"]["entry_component_ids"] = ["facade"]
    _write_json(manifest_path, manifest)
    hooks_path = skill / "hook-contracts.json"
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    hooks["hooks"][0]["owner"] = {
        "component_id": "facade",
        "symbol": owner_symbol,
    }
    _write_json(hooks_path, hooks)

    facts = compile_architecture_facts(tmp_path, _row(tmp_path))
    hook = facts["hook_owner_test_mapping"][0]

    assert hook["owner_component_exists"] is True
    assert hook["owner_symbol_exists"] is True


def test_hook_mapping_preserves_missing_component_and_test_dispositions(
    tmp_path: Path,
) -> None:
    _write_v3_adapter(tmp_path)
    row = _row(tmp_path)
    convention = json.loads(
        (tmp_path / row["code_convention_contract_path"]).read_text(
            encoding="utf-8"
        )
    )
    missing_test_row = json.loads(json.dumps(row))
    missing_test_row["hook_contracts"][0]["test_component_ids"] = [
        "missing-test"
    ]

    missing_test_facts = compile_architecture_facts(
        tmp_path, missing_test_row
    )
    missing_test_hook = missing_test_facts["hook_owner_test_mapping"][0]
    missing_test_result = adjudicate_architecture(
        missing_test_facts, convention, None
    )

    assert missing_test_hook["owner_component_exists"] is True
    assert missing_test_hook["owner_symbol_exists"] is True
    assert missing_test_hook["tests_exist"] is False
    assert missing_test_result["adapter_consumability_status"] == "pass"
    assert missing_test_result["adapter_architecture_status"] == "not_evaluated"

    missing_owner_row = json.loads(json.dumps(row))
    missing_owner_row["hook_contracts"][0]["owner"] = {
        "component_id": "missing-component",
        "symbol": "quality_vector",
    }
    missing_owner_facts = compile_architecture_facts(
        tmp_path, missing_owner_row
    )
    missing_owner_hook = missing_owner_facts["hook_owner_test_mapping"][0]
    missing_owner_result = adjudicate_architecture(
        missing_owner_facts, convention, None
    )

    assert missing_owner_hook["owner_component_exists"] is False
    assert missing_owner_hook["owner_symbol_exists"] is False
    assert missing_owner_result["adapter_consumability_status"] == "blocked"
    assert missing_owner_result["adapter_architecture_status"] == "blocked"


def test_cache_and_native_validation_bind_full_revision_closure(tmp_path: Path) -> None:
    _write_v3_adapter(tmp_path)
    row = _row(tmp_path)
    facts = compile_architecture_facts(tmp_path, row)
    convention = json.loads(
        (tmp_path / row["code_convention_contract_path"]).read_text(encoding="utf-8")
    )
    adjudication = adjudicate_architecture(facts, convention, None)
    first = architecture_cache_fingerprint(row, row)
    changed = json.loads(json.dumps(row))
    changed["runtime_closure"]["runtime_closure_sha256"] = "f" * 64
    second = architecture_cache_fingerprint(row, changed)

    assert first != second
    assert adjudication["adapter_architecture_status"] == "not_evaluated"
    packet = build_adapter_validation_packet(
        cycle_id="cycle-v3",
        task_id="task-v3",
        before_row=row,
        after_row=row,
        facts=facts,
        adjudication=adjudication,
        cache_fingerprint=first,
        evidence_paths=[row["manifest_path"]],
    )
    assert packet["adapter_consumability_status"] == "pass"
    assert packet["adapter_architecture_status"] == "not_evaluated"
    assert packet["adapter_validation_status"] == "pass"
    digest = packet.pop("validation_packet_sha256")
    assert digest == object_sha256(packet)


def test_manifest_v2_remains_explicit_legacy_partial(tmp_path: Path) -> None:
    skill = tmp_path / ".codex/skills/legacy-adapter"
    script = skill / "adapter.py"
    script.parent.mkdir(parents=True)
    script.write_text("def hook():\n    return {}\n", encoding="utf-8")
    _write_json(
        skill / "adapter.manifest.json",
        {
            "format_version": 2,
            "adapter_id": "legacy-adapter",
            "status": "active",
            "implementation_path": ".codex/skills/legacy-adapter/adapter.py",
            "not_goal_truth": True,
            "not_validation_evidence": True,
            "required_consumer_ids": ["consumer"],
            "hooks": ["hook"],
            "phase_consumers": {"derive": ["consumer"]},
            "phase_hooks": {"derive": ["hook"]},
        },
    )

    row = scan_repo_skill_adapters(tmp_path)["repo_skill_adapter_packet"]["adapters"][0]

    assert row["static_validation"]["status"] == "pass"
    assert row["manifest_format_version"] == 2
    assert row["manifest_compatibility_status"] == "legacy_partial"
    assert row["runtime_closure"] is None
    assert row["adapter_revision_sha256"]


def test_native_stage_envelopes_validate_integrity_and_preserve_origins(
    tmp_path: Path,
) -> None:
    _write_v3_adapter(tmp_path)
    row = _row(tmp_path)
    facts = compile_architecture_facts(tmp_path, row)
    convention = json.loads(
        (tmp_path / row["code_convention_contract_path"]).read_text(encoding="utf-8")
    )
    adjudication = adjudicate_architecture(facts, convention, None)
    packet = build_adapter_validation_packet(
        cycle_id="cycle-v3",
        task_id="task-v3",
        before_row=row,
        after_row=row,
        facts=facts,
        adjudication=adjudication,
        cache_fingerprint=architecture_cache_fingerprint(row, row),
    )
    normalized = normalize_native_owner_result(
        "repo_skill_adapter_validate",
        packet,
        cycle_id="cycle-v3",
        source_ref=".task/native-adapter-validation.json",
    )
    assert normalized["adapter_architecture_status"] == "not_evaluated"
    assert normalized["field_origins"]["adapter_architecture_status"] == (
        "deterministic_adjudication"
    )
    assert normalized["evidence_paths"] == [
        ".task/native-adapter-validation.json"
    ]

    structure = build_code_structure_packet(
        cycle_id="cycle-v3",
        result={
            "step": "code_structure_audit",
            "task_id": "task-v3",
            "audit_status": "warn",
            "evidence_paths": [],
        },
    )
    normalized_structure = normalize_native_owner_result(
        "code_structure_audit",
        structure,
        cycle_id="cycle-v3",
        source_ref=".task/native-structure.json",
    )
    assert normalized_structure["audit_status"] == "warn"
    assert normalized_structure["field_origins"]["audit_status"] == (
        "deterministic_adjudication"
    )

    tampered = json.loads(json.dumps(packet))
    tampered["adapter_architecture_status"] = "pass"
    with pytest.raises(ValueError, match="packet integrity failed"):
        normalize_native_owner_result(
            "repo_skill_adapter_validate",
            tampered,
            cycle_id="cycle-v3",
            source_ref=".task/native-adapter-validation.json",
        )
