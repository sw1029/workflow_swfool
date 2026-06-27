#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


COMMAND_SURFACE_RE = re.compile(
    r"\b(?:build|validate|run|preflight)-[A-Za-z0-9_.:-]*[-_]v\d+[A-Za-z0-9_.:-]*"
    r"(?:contract|handoff|packet|gate|preflight|check|locator|resolution|recovery)?[A-Za-z0-9_.:-]*",
    re.IGNORECASE,
)
RUN_DIR_THRESHOLD = 100
PROCESSED_CANDIDATE_THRESHOLD = 200
VERSIONED_FAMILY_THRESHOLD = 12


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
    return records


def deep_get(data: Any, path: str) -> Any:
    current = data
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "present", "produced", "changed"}
    if isinstance(value, (list, dict)):
        return bool(value)
    return False


def first_present(event: dict[str, Any], paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = deep_get(event, path) if "." in path else event.get(path)
        if value is None:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def is_metadata_only(event: dict[str, Any]) -> bool:
    metadata_only = first_present(event, ("metadata_only", "output_delta.metadata_only", "output_delta_gate.metadata_only"))
    produced = first_present(event, ("produced_domain_delta", "output_delta.produced_domain_delta", "output_delta_gate.produced_domain_delta"))
    effective = first_present(event, ("effective_progress_kind", "output_delta.effective_progress_kind", "output_delta_gate.effective_progress_kind"))
    progress_kind = first_present(event, ("progress_kind", "selected_progress_kind", "expected_progress_kind"))
    if boolish(metadata_only):
        return True
    if produced is not None and not boolish(produced):
        return True
    return str(effective or progress_kind).lower() == "governance_only"


def collect_events(root: Path, cycle_id: str | None) -> list[dict[str, Any]]:
    if cycle_id:
        return read_jsonl(root / ".task" / "cycle" / cycle_id / "stage.jsonl")
    events: list[dict[str, Any]] = []
    for path in sorted((root / ".task" / "cycle").glob("*/stage.jsonl")) if (root / ".task" / "cycle").is_dir() else []:
        events.extend(read_jsonl(path))
    return events


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def command_surface_budget(root: Path, metadata_only_count: int, threshold: int = 12, metadata_window: int = 2) -> dict[str, Any]:
    surfaces: list[dict[str, Any]] = []
    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(scripts_dir.rglob("*.py")):
            commands = [match.group(0).lower() for match in COMMAND_SURFACE_RE.finditer(read_text(path))]
            if not commands:
                continue
            family_counts = Counter(
                re.sub(r"[-_]v\d+", "-vNNN", command)
                for command in commands
                if any(token in command for token in ("contract", "handoff", "packet", "gate", "preflight", "check", "locator", "resolution", "recovery"))
            )
            total = sum(family_counts.values())
            if total >= threshold:
                surfaces.append(
                    {
                        "path": path.as_posix(),
                        "contract_like_command_count": total,
                        "top_command_families": [
                            {"family": family, "count": count} for family, count in family_counts.most_common(8)
                        ],
                    }
                )
    exceeded = bool(surfaces) and metadata_only_count >= metadata_window
    return {
        "threshold": threshold,
        "surface_count": len(surfaces),
        "metadata_only_window": metadata_window,
        "metadata_only_count": metadata_only_count,
        "budget_exceeded": exceeded,
        "consolidation_candidate_required": exceeded,
        "hard_gate": exceeded,
        "allowed_dispositions": ["consolidation", "goal_productive", "terminal_blocked"],
        "surfaces": surfaces[:8],
    }


def artifact_sprawl_budget(root: Path) -> dict[str, Any]:
    run_root = root / ".task" / "run"
    processed_root = root / "processed"
    run_dir_count = sum(1 for path in run_root.iterdir() if path.is_dir()) if run_root.is_dir() else 0
    processed_candidate_count = (
        sum(1 for path in processed_root.rglob("*") if path.is_dir() and "candidate" in path.name.lower())
        if processed_root.is_dir()
        else 0
    )
    versioned_family_counter: Counter[str] = Counter()
    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(scripts_dir.rglob("*.py")):
            for match in COMMAND_SURFACE_RE.finditer(read_text(path)):
                family = re.sub(r"[-_]v\d+", "-vNNN", match.group(0).lower())
                versioned_family_counter[family] += 1
    over_budget = (
        run_dir_count >= RUN_DIR_THRESHOLD
        or processed_candidate_count >= PROCESSED_CANDIDATE_THRESHOLD
        or any(count >= VERSIONED_FAMILY_THRESHOLD for count in versioned_family_counter.values())
    )
    return {
        "run_dir_threshold": RUN_DIR_THRESHOLD,
        "run_dir_count": run_dir_count,
        "processed_candidate_threshold": PROCESSED_CANDIDATE_THRESHOLD,
        "processed_candidate_count": processed_candidate_count,
        "versioned_family_threshold": VERSIONED_FAMILY_THRESHOLD,
        "top_versioned_command_families": [
            {"family": family, "count": count} for family, count in versioned_family_counter.most_common(8)
        ],
        "consolidation_candidate_required": over_budget,
        "hard_gate": over_budget,
        "allowed_dispositions": ["consolidation", "goal_productive", "terminal_blocked", "user_escalation"],
    }


def analyze(root: Path, events: list[dict[str, Any]], index_records: list[dict[str, Any]]) -> dict[str, Any]:
    progress_values = [str(event.get("progress_verdict")).lower() for event in events if event.get("progress_verdict")]
    progress_kinds = [str(first_present(event, ("effective_progress_kind", "progress_kind"))).lower() for event in events if first_present(event, ("effective_progress_kind", "progress_kind"))]
    blockers = [str(item) for event in events for item in (event.get("blockers") or [])]
    artifacts = [str(item) for event in events for item in (event.get("artifacts") or [])]
    validation_profiles = [str(event.get("validation_profile")).lower() for event in events if event.get("validation_profile")]
    blocker_signatures = [str(event.get("blocker_signature")).lower() for event in events if event.get("blocker_signature")]
    validation_set_events = [event for event in events if str(event.get("step") or "") == "validation_set_build"]
    validation_set_artifacts = [artifact for artifact in artifacts if ".validation/sets/" in artifact or ".task/validation_set/" in artifact]
    validation_set_blockers = [
        blocker
        for blocker in blockers
        if any(token in blocker.lower() for token in ("validation_set", "validation set", "oracle", "leakage", "source_class", "quality"))
    ]
    repeated_blockers = [{"blocker": key, "count": count} for key, count in Counter(blockers).most_common() if count >= 2]
    repeated_signatures = [{"blocker_signature": key, "count": count} for key, count in Counter(blocker_signatures).most_common() if count >= 2]
    duplicate_artifacts = [{"artifact": key, "count": count} for key, count in Counter(artifacts).most_common() if count >= 2]
    progress_events = [event for event in events if event.get("progress_verdict") or first_present(event, ("progress_kind", "effective_progress_kind"))]
    metadata_only_events = [event for event in progress_events if is_metadata_only(event)]
    full_chain_without_reason = [
        event
        for event in events
        if str(event.get("validation_profile")).lower() == "full_chain" and not event.get("escalation_reason")
    ]
    findings: list[dict[str, Any]] = []
    if len(progress_values) >= 2 and progress_values[-2:] == ["safety_only", "safety_only"]:
        findings.append({"severity": "warn", "code": "consecutive_safety_only", "message": "The last two progress verdicts are safety_only."})
    if len(progress_events) >= 2 and all(is_metadata_only(event) for event in progress_events[-2:]):
        findings.append(
            {
                "severity": "warn",
                "code": "consecutive_metadata_only",
                "message": "The last two progress-bearing events are metadata-only after output-delta review.",
                "recommendation": "resume_primary_output",
            }
        )
    if repeated_blockers:
        findings.append({"severity": "warn", "code": "repeated_blocker", "message": "A blocker appears multiple times.", "evidence": repeated_blockers[:5]})
    if repeated_signatures:
        findings.append({"severity": "warn", "code": "repeated_blocker_signature", "message": "A normalized blocker signature appears multiple times.", "evidence": repeated_signatures[:5]})
    if duplicate_artifacts:
        findings.append({"severity": "warn", "code": "duplicate_artifact_paths", "message": "Artifact paths repeat across events.", "evidence": duplicate_artifacts[:5]})
    if full_chain_without_reason:
        findings.append({"severity": "warn", "code": "full_chain_without_escalation_reason", "message": "Full-chain validation was recorded without escalation reason.", "count": len(full_chain_without_reason)})
    if validation_set_blockers and not validation_set_events:
        findings.append(
            {
                "severity": "warn",
                "code": "validation_set_gap_without_build_phase",
                "message": "Validation-set, oracle, leakage, source-class, or quality blockers exist but no validation_set_build stage was recorded.",
                "evidence": validation_set_blockers[:5],
            }
        )
    if len(validation_set_artifacts) != len(set(validation_set_artifacts)):
        findings.append({"severity": "warn", "code": "duplicate_validation_set_artifacts", "message": "Validation-set artifact paths repeat across events."})
    if any("base_commit" in json.dumps(record, sort_keys=True) for record in index_records):
        findings.append({"severity": "info", "code": "base_commit_present", "message": "Pre-commit hashes should stay classified as base/pre_commit evidence until $repo-change-commit returns a final commit."})
    surface_budget = command_surface_budget(root, len(metadata_only_events))
    sprawl_budget = artifact_sprawl_budget(root)
    if surface_budget["consolidation_candidate_required"]:
        findings.append(
            {
                "severity": "warn",
                "code": "command_surface_budget_exceeded",
                "message": "A target script has accumulated contract/preflight command surface while recent progress is metadata-only.",
                "evidence": surface_budget,
            }
        )
    if sprawl_budget["consolidation_candidate_required"]:
        findings.append(
            {
                "severity": "warn",
                "code": "artifact_sprawl_budget_exceeded",
                "message": "Run directories, processed candidates, or versioned command families exceed consolidation thresholds.",
                "evidence": sprawl_budget,
            }
        )
    recommendations: list[str] = []
    codes = {item["code"] for item in findings}
    if "consecutive_safety_only" in codes and repeated_blockers:
        recommendations.append("supply_evidence_path_or_bounded_preflight")
    if "consecutive_metadata_only" in codes:
        recommendations.append("resume_primary_output")
    if "repeated_blocker_signature" in codes:
        recommendations.append("consume_or_reorder_task_pack_or_terminal_block")
    if "command_surface_budget_exceeded" in codes:
        recommendations.append("register_consolidation_candidate")
    if "artifact_sprawl_budget_exceeded" in codes:
        recommendations.append("register_consolidation_candidate")
    if "consecutive_safety_only" in codes:
        recommendations.append("batch_micro_contracts")
    if "validation_set_gap_without_build_phase" in codes:
        recommendations.append("route_validation_set_plan_or_build")
    recommendation = recommendations[0] if recommendations else "continue"
    return {
        "status": "warn" if any(item["severity"] == "warn" for item in findings) else "ok",
        "event_count": len(events),
        "progress_counts": dict(Counter(progress_values)),
        "progress_kind_counts": dict(Counter(progress_kinds)),
        "metadata_only_count": len(metadata_only_events),
        "validation_profile_counts": dict(Counter(validation_profiles)),
        "blocker_signature_counts": dict(Counter(blocker_signatures)),
        "validation_set_build_count": len(validation_set_events),
        "command_surface_budget": surface_budget,
        "artifact_sprawl_budget": sprawl_budget,
        "findings": findings,
        "recommendation": recommendation,
        "recommendations": recommendations or ["continue"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile task-cycle efficiency from ledger/index evidence.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--cycle-id")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    output = analyze(root, collect_events(root, args.cycle_id), read_jsonl(root / ".task" / "index.jsonl"))
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
