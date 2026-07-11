from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contracts = load_module(
    ROOT / "orchestrate-task-cycle" / "scripts" / "result_contract.py",
    "session_audit_result_contract",
)
cycle_context = load_module(
    ROOT / "orchestrate-task-cycle" / "scripts" / "collect_cycle_context.py",
    "session_audit_cycle_context",
)
completion_evidence = load_module(
    ROOT / "validate-task-completion" / "scripts" / "collect_completion_evidence.py",
    "session_audit_completion_evidence",
)
renderer = load_module(
    ROOT / "orchestrate-task-cycle" / "scripts" / "render_subskill_packet.py",
    "session_audit_packet_renderer",
)
audit_producer = load_module(
    ROOT / "audit-session-governance" / "scripts" / "session_audit.py",
    "session_audit_integration_producer",
)


def packet(
    *,
    capture_status: str = "complete",
    consumable: bool = True,
    findings: list[dict[str, Any]] | None = None,
    source_path: str = "logs/codex/session.jsonl",
    source_bytes: bytes = b"",
) -> dict[str, Any]:
    value = {
        "format_version": 1,
        "artifact_kind": "session_governance_audit",
        "parser_version": "session-audit/1",
        "tool": "codex",
        "session_id": "session-1",
        "source": {
            "path": source_path,
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "size_bytes": len(source_bytes),
        },
        "capture_mode": "conversation_projection",
        "capture_status": capture_status,
        "integrity_status": "source_hash_only",
        "binding": {"status": "bound", "cycle_id": "cycle-1", "task_id": "task-1"},
        "consumable": consumable,
        "not_goal_truth": True,
        "not_validation_evidence": True,
        "repair_class": "none",
        "auto_repair_allowed": False,
        "findings": findings or [],
        "event_counts": {"user": 1, "assistant": 1},
        "timestamp_bounds": {"first": "2026-07-11T00:00:00Z", "last": "2026-07-11T00:01:00Z"},
        "evidence_paths": [source_path],
    }
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    value["audit_id"] = "audit-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return value


def validate_payload(*, complete: bool = True) -> dict[str, Any]:
    return {
        "step": "validate",
        "task_id": "task-1",
        "validation_verdict": "pass" if complete else "partial",
        "progress_verdict": "advanced" if complete else "partial",
        "blockers": [],
        "evidence_paths": ["validation.json"],
        "agent_routing_applicability": "deterministic_only",
    }


def codes(result: dict[str, Any]) -> set[str]:
    return {str(finding.get("code")) for finding in result.get("findings", [])}


def test_invalid_optional_packets_warn_and_required_positive_close_blocks() -> None:
    invalid_flags = packet()
    invalid_flags["not_goal_truth"] = False
    result = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {"long_run_state_checked": True, "session_audit": invalid_flags},
    )
    assert "session_audit_goal_truth_flag_invalid" in codes(result)
    assert next(
        finding for finding in result["findings"] if finding["code"] == "session_audit_goal_truth_flag_invalid"
    )["severity"] == "warn"

    required = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {
            "long_run_state_checked": True,
            "session_audit_required": True,
            "session_audit": invalid_flags,
        },
    )
    assert required["status"] == "block"

    leaked = packet()
    leaked["raw_body"] = "private transcript text"
    result = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {"long_run_state_checked": True, "session_audit": leaked},
    )
    assert "session_audit_body_field_forbidden" in codes(result)
    assert next(
        finding for finding in result["findings"] if finding["code"] == "session_audit_body_field_forbidden"
    )["severity"] == "warn"


def test_only_verified_canonical_block_findings_prevent_positive_close(tmp_path: Path) -> None:
    source = tmp_path / "logs" / "codex" / "session.jsonl"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"")
    canonical_artifact = tmp_path / ".task" / "cycle" / "cycle-1" / "stage.jsonl"
    canonical_artifact.parent.mkdir(parents=True)
    canonical_artifact.write_text('{"step":"validate"}\n', encoding="utf-8")
    canonical = packet(
        findings=[
            {
                "code": "claim_without_evidence",
                "severity": "block",
                "message": "claim conflicts with ledger",
                "evidence_class": "cross_source_mismatch",
                "resolved": False,
                "evidence": {
                    "canonical_evidence_refs": [
                        {
                            "path": ".task/cycle/cycle-1/stage.jsonl",
                            "sha256": hashlib.sha256(canonical_artifact.read_bytes()).hexdigest(),
                            "cycle_id": "cycle-1",
                            "task_id": "task-1",
                        }
                    ]
                },
            }
        ]
    )
    blocked = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {"long_run_state_checked": True, "cycle_id": "cycle-1", "session_audit": canonical},
    )
    assert "session_audit_canonical_finding_not_bound_to_current_close" in codes(blocked)
    assert next(
        item
        for item in blocked["findings"]
        if item["code"] == "session_audit_canonical_finding_not_bound_to_current_close"
    )["severity"] == "warn"

    audit_dir = tmp_path / ".task" / "session_audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / f"{canonical['audit_id']}.json").write_text(json.dumps(canonical), encoding="utf-8")
    verified_collection = cycle_context.collect(tmp_path, include_git=False, max_files=12)["session_audit"]
    assert verified_collection["valid_count"] == 1
    blocked = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {
            "long_run_state_checked": True,
            "cycle_id": "cycle-1",
            "session_audit": verified_collection,
        },
    )
    assert blocked["status"] == "block"
    assert "session_audit_unresolved_canonical_finding" in codes(blocked)

    partial = contracts.validate(
        "validate",
        validate_payload(complete=False),
        "warn",
        {
            "long_run_state_checked": True,
            "cycle_id": "cycle-1",
            "session_audit": verified_collection,
        },
    )
    finding = next(item for item in partial["findings"] if item["code"] == "session_audit_unresolved_canonical_finding")
    assert finding["severity"] == "warn"

    mismatched = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {
            "long_run_state_checked": True,
            "cycle_id": "cycle-other",
            "session_audit": verified_collection,
        },
    )
    mismatch_finding = next(
        item
        for item in mismatched["findings"]
        if item["code"] == "session_audit_canonical_finding_not_bound_to_current_close"
    )
    assert mismatch_finding["severity"] == "warn"

    transcript_only = packet(
        findings=[
            {
                "code": "action_not_mentioned",
                "severity": "block",
                "message": "the transcript did not mention a command",
                "evidence_class": "absence_unknown",
                "resolved": False,
            }
        ]
    )
    routed = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {"long_run_state_checked": True, "session_audit": transcript_only},
    )
    assert "session_audit_observation_routes_review" in codes(routed)
    assert not any(
        finding["severity"] == "block" and finding["code"] == "session_audit_observation_routes_review"
        for finding in routed["findings"]
    )

    report = contracts.validate(
        "report",
        {
            "step": "report",
            "completion_status": "complete_verified",
            "validation_verdict": "passed",
            "progress_verdict": "advanced",
            "blockers": [],
            "commands": ["pytest: passed"],
            "progress_axes": {"behavior": "advanced"},
            "evidence_paths": ["validation.json"],
            "task_id": "task-1",
            "next_task_id": "task-2",
            "selected_task_source": "standalone",
            "closure_steps": ["issue", "derive", "commit", "dashboard"],
            "closure_records": [],
        },
        "warn",
        {"cycle_id": "cycle-1", "session_audit": verified_collection},
    )
    assert "session_audit_unresolved_canonical_finding" in codes(report)
    assert next(
        finding for finding in report["findings"] if finding["code"] == "session_audit_unresolved_canonical_finding"
    )["severity"] == "block"


def test_incomplete_capture_blocks_only_when_caller_requires_it() -> None:
    partial_packet = packet(capture_status="partial", consumable=False)
    optional = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {"long_run_state_checked": True, "session_audit": partial_packet},
    )
    assert "required_session_audit_capture_incomplete" not in codes(optional)

    required = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {"long_run_state_checked": True, "session_audit_required": True, "session_audit": partial_packet},
    )
    assert required["status"] == "block"
    assert "required_session_audit_capture_incomplete" in codes(required)


def test_clean_packet_never_upgrades_validation() -> None:
    result = contracts.validate(
        "validate",
        validate_payload(complete=False),
        "warn",
        {"long_run_state_checked": True, "session_audit": packet()},
    )
    assert result["status"] != "block"
    assert "validation_verdict" not in result
    assert "progress_verdict" not in result


def test_collectors_and_renderer_exclude_raw_logs_and_finding_messages(tmp_path: Path) -> None:
    secret = "SESSION-RAW-SECRET-DO-NOT-COLLECT"
    raw_dir = tmp_path / "logs" / "codex"
    raw_dir.mkdir(parents=True)
    source_bytes = secret.encode("utf-8")
    (raw_dir / "session.jsonl").write_bytes(source_bytes)
    audit_dir = tmp_path / ".task" / "session_audit"
    audit_dir.mkdir(parents=True)
    valid = packet(
        source_bytes=source_bytes,
        findings=[
            {
                "code": "observation",
                "severity": "warn",
                "message": secret,
                "evidence_class": "transcript_observation",
                "resolved": False,
            }
        ]
    )
    (audit_dir / f"{valid['audit_id']}.json").write_text(json.dumps(valid), encoding="utf-8")
    (audit_dir / "broken.json").write_text("{broken", encoding="utf-8")

    cycle = cycle_context.collect(tmp_path, include_git=False, max_files=12)
    completion = completion_evidence.collect(tmp_path, include_git=False, max_files=12)
    for collected in (cycle, completion):
        rendered = json.dumps(collected, sort_keys=True)
        assert secret not in rendered
        assert "logs/codex/session.jsonl" not in rendered
        assert collected["session_audit"]["valid_count"] == 1
        assert collected["session_audit"]["malformed_count"] == 1
        assert collected["session_audit"]["invalid_packets"][0]["contract_status"] == "malformed"

    subskill_packet = renderer.packet_for("validate", cycle, {})
    rendered = json.dumps(subskill_packet, sort_keys=True)
    assert secret not in rendered
    assert subskill_packet["context_counts"]["session_audit_count"] == 1
    assert subskill_packet["session_audit"]["valid_count"] == 1
    assert subskill_packet["session_audit"]["malformed_count"] == 1

    optional_close = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {
            "long_run_state_checked": True,
            "cycle_id": "cycle-1",
            "session_audit": cycle["session_audit"],
        },
    )
    optional_diagnostic = next(
        finding
        for finding in optional_close["findings"]
        if finding["code"] == "session_audit_collection_contains_invalid_packets"
    )
    assert optional_diagnostic["severity"] == "warn"

    truncated = cycle_context.collect(tmp_path, include_git=False, max_files=1)["session_audit"]
    assert truncated["total_packet_count"] == 2
    assert truncated["scanned_packet_count"] == 1
    assert truncated["truncated_count"] == 1
    required_close = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {
            "long_run_state_checked": True,
            "cycle_id": "cycle-1",
            "session_audit_required": True,
            "session_audit": truncated,
        },
    )
    assert next(
        finding for finding in required_close["findings"] if finding["code"] == "session_audit_collection_truncated"
    )["severity"] == "block"

    cycle["session_audit"]["packets"][0]["file"]["raw_body"] = secret
    cycle["session_audit"]["packets"][0]["findings"][0]["message"] = secret
    assert secret not in json.dumps(renderer.packet_for("validate", cycle, {}), sort_keys=True)


def test_validated_derived_index_is_metadata_only_and_fixed_target(tmp_path: Path) -> None:
    source = tmp_path / "logs" / "codex" / "session.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "timestamp": "2026-07-11T01:00:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "private index source"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    audit_producer.inspect(
        tmp_path,
        source,
        tool="codex",
        cycle_id="cycle-1",
        task_id="task-1",
    )
    audit_producer.rebuild_index(tmp_path)

    collection = cycle_context.collect(tmp_path, include_git=False, max_files=12)["session_audit"]
    assert collection["index"]["contract_status"] == "valid"
    assert collection["index"]["repair_class"] == "derived_metadata_only"
    assert collection["index"]["auto_repair_target"] == ".task/session_audit/index.json"
    serialized = json.dumps(collection["index"], sort_keys=True)
    assert "private index source" not in serialized
    assert "entries" not in collection["index"]
    assert "evidence_paths" not in collection["index"]

    forged = json.loads(json.dumps(collection))
    forged["index"]["auto_repair_target"] = "task.md"
    validated = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {"long_run_state_checked": True, "cycle_id": "cycle-1", "session_audit": forged},
    )
    assert "session_audit_index_projection_policy_invalid" in codes(validated)
