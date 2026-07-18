from __future__ import annotations

from typing import Any
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
from .common import (
    DOMAIN_ADAPTER_ENV,
    REGISTRY_REL_PATH,
    ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT,
    ROOT_CAUSE_LEDGER_REL_PATH,
)
from . import evaluator as _evaluator
from . import io_utils as _io_utils
from . import registry as _registry
from . import values as _values
from .recurrence_identity import evaluate_recurrence_identity


def _operation_builders() -> tuple[Any | None, Any | None]:
    """Load mutation builders only when a mutation candidate is requested."""
    try:
        from orchestrate_task_cycle.ledger.operation_contract import (
            build_durable_operation,
            build_typed_operations_candidate,
        )
    except ImportError:
        return None, None
    return build_durable_operation, build_typed_operations_candidate


def _packet_progress_verdict(packet: dict[str, Any]) -> str:
    if not _values.bool_value(packet.get("scope_verified")) or str(packet.get("evidence_class") or "") == "not_evaluated":
        return "not_evaluated"
    if _values.bool_value(packet.get("authoritative_semantic_progress")):
        return "advanced"
    if _values.bool_value(packet.get("hard_stop_required")):
        return "blocked"
    return "stalled"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_handoff(packet: dict[str, Any], root: Path, output: Path | None) -> dict[str, Any]:
    if output is None:
        return {
            "handoff_contract_version": 1,
            "applicability": "missing_required",
            "applicability_reason": "loopback_packet_not_durably_written",
        }
    compatibility_rows = [
        row for row in packet.get("gate_compatibility_results") or [] if isinstance(row, dict)
    ]
    compatible_ids = sorted(
        str(row.get("gate_id"))
        for row in compatibility_rows
        if row.get("gate_id") and row.get("gate_compatibility_status") == "compatible"
    )
    incompatible_ids = sorted(
        str(row.get("gate_id"))
        for row in compatibility_rows
        if row.get("gate_id") and row.get("gate_compatibility_status") != "compatible"
    )
    return {
        "handoff_contract_version": 1,
        "applicability": "required",
        "finalization_required": True,
        "authoritative_consumption_allowed": False,
        "packet_ref": _io_utils.rel_path(root, output),
        "packet_sha256": _file_sha256(output),
        "artifact_id": packet.get("artifact_id"),
        "artifact_sha256": packet.get("artifact_sha256"),
        "artifact_family": packet.get("artifact_family"),
        "blocker_signature": packet.get("blocker_signature"),
        "progress_verdict": packet.get("progress_verdict"),
        "hard_stop": _values.bool_value(packet.get("hard_stop_required")),
        "terminal_state": packet.get("recommended_disposition"),
        "allowed_next_action_classes": packet.get("allowed_next_action_classes") or [],
        "compatible_gate_ids": compatible_ids,
        "incompatible_gate_ids": incompatible_ids,
        "durable_mutation_candidate_sha256": (
            packet.get("durable_mutation_candidate") or {}
        ).get("candidate_sha256"),
    }


def _build_durable_mutation_candidate(
    packet: dict[str, Any],
    registry_rows: list[dict[str, Any]],
    *,
    legacy_write_requested: bool,
) -> dict[str, Any]:
    build_durable_operation, build_typed_operations_candidate = _operation_builders()
    if build_durable_operation is None or build_typed_operations_candidate is None:
        return {
            "contract_version": 2,
            "status": "unavailable",
            "producer": "audit-cycle-loopback",
            "attempt_identity": str(packet.get("attempt_identity") or ""),
            "operations": [],
            "authoritative_consumption_allowed": False,
            "findings": ["typed_operation_builder_unavailable"],
            "legacy_write_requested": legacy_write_requested,
        }
    registry_payload = {
        "rows": [
            _registry.bounded_durable_projection(row)
            for row in registry_rows
            if isinstance(row, dict)
        ]
    }
    ledger_payload = {
        "rows": [
            _registry.bounded_durable_projection(row)
            for row in packet.get("root_cause_ledger_projection") or []
            if isinstance(row, dict)
        ]
    }
    seal_projection = packet.get("sealed_blocker_families_projection")
    seal_projection_is_valid = bool(
        isinstance(seal_projection, dict)
        and seal_projection.get("schema_version") == "sealed-blocker-families-v1"
        and isinstance(seal_projection.get("families"), list)
    )
    seal_payload = {
        "state": _registry.bounded_durable_projection(seal_projection)
        if seal_projection_is_valid
        else {"schema_version": "sealed-blocker-families-v1", "families": []}
    }
    attempt_identity = str(packet.get("attempt_identity") or "")
    prior_revisions = (
        packet.get("target_revision_ids")
        if isinstance(packet.get("target_revision_ids"), dict)
        else {}
    )
    mutations: list[dict[str, Any]] = []
    for target_ref, schema_id, payload in (
        ("family_progress_registry", "family-progress-registry-v1", registry_payload),
        ("root_cause_ledger", "root-cause-ledger-v1", ledger_payload),
        ("sealed_blocker_families", "sealed-blocker-families-v1", seal_payload),
    ):
        dependencies = [mutations[-1]["operation_id"]] if mutations else []
        mutations.append(
            build_durable_operation(
                target_ref=target_ref,
                operation_kind="replace_projection",
                attempt_identity=attempt_identity,
                payload_schema_id=schema_id,
                payload=payload,
                expected_revision_id=prior_revisions.get(target_ref),
                depends_on_operation_ids=dependencies,
            )
        )
    recurrence_identity = packet.get("recurrence_identity")
    if (
        isinstance(recurrence_identity, dict)
        and recurrence_identity.get("durable_update_required") is True
        and isinstance(recurrence_identity.get("projection"), dict)
    ):
        recurrence_payload = {"state": recurrence_identity["projection"]}
        mutations.append(
            build_durable_operation(
                target_ref="recurrence_identity",
                operation_kind="replace_projection",
                attempt_identity=attempt_identity,
                payload_schema_id="recurrence-identity-v1",
                payload=recurrence_payload,
                expected_revision_id=prior_revisions.get("recurrence_identity"),
                depends_on_operation_ids=[mutations[-1]["operation_id"]],
            )
        )
    return build_typed_operations_candidate(
        producer="audit-cycle-loopback",
        attempt_identity=attempt_identity,
        operations=mutations,
    )


def _write_candidate_packet(path: Path, packet: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute a conservative anti-loop progress gate packet.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument(
        "--finalized-cycle-id",
        help="Cycle whose helper-verified current finalization supplies prior registry/ledger/seal projections; defaults to --cycle-id.",
    )
    parser.add_argument("--task-id", default="unknown")
    parser.add_argument("--artifact-family", default="unknown")
    parser.add_argument("--semantic-signature", default="unknown")
    parser.add_argument("--root-key", help="Suffix-normalized root key for measurement cap and loop comparison.")
    parser.add_argument("--domain-adapter", help=f"Path to a repository domain adapter module; defaults to ${DOMAIN_ADAPTER_ENV} when set.")
    parser.add_argument("--adapter-scan-json", help="Path or JSON object from orchestrate-task-cycle repo-adapter scan; the registered loopback wrapper is handed off explicitly.")
    parser.add_argument("--provider-request-count", type=int, default=0)
    parser.add_argument("--artifact-path", action="append", default=[])
    parser.add_argument("--artifact-paths-json")
    parser.add_argument("--artifact-ref-json", help="Path or JSON object containing the exact decision artifact identity, hash, class, lane, and discovery basis.")
    parser.add_argument("--changed-file", action="append", default=[], help="Changed repository file path used for verifier-source coupling checks.")
    parser.add_argument("--changed-files-json", help="Path or JSON list/dict of changed repository files for verifier-source coupling checks.")
    parser.add_argument("--gate-state-json", action="append", default=[], help="Path or JSON containing disposition gates from loop detection or portfolio planning.")
    parser.add_argument("--recent-progress-json", help="Path or JSON containing recent progress items for consolidation-streak calculation.")
    parser.add_argument("--runner-validation-json", help="Path or JSON for strict runner validation, used only to detect semantic-progress disagreement.")
    parser.add_argument("--output-delta-json", help="Path or JSON for output-delta packet, used only to detect semantic-progress disagreement.")
    parser.add_argument("--failure-autopsy-json", action="append", default=[], help="Path or JSON for scalar-safe failure autopsy packets from run-task-code-and-log.")
    parser.add_argument("--substance-metrics-json", help="Path or JSON object with adapter-compatible substance_metrics/current_substance_vector values.")
    parser.add_argument("--corrective-resolution-json", help="Path or JSON with corrective lane attempted/resolved counts.")
    parser.add_argument("--facet-root-map-json", help="Path or JSON mapping facet labels to root families.")
    parser.add_argument(
        "--recurrence-identity-json",
        help="Path or JSON object with caller-owned stable-root, facet, local-family, delta, and lineage recurrence state.",
    )
    parser.add_argument("--acceptance-reachability-json", help="Path or JSON object with acceptance_min_output, frozen_envelope, and optional reachability_verdict.")
    parser.add_argument("--metric-validity-json", help="Path or JSON object/list from an oracle or metric validity self-check.")
    parser.add_argument("--root-cause-hypotheses-json", help="Path or JSON list/dict of root-cause hypotheses for the generic root-cause ledger.")
    parser.add_argument("--hypothesized-root-cause", help="Single root-cause hypothesis slug to record when no JSON/adapter list is supplied.")
    parser.add_argument("--root-cause-repair-attempted", action="store_true", help="Mark the supplied root-cause hypothesis as explicitly attempted by this cycle.")
    parser.add_argument("--root-cause-repair-task-id", help="Task id for the repair attempt targeting the supplied root-cause hypothesis.")
    parser.add_argument("--root-cause-actionable", action="store_true", help="Assert the supplied root-cause hypothesis is actionable; untried promotion still requires structural fields or provenance evidence.")
    parser.add_argument("--untried-promotion-budget", type=int, help="Repository-supplied same-family vacuous-repair budget; absent means budget_unverified and cannot exhaust the family.")
    parser.add_argument("--measurement-check-id", action="append", default=[], help="Stable check/oracle ID introduced or exercised by this cycle.")
    parser.add_argument("--measurement-check-ids-json", help="Path or JSON list/dict containing check or oracle IDs.")
    parser.add_argument("--measurement-frontier", action="append", default=[], help="Named measurement frontier observed by this cycle.")
    parser.add_argument("--measurement-streak-cap", type=int, help="Repository-supplied measurement/nonsemantic budget.")
    parser.add_argument("--detection-only-streak-cap", type=int, help="Repository-supplied detection-only budget.")
    parser.add_argument("--adapter-mandate-streak-cap", type=int, help="Repository-supplied adapter-mandate budget.")
    parser.add_argument("--cumulative-chain-streak-cap", type=int, help="Repository-supplied cumulative stall budget.")
    parser.add_argument("--instrumentation-trigger-threshold", type=int, help="Caller/config instrumentation-attempt budget; an adapter hook may override it.")
    parser.add_argument("--envelope-thaw-streak-cap", type=int, help="Repository-supplied envelope-thaw omission budget.")
    parser.add_argument("--blocker-signature", help="Stable current blocker signature before suffix normalization.")
    parser.add_argument("--blocker-rung", help="Current capability-ladder rung for the blocker family.")
    parser.add_argument("--max-forward-mutations", type=int, help="Repository-supplied forward-mutation attempt budget.")
    parser.add_argument("--consolidation-streak-cap", type=int, help="Repository-supplied governance-only consolidation budget.")
    parser.add_argument("--registry-path", default=REGISTRY_REL_PATH)
    parser.add_argument("--root-cause-ledger-path", default=ROOT_CAUSE_LEDGER_REL_PATH)
    parser.add_argument("--threshold", type=int, help="Repository-supplied same-family nonsemantic budget; absent never creates a threshold hard stop.")
    parser.add_argument("--epsilon", type=float, default=1e-9)
    parser.add_argument("--max-rows-per-family", type=int, default=200)
    parser.add_argument("--max-root-cause-rows-per-family", type=int, default=ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT)
    parser.add_argument(
        "--write-registry",
        action="store_true",
        help="Compatibility flag: prepare registry/ledger/seal mutations for orchestrator finalization; never write authoritative state directly.",
    )
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    packet, registry_rows, should_write = _evaluator.evaluate(args)
    root = Path(args.root).resolve()
    recurrence_identity = evaluate_recurrence_identity(
        _values.load_json_value(root, args.recurrence_identity_json)
    )
    packet["recurrence_identity"] = recurrence_identity
    packet["recurrence_identity_status"] = recurrence_identity.get("status")
    if recurrence_identity.get("status") == "block":
        packet["scope_verified"] = False
        packet["semantic_progress"] = False
        packet["authoritative_semantic_progress"] = False
        packet["recommended_disposition"] = "repair_recurrence_contract"
        packet["effective_allowed_dispositions"] = ["repair_recurrence_contract"]
    packet["registry_updated"] = False
    packet["registry_update_candidate"] = bool(should_write)
    packet["registry_update_status"] = (
        "prepared_not_finalized" if should_write else "no_change_candidate"
    )
    packet["write_registry_deferred"] = bool(args.write_registry)
    packet["decision_contract_version"] = 1
    packet["progress_verdict"] = _packet_progress_verdict(packet)
    packet["terminal_state"] = packet.get("recommended_disposition")
    packet["allowed_next_action_classes"] = list(packet.get("effective_allowed_dispositions") or [])
    if not packet["allowed_next_action_classes"]:
        packet["allowed_next_action_classes"] = [
            str(packet.get("recommended_disposition") or ("terminal_blocked" if packet.get("hard_stop_required") else "conservative_hold"))
        ]
    packet["required_gate_ids"] = list(packet.get("required_gate_ids") or [])
    packet["decision_consumed_gate_ids"] = sorted(
        str(row.get("gate_id"))
        for row in packet.get("gate_compatibility_results") or []
        if isinstance(row, dict)
        and row.get("gate_id")
        and row.get("gate_compatibility_status") == "compatible"
    )
    packet["durable_mutation_candidate"] = _build_durable_mutation_candidate(
        packet,
        registry_rows,
        legacy_write_requested=bool(args.write_registry),
    )
    output: Path | None = None
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        _write_candidate_packet(output, packet)
    packet["anti_loop_handoff"] = _build_handoff(packet, root, output)
    json.dump(packet, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if (
        packet.get("evidence_class") == "computed"
        and packet.get("recurrence_identity_status") != "block"
    ) else 2
