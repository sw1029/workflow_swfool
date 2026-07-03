from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
import re
from pathlib import Path
from typing import Any

from .constants import *
from .values import *
from .io_utils import *
from .registry import load_symbol_registry
from .normalizers import *
from .fingerprints import *
from .gates import *


class EvidenceSource(ABC):
    """Base contract for progress-loop evidence sources."""

    confidence: str
    source: str

    @abstractmethod
    def collect(self, root: Path, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError


def progress_kind(value: dict[str, Any], progress: str | None, text: str = "") -> str | None:
    delta = output_delta_gate(value)
    lowered = text.lower()
    if delta["effective_progress_kind"] in {"goal_productive", "governance_only"}:
        return str(delta["effective_progress_kind"])
    if delta["has_output_delta_fields"]:
        if delta["metadata_only"] or not delta["produced_domain_delta"]:
            return "governance_only"
        if delta["produced_domain_delta"]:
            return "goal_productive"
    coverage_gate = coverage_quality_delta_gate(value)
    if boolish(first_value(value, ("measurement_progress", "anti_loop_progress_gate.measurement_progress"))):
        if not boolish(
            first_value(value, ("measurement_progress_allowed", "anti_loop_progress_gate.measurement_progress_allowed"))
        ) or not boolish(coverage_gate.get("quality_delta_pass")):
            return "governance_only"
    if "produced_domain_delta=true" in lowered:
        return "goal_productive"
    if "produced_domain_delta=false" in lowered or (
        ("metadata-only" in lowered or "metadata_only" in lowered) and "positive_evidence_supplied=false" in lowered
    ):
        return "governance_only"

    for key in ("progress_kind", "progress_category", "progress_class", "goal_progress_kind"):
        raw = value.get(key)
        if isinstance(raw, dict):
            raw = raw.get("kind") or raw.get("progress_kind")
        if isinstance(raw, str) and raw.lower() in {"goal_productive", "governance_only"}:
            return raw.lower()

    positive_fields = (
        "goal_productive_this_cycle",
        "goal_productive_output",
        "produced_domain_delta",
        "semantic_quality_evidence_added",
        "quality_metric_improved",
        "reviewable_output_added",
        "source_backed_output_added",
        "validation_set_built",
    )
    governance_fields = (
        "artifact_sidecar_added",
        "governance_only",
        "workflow_only",
        "metadata_only",
        "sidecar_only",
    )
    if any(boolish(value.get(field)) for field in positive_fields):
        return "goal_productive"
    if any(boolish(value.get(field)) for field in governance_fields):
        return "governance_only"

    if any(
        token in lowered
        for token in (
            "goal_productive",
            "produced domain delta",
            "semantic_quality_evidence_added",
            "quality metric improved",
            "reviewable output added",
            "source-backed validation",
            "source backed validation",
        )
    ):
        return "goal_productive"
    if any(token in lowered for token in ("governance_only", "artifact_sidecar_added", "sidecar only", "metadata-only", "no-live")):
        return "governance_only"
    if progress in {"safety_only", "no_progress"}:
        return "governance_only"
    return None


def task_correction_class(
    value: dict[str, Any],
    delta: dict[str, Any],
    coverage_gate: dict[str, Any],
    provider_gate: dict[str, Any],
    text: str = "",
) -> str:
    explicit = first_value(value, ("task_correction_class", "anti_loop_progress_gate.task_correction_class"))
    if isinstance(explicit, str) and explicit.strip().lower() in {"detection", "correction", "mixed", "unknown"}:
        return explicit.strip().lower()
    lowered = " ".join([text, *scalar_values(value)]).lower()
    detection = bool(
        boolish(first_value(value, ("measurement_progress", "anti_loop_progress_gate.measurement_progress")))
        or DETECTION_TERMS_RE.search(lowered)
    )
    correction = bool(
        boolish(delta.get("produced_domain_delta"))
        or boolish(delta.get("changed_vs_previous"))
        or boolish(delta.get("semantic_progress"))
        or boolish(coverage_gate.get("quality_delta_pass"))
        or (number_value(provider_gate.get("provider_request_count")) or 0) > 0
        or CORRECTION_TERMS_RE.search(lowered)
    )
    if detection and correction:
        return "mixed"
    if detection:
        return "detection"
    if correction:
        return "correction"
    return "unknown"


def input_kinds(value: dict[str, Any]) -> list[str]:
    kinds: list[str] = []
    for key in ("new_input_kinds", "input_kinds", "required_new_input_kinds", "introduced_input_kinds"):
        kinds.extend(list_field(value.get(key)))
    return sorted(set(kinds))


def positive_delta_required(value: dict[str, Any]) -> bool:
    raw = value.get("positive_input_delta_required")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.lower() in {"true", "yes", "1", "required"}
    return False


def evidence_item_from_value(
    root: Path,
    path: Path,
    source: str,
    confidence: str,
    value: dict[str, Any],
    progress: str | None,
    blockers: list[str],
    registry: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    signature = normalized_signature(value, blockers)
    semantic = semantic_signature(value, blockers)
    axis = root_axis(value, blockers, semantic, signature)
    key = root_key(value, blockers, semantic, signature)
    root_family = normalize_root_family_key(key, signature, semantic)
    feature = workflow_feature_symbol(root, value, blockers, axis)
    observed = observed_output_class(root, value, registry.get(feature["symbol"]))
    delta = output_delta_gate(value, observed)
    coverage_gate = coverage_quality_delta_gate(value)
    dispatch_gate = provider_scale_dispatch_gate(value, coverage_gate)
    kind = progress_kind(value, progress)
    if delta.get("observed_override_applied"):
        kind = str(delta.get("effective_progress_kind") or kind or "")
    supplied = supplied_input_delta_gate(root, value, delta)
    provider_gate = provider_reattempt_gate(value)
    validator_gate = validator_integrity_gate(value)
    correction_class = task_correction_class(value, delta, coverage_gate, dispatch_gate)
    detection_only = correction_class == "detection" and kind != "goal_productive"
    unverified_hypotheses = first_value(
        value,
        (
            "root_cause_unverified_hypotheses",
            "anti_loop_progress_gate.root_cause_unverified_hypotheses",
            "result.anti_loop_progress_gate.root_cause_unverified_hypotheses",
        ),
    )
    return {
        "path": rel_path(root, path),
        "source": source,
        "confidence": confidence,
        "progress_verdict": progress,
        "progress_kind": kind,
        "progress_target": first_value(value, ("progress_target", "target_progress", "selected_progress_target")),
        "selected_task_source": first_value(value, ("selected_task_source", "derive.selected_task_source")),
        "selected_task_kind": first_value(value, ("selected_task_kind", "derive.selected_task_kind")),
        "disposition": first_value(value, ("selected_disposition", "disposition", "recommended_disposition")),
        "recommended_disposition": first_value(value, ("recommended_disposition", "anti_loop_progress_gate.recommended_disposition")),
        "blockers": blockers,
        "blocker_signature": signature,
        "semantic_signature": semantic,
        "root_axis": axis,
        "root_key": key,
        "blocker_root_family": root_family,
        "feature_symbol": feature,
        "observed_output": observed,
        "new_input_kinds": input_kinds(value),
        "has_supplied_input_delta": supplied["has_supplied_input_delta"],
        "supplied_input_artifact_paths": supplied["supplied_input_artifact_paths"],
        "positive_input_delta_required": positive_delta_required(value),
        "output_delta_gate": delta,
        "coverage_quality_delta_gate": coverage_gate,
        "provider_scale_dispatch_gate": dispatch_gate,
        "provider_reattempt_gate": provider_gate,
        "validator_integrity_gate": validator_gate,
        "terminal_outcome_changed": boolish(first_value(value, ("terminal_outcome_changed", "anti_loop_progress_gate.terminal_outcome_changed"))),
        "observed_delta_class": first_value(value, ("observed_delta_class", "anti_loop_progress_gate.observed_delta_class")),
        "untried_actionable_root_cause_exists": boolish(first_value(value, ("untried_actionable_root_cause_exists", "anti_loop_progress_gate.untried_actionable_root_cause_exists"))),
        "hypothesis_exhausted": boolish(first_value(value, ("hypothesis_exhausted", "anti_loop_progress_gate.hypothesis_exhausted"))),
        "vacuous_untried_streak": number_value(first_value(value, ("vacuous_untried_streak", "anti_loop_progress_gate.vacuous_untried_streak"))) or 0,
        "vacuous_untried_attempt_count": number_value(first_value(value, ("vacuous_untried_attempt_count", "anti_loop_progress_gate.vacuous_untried_attempt_count"))) or 0,
        "root_cause_unverified_count": len(unverified_hypotheses) if isinstance(unverified_hypotheses, list) else 0,
        "task_correction_class": correction_class,
        "detection_only": detection_only,
        "metadata_only": delta["metadata_only"] or kind == "governance_only",
        "has_no_live_language": progress == "safety_only",
        "has_source_backed_language": bool(value.get("source_backed") or value.get("bounded_preflight")),
    }


def structured_evidence(root: Path, recent: int) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    registry = load_symbol_registry(root)
    cycle_root = root / ".task" / "cycle"
    if cycle_root.is_dir():
        for ledger in sorted(cycle_root.glob("*/stage.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True):
            for event in reversed(read_jsonl(ledger)):
                progress = structured_progress(event)
                blockers = structured_blockers(event)
                if progress or blockers:
                    evidence.append(evidence_item_from_value(root, ledger, "cycle_ledger", "high", event, progress, blockers, registry))
                if len(evidence) >= recent:
                    return evidence
    index_path = root / ".task" / "index.jsonl"
    for record in reversed(read_jsonl(index_path)):
        progress = structured_progress(record)
        blockers = structured_blockers(record)
        if progress or blockers:
            evidence.append(evidence_item_from_value(root, index_path, "task_index", "medium", record, progress, blockers, registry))
        if len(evidence) >= recent:
            return evidence
    validation_dir = root / ".task" / "validation"
    if validation_dir.is_dir():
        for path in sorted(validation_dir.rglob("*"), key=lambda p: p.stat().st_mtime if p.is_file() else 0, reverse=True):
            if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
                continue
            values = read_jsonl(path) if path.suffix.lower() == ".jsonl" else [read_json(path)]
            for value in values:
                if not isinstance(value, dict):
                    continue
                progress = structured_progress(value)
                blockers = structured_blockers(value)
                if progress or blockers:
                    evidence.append(evidence_item_from_value(root, path, "structured_validation", "medium", value, progress, blockers, registry))
            if len(evidence) >= recent:
                return evidence
    return evidence[:recent]


def classify_progress(text: str) -> str | None:
    match = PROGRESS_RE.search(text)
    if match:
        return match.group(1).lower()
    lowered = text.lower()
    if "safety_only" in lowered or "fail-closed" in lowered or "no-live" in lowered or "non-dispatchable" in lowered:
        return "safety_only"
    if "no_progress" in lowered:
        return "no_progress"
    if "regressed" in lowered:
        return "regressed"
    if "advanced" in lowered:
        return "advanced"
    return None


def extract_blockers(text: str) -> list[str]:
    blockers = [match.group(1).strip()[:160] for match in BLOCKER_RE.finditer(text) if match.group(1).strip()]
    blockers.extend(match.group(1).rstrip(".,;") for match in ISSUE_RE.finditer(text))
    return blockers


def extract_input_kinds(text: str) -> list[str]:
    return sorted(set(match.group(1).strip().lower() for match in INPUT_KIND_RE.finditer(text)))


def has_positive_source_backed_signal(text: str) -> bool:
    if "source-backed" not in text and "bounded preflight" not in text:
        return False
    negative_phrases = (
        "without source-backed",
        "missing source-backed",
        "lacks source-backed",
        "lack source-backed",
        "no source-backed",
        "not source-backed",
    )
    return not any(phrase in text for phrase in negative_phrases)


def collect_sealed_families(root: Path) -> list[dict[str, Any]]:
    sealed: list[dict[str, Any]] = []

    def add_from_mapping(value: Any, path: Path) -> None:
        if not isinstance(value, dict):
            return
        records: list[Any]
        if isinstance(value.get("families"), list):
            records = value["families"]
        elif isinstance(value.get("sealed_families"), list):
            records = value["sealed_families"]
        elif value.get("semantic_signature") or value.get("blocker_signature"):
            records = [value]
        else:
            records = []
        for record in records:
            if not isinstance(record, dict):
                continue
            semantic = record.get("semantic_signature") or record.get("family") or record.get("signature")
            blocker = record.get("blocker_signature")
            if semantic or blocker:
                sealed.append(
                    {
                        "semantic_signature": str(semantic).lower() if semantic else None,
                        "blocker_signature": str(blocker).lower() if blocker else None,
                        "path": rel_path(root, path),
                        "reason": record.get("reason") or record.get("required_handoff"),
                    }
                )

    for path in (root / ".task").glob("sealed_blocker_families.json*"):
        if path.suffix == ".jsonl":
            for record in read_jsonl(path):
                add_from_mapping(record, path)
        else:
            add_from_mapping(read_json(path), path)

    pack_root = root / ".task" / "task_pack"
    if pack_root.is_dir():
        for path in pack_root.glob("*.json"):
            pack = read_json(path)
            if not isinstance(pack, dict):
                continue
            terminal = pack.get("terminal_blocker")
            if isinstance(terminal, dict):
                add_from_mapping(terminal, path)
    return sealed


def command_surface_budget(root: Path, threshold: int, metadata_only_count: int, metadata_window: int = 2) -> dict[str, Any]:
    surfaces: list[dict[str, Any]] = []
    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(scripts_dir.rglob("*.py")):
            text = read_text(path)
            if not text:
                continue
            commands = [match.group(0).lower() for match in COMMAND_SURFACE_RE.finditer(text)]
            if not commands:
                continue
            family_counts = Counter(
                re.sub(r"[-_]v\d+", "-vNNN", command)
                for command in commands
                if any(token in command for token in ("contract", "handoff", "packet", "gate", "preflight", "check", "locator", "resolution", "recovery"))
            )
            total_contract_like = sum(family_counts.values())
            if total_contract_like >= threshold:
                surfaces.append(
                    {
                        "path": rel_path(root, path),
                        "contract_like_command_count": total_contract_like,
                        "top_command_families": [
                            {"family": family, "count": count} for family, count in family_counts.most_common(8)
                        ],
                    }
                )
    budget_exceeded = bool(surfaces) and metadata_only_count >= metadata_window
    return {
        "threshold": threshold,
        "surface_count": len(surfaces),
        "metadata_only_window": metadata_window,
        "metadata_only_count": metadata_only_count,
        "budget_exceeded": budget_exceeded,
        "consolidation_candidate_required": budget_exceeded,
        "surfaces": surfaces[:8],
    }
