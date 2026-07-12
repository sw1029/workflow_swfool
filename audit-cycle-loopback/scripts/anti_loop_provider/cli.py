from __future__ import annotations

from .common import *

def _packet_progress_verdict(packet: dict[str, Any]) -> str:
    if not bool_value(packet.get("scope_verified")) or str(packet.get("evidence_class") or "") == "not_evaluated":
        return "not_evaluated"
    if bool_value(packet.get("authoritative_semantic_progress")):
        return "advanced"
    if bool_value(packet.get("hard_stop_required")):
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
        "packet_ref": rel_path(root, output),
        "packet_sha256": _file_sha256(output),
        "artifact_id": packet.get("artifact_id"),
        "artifact_sha256": packet.get("artifact_sha256"),
        "artifact_family": packet.get("artifact_family"),
        "blocker_signature": packet.get("blocker_signature"),
        "progress_verdict": packet.get("progress_verdict"),
        "hard_stop": bool_value(packet.get("hard_stop_required")),
        "terminal_state": packet.get("recommended_disposition"),
        "allowed_next_action_classes": packet.get("allowed_next_action_classes") or [],
        "compatible_gate_ids": compatible_ids,
        "incompatible_gate_ids": incompatible_ids,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute a conservative anti-loop progress gate packet.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--task-id", default="unknown")
    parser.add_argument("--artifact-family", default="unknown")
    parser.add_argument("--semantic-signature", default="unknown")
    parser.add_argument("--root-key", help="Suffix-normalized root key for measurement cap and loop comparison.")
    parser.add_argument("--domain-adapter", help=f"Path to a repository domain adapter module; defaults to ${DOMAIN_ADAPTER_ENV} when set.")
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
    parser.add_argument("--acceptance-reachability-json", help="Path or JSON object with acceptance_min_output, frozen_envelope, and optional reachability_verdict.")
    parser.add_argument("--metric-validity-json", help="Path or JSON object/list from an oracle or metric validity self-check.")
    parser.add_argument("--root-cause-hypotheses-json", help="Path or JSON list/dict of root-cause hypotheses for the generic root-cause ledger.")
    parser.add_argument("--hypothesized-root-cause", help="Single root-cause hypothesis slug to record when no JSON/adapter list is supplied.")
    parser.add_argument("--root-cause-repair-attempted", action="store_true", help="Mark the supplied root-cause hypothesis as explicitly attempted by this cycle.")
    parser.add_argument("--root-cause-repair-task-id", help="Task id for the repair attempt targeting the supplied root-cause hypothesis.")
    parser.add_argument("--root-cause-actionable", action="store_true", help="Assert the supplied root-cause hypothesis is actionable; untried promotion still requires structural fields or provenance evidence.")
    parser.add_argument("--untried-promotion-budget", type=int, default=UNTRIED_PROMOTION_BUDGET_DEFAULT, help="Same-family vacuous untried repairs allowed before hypothesis_exhausted=true.")
    parser.add_argument("--measurement-check-id", action="append", default=[], help="Stable check/oracle ID introduced or exercised by this cycle.")
    parser.add_argument("--measurement-check-ids-json", help="Path or JSON list/dict containing check or oracle IDs.")
    parser.add_argument("--measurement-frontier", action="append", default=[], help="Named measurement frontier observed by this cycle.")
    parser.add_argument("--measurement-streak-cap", type=int, default=MEASUREMENT_STREAK_CAP_DEFAULT)
    parser.add_argument("--detection-only-streak-cap", type=int, default=DETECTION_ONLY_STREAK_CAP_DEFAULT)
    parser.add_argument("--adapter-mandate-streak-cap", type=int, default=ADAPTER_MANDATE_STREAK_CAP_DEFAULT)
    parser.add_argument("--cumulative-chain-streak-cap", type=int, default=CUMULATIVE_CHAIN_STREAK_CAP_DEFAULT)
    parser.add_argument("--instrumentation-trigger-threshold", type=int, default=INSTRUMENTATION_TRIGGER_THRESHOLD_DEFAULT)
    parser.add_argument("--envelope-thaw-streak-cap", type=int, default=ENVELOPE_THAW_STREAK_CAP_DEFAULT)
    parser.add_argument("--blocker-signature", help="Stable current blocker signature before suffix normalization.")
    parser.add_argument("--blocker-rung", help="Current capability-ladder rung for the blocker family.")
    parser.add_argument("--max-forward-mutations", type=int, default=MAX_FORWARD_MUTATIONS_DEFAULT)
    parser.add_argument("--consolidation-streak-cap", type=int, default=CONSOLIDATION_STREAK_CAP_DEFAULT)
    parser.add_argument("--registry-path", default=REGISTRY_REL_PATH)
    parser.add_argument("--root-cause-ledger-path", default=ROOT_CAUSE_LEDGER_REL_PATH)
    parser.add_argument("--threshold", type=int, default=3)
    parser.add_argument("--epsilon", type=float, default=1e-9)
    parser.add_argument("--max-rows-per-family", type=int, default=200)
    parser.add_argument("--max-root-cause-rows-per-family", type=int, default=ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT)
    parser.add_argument("--write-registry", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    packet, registry_rows, should_write = evaluate(args)
    root = Path(args.root).resolve()
    registry_path = Path(args.registry_path)
    if not registry_path.is_absolute():
        registry_path = root / registry_path
    if args.write_registry and should_write:
        write_registry(registry_path, registry_rows)
        packet["registry_updated"] = True
    else:
        packet["registry_updated"] = False
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
    output: Path | None = None
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    packet["anti_loop_handoff"] = _build_handoff(packet, root, output)
    json.dump(packet, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if packet.get("evidence_class") == "computed" else 2
