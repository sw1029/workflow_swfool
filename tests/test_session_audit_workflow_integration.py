from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from audit_session_governance import session_audit as audit_producer
from orchestrate_task_cycle import collect_cycle_context as cycle_context
from orchestrate_task_cycle import render_subskill_packet as renderer
from orchestrate_task_cycle.result_contract import api as contracts
from orchestrate_task_cycle.result_contract.legacy_revision_bridge import (
    legacy_revision_bridge_sha256,
)
from validate_task_completion import collect_completion_evidence as completion_evidence


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
    identity = {
        "artifact_id": "artifact-session-A",
        "artifact_class": "session-audit",
        "artifact_sha256": "a" * 64,
        "production_lane_identity": "lane-session-A",
        "discovery_basis": "explicit_artifact_ref",
        "scope_verified": True,
    }
    bridge = {
        "bridge_contract_version": 1,
        "bridge_status": "revision_bound",
        "artifact_id": identity["artifact_id"],
        "artifact_class": identity["artifact_class"],
        "artifact_sha256": identity["artifact_sha256"],
        "revision_id": "revision-session-A",
        "subject_digest": identity["artifact_sha256"],
        "lineage_id": "lineage-session-A",
        "freshness_status": "current",
        "evidence_ref": "session-bridge-evidence-A",
        "evidence_sha256": "e" * 64,
    }
    bridge["receipt_sha256"] = legacy_revision_bridge_sha256(bridge)
    return {
        "step": "validate",
        "task_id": "task-1",
        "validation_verdict": "pass" if complete else "partial",
        "progress_verdict": "advanced" if complete else "partial",
        "decision_contract_version": 0,
        "decision_artifact_ref": identity,
        "legacy_revision_bridge_receipt": bridge,
        "verdict_contract_version": 0,
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


def test_required_audit_accepts_only_collector_verified_source_projection(
    tmp_path: Path,
) -> None:
    source = tmp_path / "logs" / "codex" / "session.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "timestamp": "2026-07-11T01:00:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "private"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    produced, _ = audit_producer.inspect(
        tmp_path,
        source,
        tool="codex",
        cycle_id="cycle-1",
        task_id="task-1",
    )

    direct = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {
            "long_run_state_checked": True,
            "session_audit_required": True,
            "session_audit": produced,
        },
    )
    assert direct["status"] == "block"
    assert "required_session_audit_source_projection_unverified" in codes(direct)

    collection = cycle_context.collect(tmp_path, include_git=False, max_files=12)["session_audit"]
    assert collection["valid_count"] == 1
    verified = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {
            "long_run_state_checked": True,
            "session_audit_required": True,
            "session_audit": collection,
        },
    )
    assert verified["status"] != "block"
    assert "required_session_audit_source_projection_unverified" not in codes(verified)

    self_promoted_result = {
        **validate_payload(),
        "session_audit": collection,
    }
    self_promoted = contracts.validate(
        "validate",
        self_promoted_result,
        "warn",
        {
            "long_run_state_checked": True,
            "session_audit_required": True,
        },
    )
    assert self_promoted["status"] == "block"
    assert "session_audit_collection_projection_untrusted_origin" in codes(
        self_promoted
    )
    assert "required_session_audit_source_projection_unverified" in codes(
        self_promoted
    )


def test_collector_rejects_handcrafted_complete_packet_for_raw_tool_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "logs" / "codex" / "session.jsonl"
    source.parent.mkdir(parents=True)
    source_bytes = (
        json.dumps(
            {
                "timestamp": "2026-07-11T01:00:00Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "private tool payload",
                },
            }
        )
        + "\n"
    ).encode("utf-8")
    source.write_bytes(source_bytes)
    forged = packet(source_bytes=source_bytes)
    audit_dir = tmp_path / ".task" / "session_audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / f"{forged['audit_id']}.json").write_text(
        json.dumps(forged), encoding="utf-8"
    )

    collection = cycle_context.collect(tmp_path, include_git=False, max_files=12)["session_audit"]
    assert collection["valid_count"] == 0
    assert collection["invalid_count"] == 1
    assert "session_audit_source_projection_mismatch" in collection["invalid_packets"][0]["error_codes"]

    required = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {
            "long_run_state_checked": True,
            "session_audit_required": True,
            "session_audit": collection,
        },
    )
    assert required["status"] == "block"
    assert "required_session_audit_not_consumable" in codes(required)


def test_session_packet_cannot_invent_cross_source_close_block(
    tmp_path: Path,
) -> None:
    source = tmp_path / "logs" / "codex" / "session.jsonl"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"")
    canonical_artifact = tmp_path / ".task" / "cycle" / "cycle-1" / "stage.jsonl"
    canonical_artifact.parent.mkdir(parents=True)
    canonical_artifact.write_text('{"step":"validate"}\n', encoding="utf-8")
    invented = packet(
        findings=[
            {
                "code": "invented_relation",
                "severity": "block",
                "message": "session packet claims a semantic mismatch",
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
    audit_dir = tmp_path / ".task" / "session_audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / f"{invented['audit_id']}.json").write_text(
        json.dumps(invented), encoding="utf-8"
    )

    collection = cycle_context.collect(tmp_path, include_git=False, max_files=12)["session_audit"]
    assert collection["valid_count"] == 0
    assert "session_audit_source_projection_mismatch" in collection["invalid_packets"][0]["error_codes"]
    result = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {
            "long_run_state_checked": True,
            "cycle_id": "cycle-1",
            "session_audit": collection,
        },
    )
    assert "session_audit_unresolved_canonical_finding" not in codes(result)
    assert not any(
        finding["severity"] == "block"
        for finding in result["findings"]
        if finding["code"].startswith("session_audit_")
    )


def test_session_owned_findings_remain_advisory_without_comparator_contract(
    tmp_path: Path,
) -> None:
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
    direct = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {"long_run_state_checked": True, "cycle_id": "cycle-1", "session_audit": canonical},
    )
    assert "session_audit_cross_source_claim_routes_review" in codes(direct)
    assert next(
        item
        for item in direct["findings"]
        if item["code"] == "session_audit_cross_source_claim_routes_review"
    )["severity"] == "warn"

    audit_dir = tmp_path / ".task" / "session_audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / f"{canonical['audit_id']}.json").write_text(json.dumps(canonical), encoding="utf-8")
    collection = cycle_context.collect(tmp_path, include_git=False, max_files=12)["session_audit"]
    assert collection["valid_count"] == 0
    assert "session_audit_source_projection_mismatch" in collection["invalid_packets"][0]["error_codes"]
    collected = contracts.validate(
        "validate",
        validate_payload(),
        "warn",
        {
            "long_run_state_checked": True,
            "cycle_id": "cycle-1",
            "session_audit": collection,
        },
    )
    assert collected["status"] != "block"
    assert "session_audit_unresolved_canonical_finding" not in codes(collected)

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
    source = raw_dir / "session.jsonl"
    source.write_text(
        json.dumps(
            {
                "timestamp": "2026-07-11T01:00:00Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": secret},
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
    audit_dir = tmp_path / ".task" / "session_audit"
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
    cycle["session_audit"]["packets"][0]["findings"].append(
        {
            "code": "observation",
            "severity": "warn",
            "message": secret,
            "evidence_class": "transcript_observation",
            "resolved": False,
            "canonical_evidence_ref_hashes": [],
        }
    )
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
