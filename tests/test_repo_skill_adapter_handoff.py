from __future__ import annotations

import importlib
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATE_SCRIPTS = ROOT / "orchestrate-task-cycle" / "scripts"
LOOPBACK_SCRIPTS = ROOT / "audit-cycle-loopback" / "scripts"
for path in (ORCHESTRATE_SCRIPTS, LOOPBACK_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


repo_adapter = importlib.import_module("orchestrate_task_cycle.repo_skill_adapter")
result_contract = importlib.import_module("orchestrate_task_cycle.result_contract.api")
adapter_loading = importlib.import_module("audit_cycle_loopback.adapter_loading")
evaluation_frame = importlib.import_module("audit_cycle_loopback.evaluation_frame")
setup_artifact = importlib.import_module(
    "audit_cycle_loopback.evaluation_stages.setup_artifact"
)
setup_adapter = importlib.import_module(
    "audit_cycle_loopback.evaluation_stages.setup_adapter"
)
setup_identity = importlib.import_module(
    "audit_cycle_loopback.evaluation_stages.setup_identity"
)
consumer_context = importlib.import_module("audit_cycle_loopback.consumer_context")
artifact_selection = importlib.import_module("audit_cycle_loopback.artifact_selection")
primary_metric = importlib.import_module("audit_cycle_loopback.primary_metric")
loopback_identity_contract = importlib.import_module(
    "audit_cycle_loopback.decision_identity_dimensions"
)
orchestrate_identity_contract = importlib.import_module(
    "orchestrate_task_cycle.result_contract.decision_identity_dimensions"
)


def _explicit_identity(subject_digest: str, **updates: object) -> dict[str, object]:
    identity: dict[str, object] = {
        "decision_subject_id": "subject-opaque-1",
        "subject_class_id": "class-opaque-1",
        "revision_id": "revision-opaque-1",
        "subject_digest": subject_digest,
        "lineage_id": "lineage-opaque-1",
        "freshness_status": "current",
        "body_fingerprint": {"applicability": "not_applicable", "value": None},
        "production_lane": {"applicability": "not_applicable", "value": None},
        "cohort": {"applicability": "not_applicable", "value": None},
        "producer_run": {"applicability": "not_applicable", "value": None},
    }
    identity.update(updates)
    return identity


def _render_identity_packet(
    root: Path, identity: dict[str, object]
) -> dict[str, object]:
    renderer_path = (
        root
        / ".codex"
        / "skills"
        / "example-workflow-adapter"
        / "scripts"
        / "render_adapter_packet.py"
    )
    if not renderer_path.is_file():
        _write_adapter(root)
    renderer_path.write_text(
        "def render(*, decision_identity=None, **kwargs):\n"
        "    return {'decision_identity': dict(decision_identity or {})}\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location(
        "explicit_forward_renderer", renderer_path
    )
    assert spec is not None and spec.loader is not None
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    return renderer.render(decision_identity=identity)


def _write_adapter(root: Path) -> Path:
    skill = root / ".codex" / "skills" / "example-workflow-adapter"
    scripts = skill / "scripts"
    scripts.mkdir(parents=True)
    task = root / ".task"
    task.mkdir()
    wrapper = scripts / "adapter.py"
    legacy = task / "domain_adapter.py"
    renderer = scripts / "render_adapter_packet.py"
    wrapper.write_text(
        "def quality_vector(**kwargs):\n    return {}\n", encoding="utf-8"
    )
    legacy.write_text(
        "def quality_vector(**kwargs):\n    return {}\n", encoding="utf-8"
    )
    renderer.write_text("def render(**kwargs):\n    return {}\n", encoding="utf-8")
    manifest = {
        "format_version": 2,
        "adapter_id": "example-workflow-adapter",
        "status": "active",
        "implementation_path": ".codex/skills/example-workflow-adapter/scripts/adapter.py",
        "legacy_compatibility_path": ".task/domain_adapter.py",
        "renderer_path": ".codex/skills/example-workflow-adapter/scripts/render_adapter_packet.py",
        "not_goal_truth": True,
        "not_validation_evidence": True,
        "required_consumer_ids": ["audit-cycle-loopback", "derive-improvement-task"],
        "hooks": ["quality_vector", "capability_ladder"],
        "phase_consumers": {
            "loopback_audit": ["audit-cycle-loopback"],
            "derive": ["derive-improvement-task"],
        },
        "phase_hooks": {
            "loopback_audit": ["quality_vector"],
            "derive": ["capability_ladder"],
        },
    }
    (skill / "adapter.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return wrapper


def test_scan_preserves_all_callable_components_and_phase_handoff(
    tmp_path: Path,
) -> None:
    _write_adapter(tmp_path)
    scan = repo_adapter.scan_repo_skill_adapters(tmp_path, cycle_id="cycle-opaque-1")

    assert scan["adapter_scan_status"] == "pass"
    assert scan["adapter_count"] == 1
    row = scan["repo_skill_adapter_packet"]["adapters"][0]
    assert row["static_validation"]["status"] == "pass"
    for path_field, hash_field in (
        ("implementation_path", "implementation_sha256"),
        ("legacy_compatibility_path", "legacy_compatibility_sha256"),
        ("renderer_path", "renderer_sha256"),
        ("manifest_path", "manifest_sha256"),
    ):
        assert row[path_field]
        assert len(row[hash_field]) == 64
    assert row["phase_consumer_map"]["loopback_audit"] == ["audit-cycle-loopback"]
    assert len(row["adapter_revision_sha256"]) == 64


def test_scan_binds_optional_authority_projection_when_declared(
    tmp_path: Path,
) -> None:
    _write_adapter(tmp_path)
    skill = tmp_path / ".codex/skills/example-workflow-adapter"
    projection = skill / "scripts/adapter_authority.py"
    projection.write_text(
        "def authority_axis_classify(**kwargs):\n    return {}\n",
        encoding="utf-8",
    )
    manifest_path = skill / "adapter.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["authority_projection_path"] = (
        ".codex/skills/example-workflow-adapter/scripts/adapter_authority.py"
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    scan = repo_adapter.scan_repo_skill_adapters(tmp_path, cycle_id="cycle-A")
    row = scan["repo_skill_adapter_packet"]["adapters"][0]

    assert row["static_validation"]["status"] == "pass"
    assert row["authority_projection_path"] == manifest["authority_projection_path"]
    assert len(row["authority_projection_sha256"]) == 64
    handoff = repo_adapter.registered_adapter_handoff(
        tmp_path,
        scan,
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )
    assert handoff["status"] == "ready"
    assert handoff["authority_projection_sha256"] == row["authority_projection_sha256"]

    projection.write_text(
        "def authority_axis_classify(**kwargs):\n    return {'changed': True}\n",
        encoding="utf-8",
    )
    stale = repo_adapter.registered_adapter_handoff(
        tmp_path,
        scan,
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )
    assert stale["status"] == "registered_unavailable"
    assert "authority_projection_path" in stale["stale_components"]
    assert "adapter_revision_sha256" in stale["stale_components"]

    refreshed_scan = repo_adapter.scan_repo_skill_adapters(tmp_path, cycle_id="cycle-A")
    handoff = repo_adapter.registered_adapter_handoff(
        tmp_path,
        refreshed_scan,
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )
    assert handoff["status"] == "ready"
    assert handoff["adapter_registered"] is True
    assert handoff["adapter_loaded"] is False
    assert handoff["implementation_path"] == row["implementation_path"]
    assert handoff["authority_granted"] is False


def test_generic_adapter_does_not_require_legacy_delegate_or_renderer(
    tmp_path: Path,
) -> None:
    _write_adapter(tmp_path)
    manifest_path = (
        tmp_path
        / ".codex"
        / "skills"
        / "example-workflow-adapter"
        / "adapter.manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("legacy_compatibility_path")
    manifest.pop("renderer_path")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    scan = repo_adapter.scan_repo_skill_adapters(tmp_path)
    row = scan["repo_skill_adapter_packet"]["adapters"][0]
    handoff = repo_adapter.registered_adapter_handoff(
        tmp_path,
        scan,
        phase="derive",
        consumer_id="derive-improvement-task",
    )

    assert scan["adapter_scan_status"] == "pass"
    assert row["legacy_compatibility_path"] is None
    assert row["renderer_path"] is None
    assert handoff["status"] == "ready"


def test_malformed_phase_consumer_values_fail_static_scan_and_handoff(
    tmp_path: Path,
) -> None:
    _write_adapter(tmp_path)
    manifest_path = (
        tmp_path
        / ".codex"
        / "skills"
        / "example-workflow-adapter"
        / "adapter.manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["phase_consumers"]["derive"] = "derive-improvement-task"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    scan = repo_adapter.scan_repo_skill_adapters(tmp_path)
    handoff = repo_adapter.registered_adapter_handoff(
        tmp_path,
        scan,
        phase="derive",
        consumer_id="derive-improvement-task",
    )

    assert scan["adapter_scan_status"] == "block"
    assert "phase_consumer_registry_invalid" in scan["blockers"][0]["errors"]
    assert handoff["status"] == "invalid_scan"
    assert handoff["classification"] == "adapter_scan_contract_defect"


def test_loopback_consumes_scan_path_and_rejects_stale_registered_adapter(
    tmp_path: Path,
) -> None:
    wrapper = _write_adapter(tmp_path)
    scan = repo_adapter.scan_repo_skill_adapters(tmp_path, cycle_id="cycle-opaque-1")
    encoded = json.dumps(scan)

    ready = adapter_loading.registered_adapter_from_scan(
        tmp_path,
        encoded,
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )
    assert ready["status"] == "ready"
    assert ready["adapter_registered"] is True
    assert Path(ready["implementation_path"]) == wrapper
    assert len(ready["adapter_revision_sha256"]) == 64
    assert ready["required_consumer_ids"] == ["audit-cycle-loopback"]

    wrapper.write_text(
        "def quality_vector(**kwargs):\n    return {'changed': True}\n",
        encoding="utf-8",
    )
    stale = adapter_loading.registered_adapter_from_scan(
        tmp_path,
        encoded,
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )
    assert stale["status"] == "wiring_defect"
    assert stale["adapter_registered"] is True
    assert stale["implementation_path"]
    assert stale["error"].startswith("registered_adapter_unavailable")


def test_registered_adapter_handoff_never_falls_back_to_absence_on_hash_drift(
    tmp_path: Path,
) -> None:
    wrapper = _write_adapter(tmp_path)
    scan = repo_adapter.scan_repo_skill_adapters(tmp_path)
    wrapper.write_text("raise RuntimeError('changed')\n", encoding="utf-8")

    handoff = repo_adapter.registered_adapter_handoff(
        tmp_path,
        scan,
        phase="derive",
        consumer_id="derive-improvement-task",
    )
    assert handoff["status"] == "registered_unavailable"
    assert handoff["adapter_registered"] is True
    assert handoff["adapter_loaded"] is False
    assert handoff["classification"] == "adapter_wiring_defect"
    assert "implementation_path" in handoff["stale_components"]
    assert "adapter_revision_sha256" in handoff["stale_components"]


def test_consumer_declaration_uses_scan_and_explicit_legacy_modes() -> None:
    from_ready = setup_identity._adapter_consumer_declaration(
        {
            "status": "ready",
            "required_consumer_ids": ["audit-cycle-loopback"],
        },
        adapter_registered=True,
        consumer_id="audit-cycle-loopback",
        scan_supplied=True,
    )
    explicit_legacy = setup_identity._adapter_consumer_declaration(
        {"status": "not_supplied"},
        adapter_registered=True,
        consumer_id="audit-cycle-loopback",
        scan_supplied=False,
    )
    invalid_scan = setup_identity._adapter_consumer_declaration(
        {"status": "invalid_scan"},
        adapter_registered=False,
        consumer_id="audit-cycle-loopback",
        scan_supplied=True,
    )

    assert from_ready == (["audit-cycle-loopback"], "manifest_v2")
    assert explicit_legacy == (
        ["audit-cycle-loopback"],
        "legacy_explicit_adapter",
    )
    assert invalid_scan == (["audit-cycle-loopback"], "scan_unavailable")


def test_loopback_setup_loads_the_explicit_registered_wrapper(tmp_path: Path) -> None:
    wrapper = _write_adapter(tmp_path)
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    scan = repo_adapter.scan_repo_skill_adapters(tmp_path)
    args = argparse.Namespace(
        artifact_paths_json=None,
        artifact_path=["artifact.json"],
        artifact_ref_json=None,
        artifact_family="opaque-family",
        changed_files_json=None,
        changed_file=[],
        domain_adapter=None,
        adapter_scan_json=json.dumps(scan),
    )
    frame = evaluation_frame._EvaluationFrame({"args": args, "root": tmp_path})

    setup_artifact._prepare_artifact_state(frame)
    state = frame.snapshot()
    assert state["adapter_registered"] is True
    assert state["domain_adapter"] is not None
    assert Path(state["domain_adapter_path"]) == wrapper
    assert state["adapter_scan_handoff"]["status"] == "ready"
    assert (
        state["adapter_revision_sha256"]
        == scan["repo_skill_adapter_packet"]["adapters"][0]["adapter_revision_sha256"]
    )

    setup_adapter._prepare_adapter_state(frame)
    gate = frame.snapshot()["adapter_load_gate"]
    assert gate["adapter_registered"] is True
    assert gate["adapter_loaded"] is True
    assert gate["adapter_wiring_defect"] is False


def test_python_adapter_loader_restores_prior_registry_entry_on_failure(
    tmp_path: Path,
) -> None:
    failing = tmp_path / "failing_adapter.py"
    failing.write_text(
        "import sys\n"
        "assert sys.modules[__name__] is not None\n"
        "raise RuntimeError('adapter import failed')\n",
        encoding="utf-8",
    )
    module_name = "failing_repo_adapter_registry_contract"
    original = sys.modules.get(module_name)
    prior = ModuleType(module_name)
    try:
        sys.modules[module_name] = prior
        try:
            adapter_loading.load_python_module(failing, module_name)
        except RuntimeError:
            pass
        else:
            raise AssertionError("failing adapter import unexpectedly succeeded")
        assert sys.modules[module_name] is prior

        sys.modules.pop(module_name, None)
        try:
            adapter_loading.load_python_module(failing, module_name)
        except RuntimeError:
            pass
        else:
            raise AssertionError("failing adapter import unexpectedly succeeded")
        assert module_name not in sys.modules
    finally:
        sys.modules.pop(module_name, None)
        if original is not None:
            sys.modules[module_name] = original


def test_loopback_setup_classifies_registered_unloaded_as_wiring_defect(
    tmp_path: Path,
) -> None:
    wrapper = _write_adapter(tmp_path)
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}\n", encoding="utf-8")
    scan = repo_adapter.scan_repo_skill_adapters(tmp_path)
    wrapper.write_text("raise RuntimeError('stale')\n", encoding="utf-8")
    args = argparse.Namespace(
        artifact_paths_json=None,
        artifact_path=["artifact.json"],
        artifact_ref_json=None,
        artifact_family="opaque-family",
        changed_files_json=None,
        changed_file=[],
        domain_adapter=None,
        adapter_scan_json=json.dumps(scan),
    )
    frame = evaluation_frame._EvaluationFrame({"args": args, "root": tmp_path})

    setup_artifact._prepare_artifact_state(frame)
    assert frame.snapshot()["adapter_registered"] is True
    assert frame.snapshot()["domain_adapter"] is None
    setup_adapter._prepare_adapter_state(frame)
    gate = frame.snapshot()["adapter_load_gate"]
    assert gate["adapter_loaded"] is False
    assert gate["adapter_wiring_defect"] is True
    assert gate["recommended_disposition"] == "self_inflicted_gate_defect"


def test_post_use_consumer_receipt_binds_task_and_adapter_revision() -> None:
    artifact_ref = {
        "artifact_id": "artifact-opaque-1",
        "artifact_sha256": "a" * 64,
        "production_lane_identity": "lane-opaque-1",
        "body_projection_fingerprint": "b" * 64,
        "verification_input_ids": ["input-opaque-1"],
    }
    row = {
        "consumer_context_id": "audit-cycle-loopback",
        "hook_id": "quality_vector",
        "cycle_id": "cycle-opaque-1",
        "task_id": "task-opaque-1",
        "attempt_identity": "attempt-opaque-1",
        "input_state_fingerprint": "c" * 64,
        "adapter_revision_sha256": "d" * 64,
        **artifact_ref,
        "adapter_loaded": True,
        "hook_resolved": True,
        "required_hook_callable": True,
        "hook_signature_compatible": True,
        "invocation_completed": True,
        "return_contract_valid": True,
        "artifact_identity_echo_valid": True,
        "value_consumed_by_decision": True,
        "evidence_provenance": "self_grounded",
        "probe_evidence_ref": "packet:opaque-probe-1",
    }
    row["probe_evidence_sha256"] = consumer_context.consumer_receipt_binding_sha256(row)
    assert row[
        "probe_evidence_sha256"
    ] == result_contract._consumer_receipt_binding_sha256(row)
    row["probe_evidence_id"] = "probe-" + row["probe_evidence_sha256"][:16]
    valid = consumer_context.consumer_context_conformance_gate(
        {
            "required_consumer_ids": ["audit-cycle-loopback"],
            "consumer_context_conformance": {"rows": [row]},
        },
        expected_artifact_ref=artifact_ref,
        expected_cycle_id="cycle-opaque-1",
        expected_task_id="task-opaque-1",
        expected_attempt_identity="attempt-opaque-1",
        expected_input_state_fingerprint="c" * 64,
        expected_adapter_revision_sha256="d" * 64,
    )
    assert valid["status"] == "pass"

    stale = {**row, "adapter_revision_sha256": "e" * 64}
    stale["probe_evidence_sha256"] = consumer_context.consumer_receipt_binding_sha256(
        stale
    )
    stale["probe_evidence_id"] = "probe-" + stale["probe_evidence_sha256"][:16]
    invalid = consumer_context.consumer_context_conformance_gate(
        {
            "required_consumer_ids": ["audit-cycle-loopback"],
            "consumer_context_conformance": {"rows": [stale]},
        },
        expected_artifact_ref=artifact_ref,
        expected_cycle_id="cycle-opaque-1",
        expected_task_id="task-opaque-1",
        expected_attempt_identity="attempt-opaque-1",
        expected_input_state_fingerprint="c" * 64,
        expected_adapter_revision_sha256="d" * 64,
    )
    assert invalid["status"] == "not_evaluated"
    assert invalid["missing_consumer_context_ids"] == ["audit-cycle-loopback"]


def test_handoff_rejects_a_tampered_phase_consumer_map(tmp_path: Path) -> None:
    _write_adapter(tmp_path)
    scan = repo_adapter.scan_repo_skill_adapters(tmp_path)
    row = scan["repo_skill_adapter_packet"]["adapters"][0]
    row["phase_consumer_map"]["derive"] = [
        "derive-improvement-task",
        "unexpected-consumer",
    ]

    handoff = repo_adapter.registered_adapter_handoff(
        tmp_path,
        scan,
        phase="derive",
        consumer_id="unexpected-consumer",
    )
    assert handoff["status"] == "registered_unavailable"
    assert handoff["classification"] == "adapter_wiring_defect"
    assert "phase_consumer_map" in handoff["stale_components"]


def test_validator_component_is_revision_bound_and_tamper_blocks_handoff(
    tmp_path: Path,
) -> None:
    _write_adapter(tmp_path)
    skill = tmp_path / ".codex" / "skills" / "example-workflow-adapter"
    validator = skill / "scripts" / "decision_identity.py"
    validator.write_text("def validate(value):\n    return value\n", encoding="utf-8")
    manifest_path = skill / "adapter.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["decision_identity_validator_path"] = validator.relative_to(
        tmp_path
    ).as_posix()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    scan = repo_adapter.scan_repo_skill_adapters(tmp_path)
    row = scan["repo_skill_adapter_packet"]["adapters"][0]
    original_revision = row["adapter_revision_sha256"]
    assert (
        row["decision_identity_validator_sha256"]
        == hashlib.sha256(validator.read_bytes()).hexdigest()
    )

    validator.write_text("def validate(value):\n    return None\n", encoding="utf-8")
    rejected = repo_adapter.registered_adapter_handoff(
        tmp_path,
        scan,
        phase="loopback_audit",
        consumer_id="audit-cycle-loopback",
    )
    rescanned = repo_adapter.scan_repo_skill_adapters(tmp_path)

    assert rejected["status"] == "registered_unavailable"
    assert "decision_identity_validator_path" in rejected["stale_components"]
    assert (
        rescanned["repo_skill_adapter_packet"]["adapters"][0]["adapter_revision_sha256"]
        != original_revision
    )


def test_renderer_to_loopback_preserves_all_na_explicit_identity(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact-opaque.json"
    artifact.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    identity = _explicit_identity(digest)
    rendered = _render_identity_packet(tmp_path, identity)

    paths, selected = artifact_selection.load_artifact_selection(
        tmp_path,
        None,
        [artifact.name],
        artifact_ref_json=json.dumps(rendered),
        artifact_family="class-opaque-1",
    )

    assert paths == [artifact]
    assert selected["scope_verified"] is True
    assert selected["decision_identity_kind"] == "explicit_v2"
    for field in (
        "decision_subject_id",
        "subject_class_id",
        "revision_id",
        "subject_digest",
        "lineage_id",
        "freshness_status",
        "body_fingerprint",
        "production_lane",
        "cohort",
        "producer_run",
    ):
        assert selected[field] == identity[field]
    assert selected["decision_identity_echo"]["dimension_values"] == {}
    assert selected["decision_identity"] == identity
    assert selected["body_projection_fingerprint"] is None
    assert selected["production_lane_identity"] is None
    assert selected["verification_input_ids"] is None
    assert selected["producer_run_id"] is None

    metric_source = {
        "decision_identity_echo": selected["decision_identity_echo"],
    }
    assert primary_metric.primary_metric_artifact_binding(metric_source, selected) == (
        True,
        [],
    )

    receipt = {
        "consumer_context_id": "audit-cycle-loopback",
        "hook_id": "quality_vector",
        "cycle_id": "cycle-opaque-1",
        "task_id": "task-opaque-1",
        "attempt_identity": "attempt-opaque-1",
        "input_state_fingerprint": "c" * 64,
        "adapter_revision_sha256": "d" * 64,
        "decision_identity_echo": selected["decision_identity_echo"],
        "adapter_loaded": True,
        "hook_resolved": True,
        "required_hook_callable": True,
        "hook_signature_compatible": True,
        "invocation_completed": True,
        "return_contract_valid": True,
        "artifact_identity_echo_valid": True,
        "value_consumed_by_decision": True,
        "evidence_provenance": "self_grounded",
        "probe_evidence_ref": "packet:explicit-forward-probe",
    }
    receipt["probe_evidence_sha256"] = consumer_context.consumer_receipt_binding_sha256(
        receipt
    )
    gate = consumer_context.consumer_context_conformance_gate(
        {
            "required_consumer_ids": ["audit-cycle-loopback"],
            "consumer_context_conformance": {"rows": [receipt]},
        },
        expected_artifact_ref=selected,
        expected_cycle_id="cycle-opaque-1",
        expected_task_id="task-opaque-1",
        expected_attempt_identity="attempt-opaque-1",
        expected_input_state_fingerprint="c" * 64,
        expected_adapter_revision_sha256="d" * 64,
    )
    assert gate["status"] == "pass"
    assert (
        gate["rows"][0]["decision_identity_echo"] == selected["decision_identity_echo"]
    )


def test_loopback_and_orchestration_share_the_same_explicit_identity_projection() -> (
    None
):
    assert (
        loopback_identity_contract.CONTRACT_SPEC_SHA256
        == orchestrate_identity_contract.CONTRACT_SPEC_SHA256
    )
    identity = _explicit_identity(
        "a" * 64,
        body_fingerprint={"applicability": "applicable", "value": "b" * 64},
        cohort={"applicability": "applicable", "value": ["cohort-opaque-1"]},
    )
    missing_dimension = {
        key: value for key, value in identity.items() if key != "producer_run"
    }
    dimension_extra = {
        **identity,
        "cohort": {**identity["cohort"], "raw_source": "forbidden"},
    }
    cases = (
        identity,
        missing_dimension,
        {**identity, "freshness_status": "stale"},
        {**identity, "raw_source": "forbidden"},
        dimension_extra,
        {**identity, "decision_subject_id": "subject / raw"},
        {**identity, "lineage_id": "source.json"},
    )
    for value in cases:
        loopback = loopback_identity_contract.parse_decision_identity(value)
        orchestrated = orchestrate_identity_contract.parse_decision_identity(value)
        assert loopback.explicit == orchestrated.explicit
        assert loopback.subject_values == orchestrated.subject_values
        assert loopback.dimension_statuses == orchestrated.dimension_statuses
        assert loopback.dimension_values == orchestrated.dimension_values
        assert loopback.issues == orchestrated.issues

    envelope = {"scope_verified": True, "decision_identity": identity}
    loopback_envelope = loopback_identity_contract.parse_decision_identity(envelope)
    orchestrated_envelope = orchestrate_identity_contract.parse_decision_identity(
        envelope
    )
    assert loopback_envelope.explicit is True
    assert loopback_envelope.issues == orchestrated_envelope.issues == ()
    unknown_wrapper = {**envelope, "raw_source": "forbidden"}
    assert "identity.envelope_closed_schema" in (
        loopback_identity_contract.parse_decision_identity(unknown_wrapper).issues
    )
    extracted = orchestrate_identity_contract.explicit_identity_object(envelope)
    assert extracted == identity
    assert not orchestrate_identity_contract.parse_decision_identity(extracted).issues


def test_loopback_explicit_identity_fails_closed_on_stale_missing_and_hash_drift(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact-opaque.json"
    artifact.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    cases = (
        _explicit_identity(digest, freshness_status="stale"),
        {
            key: value
            for key, value in _explicit_identity(digest).items()
            if key != "producer_run"
        },
        _explicit_identity("f" * 64),
    )

    for identity in cases:
        rendered = _render_identity_packet(tmp_path, identity)
        _, selected = artifact_selection.load_artifact_selection(
            tmp_path,
            None,
            [artifact.name],
            artifact_ref_json=json.dumps(rendered),
            artifact_family="class-opaque-1",
        )
        assert selected["scope_verified"] is False
        assert selected["advisory_discovery"] is True
        assert selected["identity_status"] != "verified"


def test_explicit_applicable_dimensions_require_exact_echo_and_reject_na_overecho(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact-opaque.json"
    artifact.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    applicable = _explicit_identity(
        digest,
        body_fingerprint={"applicability": "applicable", "value": "b" * 64},
        production_lane={"applicability": "applicable", "value": "lane-opaque-1"},
        cohort={"applicability": "applicable", "value": ["cohort-opaque-1"]},
        producer_run={"applicability": "applicable", "value": "run-opaque-1"},
    )
    rendered = _render_identity_packet(tmp_path, applicable)
    _, selected = artifact_selection.load_artifact_selection(
        tmp_path,
        None,
        [artifact.name],
        artifact_ref_json=json.dumps(rendered),
        artifact_family="class-opaque-1",
    )
    exact = {"decision_identity_echo": selected["decision_identity_echo"]}
    assert primary_metric.primary_metric_artifact_binding(exact, selected) == (True, [])

    omitted = json.loads(json.dumps(exact))
    del omitted["decision_identity_echo"]["dimension_values"]["producer_run"]
    exact_binding, omitted_fields = primary_metric.primary_metric_artifact_binding(
        omitted, selected
    )
    assert exact_binding is False
    assert "dimension_values" in omitted_fields

    all_na = _explicit_identity(digest)
    rendered_na = _render_identity_packet(tmp_path, all_na)
    _, selected_na = artifact_selection.load_artifact_selection(
        tmp_path,
        None,
        [artifact.name],
        artifact_ref_json=json.dumps(rendered_na),
        artifact_family="class-opaque-1",
    )
    overecho = json.loads(json.dumps(selected_na["decision_identity_echo"]))
    overecho["dimension_values"]["body_fingerprint"] = "b" * 64
    exact_binding, overecho_fields = primary_metric.primary_metric_artifact_binding(
        {"decision_identity_echo": overecho}, selected_na
    )
    assert exact_binding is False
    assert "dimension_values" in overecho_fields

    legacy_alias_overecho = {
        "decision_identity_echo": selected_na["decision_identity_echo"],
        "body_projection_fingerprint": "b" * 64,
    }
    exact_binding, alias_fields = primary_metric.primary_metric_artifact_binding(
        legacy_alias_overecho,
        selected_na,
    )
    assert exact_binding is False
    assert "body_fingerprint.nonapplicable_alias" in alias_fields
