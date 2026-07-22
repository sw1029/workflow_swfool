"""Integrity-bound native deterministic result envelopes."""

from __future__ import annotations

from typing import Any, Iterable

from .contracts import object_sha256


def _finish(packet: dict[str, Any], field: str) -> dict[str, Any]:
    packet[field] = object_sha256(packet)
    return packet


def build_adapter_validation_packet(
    *,
    cycle_id: str,
    task_id: str | None,
    before_row: dict[str, Any] | None,
    after_row: dict[str, Any],
    facts: dict[str, Any],
    adjudication: dict[str, Any],
    cache_fingerprint: str,
    evidence_paths: Iterable[str] = (),
) -> dict[str, Any]:
    blockers = list(adjudication.get("deterministic_blockers") or [])
    static_status = (after_row.get("static_validation") or {}).get("status")
    if static_status != "pass":
        blockers.append(
            {
                "code": "repo_skill_adapter_static_validation_failed",
                "errors": list((after_row.get("static_validation") or {}).get("errors") or []),
            }
        )
    packet = {
        "schema_version": 2,
        "artifact_kind": "repo_skill_adapter_validation_packet",
        "step": "repo_skill_adapter_validate",
        "cycle_id": cycle_id,
        "task_id": task_id,
        "adapter_validation_status": "block" if blockers else "pass",
        "adapter_consumability_status": adjudication.get(
            "adapter_consumability_status"
        ),
        "adapter_architecture_status": adjudication.get(
            "adapter_architecture_status"
        ),
        "adapter_change_count": int(
            not isinstance(before_row, dict)
            or before_row.get("adapter_revision_sha256")
            != after_row.get("adapter_revision_sha256")
        ),
        "adapter_validation_count": 1,
        "adapter_revision_before_sha256": before_row.get("adapter_revision_sha256")
        if isinstance(before_row, dict)
        else None,
        "adapter_revision_after_sha256": after_row.get("adapter_revision_sha256"),
        "adapter_architecture": {
            "fact_packet_sha256": facts.get("fact_packet_sha256"),
            "coverage": facts.get("coverage"),
            "adjudication": adjudication,
            "cache_fingerprint": cache_fingerprint,
            "raw_source_persisted": False,
        },
        "field_origins": {
            "adapter_validation_status": "deterministic_adjudication",
            "adapter_consumability_status": "deterministic_adjudication",
            "adapter_architecture_status": "deterministic_adjudication",
            "adapter_architecture": "deterministic_fact",
            "cache_fingerprint": "deterministic_fact",
        },
        "blockers": blockers,
        "evidence_paths": sorted(set(evidence_paths)),
    }
    return _finish(packet, "validation_packet_sha256")


def build_code_structure_packet(
    *,
    cycle_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    packet = {
        "schema_version": 2,
        "artifact_kind": "code_structure_audit_packet",
        "step": "code_structure_audit",
        "cycle_id": cycle_id,
        "result": dict(result),
        "field_origins": {
            "audit_status": "deterministic_adjudication",
            "semantic_structure_metrics": "deterministic_fact",
            "semantic_structure_findings": "deterministic_adjudication",
            "convention_conformance": "repo_policy",
            "semantic_refactor_plan": "semantic_receipt",
        },
    }
    return _finish(packet, "audit_packet_sha256")


__all__ = ("build_adapter_validation_packet", "build_code_structure_packet")
