#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import fnmatch
import hashlib
import inspect
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


REGISTRY_REL_PATH = ".task/anti_loop/family_progress_registry.jsonl"
ROOT_CAUSE_LEDGER_REL_PATH = ".task/anti_loop/root_cause_ledger.jsonl"
SCHEMA_VERSION = "anti-loop-progress-gate-v1"
LEGACY_QUALITY_MODULE_NAME = "novel_kg_quality_metrics.py"
DOMAIN_ADAPTER_ENV = "TASK_CYCLE_DOMAIN_ADAPTER_PATH"
DEFAULT_DOMAIN_ADAPTER_REL_PATH = ".task/domain_adapter.py"
LEGACY_QUALITY_ENV = "NOVEL_KG_QUALITY_METRICS_PATH"
DISPOSITION_UNIVERSE = {"goal_productive", "consolidation", "terminal_blocked", "user_escalation"}
SAFETY_VALVES = {"terminal_blocked", "user_escalation"}
CONSOLIDATION_STREAK_CAP_DEFAULT = 2
MEASUREMENT_STREAK_CAP_DEFAULT = 1
MAX_FORWARD_MUTATIONS_DEFAULT = 3
DETECTION_ONLY_STREAK_CAP_DEFAULT = 2
UNTRIED_PROMOTION_BUDGET_DEFAULT = 2
ADAPTER_MANDATE_STREAK_CAP_DEFAULT = 3
CUMULATIVE_CHAIN_STREAK_CAP_DEFAULT = 3
INSTRUMENTATION_TRIGGER_THRESHOLD_DEFAULT = 2
ENVELOPE_THAW_STREAK_CAP_DEFAULT = 2
ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT = 200
ROOT_STEERING_DOC_NAMES = {"task_advice.md", "skill_advice.md", "task_doctor_steering.md"}
QUALITY_DELTA_KEYS = (
    "event_named_ratio",
    "proper_noun_character_ratio",
    "coreference_resolved_ratio",
    "causal_edge_count",
    "windows_covered",
)
ROOT_KEY_KEYS = {"root_key", "semantic_root_key", "loop_root_key"}
IDEMPOTENT_REPLAY_KEYS = (
    "measurement_progress",
    "measurement_progress_allowed",
    "measurement_streak",
    "measurement_streak_cap",
    "measurement_check_ids",
    "measurement_frontiers_observed",
    "measurement_progress_basis",
    "measurement_progress_streak_for_root_key",
    "measurement_progress_streak_for_root_family",
    "legacy_family_key",
    "root_family_key",
    "blocker_root_family",
    "root_key",
    "previous_high_water_mark",
    "coverage_quality_delta_gate",
    "coverage_quality_delta_reconciliation_gate",
    "substance_metrics",
    "substance_delta_gate",
    "vacuous_corrective_gate",
    "facet_root_map_applied",
    "facet_root_map_missing",
    "facet_root_map_size",
    "terminal_outcome_key",
    "terminal_outcome_family_key",
    "terminal_outcome_family_fallback_applied",
    "terminal_outcome_family_previous_count",
    "advice_freshness_gate",
    "partial_progress_axes_gate",
    "structure_metrics_gate",
    "structure_high_water_key_scope",
    "structure_global_invariant_metrics",
    "previous_accepted_baseline",
    "provider_scale_dispatch_gate",
    "measurement_goal_productive_allowed",
    "requires_non_measurement_goal_productive",
    "blocker_signature",
    "blocker_ladder_rung",
    "blocker_mutation_kind",
    "forward_mutation_budget_remaining",
    "terminal_outcome_changed",
    "observed_delta_class",
    "forward_mutation_vacuous",
    "root_cause_ledger_path",
    "root_cause_ledger_status",
    "root_cause_ledger_entries",
    "root_cause_unverified_hypotheses",
    "root_cause_duplicate_hypotheses",
    "repo_owned_source_roots",
    "repo_owned_source_roots_status",
    "repo_owned_source_roots_error",
    "adapter_mandate_gate",
    "adapter_mandate_required",
    "adapter_missing_streak",
    "adapter_contract_unmet",
    "cumulative_goal_distance_gate",
    "cumulative_goal_distance_scope_key",
    "cumulative_goal_distance_stall_streak",
    "cumulative_goal_distance_stalled",
    "cumulative_untried_chain_without_quality_delta",
    "high_water_vector",
    "high_water_last_improved_cycle",
    "untried_veto_overridden_by_chain_stall",
    "acceptance_reachability_gate",
    "acceptance_unreachable_under_frozen_config",
    "acceptance_verifier_not_evaluated",
    "unverifiable_acceptance_contract",
    "relaxation_or_escalation_required",
    "residual_gap_policy",
    "residual_gap_ratio",
    "marginal_repair",
    "oracle_metric_validity_gate",
    "metric_verifier_not_evaluated",
    "adapter_wiring_gate",
    "adapter_wiring_defect",
    "adapter_loaded",
    "adapter_path",
    "adapter_registered",
    "adapter_expected_path",
    "chain_stall_forced_retarget_gate",
    "forced_selected_task",
    "forced_selected_task_options",
    "untried_actionable_root_cause_exists",
    "untried_root_cause_hypotheses",
    "untried_promotion_budget",
    "vacuous_untried_attempt_count",
    "vacuous_untried_streak",
    "hypothesis_exhausted",
    "hypothesis_exhaustion_seal_path",
    "terminal_blocked_invalid_due_to_untried_root_cause",
    "force_implementation_cycle",
    "task_correction_class",
    "detection_only",
    "detection_only_streak_for_root_family",
    "detection_only_streak_cap",
    "requires_correction_or_terminal",
    "validator_integrity_gate",
    "evidence_provenance_gate",
    "producer_attested_fields",
    "independently_verified_fields",
    "attested_only_movement",
    "primary_metric_gate",
    "primary_metric_high_water_moved",
    "primary_metric_zero_movement_streak",
    "primary_metric_stalled",
    "c4_user_escalation_backstop_required",
    "failure_surface_stage_gate",
    "execution_stage_ladder_status",
    "last_successful_stage",
    "failure_surface_stage",
    "failure_surface_count_key",
    "terminal_classification_stage_contradiction",
    "terminal_classification_invalid_for_counting",
    "same_input_contract_gate",
    "same_input_contract_violation",
    "diagnostics_unavailable",
    "diagnostics_unavailable_streak",
    "diagnostics_unavailable_gate",
    "instrumentation_supply_required",
    "verification_source_separation_gate",
    "independent_source_separation_status",
    "independently_verified_downgraded_fields",
    "envelope_thaw_item_required",
    "envelope_thaw_item",
    "envelope_thaw_streak",
    "root_dominant_parameter_key",
    "coupled_verifier_gate",
    "pass_with_coupled_verifier",
    "changed_verifier_source_paths",
    "effective_allowed_dispositions",
    "disposition_intersection_basis",
    "consolidation_streak",
    "consolidation_reduces_goal_distance",
    "consolidation_streak_cap",
    "authoritative_semantic_progress",
    "findings",
)
FRONTIER_CHECK_KEYS = {
    "event_sequence_oracle",
    "reconstruction_coverage",
    "relation_class_filled",
    "story_vs_narrative_split",
}
CHECK_ID_KEYS = {
    "check_id",
    "check_ids",
    "check_name",
    "check_names",
    "metric_id",
    "metric_ids",
    "oracle_id",
    "oracle_ids",
    "oracle_name",
    "oracle_names",
    "validation_check",
    "validation_checks",
}
BLOCKER_SIGNATURE_KEYS = {
    "blocker",
    "blocker_code",
    "blocker_reason",
    "blocker_signature",
    "failed_reason",
    "failure_reason",
}
LADDER_RANK = {
    "single_window": 0,
    "multi_window": 1,
    "entity_coref": 2,
    "causal_temporal": 3,
    "pov_timeline": 4,
    "reconstruction": 5,
    "unseen_batch": 6,
}
RUNG_ALIASES = {
    "single_window_sweep": "single_window",
    "multi_window_sweep": "multi_window",
    "coreference": "entity_coref",
    "entity_coreference": "entity_coref",
    "causal_temporal_edge": "causal_temporal",
    "temporal_causal": "causal_temporal",
    "timeline": "pov_timeline",
    "pov": "pov_timeline",
    "rich_profiles": "pov_timeline",
    "reconstruction_oracle": "reconstruction",
}
VOLATILE_KEYS = {
    "created_at",
    "updated_at",
    "run_id",
    "cycle_id",
    "timestamp",
    "source_path",
    "path",
    "offset",
    "start_offset",
    "end_offset",
}
FACET_SUFFIX_RE = re.compile(
    r"([_.:/|-])(?:v\d+|ver\d+|version\d+|facet|variant|case|mode|phase|stage|"
    r"vocab|pov|timing|typing|schema|contract|gate|metric|oracle|validator|lineage|"
    r"coverage|preflight|handoff|packet|dashboard|report|field|scalar|check|review|surface)$",
    re.IGNORECASE,
)
PASS_STATUS_VALUES = {"pass", "passed", "ok", "valid", "success", "succeeded", "complete", "completed", "true"}
FAIL_STATUS_VALUES = {"fail", "failed", "invalid", "error", "blocked", "false"}
VALIDATOR_RESULT_KEYS = {
    "pass",
    "passed",
    "ok",
    "valid",
    "success",
    "succeeded",
    "semantic_progress",
    "result",
    "status",
    "validates",
}
VALIDATOR_CHILD_KEYS = {
    "checks",
    "sub_checks",
    "sub_results",
    "subresults",
    "results",
    "validators",
    "validations",
    "assertions",
    "items",
    "embedded_results",
}
POPULATION_COUNT_KEYS = {
    "population_count",
    "declared_population_count",
    "target_count",
    "expected_count",
    "total_count",
    "candidate_count",
    "declared_count",
}
INSPECTED_COUNT_KEYS = {
    "checked_count",
    "validated_count",
    "inspected_count",
    "reviewed_count",
    "actual_count",
    "covered_count",
    "processed_count",
}
DETECTION_TERMS_RE = re.compile(
    r"(validator|validation|oracle|metric|gate|contract|check|dashboard|lineage|gap[-_ ]?report|"
    r"coverage[-_ ]?report|instrumentation|measurement)",
    re.IGNORECASE,
)
CORRECTION_TERMS_RE = re.compile(
    r"(producer|transform|prompt|resolver|resolution|extract|extraction|generate|generation|"
    r"repair|fix|implementation|run|primary[-_ ]?output|source[-_ ]?backed)",
    re.IGNORECASE,
)


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return []
    return rows


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


_QUALITY_METRICS_MODULE: Any | None = None
_DOMAIN_ADAPTER_MODULE: Any | None = None


def load_python_module(path: Path, module_name: str) -> Any | None:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        return None
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def domain_adapter_candidate_paths(root: Path, explicit_path: str | None) -> list[Path]:
    candidates: list[Path] = []
    for raw in (explicit_path, os.environ.get(DOMAIN_ADAPTER_ENV), os.environ.get("DOMAIN_ADAPTER_PATH")):
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        candidates.append(candidate)
    default_candidate = root / DEFAULT_DOMAIN_ADAPTER_REL_PATH
    if default_candidate.is_file():
        candidates.append(default_candidate)
    return candidates


def load_domain_adapter(root: Path, explicit_path: str | None) -> tuple[Any | None, str | None, str | None]:
    global _DOMAIN_ADAPTER_MODULE
    if _DOMAIN_ADAPTER_MODULE is not None:
        return _DOMAIN_ADAPTER_MODULE, None, None
    candidates = domain_adapter_candidate_paths(root, explicit_path)
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.as_posix() in seen:
            continue
        seen.add(resolved.as_posix())
        try:
            module = load_python_module(resolved, "task_cycle_domain_adapter")
        except Exception as exc:  # pragma: no cover - defensive import boundary
            return None, resolved.as_posix(), f"domain_adapter_import_failed:{type(exc).__name__}"
        if module is not None:
            _DOMAIN_ADAPTER_MODULE = module
            return module, resolved.as_posix(), None
    if candidates:
        return None, None, "domain_adapter_not_found"
    return None, None, None


def call_adapter(adapter: Any | None, function_name: str, **kwargs: Any) -> tuple[Any, str | None]:
    if adapter is None or not hasattr(adapter, function_name):
        return None, None
    function = getattr(adapter, function_name)
    try:
        signature = inspect.signature(function)
        accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
        if accepts_kwargs:
            return function(**kwargs), None
        accepted = {key: value for key, value in kwargs.items() if key in signature.parameters}
        return function(**accepted), None
    except TypeError:
        try:
            return function(), None
        except Exception as exc:  # pragma: no cover - adapter-owned code
            return None, f"{function_name}_failed:{type(exc).__name__}"
    except Exception as exc:  # pragma: no cover - adapter-owned code
        return None, f"{function_name}_failed:{type(exc).__name__}"


def load_quality_metrics(root: Path) -> Any:
    global _QUALITY_METRICS_MODULE
    if _QUALITY_METRICS_MODULE is not None:
        return _QUALITY_METRICS_MODULE
    candidates: list[Path] = []
    env_path = os.environ.get(LEGACY_QUALITY_ENV)
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            root / "scripts" / LEGACY_QUALITY_MODULE_NAME,
            Path.cwd() / "scripts" / LEGACY_QUALITY_MODULE_NAME,
        ]
    )
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.as_posix() in seen:
            continue
        seen.add(resolved.as_posix())
        if not resolved.is_file():
            continue
        module = load_python_module(resolved, "legacy_quality_metrics_shared")
        if module is None:
            continue
        _QUALITY_METRICS_MODULE = module
        return module
    raise RuntimeError(f"{LEGACY_QUALITY_MODULE_NAME}_not_found")


def load_artifact_paths(root: Path, artifact_paths_json: str | None, artifact_paths: list[str]) -> list[Path]:
    values = list(artifact_paths)
    if artifact_paths_json:
        source = Path(artifact_paths_json)
        loaded: Any = None
        if not source.is_absolute():
            source = root / source
        if source.is_file():
            loaded = read_json(source)
        else:
            try:
                loaded = json.loads(artifact_paths_json)
            except json.JSONDecodeError:
                loaded = None
        if isinstance(loaded, list):
            values.extend(str(item) for item in loaded)
        elif isinstance(loaded, dict):
            for key in ("artifact_paths", "artifacts", "evidence_paths", "changed_files", "reviewed_artifacts"):
                raw = loaded.get(key)
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict) and item.get("path"):
                            values.append(str(item["path"]))
                        else:
                            values.append(str(item))
    paths: list[Path] = []
    for value in values:
        if not value or "://" in value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        if path not in paths:
            paths.append(path)
    return paths


def candidate_work_dirs(paths: list[Path]) -> list[Path]:
    candidates: set[Path] = set()
    required_names = {"kg_nodes.jsonl", "kg_edges.jsonl", "evidence.jsonl", "quality_report.json"}
    for path in paths:
        if path.is_file() and path.name in required_names:
            candidates.add(path.parent)
        elif path.is_dir():
            if any((path / name).exists() for name in required_names):
                candidates.add(path)
            for name in required_names:
                for match in path.rglob(name):
                    candidates.add(match.parent)
    return sorted(candidates, key=lambda item: item.as_posix())


def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): canonicalize(child) for key, child in sorted(value.items()) if str(key) not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [canonicalize(child) for child in value]
    return value


def fingerprint_rows(rows: list[dict[str, Any]]) -> str:
    canonical = [canonicalize(row) for row in rows]
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_quality(root: Path, paths: list[Path], adapter: Any | None) -> tuple[dict[str, Any], list[str], str | None]:
    if adapter is not None:
        adapter_value, adapter_error = call_adapter(
            adapter,
            "quality_vector",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            absolute_artifact_paths=[path.as_posix() for path in paths],
        )
        if adapter_error:
            return {}, [], adapter_error
        return normalize_adapter_quality_result(adapter_value, root)

    work_dirs = candidate_work_dirs(paths)
    if not paths:
        return {}, [], "no_artifact_paths_supplied"
    if not work_dirs:
        return {}, [rel_path(root, path) for path in paths if path.exists()], "no_kg_work_dirs_found"

    all_nodes: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    evidence_count = 0
    missing: list[str] = []
    evidence_paths: list[str] = []
    for work_dir in work_dirs:
        nodes_path = work_dir / "kg_nodes.jsonl"
        edges_path = work_dir / "kg_edges.jsonl"
        evidence_path = work_dir / "evidence.jsonl"
        for path in (nodes_path, edges_path, evidence_path, work_dir / "quality_report.json"):
            if not path.exists():
                missing.append(rel_path(root, path))
            elif path.is_file():
                evidence_paths.append(rel_path(root, path))
        nodes = read_jsonl(nodes_path)
        edges = read_jsonl(edges_path)
        evidence = read_jsonl(evidence_path)
        all_nodes.extend(nodes)
        all_edges.extend(edges)
        evidence_count += len(evidence)

    if missing or not all_nodes or not all_edges or evidence_count == 0:
        return {}, sorted(set(evidence_paths)), "required_output_artifacts_missing_or_empty"

    try:
        quality_metrics = load_quality_metrics(root)
    except RuntimeError as exc:
        return {}, sorted(set(evidence_paths)), str(exc)
    quality = quality_metrics.summarize_quality(all_nodes, all_edges, evidence_count, root=root)
    quality["current_output_fingerprint"] = fingerprint_rows(all_nodes + all_edges)
    if quality.get("quality_signal_confidence") == "low":
        return quality, sorted(set(evidence_paths)), "quality_signal_confidence_low"
    return quality, sorted(set(evidence_paths)), None


def normalize_family_key(artifact_family: str, semantic_signature: str) -> str:
    raw = f"{artifact_family or 'unknown'}|{semantic_signature or 'unknown'}".lower()
    raw = re.sub(r"\bcycle-\d{8}-\d{6}\b", "cycle", raw)
    raw = re.sub(r"\b20\d{6}(?:[-_]\d{2,6})?\b", "date", raw)
    raw = re.sub(r"[-_]v\d+\b", "-vNNN", raw)
    raw = re.sub(r"\bv\d+\b", "vNNN", raw)
    raw = re.sub(r"after[-_][a-z0-9_.-]+", "after-X", raw)
    raw = re.sub(r"run[-_][a-z0-9_.-]+", "run-X", raw)
    raw = re.sub(r"w_[a-f0-9]{8,}", "w_HASH", raw)
    raw = re.sub(r"[^a-z0-9|._-]+", "-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-")
    return raw or "unknown|unknown"


def normalize_root_family_key(*values: Any) -> str:
    raw = "|".join(str(value or "") for value in values if value is not None and str(value).strip()).lower()
    if not raw:
        return "unknown"
    raw = re.sub(r"\bcycle-\d{8}-\d{6}\b", "cycle", raw)
    raw = re.sub(r"\b20\d{6}(?:[-_]\d{2,6})?\b", "date", raw)
    raw = re.sub(r"\b\d{8,14}\b", "date", raw)
    raw = re.sub(r"\b[0-9a-f]{7,40}\b", "hash", raw)
    raw = re.sub(r"after[-_][a-z0-9_.-]+", "after-x", raw)
    raw = re.sub(r"run[-_][a-z0-9_.-]+", "run-x", raw)
    raw = re.sub(r"\bv\d+\b|[-_]v\d+\b", "vnnn", raw)
    raw = re.sub(r"[^a-z0-9가-힣|._:/-]+", "-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-_.:/|")
    for _ in range(6):
        updated = FACET_SUFFIX_RE.sub("", raw).strip("-_.:/|")
        if updated == raw:
            break
        raw = updated
    tokens = [token for token in re.split(r"[|._:/-]+", raw) if token and token not in {"date", "run", "cycle"}]
    return "_".join(dict.fromkeys(tokens[:16]))[:200] or "unknown"


def default_high_water() -> dict[str, Any]:
    return {
        "event_named_ratio": 0.0,
        "proper_noun_character_ratio": 0.0,
        "coreference_resolved_ratio": 0.0,
        "causal_edge_count": 0,
        "windows_covered": 0,
        "ever_causal_edge": False,
        "ever_provider_dispatch": False,
    }


def load_registry(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return []
    return rows


def compact_registry(rows: list[dict[str, Any]], max_rows_per_family: int) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(str(row.get("family_key") or "unknown"), []).append(row)
    compacted: list[dict[str, Any]] = []
    for family_rows in buckets.values():
        compacted.extend(family_rows[-max_rows_per_family:])
    return compacted


def write_registry(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def compact_root_cause_ledger(rows: list[dict[str, Any]], max_rows_per_family: int) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        family = str(row.get("family_key") or "unknown")
        buckets.setdefault(family, []).append(row)
    compacted: list[dict[str, Any]] = []
    for family_rows in buckets.values():
        latest_by_equivalence: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in family_rows:
            key = root_cause_distinct_key(row)
            existing = latest_by_equivalence.get(key)
            merged = dict(row)
            attempted_increment = 1 if bool_value(row.get("repair_attempted")) else 0
            vacuous_increment = attempted_increment if not bool_value(row.get("terminal_outcome_changed")) else 0
            if existing:
                merged["attempt_count"] = root_cause_attempt_weight(existing, "attempt_count") + attempted_increment
                merged["vacuous_attempt_count"] = root_cause_attempt_weight(existing, "vacuous_attempt_count") + vacuous_increment
                merged["terminal_outcome_changed"] = bool_value(existing.get("terminal_outcome_changed")) or bool_value(row.get("terminal_outcome_changed"))
                merged["first_cycle_id"] = existing.get("first_cycle_id") or existing.get("cycle_id")
                merged["previous_cycle_id"] = existing.get("cycle_id")
                aliases = set(list_values(existing.get("hypothesis_aliases")))
                aliases.add(str(existing.get("hypothesized_root_cause") or ""))
                aliases.add(str(row.get("hypothesized_root_cause") or ""))
                merged["hypothesis_aliases"] = sorted(alias for alias in aliases if alias)[:20]
            else:
                merged["attempt_count"] = root_cause_attempt_weight(row, "attempt_count", attempted_increment)
                merged["vacuous_attempt_count"] = root_cause_attempt_weight(row, "vacuous_attempt_count", vacuous_increment)
            latest_by_equivalence[key] = merged
        compacted.extend(list(latest_by_equivalence.values())[-max_rows_per_family:])
    return compacted


def append_root_cause_ledger(path: Path, entries: list[dict[str, Any]], max_rows_per_family: int = ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT) -> tuple[list[dict[str, Any]], bool]:
    rows = read_jsonl(path)
    seen = {
        (
            str(row.get("cycle_id") or ""),
            str(row.get("family_key") or ""),
            str(row.get("root_key") or ""),
            str(row.get("hypothesized_root_cause") or ""),
        )
        for row in rows
    }
    changed = False
    for entry in entries:
        key = (
            str(entry.get("cycle_id") or ""),
            str(entry.get("family_key") or ""),
            str(entry.get("root_key") or ""),
            str(entry.get("hypothesized_root_cause") or ""),
        )
        if key in seen:
            continue
        rows.append(entry)
        seen.add(key)
        changed = True
    if changed:
        rows = compact_root_cause_ledger(rows, max_rows_per_family)
        write_registry(path, rows)
    return rows, changed


def feed_exhausted_family_seal(root: Path, packet: dict[str, Any]) -> str | None:
    path = root / ".task" / "sealed_blocker_families.json"
    existing = read_json(path)
    if isinstance(existing, dict) and isinstance(existing.get("families"), list):
        data = existing
        records = [item for item in existing["families"] if isinstance(item, dict)]
    elif isinstance(existing, list):
        data = {"schema_version": "sealed-blocker-families-v1", "families": [item for item in existing if isinstance(item, dict)]}
        records = data["families"]
    elif isinstance(existing, dict):
        records = [existing]
        data = {"schema_version": "sealed-blocker-families-v1", "families": records}
    else:
        data = {"schema_version": "sealed-blocker-families-v1", "families": []}
        records = data["families"]
    semantic = str(packet.get("semantic_signature") or "").lower()
    blocker = str(packet.get("blocker_signature") or "").lower()
    root_family = str(packet.get("root_family_key") or packet.get("blocker_root_family") or "").lower()
    root_key = str(packet.get("root_key") or "").lower()
    record = {
        "semantic_signature": semantic or None,
        "blocker_signature": blocker or None,
        "root_key": root_key or None,
        "root_family_key": root_family or None,
        "hypothesis_exhausted": True,
        "vacuous_untried_attempt_count": packet.get("vacuous_untried_attempt_count"),
        "untried_promotion_budget": packet.get("untried_promotion_budget"),
        "reason": "root-cause hypothesis budget exhausted without terminal_outcome_changed",
        "updated_at": now_iso(),
        "source": "audit-cycle-loopback",
    }
    replaced = False
    for index, item in enumerate(records):
        if (
            str(item.get("semantic_signature") or "").lower() == semantic
            and str(item.get("blocker_signature") or "").lower() == blocker
            and str(item.get("root_family_key") or "").lower() == root_family
        ):
            records[index] = {**item, **record}
            replaced = True
            break
    if not replaced:
        records.append(record)
    data["families"] = records[-200:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rel_path(root, path)


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "present"}
    return False


def float_value(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def int_metric(value: Any) -> int:
    return int(max(0.0, float_value(value)))


def truthy_observation(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        text = value.strip().lower()
        return bool(text) and text not in {"false", "none", "null", "unknown", "0", "no"}
    if isinstance(value, (list, dict)):
        return bool(value)
    return False


def list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def load_json_value(root: Path, raw: str | None) -> Any:
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    if path.is_file():
        return read_json(path)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def load_json_values(root: Path, raws: list[str] | None) -> list[Any]:
    values: list[Any] = []
    for raw in raws or []:
        loaded = load_json_value(root, raw)
        if loaded is not None:
            values.append(loaded)
    return values


def iter_dicts(value: Any, *, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 6:
        return []
    items: list[dict[str, Any]] = []
    if isinstance(value, dict):
        items.append(value)
        for child in value.values():
            items.extend(iter_dicts(child, depth=depth + 1))
    elif isinstance(value, list):
        for child in value:
            items.extend(iter_dicts(child, depth=depth + 1))
    return items


def first_field_value(values: list[Any], keys: set[str]) -> Any:
    normalized_keys = {normalize_root_family_key(key) for key in keys}
    for value in values:
        for item in iter_dicts(value):
            for key, child in item.items():
                if normalize_root_family_key(key) in normalized_keys and child not in (None, "", []):
                    return child
    return None


def normalize_stage_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return text or None


def normalize_execution_stage_ladder(value: Any) -> tuple[list[str], dict[str, set[str]], bool]:
    if value is None:
        return [], {}, False
    source = value
    classification_map_value: Any = None
    if isinstance(value, dict):
        classification_map_value = (
            value.get("terminal_classification_stage_map")
            or value.get("classification_stage_map")
            or value.get("terminal_stage_map")
        )
        for key in ("execution_stage_ladder", "stage_ladder", "stages", "ladder"):
            if key in value:
                source = value.get(key)
                break
    stages: list[str] = []
    if isinstance(source, list):
        for item in source:
            stage = item.get("name") if isinstance(item, dict) else item
            normalized = normalize_stage_name(stage)
            if normalized and normalized not in stages:
                stages.append(normalized)
    elif isinstance(source, dict):
        raw_stages = source.get("stages") or source.get("execution_stage_ladder") or source.get("stage_ladder")
        if isinstance(raw_stages, list):
            stages, _, _ = normalize_execution_stage_ladder(raw_stages)
        else:
            for key in source:
                if key in {"terminal_classification_stage_map", "classification_stage_map", "terminal_stage_map"}:
                    continue
                normalized = normalize_stage_name(key)
                if normalized and normalized not in stages:
                    stages.append(normalized)
    elif isinstance(source, str):
        for item in re.split(r"[,>\s]+", source):
            normalized = normalize_stage_name(item)
            if normalized and normalized not in stages:
                stages.append(normalized)
    return stages, normalize_classification_stage_map(classification_map_value), bool(stages)


def normalize_classification_stage_map(value: Any) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    if value is None:
        return mapping

    def add(classification: Any, stages: Any) -> None:
        key = normalize_root_family_key(classification)
        if not key:
            return
        stage_values = string_list(stages)
        if isinstance(stages, dict):
            for child_key in ("stages", "failure_stages", "allowed_failure_stages", "stage"):
                stage_values.extend(string_list(stages.get(child_key)))
        normalized_stages = {stage for item in stage_values if (stage := normalize_stage_name(item))}
        if normalized_stages:
            mapping.setdefault(key, set()).update(normalized_stages)

    if isinstance(value, dict):
        for classification, stages in value.items():
            add(classification, stages)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                add(
                    item.get("classification") or item.get("terminal_classification") or item.get("name"),
                    item.get("stages") or item.get("failure_stages") or item.get("stage"),
                )
    return mapping


def next_failure_surface_stage(stages: list[str], last_successful_stage: str | None) -> str | None:
    if not stages or not last_successful_stage or last_successful_stage not in stages:
        return None
    index = stages.index(last_successful_stage)
    return stages[index + 1] if index + 1 < len(stages) else None


LAST_STAGE_KEYS = {"last_successful_stage", "last_completed_stage", "last_stage_reached"}
FAILURE_STAGE_KEYS = {"failure_surface_stage", "failed_stage", "failure_stage"}
TERMINAL_CLASSIFICATION_KEYS = {
    "terminal_classification",
    "terminal_outcome_classification",
    "classification",
    "failure_class",
    "recommended_disposition",
}


def terminal_stage_resolution_gate(
    *,
    ladder_value: Any,
    classification_map_value: Any,
    contexts: list[Any],
    root_family_key: str,
    dominant_parameter: str,
) -> dict[str, Any]:
    stages, embedded_map, ladder_provided = normalize_execution_stage_ladder(ladder_value)
    explicit_map = normalize_classification_stage_map(classification_map_value)
    classification_map = {**embedded_map, **explicit_map}
    last_stage = normalize_stage_name(first_field_value(contexts, LAST_STAGE_KEYS))
    failure_stage = normalize_stage_name(first_field_value(contexts, FAILURE_STAGE_KEYS)) or next_failure_surface_stage(stages, last_stage)
    terminal_classification = first_field_value(contexts, TERMINAL_CLASSIFICATION_KEYS)
    terminal_key = normalize_root_family_key(terminal_classification) if terminal_classification is not None else None
    mapped_stages = classification_map.get(terminal_key or "")
    contradiction = bool(failure_stage and mapped_stages and failure_stage not in mapped_stages)
    failure_surface_count_key = normalize_root_family_key(root_family_key, dominant_parameter, failure_stage) if failure_stage else None
    return {
        "gate": "H2-FAILURE-SURFACE-STAGE",
        "execution_stage_ladder_status": "provided" if ladder_provided else "not_provided",
        "execution_stage_ladder": stages,
        "terminal_classification_stage_map_status": "provided" if classification_map else "not_provided",
        "last_successful_stage": last_stage,
        "failure_surface_stage": failure_stage,
        "failure_surface_count_key": failure_surface_count_key,
        "terminal_classification": terminal_classification,
        "terminal_classification_key": terminal_key,
        "terminal_classification_allowed_stages": sorted(mapped_stages or []),
        "terminal_classification_stage_contradiction": contradiction,
        "terminal_classification_invalid_for_counting": contradiction,
        "root_dominant_parameter_key": dominant_parameter,
        "status": "block" if contradiction else ("pass" if failure_stage else "not_evaluated"),
        "constrains_disposition": contradiction,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": ["terminal_classification_stage_repair", "instrumentation_supply"],
    }


def same_input_contract_gate(contexts: list[Any]) -> dict[str, Any]:
    for value in contexts:
        for item in iter_dicts(value):
            match_value = (
                item.get("same_input_set_match")
                if "same_input_set_match" in item
                else item.get("same_window_window_count_match")
                if "same_window_window_count_match" in item
                else item.get("same_condition_input_set_match")
            )
            expected = (
                item.get("expected_input_set_size")
                or item.get("expected_window_count")
                or item.get("baseline_window_count")
                or item.get("target_input_set_size")
            )
            actual = (
                item.get("actual_input_set_size")
                or item.get("runtime_input_set_size")
                or item.get("runtime_window_count")
                or item.get("actual_window_count")
            )
            declared = bool_value(
                item.get("same_input_set_contract")
                or item.get("same_condition_contract")
                or item.get("same_window_contract")
            ) or match_value is not None or (expected is not None and actual is not None)
            if not declared:
                continue
            mismatch = (match_value is not None and not bool_value(match_value))
            if expected is not None and actual is not None:
                mismatch = mismatch or str(expected) != str(actual)
            return {
                "gate": "H2-SAME-INPUT-CONTRACT",
                "same_input_contract_declared": True,
                "expected_input_set_size": expected,
                "actual_input_set_size": actual,
                "same_input_set_match": not mismatch,
                "same_input_contract_violation": mismatch,
                "status": "block" if mismatch else "pass",
                "constrains_disposition": mismatch,
                "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
                "allowed_task_kinds": ["input_set_contract_repair", "instrumentation_supply"],
            }
    return {
        "gate": "H2-SAME-INPUT-CONTRACT",
        "same_input_contract_declared": False,
        "same_input_contract_violation": False,
        "status": "not_evaluated",
        "constrains_disposition": False,
    }


def diagnostics_unavailable_gate(
    *,
    registry_rows: list[dict[str, Any]],
    failure_surface_count_key: str | None,
    contexts: list[Any],
    threshold: int,
) -> dict[str, Any]:
    diagnostics_unavailable = any(bool_value(first_field_value([context], {"diagnostics_unavailable"})) for context in contexts)
    streak = 1 if diagnostics_unavailable else 0
    if diagnostics_unavailable and failure_surface_count_key:
        for row in reversed(registry_rows):
            if row.get("failure_surface_count_key") != failure_surface_count_key:
                continue
            if bool_value(row.get("diagnostics_unavailable")):
                streak += 1
                continue
            break
    required = diagnostics_unavailable and streak >= max(1, threshold)
    return {
        "gate": "H3-DIAGNOSTICS-UNAVAILABLE",
        "diagnostics_unavailable": diagnostics_unavailable,
        "diagnostics_unavailable_streak": streak,
        "instrumentation_trigger_threshold": max(1, threshold),
        "instrumentation_supply_required": required,
        "status": "block" if required else ("warn" if diagnostics_unavailable else "not_applicable"),
        "constrains_disposition": required,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": ["instrumentation_supply", "execution_diagnostics_supply"],
    }


def evidence_source_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    source = value.get("evidence_provenance_gate") if isinstance(value.get("evidence_provenance_gate"), dict) else value
    return {
        "verification_input_paths": string_list(
            source.get("verification_input_paths")
            or source.get("verification_inputs")
            or source.get("input_paths")
            or source.get("read_paths")
        ),
        "self_grounded_axes": {
            normalize_gate_key(item)
            for item in string_list(
                source.get("self_grounded_axes")
                or source.get("self_grounded_fields")
                or source.get("self_grounded_metrics")
            )
        },
        "disagreement_count": source.get("disagreement_count"),
        "zero_disagreement_reported": (
            source.get("disagreement_count") == 0
            or bool_value(source.get("zero_disagreement_reported"))
            or bool_value(source.get("no_disagreements"))
        ),
    }


def verification_source_separation_gate(
    *,
    provenance_value: Any,
    verified_artifact_paths: list[str],
    independently_verified_fields: list[str],
) -> dict[str, Any]:
    metadata = evidence_source_metadata(provenance_value)
    independent = sorted(set(independently_verified_fields))
    self_grounded = set(metadata.get("self_grounded_axes") or set())
    source_required_fields = [field for field in independent if normalize_gate_key(field) not in self_grounded]
    input_paths = [path.replace("\\", "/").lstrip("./") for path in metadata.get("verification_input_paths") or []]
    artifact_paths = [path.replace("\\", "/").lstrip("./") for path in verified_artifact_paths]
    overlaps: list[str] = []
    for input_path in input_paths:
        for artifact_path in artifact_paths:
            if input_path == artifact_path or path_matches_pattern(input_path, artifact_path) or path_matches_pattern(artifact_path, input_path):
                overlaps.append(input_path)
                break
    missing = bool(source_required_fields and not input_paths)
    overlap = bool(source_required_fields and overlaps)
    pass_status = bool(independent) and not missing and not overlap
    downgraded = source_required_fields if (missing or overlap) else []
    status = "pass" if pass_status else ("not_evaluated" if not independent else "block")
    return {
        "gate": "H4-VERIFICATION-SOURCE-SEPARATION",
        "verification_input_paths": input_paths,
        "verified_artifact_paths": artifact_paths,
        "self_grounded_axes": sorted(self_grounded),
        "source_separation_required_fields": source_required_fields,
        "verification_input_disjoint": bool(source_required_fields and input_paths and not overlaps),
        "verification_input_overlap_paths": sorted(set(overlaps)),
        "independent_source_separation_status": "missing" if missing else ("overlap" if overlap else ("pass" if pass_status else "not_evaluated")),
        "independently_verified_downgraded_fields": downgraded,
        "zero_disagreement_reported": bool_value(metadata.get("zero_disagreement_reported")),
        "status": status,
        "constrains_disposition": False,
    }

def load_changed_files(root: Path, changed_files_json: str | None, changed_files: list[str]) -> list[str]:
    values: list[str] = list(changed_files or [])
    loaded = load_json_value(root, changed_files_json)
    if isinstance(loaded, list):
        values.extend(str(item) for item in loaded if item is not None)
    elif isinstance(loaded, dict):
        for key in ("changed_files", "files", "paths", "changed_paths", "modified_files"):
            raw = loaded.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict) and item.get("path"):
                        values.append(str(item["path"]))
                    elif item is not None:
                        values.append(str(item))
    normalized: list[str] = []
    for value in values:
        text = clean_provenance_path_ref(str(value or ""))
        if not text:
            continue
        path = Path(text)
        if path.is_absolute():
            try:
                text = path.resolve().relative_to(root.resolve()).as_posix()
            except (OSError, ValueError):
                text = path.as_posix()
        else:
            text = text.replace("\\", "/").lstrip("./")
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def path_matches_pattern(path: str, pattern: str) -> bool:
    candidate = path.replace("\\", "/").lstrip("./")
    raw = pattern.replace("\\", "/").strip().lstrip("./")
    if not candidate or not raw:
        return False
    if raw.endswith("/"):
        return candidate.startswith(raw)
    return (
        candidate == raw
        or candidate.startswith(raw.rstrip("/") + "/")
        or fnmatch.fnmatch(candidate, raw)
        or fnmatch.fnmatch(candidate, raw.rstrip("/") + "/**")
    )


def normalize_gate_key(value: Any) -> str:
    return normalize_root_family_key(str(value or "unknown_gate"))


def normalize_verifier_source_paths(value: Any) -> tuple[dict[str, list[str]], bool]:
    if value is None:
        return {}, False
    source = value
    if isinstance(value, dict):
        for key in ("verifier_source_paths", "gate_verifier_source_paths", "gate_sources", "sources"):
            if key in value:
                source = value.get(key)
                break
    mapping: dict[str, list[str]] = {}

    def add(gate_id: Any, paths: Any) -> None:
        key = normalize_gate_key(gate_id or "*")
        values = string_list(paths)
        if isinstance(paths, dict):
            for child_key in ("paths", "source_paths", "verifier_paths", "files"):
                values.extend(string_list(paths.get(child_key)))
        if values:
            bucket = mapping.setdefault(key, [])
            for item in values:
                if item not in bucket:
                    bucket.append(item)

    if isinstance(source, dict):
        for gate_id, paths in source.items():
            if gate_id in {"paths", "source_paths", "verifier_paths", "files"}:
                add("*", paths)
            else:
                add(gate_id, paths)
    elif isinstance(source, list):
        for item in source:
            if isinstance(item, dict):
                gate_id = item.get("gate") or item.get("gate_id") or item.get("name") or item.get("id") or "*"
                paths = item.get("paths") or item.get("source_paths") or item.get("verifier_paths") or item.get("files")
                add(gate_id, paths)
            elif isinstance(item, str):
                add("*", item)
    elif isinstance(source, str):
        add("*", source)
    return mapping, True


def gate_evaluation_status(gate: dict[str, Any]) -> str | None:
    for key in ("evaluation_status", "status", "verdict", "result"):
        normalized = normalize_gate_evaluation_status(gate.get(key))
        if normalized:
            return normalized
    return None


def gate_is_passing(gate: dict[str, Any]) -> bool:
    status = gate_evaluation_status(gate)
    if status == "pass":
        return True
    if status in {"fail", "not_evaluated"}:
        return False
    return any(
        bool_value(gate.get(key))
        for key in (
            "quality_delta_pass",
            "substance_delta_pass",
            "primary_metric_high_water_moved",
            "structure_high_water_moved",
        )
    )


def coupled_verifier_gate(
    *,
    changed_files: list[str],
    verifier_source_map: dict[str, list[str]],
    hook_provided: bool,
    gates: list[dict[str, Any]],
) -> dict[str, Any]:
    if not hook_provided:
        return {
            "gate": "F1-VERIFIER-COUPLING",
            "verifier_source_paths_status": "not_provided",
            "changed_files_status": "not_provided" if not changed_files else "provided",
            "pass_with_coupled_verifier": False,
            "status": "not_evaluated",
            "constrains_disposition": False,
        }
    affected: list[dict[str, Any]] = []
    changed_source_paths: list[str] = []
    for gate in gates:
        gate_id = normalize_gate_key(gate.get("gate") or gate.get("name") or gate.get("id"))
        patterns = list(verifier_source_map.get(gate_id) or []) + list(verifier_source_map.get("*") or [])
        if not patterns:
            continue
        matched = [
            changed
            for changed in changed_files
            if any(path_matches_pattern(changed, pattern) for pattern in patterns)
        ]
        if not matched:
            continue
        changed_source_paths.extend(matched)
        if gate_is_passing(gate):
            affected.append(
                {
                    "gate": gate.get("gate") or gate.get("name") or gate_id,
                    "evaluation_status": gate_evaluation_status(gate) or "pass",
                    "changed_source_paths": sorted(set(matched)),
                    "verifier_source_paths": sorted(set(patterns)),
                    "effective_result": "pass_with_coupled_verifier",
                }
            )
    coupled = bool(affected)
    return {
        "gate": "F1-VERIFIER-COUPLING",
        "verifier_source_paths_status": "provided",
        "changed_files_status": "provided" if changed_files else "not_provided",
        "changed_files": changed_files,
        "changed_verifier_source_paths": sorted(set(changed_source_paths)),
        "affected_passing_gates": affected,
        "pass_with_coupled_verifier": coupled,
        "status": "block" if coupled else "ok",
        "hard_stop_required": coupled,
        "constrains_disposition": coupled,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": ["verifier_revalidation", "independent_evidence_recalculation"],
    }


def first_scalar_by_key(value: Any, keys: set[str]) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() in keys:
                scalars = scalar_strings(child)
                if scalars:
                    return scalars[0]
            found = first_scalar_by_key(child, keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = first_scalar_by_key(child, keys)
            if found:
                return found
    return None


def observed_delta_class(output_delta: Any, changed_vs_previous: bool, semantic_progress: bool) -> str:
    observed = first_scalar_by_key(
        output_delta,
        {"observed_delta_class", "observed_output_class", "output_class", "effective_progress_kind"},
    )
    if observed:
        return observed.strip().lower()
    if changed_vs_previous and semantic_progress:
        return "changed_semantic_output"
    return "no_observed_domain_delta"


def terminal_outcome_changed(output_delta: Any, changed_vs_previous: bool, semantic_progress: bool) -> bool:
    produced = first_scalar_by_key(output_delta, {"produced_domain_delta", "domain_delta", "positive_output_delta"})
    changed = first_scalar_by_key(output_delta, {"changed_vs_previous"})
    semantic = first_scalar_by_key(output_delta, {"semantic_progress"})
    metadata = first_scalar_by_key(output_delta, {"metadata_only"})
    observed = observed_delta_class(output_delta, changed_vs_previous, semantic_progress)
    strict_changed = bool_value(changed) if changed is not None else changed_vs_previous
    strict_semantic = bool_value(semantic) if semantic is not None else semantic_progress
    if bool_value(metadata):
        return False
    if observed in {"node_edge_delta", "semantic_delta", "changed_semantic_output", "primary_output_delta"}:
        return strict_changed and strict_semantic
    if produced is not None and not bool_value(produced):
        return False
    return bool_value(produced) and strict_changed and strict_semantic


def terminal_outcome_key(output_delta: Any, changed_vs_previous: bool, semantic_progress: bool) -> str:
    observed = observed_delta_class(output_delta, changed_vs_previous, semantic_progress)
    status = first_scalar_by_key(
        output_delta,
        {
            "terminal_outcome",
            "output_delta_status",
            "status",
            "failure_class",
            "blocked_reason",
            "blocker_signature",
        },
    )
    produced = first_scalar_by_key(output_delta, {"produced_domain_delta", "domain_delta", "positive_output_delta"})
    metadata = first_scalar_by_key(output_delta, {"metadata_only"})
    if bool_value(metadata):
        base = "metadata_only"
    elif terminal_outcome_changed(output_delta, changed_vs_previous, semantic_progress):
        base = "changed_semantic_output"
    elif produced is not None and not bool_value(produced):
        base = "no_primary_output_delta"
    elif observed and observed not in {"unknown", "none", "null"}:
        base = observed
    else:
        base = "no_semantic_output_delta"
    return normalize_root_family_key(base, status or "")


def terminal_outcome_root_family(
    facet_map: dict[str, str],
    *,
    artifact_family: str,
    outcome_key: str,
    root_key: str,
    semantic_signature: str,
) -> tuple[str, str, bool]:
    if facet_map:
        mapped = collapse_root_family(facet_map, root_key, semantic_signature, artifact_family, outcome_key)
        return mapped, "facet_root_map", False
    return normalize_root_family_key(artifact_family, outcome_key), "terminal_outcome_fallback", True


def latest_root_family_row(rows: list[dict[str, Any]], root_family_key: str) -> dict[str, Any] | None:
    return next((row for row in reversed(rows) if row_root_family(row) == root_family_key), None)


def row_effective_count_key(row: dict[str, Any]) -> str:
    return str(row.get("failure_surface_count_key") or row.get("effective_count_key") or row_root_family(row))


def previous_micro_hardening_count(rows: list[dict[str, Any]], root_family_key: str) -> int:
    family_rows = [row for row in rows if row_root_family(row) == root_family_key]
    if not family_rows:
        return 0
    return max(int_metric(row.get("same_family_micro_hardening_count") or row.get("micro_hardening_count") or 0) for row in family_rows)


def previous_micro_hardening_count_for_count_key(rows: list[dict[str, Any]], count_key: str) -> int:
    family_rows = [row for row in rows if row_effective_count_key(row) == count_key]
    if not family_rows:
        return 0
    return max(int_metric(row.get("same_family_micro_hardening_count") or row.get("micro_hardening_count") or 0) for row in family_rows)


def normalize_root_cause_slug(value: Any) -> str:
    return normalize_root_family_key(str(value or "unknown_root_cause"))


def normalize_root_cause_equivalence_slug(value: Any) -> str:
    slug = normalize_root_cause_slug(value)
    slug = re.sub(r"([_.:/-])v(?:nnn|\d+)$", "", slug)
    slug = re.sub(r"([_.:/-])(?:variant|facet|phase|stage|case|mode|fix|repair)$", "", slug)
    return slug.strip("-_.:/|") or "unknown_root_cause"


def normalize_root_cause_hypotheses(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        for key in ("root_cause_hypotheses", "hypotheses", "items", "root_causes"):
            if isinstance(value.get(key), list):
                value = value[key]
                break
        else:
            value = [value]
    if isinstance(value, str):
        value = [{"hypothesized_root_cause": value}]
    if not isinstance(value, list):
        return []
    hypotheses: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            item = {"hypothesized_root_cause": item}
        if not isinstance(item, dict):
            continue
        raw = item.get("hypothesized_root_cause") or item.get("root_cause") or item.get("root_key") or item.get("root")
        slug = normalize_root_cause_slug(raw)
        if slug == "unknown_root_cause":
            continue
        normalized = dict(item)
        normalized["hypothesized_root_cause"] = slug
        hypotheses.append(normalized)
    return hypotheses


ROOT_CAUSE_PROVENANCE_KEYS = (
    "provenance_refs",
    "provenance",
    "advice_id",
    "advice_path",
    "issue_id",
    "issue_path",
    "run_id",
    "run_evidence_path",
    "evidence_path",
    "evidence_paths",
    "source_evidence_path",
    "source_evidence_paths",
)


def normalize_repo_owned_source_roots(value: Any) -> list[str]:
    if isinstance(value, dict):
        for key in ("repo_owned_source_roots", "source_roots", "roots", "patterns"):
            if key in value:
                value = value.get(key)
                break
        else:
            return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    roots: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        normalized = text.replace("\\", "/").strip()
        if normalized not in roots:
            roots.append(normalized)
    return roots[:50]


def root_cause_provenance_refs(entry: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ROOT_CAUSE_PROVENANCE_KEYS:
        value = entry.get(key)
        if isinstance(value, list):
            refs.extend(str(item).strip() for item in value if item is not None and str(item).strip())
        elif isinstance(value, dict):
            refs.extend(str(item).strip() for item in value.values() if item is not None and str(item).strip())
        elif value is not None and str(value).strip():
            refs.append(str(value).strip())
    return sorted(set(refs))[:12]


def clean_provenance_path_ref(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("file://"):
        text = text[len("file://") :]
    match = re.match(r"^(.*?):[0-9]+(?::[0-9]+)?$", text)
    if match:
        text = match.group(1)
    return text.replace("\\", "/").strip()


def repo_owned_provenance_refs(root: Path | None, refs: list[str], source_roots: list[str]) -> list[str]:
    if root is None or not source_roots:
        return []
    root_resolved = root.resolve()
    owned: list[str] = []
    for ref in refs:
        cleaned = clean_provenance_path_ref(ref)
        if not cleaned:
            continue
        ref_path = Path(cleaned)
        if not ref_path.is_absolute():
            ref_path = root_resolved / ref_path
        try:
            rel = ref_path.resolve().relative_to(root_resolved).as_posix()
        except (OSError, ValueError):
            rel = cleaned.lstrip("./")
        for raw_pattern in source_roots:
            pattern = raw_pattern.strip().replace("\\", "/").strip("/")
            if not pattern:
                continue
            zero_depth_pattern = pattern.replace("/**/", "/")
            if (
                rel == pattern
                or rel.startswith(pattern + "/")
                or fnmatch.fnmatch(rel, pattern)
                or (zero_depth_pattern != pattern and fnmatch.fnmatch(rel, zero_depth_pattern))
                or fnmatch.fnmatch(rel, pattern.rstrip("/") + "/**")
            ):
                owned.append(ref)
                break
    return sorted(set(owned))[:12]


def root_cause_actionability(
    entry: dict[str, Any],
    *,
    root: Path | None = None,
    repo_owned_source_roots: list[str] | None = None,
) -> dict[str, Any]:
    structural_fields = ("local", "bounded", "provider_free", "in_scope", "authority_allowed")
    structural = all(bool_value(entry.get(field)) for field in structural_fields)
    asserted = bool_value(entry.get("actionable")) or bool_value(entry.get("root_cause_actionable"))
    provenance = root_cause_provenance_refs(entry)
    explicit_owned_refs = string_list(entry.get("repo_owned_source_refs"))
    computed_owned_refs = repo_owned_provenance_refs(root, provenance, repo_owned_source_roots or [])
    owned_refs = sorted(set(explicit_owned_refs + computed_owned_refs))[:12]
    provenance_derived = bool(owned_refs)
    actionable = structural or provenance_derived or (asserted and bool(provenance))
    if actionable:
        status = "verified"
    elif asserted:
        status = "unverified"
    else:
        status = "not_actionable"
    basis = {
        "asserted_actionable": asserted,
        "structural_actionable": structural,
        "provenance_derived_actionable": provenance_derived,
        "repo_owned_source_ref_count": len(owned_refs),
        "repo_owned_source_refs": owned_refs,
        "provenance_ref_count": len(provenance),
        "required_structural_fields": list(structural_fields),
    }
    return {"actionable": actionable, "status": status, "basis": basis, "provenance_refs": provenance}


def harden_repo_owned_actionability(
    entry: dict[str, Any],
    *,
    root: Path,
    repo_owned_source_roots: list[str],
) -> dict[str, Any]:
    actionability = root_cause_actionability(entry, root=root, repo_owned_source_roots=repo_owned_source_roots)
    owned_refs = string_list(actionability.get("basis", {}).get("repo_owned_source_refs"))
    if not owned_refs:
        return actionability
    rejected: dict[str, Any] = {}
    for field in ("local", "in_scope", "actionable"):
        if not bool_value(entry.get(field)):
            rejected[field] = entry.get(field)
        entry[field] = True
    entry["repo_owned_source_refs"] = owned_refs
    if rejected:
        entry["self_report_rejected_fields"] = rejected
    return root_cause_actionability(entry, root=root, repo_owned_source_roots=repo_owned_source_roots)


def root_cause_actionable(entry: dict[str, Any]) -> bool:
    return bool(root_cause_actionability(entry)["actionable"])


def same_root_cause_scope(row: dict[str, Any], family_key: str, root_key: str, root_family_key: str) -> bool:
    if str(row.get("family_key") or "") == family_key:
        return True
    if root_key and str(row.get("root_key") or "") == root_key:
        return True
    if root_family_key and str(row.get("root_family_key") or row.get("blocker_root_family") or "") == root_family_key:
        return True
    return False


def root_cause_target_surface(row: dict[str, Any]) -> str:
    return normalize_root_family_key(
        row.get("target_surface")
        or row.get("blocker_signature")
        or row.get("root_key")
        or row.get("root_family_key")
        or row.get("family_key")
        or "unknown_surface"
    )


def root_cause_delta_class(row: dict[str, Any]) -> str:
    return normalize_root_family_key(row.get("observed_delta_class") or "unknown_delta")


def root_cause_distinct_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        normalize_root_cause_equivalence_slug(row.get("hypothesized_root_cause")),
        root_cause_target_surface(row),
        root_cause_delta_class(row),
    )


def equivalent_root_cause(row: dict[str, Any], attempted_row: dict[str, Any]) -> bool:
    row_key = root_cause_distinct_key(row)
    attempted_key = root_cause_distinct_key(attempted_row)
    if row_key == attempted_key:
        return True
    if row_key[1:] != attempted_key[1:]:
        return False
    ratio = difflib.SequenceMatcher(None, row_key[0], attempted_key[0]).ratio()
    return ratio >= 0.88


def root_cause_attempt_weight(row: dict[str, Any], field: str, default: int = 0) -> int:
    value = row.get(field)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str) and value.strip().isdigit():
        return max(0, int(value.strip()))
    return default


def root_cause_exhaustion_state(
    rows: list[dict[str, Any]],
    family_key: str,
    root_key: str,
    root_family_key: str,
    budget: int,
) -> dict[str, Any]:
    scoped = [row for row in rows if same_root_cause_scope(row, family_key, root_key, root_family_key)]
    attempted_rows = [row for row in scoped if bool_value(row.get("repair_attempted"))]
    positive_attempts = [
        row for row in attempted_rows if bool_value(row.get("terminal_outcome_changed"))
    ]
    vacuous_rows = [
        row for row in attempted_rows if not bool_value(row.get("terminal_outcome_changed"))
    ]
    vacuous_attempt_count = sum(root_cause_attempt_weight(row, "vacuous_attempt_count", 1) for row in vacuous_rows)
    streak = 0
    for row in reversed(scoped):
        if not bool_value(row.get("repair_attempted")):
            continue
        if bool_value(row.get("terminal_outcome_changed")):
            break
        streak += root_cause_attempt_weight(row, "vacuous_attempt_count", 1)
    exhausted = vacuous_attempt_count >= max(1, budget) and not positive_attempts
    return {
        "hypothesis_exhausted": exhausted,
        "untried_promotion_budget": max(1, budget),
        "vacuous_untried_attempt_count": vacuous_attempt_count,
        "vacuous_untried_streak": streak,
        "successful_untried_attempt_count": len(positive_attempts),
        "attempted_hypothesis_count": len(attempted_rows),
    }


def root_cause_hypothesis_gate(
    rows: list[dict[str, Any]],
    family_key: str,
    root_key: str,
    root_family_key: str,
    budget: int,
    *,
    root: Path | None = None,
    repo_owned_source_roots: list[str] | None = None,
) -> dict[str, Any]:
    latest_by_root: dict[str, dict[str, Any]] = {}
    attempted_rows: list[dict[str, Any]] = []
    for row in rows:
        if not same_root_cause_scope(row, family_key, root_key, root_family_key):
            continue
        hypothesis_root = normalize_root_cause_slug(row.get("hypothesized_root_cause"))
        latest_by_root[hypothesis_root] = row
        if bool_value(row.get("repair_attempted")):
            attempted_rows.append(row)
    untried = []
    unverified = []
    duplicates = []
    for hypothesis_root, row in sorted(latest_by_root.items()):
        actionability = root_cause_actionability(
            row,
            root=root,
            repo_owned_source_roots=repo_owned_source_roots,
        )
        if not actionability["actionable"]:
            if actionability["status"] == "unverified":
                unverified.append(
                    {
                        "family_key": row.get("family_key"),
                        "root_key": row.get("root_key"),
                        "root_family_key": row.get("root_family_key"),
                        "hypothesized_root_cause": hypothesis_root,
                        "actionability_status": "unverified",
                        "actionability_basis": actionability["basis"],
                    }
                )
            continue
        duplicate = next((attempted for attempted in attempted_rows if equivalent_root_cause(row, attempted)), None)
        if duplicate is not None:
            duplicates.append(
                {
                    "family_key": row.get("family_key"),
                    "root_key": row.get("root_key"),
                    "root_family_key": row.get("root_family_key"),
                    "hypothesized_root_cause": hypothesis_root,
                    "attempted_equivalent": normalize_root_cause_slug(duplicate.get("hypothesized_root_cause")),
                    "target_surface": root_cause_target_surface(row),
                    "observed_delta_class": row.get("observed_delta_class"),
                }
            )
            continue
        untried.append(
            {
                "family_key": row.get("family_key"),
                "root_key": row.get("root_key"),
                "root_family_key": row.get("root_family_key"),
                "hypothesized_root_cause": hypothesis_root,
                "repair_attempted": False,
                "repair_task_id": row.get("repair_task_id"),
                "terminal_outcome_changed": bool_value(row.get("terminal_outcome_changed")),
                "observed_delta_class": row.get("observed_delta_class"),
                "target_surface": root_cause_target_surface(row),
                "cycle_id": row.get("cycle_id"),
                "actionable": True,
                "actionability_status": "verified",
                "actionability_basis": actionability["basis"],
                "provenance_refs": actionability["provenance_refs"],
            }
        )
    exhaustion = root_cause_exhaustion_state(rows, family_key, root_key, root_family_key, budget)
    if exhaustion["hypothesis_exhausted"]:
        untried = []
    return {
        **exhaustion,
        "untried_root_cause_hypotheses": untried,
        "root_cause_unverified_hypotheses": unverified,
        "root_cause_duplicate_hypotheses": duplicates,
    }


def untried_root_cause_hypotheses(
    rows: list[dict[str, Any]],
    family_key: str,
    root_key: str,
    root_family_key: str,
    *,
    root: Path | None = None,
    repo_owned_source_roots: list[str] | None = None,
) -> list[dict[str, Any]]:
    return root_cause_hypothesis_gate(
        rows,
        family_key,
        root_key,
        root_family_key,
        UNTRIED_PROMOTION_BUDGET_DEFAULT,
        root=root,
        repo_owned_source_roots=repo_owned_source_roots,
    )["untried_root_cause_hypotheses"]


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def numeric_vector(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    vector: dict[str, float] = {}
    for key, child in value.items():
        if isinstance(child, dict):
            continue
        text_key = str(key).strip()
        if not text_key:
            continue
        if isinstance(child, bool):
            vector[text_key] = 1.0 if child else 0.0
        elif isinstance(child, (int, float)):
            vector[text_key] = float(child)
        elif isinstance(child, str):
            try:
                vector[text_key] = float(child.strip())
            except ValueError:
                continue
    return vector


def normalize_previous_accepted_baseline(value: Any) -> tuple[str | None, dict[str, Any], str | None]:
    if value is None:
        return None, {}, None
    if isinstance(value, (str, int, float)):
        fingerprint = str(value).strip()
        return (fingerprint or None), {}, None
    if not isinstance(value, dict):
        return None, {}, "previous_accepted_fp_unrecognized"
    fingerprint = None
    for key in (
        "previous_accepted_fp",
        "previous_accepted_fingerprint",
        "previous_output_fingerprint",
        "output_fingerprint",
        "current_output_fingerprint",
        "fingerprint",
    ):
        raw = value.get(key)
        if raw is not None and str(raw).strip():
            fingerprint = str(raw).strip()
            break
    vector_source: Any = None
    for key in (
        "previous_quality_vector",
        "quality_vector",
        "previous_high_water_mark",
        "high_water_mark",
        "coverage_quality_vector",
    ):
        if isinstance(value.get(key), dict):
            vector_source = value[key]
            break
    reason = value.get("insufficient_reason") or value.get("blocked_reason") or value.get("error")
    return fingerprint, numeric_vector(vector_source), str(reason) if reason else None


def find_coverage_quality_delta_gate(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        for item in value:
            found = find_coverage_quality_delta_gate(item)
            if found:
                return found
        return None
    if not isinstance(value, dict):
        return None
    child = value.get("coverage_quality_delta_gate")
    if isinstance(child, dict):
        return child
    gate_name = str(value.get("gate") or value.get("name") or "").strip().lower()
    if (
        gate_name in {"g-cov", "coverage_quality_delta_gate"}
        or (
            "quality_delta_pass" in value
            and any(key in value for key in ("current_quality_vector", "previous_high_water_vector", "improved_fields"))
        )
    ):
        return value
    for child in value.values():
        found = find_coverage_quality_delta_gate(child)
        if found:
            return found
    return None


def coverage_gate_pass_value(gate: dict[str, Any]) -> bool | None:
    if "quality_delta_pass" in gate:
        return bool_value(gate.get("quality_delta_pass"))
    status = str(gate.get("status") or "").strip().lower()
    if status in {"pass", "passed", "ok"}:
        return True
    if status in {"block", "blocked", "fail", "failed"}:
        return False
    return None


def coverage_gate_vector(gate: dict[str, Any], *keys: str) -> dict[str, float]:
    for key in keys:
        vector = numeric_vector(gate.get(key))
        if vector:
            return vector
    return {}


def compact_coverage_gate(gate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(gate, dict):
        return None
    return {
        "quality_delta_pass": coverage_gate_pass_value(gate),
        "status": gate.get("status"),
        "improved_fields": list_values(gate.get("improved_fields")),
        "current_quality_vector": coverage_gate_vector(gate, "current_quality_vector", "quality_vector"),
        "previous_high_water_vector": coverage_gate_vector(
            gate,
            "previous_high_water_vector",
            "previous_quality_vector",
            "high_water_mark",
        ),
    }


def coverage_quality_delta_reconciliation_gate(local_gate: dict[str, Any], external_gate: dict[str, Any] | None, epsilon: float) -> dict[str, Any]:
    if not isinstance(external_gate, dict):
        return {
            "gate": "R-GCOV",
            "status": "not_applicable",
            "compared_sources": ["audit_cycle_loopback"],
            "validator_disagreement": False,
            "gcov_metric_name_collision": False,
            "constrains_disposition": False,
        }
    local_pass = coverage_gate_pass_value(local_gate)
    external_pass = coverage_gate_pass_value(external_gate)
    pass_disagreement = external_pass is not None and local_pass is not None and external_pass != local_pass
    local_current = coverage_gate_vector(local_gate, "current_quality_vector", "quality_vector")
    external_current = coverage_gate_vector(external_gate, "current_quality_vector", "quality_vector")
    value_conflicts = []
    for key in sorted(set(local_current) & set(external_current)):
        if abs(local_current[key] - external_current[key]) > (epsilon if abs(local_current[key]) <= 1.0 else 0.0):
            value_conflicts.append(
                {
                    "metric": key,
                    "audit_cycle_loopback_value": local_current[key],
                    "output_delta_value": external_current[key],
                }
            )
    blocked = pass_disagreement or bool(value_conflicts)
    return {
        "gate": "R-GCOV",
        "status": "block" if blocked else "pass",
        "compared_sources": ["audit_cycle_loopback", "output_delta"],
        "validator_disagreement": pass_disagreement,
        "gcov_metric_name_collision": bool(value_conflicts),
        "metric_value_conflicts": value_conflicts,
        "local_coverage_quality_delta_gate": compact_coverage_gate(local_gate),
        "external_coverage_quality_delta_gate": compact_coverage_gate(external_gate),
        "constrains_disposition": blocked,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }


def structure_metrics_gate(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("structure_metrics"), dict):
        metrics = dict(value["structure_metrics"])
    elif isinstance(value, dict):
        metrics = dict(value)
    else:
        metrics = {}
    source = value if isinstance(value, dict) else {}
    semantic_metrics = source.get("semantic_structure_metrics")
    if isinstance(semantic_metrics, dict):
        metrics.update(semantic_metrics)
    recommended = any(
        bool_value(metrics.get(key))
        for key in (
            "structure_consolidation_recommended",
            "consolidation_recommended",
            "budget_exceeded",
            "over_budget",
        )
    )
    high_water_moved = bool_value(
        source.get("structure_high_water_moved")
        or source.get("target_structure_improved")
        or source.get("structure_metric_improved")
        or metrics.get("structure_high_water_moved")
        or metrics.get("target_structure_improved")
        or metrics.get("structure_metric_improved")
    )
    improved_axes = source.get("improved_structure_axes") or source.get("improved_axes") or metrics.get("improved_structure_axes") or []
    if isinstance(improved_axes, str):
        improved_axes = [improved_axes]
    if not isinstance(improved_axes, list):
        improved_axes = []
    global_metric_source = (
        source.get("global_invariants")
        or source.get("global_invariant_metrics")
        or metrics.get("global_invariants")
        or metrics.get("global_invariant_metrics")
        or {}
    )
    global_metrics = numeric_vector(global_metric_source)
    for key, metric_value in numeric_vector(metrics).items():
        if str(key).startswith("global_"):
            global_metrics.setdefault(str(key), metric_value)
    global_high_water_moved = bool_value(
        source.get("global_structure_high_water_moved")
        or source.get("global_invariant_high_water_moved")
        or metrics.get("global_structure_high_water_moved")
        or metrics.get("global_invariant_high_water_moved")
    )
    refactor_effect_required = bool_value(
        source.get("refactor_effect_required")
        or source.get("behavior_preserving_refactor")
        or metrics.get("refactor_effect_required")
        or metrics.get("behavior_preserving_refactor")
    )
    return {
        "gate": "S-STRUCT",
        "structure_metrics": numeric_vector(metrics),
        "structure_global_invariant_metrics": global_metrics,
        "structure_high_water_key_scope": "global_invariant" if global_metrics else ("per_scope" if metrics else "not_evaluated"),
        "structure_consolidation_recommended": recommended,
        "structure_high_water_moved": high_water_moved or global_high_water_moved,
        "global_structure_high_water_moved": global_high_water_moved,
        "improved_structure_axes": [str(axis) for axis in improved_axes if str(axis).strip()],
        "refactor_effect_required": refactor_effect_required,
        "status": "warn" if recommended else ("not_applicable" if not metrics else "ok"),
        "constrains_disposition": False,
    }


def vector_delta_gate(
    *,
    gate_name: str,
    current: Any,
    previous: Any,
    pass_field: str,
    current_field: str,
    previous_field: str,
    epsilon: float,
) -> dict[str, Any]:
    current_vector = numeric_vector(current)
    previous_vector = numeric_vector(previous)
    improved_axes = [
        key
        for key, value in current_vector.items()
        if value > previous_vector.get(key, 0.0) + (epsilon if abs(value) <= 1.0 else 0.0)
    ]
    missing = not current_vector
    passed = bool(improved_axes)
    return {
        "gate": gate_name,
        current_field: current_vector,
        previous_field: previous_vector,
        "improved_axes": improved_axes,
        pass_field: passed,
        "status": "missing" if missing else ("pass" if passed else "block"),
        "fail_closed": missing,
        "constrains_disposition": missing or not passed,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }


INDEPENDENT_PROVENANCE_VALUES = {
    "independently_verified",
    "independent",
    "verified",
    "adapter_recomputed",
    "recomputed",
    "source_recomputed",
}
ATTESTED_PROVENANCE_VALUES = {
    "producer_attested",
    "attested",
    "producer_claim",
    "self_report",
    "observed_producer_claim",
    "unknown",
    "missing",
}


def normalize_provenance_label(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in INDEPENDENT_PROVENANCE_VALUES:
        return "independently_verified"
    if text in ATTESTED_PROVENANCE_VALUES:
        return "producer_attested"
    return text or "producer_attested"


def normalize_evidence_provenance(value: Any) -> tuple[dict[str, str], bool]:
    if value is None:
        return {}, False
    source = value
    if isinstance(value, dict):
        for key in ("evidence_provenance", "metric_provenance", "provenance_by_metric", "metrics"):
            if isinstance(value.get(key), (dict, list)):
                source = value.get(key)
                break
    provenance: dict[str, str] = {}

    def add(metric_key: Any, provenance_value: Any) -> None:
        key = normalize_gate_key(metric_key)
        label_source = provenance_value
        if isinstance(provenance_value, dict):
            label_source = (
                provenance_value.get("evidence_provenance")
                or provenance_value.get("provenance")
                or provenance_value.get("source")
                or provenance_value.get("status")
            )
        provenance[key] = normalize_provenance_label(label_source)

    if isinstance(source, dict):
        for metric_key, provenance_value in source.items():
            add(metric_key, provenance_value)
    elif isinstance(source, list):
        for item in source:
            if not isinstance(item, dict):
                continue
            metric_key = item.get("metric") or item.get("metric_key") or item.get("field") or item.get("name")
            if metric_key:
                add(metric_key, item)
    return provenance, True


def provenance_for_metric(metric_key: str, provenance: dict[str, str], hook_provided: bool) -> str:
    if not hook_provided:
        return "legacy_unclassified"
    return provenance.get(normalize_gate_key(metric_key), "producer_attested")


def metric_is_independently_verified(metric_key: str, provenance: dict[str, str], hook_provided: bool) -> bool:
    if not hook_provided:
        return True
    return provenance_for_metric(metric_key, provenance, hook_provided) == "independently_verified"


def apply_evidence_provenance_filter(
    gate: dict[str, Any],
    *,
    improved_key: str,
    pass_key: str,
    provenance: dict[str, str],
    hook_provided: bool,
) -> tuple[dict[str, Any], list[str], list[str]]:
    if not hook_provided:
        return gate, [], []
    updated = dict(gate)
    improved = list_values(updated.get(improved_key))
    independent = [field for field in improved if metric_is_independently_verified(field, provenance, hook_provided)]
    attested = [field for field in improved if field not in independent]
    updated[improved_key] = independent
    updated[pass_key] = bool(independent)
    if improved and not independent:
        updated["status"] = "block"
    elif independent:
        updated["status"] = "pass"
    updated["evidence_provenance_status"] = "provided"
    updated["independently_verified_fields"] = independent
    updated["producer_attested_fields"] = attested
    updated["attested_only_movement"] = bool(attested and not independent)
    return updated, independent, attested


def evidence_provenance_gate(
    *,
    hook_provided: bool,
    provenance: dict[str, str],
    independent_fields: list[str],
    attested_fields: list[str],
    adapter_error: str | None,
    source_separation_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attested_only = bool(attested_fields and not independent_fields)
    source_separation_gate = source_separation_gate or {}
    return {
        "gate": "F2-EVIDENCE-PROVENANCE",
        "evidence_provenance_status": "provided" if hook_provided else ("error" if adapter_error else "not_provided"),
        "adapter_error": adapter_error,
        "provenance_by_metric": provenance,
        "independently_verified_fields": sorted(set(independent_fields)),
        "producer_attested_fields": sorted(set(attested_fields)),
        "attested_only_movement": attested_only,
        "verification_source_separation_gate": source_separation_gate,
        "verification_input_paths": source_separation_gate.get("verification_input_paths") or [],
        "verified_artifact_paths": source_separation_gate.get("verified_artifact_paths") or [],
        "independent_source_separation_status": source_separation_gate.get("independent_source_separation_status"),
        "independently_verified_downgraded_fields": source_separation_gate.get("independently_verified_downgraded_fields") or [],
        "status": "warn" if attested_only else ("pass" if independent_fields else ("not_evaluated" if not hook_provided else "ok")),
        "constrains_disposition": False,
    }


def infer_reachability_verdict(acceptance_min_output: Any, frozen_envelope: Any) -> str:
    minimums = numeric_vector(acceptance_min_output)
    envelope = numeric_vector(frozen_envelope)
    if not minimums or not envelope:
        return "indeterminate"
    comparable = False
    for key, minimum in minimums.items():
        candidates = (
            key,
            f"max_{key}",
            f"{key}_max",
            f"limit_{key}",
            f"{key}_limit",
            "max_output",
            "output_cap",
        )
        matching = [envelope[candidate] for candidate in candidates if candidate in envelope]
        if not matching:
            continue
        comparable = True
        if max(matching) < minimum:
            return "unreachable"
    return "reachable" if comparable else "indeterminate"


def normalize_gate_evaluation_status(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return None
    if text in {"pass", "passed", "ok", "valid", "verified", "satisfied", "complete", "true"}:
        return "pass"
    if text in {"fail", "failed", "block", "blocked", "invalid", "unverified", "unsatisfied", "false"}:
        return "fail"
    if text in {
        "not_evaluated",
        "not_eval",
        "not_provided",
        "missing",
        "unknown",
        "indeterminate",
        "not_applicable",
        "none",
        "null",
    }:
        return "not_evaluated"
    return None


def verifier_evaluation_status(value: dict[str, Any], verifier_contract: dict[str, Any], prefix: str) -> str | None:
    keys = (
        f"{prefix}_verifier_evaluation_status",
        f"{prefix}_verifier_status",
        "verifier_evaluation_status",
        "verifier_status",
        "live_verifier_status",
    )
    for key in keys:
        normalized = normalize_gate_evaluation_status(value.get(key))
        if normalized:
            return normalized
    for key in ("evaluation_status", "status", "verdict"):
        normalized = normalize_gate_evaluation_status(verifier_contract.get(key))
        if normalized:
            return normalized
    return None


def normalize_verifier_contract(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        source: Any = value
        for key in (
            "acceptance_verifier_contract",
            "metric_verifier_contract",
            "verifier_contract",
            "target_required_verifier",
            "required_verifier_contract",
        ):
            if key in value:
                source = value.get(key)
                break
        if isinstance(source, str):
            source = {"required_verifier": source}
        if not isinstance(source, dict):
            return {}
        contract = dict(source)
    elif isinstance(value, str) and value.strip():
        contract = {"required_verifier": value.strip()}
    else:
        return {}
    required_verifier = (
        contract.get("required_verifier")
        or contract.get("verifier_id")
        or contract.get("id")
        or contract.get("name")
    )
    if required_verifier and not contract.get("required_verifier"):
        contract["required_verifier"] = required_verifier
    if required_verifier and "verifier_required" not in contract and "required" not in contract:
        contract["verifier_required"] = True
    return contract


def acceptance_target_from_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return None
    for key in (
        "target",
        "measurable_target",
        "acceptance_target",
        "original_target",
        "acceptance_min_output",
        "min_output",
        "minimum_output",
    ):
        if key in value and value.get(key) not in (None, "", []):
            return value.get(key)
    nested_gate = value.get("acceptance_reachability_gate")
    if isinstance(nested_gate, dict):
        return acceptance_target_from_value(nested_gate)
    return None


def merge_acceptance_verifier_contract(acceptance_value: Any, verifier_value: Any) -> Any:
    contract = normalize_verifier_contract(verifier_value)
    if not contract:
        return acceptance_value
    if isinstance(acceptance_value, dict):
        merged_value = dict(acceptance_value)
    else:
        merged_value = {}
    existing = merged_value.get("acceptance_verifier_contract") or merged_value.get("verifier_contract") or {}
    if not isinstance(existing, dict):
        existing = normalize_verifier_contract(existing)
    merged_value["acceptance_verifier_contract"] = {**contract, **existing}
    return merged_value


def acceptance_reachability_gate(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("acceptance_reachability_gate"), dict):
        value = value["acceptance_reachability_gate"]
    verifier_required = False
    required_verifier = None
    verifier_status: str | None = None
    if not isinstance(value, dict):
        verdict = "indeterminate"
        acceptance_min_output: Any = {}
        frozen_envelope: Any = {}
        residual_gap_policy: Any = None
        residual_gap_ratio: Any = None
        marginal_repair: bool = False
        envelope_thaw_item: Any = None
        thaw_condition: Any = None
        thaw_schedule: Any = None
    else:
        verifier_contract = (
            value.get("acceptance_verifier_contract")
            or value.get("verifier_contract")
            or value.get("required_verifier_contract")
            or {}
        )
        if not isinstance(verifier_contract, dict):
            verifier_contract = {}
        required_verifier = (
            value.get("required_verifier")
            or value.get("verifier_id")
            or verifier_contract.get("required_verifier")
            or verifier_contract.get("verifier_id")
        )
        verifier_required = bool_value(
            value.get("verifier_required")
            or value.get("required_for_acceptance")
            or value.get("acceptance_verifier_required")
            or verifier_contract.get("required")
            or verifier_contract.get("verifier_required")
        ) or bool(str(required_verifier or "").strip())
        verifier_status = verifier_evaluation_status(value, verifier_contract, "acceptance")
        acceptance_min_output = (
            value.get("acceptance_min_output")
            or value.get("min_output")
            or value.get("minimum_output")
            or {}
        )
        frozen_envelope = value.get("frozen_envelope") or value.get("envelope") or value.get("bounds") or {}
        envelope_thaw_item = (
            value.get("envelope_thaw_item")
            or value.get("thaw_item")
            or value.get("thaw_plan_item")
        )
        thaw_condition = value.get("thaw_condition") or value.get("thaw_exit_condition")
        thaw_schedule = value.get("thaw_schedule") or value.get("envelope_ladder") or value.get("envelope_thaw_schedule")
        residual_gap_policy = value.get("residual_gap_policy")
        residual_gap_ratio = value.get("residual_gap_ratio") or value.get("gap_ratio")
        marginal_repair = bool_value(value.get("marginal_repair") or value.get("marginal_repair_candidate"))
        verdict = str(
            value.get("reachability_verdict")
            or value.get("verdict")
            or value.get("status")
            or ""
        ).strip().lower()
        if bool_value(value.get("acceptance_unreachable_under_frozen_config")):
            verdict = "unreachable"
        if verdict not in {"reachable", "unreachable", "indeterminate"}:
            verdict = infer_reachability_verdict(acceptance_min_output, frozen_envelope)
    unreachable = verdict == "unreachable"
    frozen_envelope_present = bool(frozen_envelope)
    thaw_item_present = bool(envelope_thaw_item or thaw_condition or thaw_schedule)
    envelope_thaw_item_required = unreachable and frozen_envelope_present and not thaw_item_present
    reachability_status = "fail" if unreachable else ("pass" if verdict == "reachable" else "not_evaluated")
    if verifier_required and verifier_status is None:
        verifier_status = "not_evaluated"
    verifier_failed = verifier_required and verifier_status == "fail"
    if unreachable or verifier_failed:
        evaluation_status = "fail"
    elif verifier_required and verifier_status != "pass":
        evaluation_status = "not_evaluated"
    else:
        evaluation_status = reachability_status
    acceptance_verifier_not_evaluated = verifier_required and verifier_status == "not_evaluated"
    unverifiable_acceptance_contract = verifier_required and acceptance_verifier_not_evaluated
    blocked = unreachable or verifier_failed or unverifiable_acceptance_contract or envelope_thaw_item_required
    return {
        "gate": "G-REACH",
        "acceptance_min_output": acceptance_min_output,
        "frozen_envelope": frozen_envelope,
        "reachability_verdict": verdict,
        "evaluation_status": evaluation_status,
        "required_verifier": required_verifier,
        "verifier_required": verifier_required,
        "acceptance_verifier_not_evaluated": acceptance_verifier_not_evaluated,
        "unverifiable_acceptance_contract": unverifiable_acceptance_contract,
        "residual_gap_policy": residual_gap_policy,
        "residual_gap_ratio": residual_gap_ratio,
        "marginal_repair": marginal_repair,
        "envelope_thaw_item": envelope_thaw_item,
        "thaw_condition": thaw_condition,
        "thaw_schedule": thaw_schedule,
        "envelope_thaw_item_present": thaw_item_present,
        "envelope_thaw_item_required": envelope_thaw_item_required,
        "acceptance_unreachable_under_frozen_config": unreachable,
        "relaxation_or_escalation_required": blocked,
        "status": "block" if blocked else verdict,
        "constrains_disposition": blocked,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": ["constraint_relaxation", "envelope_thaw_item", "verifier_contract_supply"],
        "blocked_micro_repair_under_frozen_envelope": blocked,
    }


def metric_validity_states(value: Any) -> list[str]:
    states: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key in ("metric_validity", "validity", "status", "verdict"):
                if item.get(key) is not None:
                    states.append(str(item.get(key)).strip().lower())
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return states


def oracle_metric_validity_gate(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("oracle_metric_validity_gate"), dict):
        value = value["oracle_metric_validity_gate"]
    states = metric_validity_states(value)
    tautological = any(state in {"tautological", "constant", "self_fulfilling", "self-fulfilling"} for state in states)
    provided = value is not None
    verifier_required = False
    required_verifier = None
    verifier_status: str | None = None
    if isinstance(value, dict):
        verifier_contract = (
            value.get("metric_verifier_contract")
            or value.get("verifier_contract")
            or value.get("required_verifier_contract")
            or {}
        )
        if not isinstance(verifier_contract, dict):
            verifier_contract = {}
        required_verifier = (
            value.get("required_verifier")
            or value.get("verifier_id")
            or verifier_contract.get("required_verifier")
            or verifier_contract.get("verifier_id")
        )
        verifier_required = bool_value(
            value.get("verifier_required")
            or value.get("required_for_acceptance")
            or value.get("metric_verifier_required")
            or verifier_contract.get("required")
            or verifier_contract.get("verifier_required")
        ) or bool(str(required_verifier or "").strip())
        verifier_status = verifier_evaluation_status(value, verifier_contract, "metric")
    if verifier_required and verifier_status is None:
        verifier_status = "not_evaluated"
    verifier_failed = verifier_required and verifier_status == "fail"
    if tautological or verifier_failed:
        evaluation_status = "fail"
    elif verifier_required and verifier_status != "pass":
        evaluation_status = "not_evaluated"
    else:
        evaluation_status = "pass" if provided else "not_evaluated"
    metric_verifier_not_evaluated = verifier_required and verifier_status == "not_evaluated"
    required_not_evaluated = verifier_required and metric_verifier_not_evaluated
    return {
        "gate": "G-OENV",
        "metric_validity": "tautological" if tautological else ("checked" if provided else "unknown"),
        "metric_validity_states": states[:20],
        "metric_validity_self_check_provided": provided,
        "evaluation_status": evaluation_status,
        "required_verifier": required_verifier,
        "verifier_required": verifier_required,
        "metric_verifier_not_evaluated": metric_verifier_not_evaluated,
        "metric_goal_productive_excluded": tautological or verifier_failed or required_not_evaluated,
        "status": "block" if tautological or verifier_failed or required_not_evaluated else ("ok" if provided else "not_provided"),
        "constrains_disposition": tautological or verifier_failed or required_not_evaluated,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }


def normalize_adapter_quality_result(value: Any, root: Path) -> tuple[dict[str, Any], list[str], str | None]:
    if not isinstance(value, dict):
        return {}, [], "domain_adapter_quality_vector_missing"
    if isinstance(value.get("quality_vector"), dict):
        quality = dict(value["quality_vector"])
    else:
        quality = {
            key: child
            for key, child in value.items()
            if key not in {"evidence_paths", "insufficient_reason", "status", "quality_vector"}
        }
    if "current_output_fingerprint" not in quality:
        for key in ("current_output_fingerprint", "output_fingerprint", "fingerprint"):
            if value.get(key):
                quality["current_output_fingerprint"] = value[key]
                break
    evidence_paths = string_list(value.get("evidence_paths"))
    evidence_paths.extend(string_list(value.get("artifact_paths")))
    reason = value.get("insufficient_reason") or value.get("blocked_reason")
    status = str(value.get("status") or "").lower()
    if not reason and status in {"missing", "blocked", "fail", "failed", "insufficient_evidence"}:
        reason = f"domain_adapter_quality_vector_{status}"
    return quality, sorted({rel_path(root, root / item) if not Path(item).is_absolute() else rel_path(root, Path(item)) for item in evidence_paths}), str(reason) if reason else None


def normalize_facet_root_map(value: Any) -> dict[str, str]:
    if isinstance(value, dict) and isinstance(value.get("facet_root_map"), dict):
        value = value["facet_root_map"]
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, child in value.items():
        source = str(key or "").strip().lower()
        target = str(child or "").strip()
        if not source or not target:
            continue
        normalized[source] = target
        normalized[normalize_root_family_key(source)] = target
    return normalized


def collapse_root_family(facet_map: dict[str, str], *values: Any) -> str:
    raw = "|".join(str(value or "") for value in values if value is not None and str(value).strip())
    normalized = normalize_root_family_key(raw)
    if not facet_map:
        return normalized
    lowered = raw.lower()
    if normalized in facet_map:
        return normalize_root_family_key(facet_map[normalized])
    if lowered in facet_map:
        return normalize_root_family_key(facet_map[lowered])
    for facet, root in facet_map.items():
        if facet and facet in lowered:
            return normalize_root_family_key(root)
    return normalized


def normalize_corrective_resolution(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict) and isinstance(value.get("lanes"), list):
        value = value["lanes"]
    elif isinstance(value, dict) and isinstance(value.get("corrective_resolution"), list):
        value = value["corrective_resolution"]
    elif isinstance(value, dict):
        value = [
            {"lane": key, **child} if isinstance(child, dict) else {"lane": key, "resolved": child}
            for key, child in value.items()
        ]
    if not isinstance(value, list):
        return []
    lanes: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        lane = str(item.get("lane") or item.get("name") or item.get("id") or f"lane_{index}")
        attempted = int_metric(item.get("attempted") or item.get("attempted_count") or item.get("rows") or 0)
        resolved = int_metric(item.get("resolved") or item.get("resolved_count") or item.get("fixed") or 0)
        lanes.append({"lane": lane, "attempted": attempted, "resolved": resolved})
    return lanes


def vacuous_corrective_gate(value: Any) -> dict[str, Any]:
    lanes = normalize_corrective_resolution(value)
    noop_lanes = [lane for lane in lanes if lane["attempted"] > 0 and lane["resolved"] == 0]
    return {
        "gate": "G-VACUOUS",
        "lanes": lanes,
        "surface_corrective_noop": bool(noop_lanes),
        "excluded_delta_lanes": [lane["lane"] for lane in noop_lanes],
        "status": "block" if noop_lanes else ("not_applicable" if not lanes else "pass"),
        "constrains_disposition": bool(noop_lanes),
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }


FINGERPRINT_CLAIM_RE = re.compile(
    r"(?:output[_ -]?fingerprints?|current[_ -]?output[_ -]?fingerprints?|artifact[_ -]?fingerprints?|fingerprints?)\s*[:=]\s*([A-Za-z0-9_.:/-]{8,128})",
    re.IGNORECASE,
)


def extract_fingerprint_claims(text: str) -> list[str]:
    claims = sorted(set(match.group(1).strip() for match in FINGERPRINT_CLAIM_RE.finditer(text)))
    for match in re.finditer(r"declared_output_fingerprints\s*:\s*(\[[^\]\n]*\])", text, re.IGNORECASE):
        try:
            loaded = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, list):
            claims.extend(str(item).strip() for item in loaded if str(item).strip())
    return sorted(set(claims))


def verdict_state(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in PASS_STATUS_VALUES:
        return "passed"
    if text in FAIL_STATUS_VALUES or text in {"block", "blocked", "safe_to_attempt_false"}:
        return "blocked"
    return text


def gate_result_regressions(values: list[Any]) -> list[dict[str, Any]]:
    regressions: list[dict[str, Any]] = []

    def walk(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                walk(child)
            return
        if not isinstance(item, dict):
            return
        gate_id = str(item.get("gate_id") or item.get("name") or item.get("gate") or "").strip()
        transition = str(item.get("verdict_transition") or item.get("transition") or "").strip().lower()
        prior = verdict_state(item.get("prior_verdict") or item.get("previous_verdict") or item.get("previous_status"))
        current = verdict_state(item.get("current_verdict") or item.get("verdict") or item.get("status"))
        env_changed_key_present = "env_fingerprint_changed" in item or "environment_changed" in item
        env_stable_key_present = "env_fingerprint_stable" in item or "same_env_fingerprint" in item
        env_changed = bool_value(item.get("env_fingerprint_changed") or item.get("environment_changed"))
        env_stable = bool_value(item.get("env_fingerprint_stable") or item.get("same_env_fingerprint")) or (
            env_changed_key_present and not env_changed
        )
        env_stability_known = env_changed_key_present or env_stable_key_present
        passed_to_blocked = transition in {"passed_to_blocked", "pass_to_block", "regressed"} or (
            prior == "passed" and current == "blocked"
        )
        if passed_to_blocked and env_stability_known and env_stable:
            regressions.append(
                {
                    "gate_id": gate_id or None,
                    "prior_verdict": prior or None,
                    "current_verdict": current or None,
                    "verdict_transition": transition or "passed_to_blocked",
                    "env_fingerprint_stable": env_stable,
                }
            )
        for child in item.values():
            if isinstance(child, (dict, list)):
                walk(child)

    for value in values:
        walk(value)
    return regressions[:10]


def partial_progress_axes_gate(value: Any, no_goal_distance_delta: bool) -> dict[str, Any]:
    if isinstance(value, dict) and "partial_progress_axes" in value:
        axes_value = value.get("partial_progress_axes")
    else:
        axes_value = value
    if isinstance(axes_value, dict):
        axes = {str(key): child for key, child in axes_value.items() if truthy_observation(child)}
    elif isinstance(axes_value, list):
        axes = {str(item): True for item in axes_value if truthy_observation(item)}
    else:
        axes = {}
    warn = bool(axes) and no_goal_distance_delta
    return {
        "gate": "W-PARTIAL-PROGRESS-AXES",
        "partial_progress_axes": axes,
        "partial_progress_axes_provided": bool(axes),
        "high_water_flat": no_goal_distance_delta,
        "status": "warn" if warn else ("pass" if axes else "not_provided"),
        "recommendation": "decompose_all_or_nothing_gate" if warn else None,
        "constrains_disposition": False,
    }


def advice_freshness_gate(
    root: Path,
    current_output_fingerprint: Any,
    gate_values: list[Any] | None = None,
) -> dict[str, Any]:
    current = str(current_output_fingerprint or "").strip()
    docs = []
    active_dir = root / ".agent_advice" / "active"
    if active_dir.is_dir():
        docs.extend(sorted(active_dir.glob("*.md")))
    docs.extend(root / name for name in sorted(ROOT_STEERING_DOC_NAMES) if (root / name).is_file())
    claimed: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    for path in docs:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fingerprints = extract_fingerprint_claims(text)
        if not fingerprints:
            continue
        row = {"path": rel_path(root, path), "declared_output_fingerprints": fingerprints}
        claimed.append(row)
        if current and current not in fingerprints:
            stale.append(row)
    regressions = gate_result_regressions(gate_values or [])
    warn = bool(stale) or bool(regressions)
    return {
        "gate": "G-ADVICE-FRESH",
        "current_output_fingerprint": current or None,
        "declared_fingerprint_claims": claimed,
        "advice_metrics_stale": bool(stale),
        "stale_advice": stale,
        "gate_result_regression_stale": bool(regressions),
        "gate_result_regressions": regressions,
        "status": "warn" if warn else ("not_applicable" if not claimed else "pass"),
        "constrains_disposition": False,
    }


def scalar_strings(value: Any) -> list[str]:
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(scalar_strings(item))
        return values
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(scalar_strings(item))
        return values
    return []


def collect_values_by_key(value: Any, keys: set[str]) -> list[str]:
    collected: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).strip().lower() in keys:
                    collected.extend(scalar_strings(child))
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return sorted({item for item in collected if item})


def extract_check_ids(*values: Any) -> set[str]:
    check_ids: set[str] = set()
    for value in values:
        check_ids.update(collect_values_by_key(value, CHECK_ID_KEYS))
    return {item[:160] for item in check_ids if item}


def frontier_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def extract_frontier_observations(*values: Any) -> set[str]:
    observed: set[str] = set()

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = frontier_key(str(key))
                if normalized in FRONTIER_CHECK_KEYS and truthy_observation(child):
                    observed.add(normalized)
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    for value in values:
        walk(value)
    return observed


def recent_family_rows(rows: list[dict[str, Any]], family_key: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("family_key") == family_key]


def row_root_family(row: dict[str, Any]) -> str:
    return str(
        row.get("root_family_key")
        or row.get("blocker_root_family")
        or normalize_root_family_key(row.get("root_key"), row.get("family_key"), row.get("blocker_signature"))
    )


def recent_root_rows(
    rows: list[dict[str, Any]],
    root_key: str,
    fallback_family_key: str,
    root_family_key: str | None = None,
) -> list[dict[str, Any]]:
    root_values = {str(item) for item in (root_key, fallback_family_key, root_family_key) if item}
    scoped = [
        row
        for row in rows
        if str(row.get("root_key") or row.get("family_key") or "") in root_values
        or (root_family_key and row_root_family(row) == root_family_key)
    ]
    return scoped or recent_family_rows(rows, fallback_family_key)


def measurement_progress_details(
    registry_rows: list[dict[str, Any]],
    family_key: str,
    root_key: str,
    root_family_key: str,
    current_check_ids: set[str],
    current_frontiers: set[str],
) -> dict[str, Any]:
    family_rows = recent_root_rows(registry_rows, root_key, family_key, root_family_key)
    known_check_ids: set[str] = set()
    known_frontiers: set[str] = set()
    for row in family_rows:
        known_check_ids.update(str(item) for item in row.get("measurement_check_ids") or [] if item)
        known_frontiers.update(str(item) for item in row.get("measurement_frontiers_observed") or [] if item)
        basis = row.get("measurement_progress_basis")
        if isinstance(basis, dict):
            known_check_ids.update(str(item) for item in basis.get("introduced_check_ids") or [] if item)
            known_frontiers.update(str(item) for item in basis.get("new_frontier_observations") or [] if item)

    introduced = current_check_ids - known_check_ids
    new_frontiers = current_frontiers - known_frontiers
    measurement_progress = bool(introduced or new_frontiers)
    streak = 1 if measurement_progress else 0
    if measurement_progress:
        for row in reversed(family_rows):
            if bool_value(row.get("measurement_progress")):
                streak += 1
                continue
            break
    return {
        "measurement_progress": measurement_progress,
        "measurement_streak": streak,
        "measurement_progress_streak_for_root_key": streak,
        "measurement_progress_streak_for_root_family": streak,
        "measurement_progress_basis": {
            "introduced_check_ids": sorted(introduced),
            "new_frontier_observations": sorted(new_frontiers),
        },
    }


def normalize_dispositions(values: Any) -> set[str]:
    normalized = {str(item).strip().lower() for item in list_values(values)}
    return {item for item in normalized if item in DISPOSITION_UNIVERSE}


def normalize_task_kind(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower().replace("-", "_")).strip("_")


def normalize_task_kinds(values: Any) -> set[str]:
    return {kind for kind in (normalize_task_kind(item) for item in list_values(values)) if kind}


def gate_allowed_dispositions(name: str, gate: dict[str, Any]) -> set[str]:
    explicit = normalize_dispositions(gate.get("allowed_dispositions"))
    if explicit:
        return explicit
    if bool_value(gate.get("requires_goal_productive_next")) or bool_value(gate.get("requires_goal_productive_or_user_escalation")):
        return {"goal_productive", "terminal_blocked", "user_escalation"}
    if name == "command_surface_budget" and (bool_value(gate.get("hard_gate")) or bool_value(gate.get("budget_exceeded"))):
        return {"consolidation", "terminal_blocked"}
    return set(DISPOSITION_UNIVERSE)


def gate_allowed_task_kinds(gate: dict[str, Any]) -> set[str]:
    kinds = normalize_task_kinds(
        gate.get("allowed_task_kinds")
        or gate.get("goal_productive_task_kinds")
        or gate.get("required_task_kinds")
    )
    forced = gate.get("forced_selected_task")
    if isinstance(forced, dict):
        kinds.update(
            normalize_task_kinds(
                [
                    forced.get("selected_task_kind"),
                    forced.get("task_kind"),
                    forced.get("kind"),
                    forced.get("rung"),
                ]
            )
        )
    options = gate.get("forced_selected_task_options")
    if isinstance(options, list):
        for option in options:
            if isinstance(option, dict):
                kinds.update(
                    normalize_task_kinds(
                        [
                            option.get("selected_task_kind"),
                            option.get("task_kind"),
                            option.get("kind"),
                            option.get("rung"),
                        ]
                    )
                )
    return kinds


def gate_constrains_disposition(name: str, gate: dict[str, Any]) -> bool:
    return any(
        (
            bool_value(gate.get("constrains_disposition")),
            bool_value(gate.get("hard_stop_required")),
            bool_value(gate.get("hard_gate")),
            bool_value(gate.get("requires_goal_productive_next")),
            bool_value(gate.get("requires_goal_productive_or_user_escalation")),
            str(gate.get("status") or "").lower() == "block",
            name == "command_surface_budget" and bool_value(gate.get("budget_exceeded")),
        )
    )


def extract_disposition_gates(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        gates: list[dict[str, Any]] = []
        for item in value:
            gates.extend(extract_disposition_gates(item))
        return gates
    if not isinstance(value, dict):
        return []
    gate_names = (
        "command_surface_budget",
        "root_axis_gate",
        "goal_distance_gate",
        "feature_symbol_gate",
        "gt_constraint_conflict_gate",
        "semantic_signature_gate",
        "adapter_wiring_gate",
        "chain_stall_forced_retarget_gate",
    )
    gates = []
    for name in gate_names:
        child = value.get(name)
        if isinstance(child, dict):
            gate = dict(child)
            gate.setdefault("name", name)
            gates.append(gate)
    for key in ("gates", "disposition_gates"):
        raw = value.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    gate = dict(item)
                    gate.setdefault("name", str(gate.get("gate") or gate.get("code") or key))
                    gates.append(gate)
    if not gates and any(key in value for key in ("allowed_dispositions", "hard_stop_required", "constrains_disposition")):
        gate = dict(value)
        gate.setdefault("name", str(value.get("name") or value.get("gate") or "gate"))
        gates.append(gate)
    return gates


def effective_allowed_dispositions(gates: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    constraining: list[set[str]] = []
    basis: dict[str, Any] = {}
    for index, gate in enumerate(gates):
        name = str(gate.get("name") or gate.get("gate") or f"gate_{index}")
        allowed = gate_allowed_dispositions(name, gate)
        constrains = gate_constrains_disposition(name, gate)
        basis[name] = {
            "allowed_dispositions": sorted(allowed),
            "constrains_disposition": constrains,
        }
        task_kinds = gate_allowed_task_kinds(gate)
        if task_kinds:
            basis[name]["allowed_task_kinds"] = sorted(task_kinds)
        if constrains:
            constraining.append(allowed)
    if constraining:
        effective = set.intersection(*constraining) | SAFETY_VALVES
    else:
        effective = set(DISPOSITION_UNIVERSE)
    return sorted(effective), basis


def item_disposition(item: dict[str, Any]) -> str:
    for key in ("disposition", "selected_disposition", "progress_target", "selected_task_source", "selected_task_kind"):
        value = str(item.get(key) or "").strip().lower()
        if value in DISPOSITION_UNIVERSE:
            return value
        if "consolidation" in value:
            return "consolidation"
        if "goal_productive" in value:
            return "goal_productive"
        if "terminal" in value:
            return "terminal_blocked"
        if "user_escalation" in value or "user-escalation" in value:
            return "user_escalation"
    return ""


def consolidation_streak(items: list[dict[str, Any]]) -> int:
    streak = 0
    for item in items:
        if item_disposition(item) != "consolidation":
            break
        effective = str(item.get("effective_progress_kind") or item.get("progress_kind") or "").strip().lower()
        if effective and effective != "governance_only":
            break
        streak += 1
    return streak


def normalize_ladder_rung(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_")
    if not text:
        return None
    text = RUNG_ALIASES.get(text, text)
    return text if text in LADDER_RANK else None


def infer_ladder_rung(*values: Any) -> str | None:
    text = " ".join(scalar_strings(list(values))).lower().replace("-", "_")
    if not text:
        return None
    if "unseen" in text or "holdout_batch" in text:
        return "unseen_batch"
    if "reconstruction" in text:
        return "reconstruction"
    if "pov" in text or "focalization" in text or "timeline" in text:
        return "pov_timeline"
    if "causal" in text or "temporal" in text or "story_order" in text:
        return "causal_temporal"
    if "coref" in text or "coreference" in text or "mention_map" in text:
        return "entity_coref"
    if "multi_window" in text or "multi window" in text:
        return "multi_window"
    if "single_window" in text or "single window" in text:
        return "single_window"
    return None


def first_named_value(values: list[Any], keys: set[str]) -> str | None:
    for value in values:
        collected = collect_values_by_key(value, keys)
        if collected:
            return collected[0][:240]
    return None


def blocker_mutation_kind(
    curr_signature: str,
    curr_rung: str | None,
    curr_root_family: str,
    prev: dict[str, Any] | None,
) -> str:
    if not prev:
        return "initial"
    prev_signature = str(prev.get("blocker_signature") or prev.get("semantic_signature") or "").strip()
    prev_root = row_root_family(prev)
    curr_root = curr_root_family or normalize_root_family_key(curr_signature)
    if curr_root and prev_root and curr_root == prev_root:
        if curr_signature and prev_signature and curr_signature == prev_signature:
            return "repeat"
        return "facet_rename"
    if curr_root and prev_root and curr_root != prev_root:
        return "forward_mutation"
    prev_rung = normalize_ladder_rung(prev.get("blocker_ladder_rung")) or infer_ladder_rung(prev_signature)
    curr_rank = LADDER_RANK.get(curr_rung or "")
    prev_rank = LADDER_RANK.get(prev_rung or "")
    if curr_rank is not None and prev_rank is not None and curr_rank > prev_rank:
        return "forward_mutation"
    if curr_signature and prev_signature and curr_signature == prev_signature:
        return "repeat"
    return "lateral"


def forward_mutation_streak(rows: list[dict[str, Any]], family_key: str) -> int:
    streak = 0
    for row in reversed(recent_family_rows(rows, family_key)):
        if row.get("blocker_mutation_kind") == "forward_mutation":
            streak += 1
            continue
        break
    return streak


def explicit_result_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in PASS_STATUS_VALUES:
            return True
        if lowered in FAIL_STATUS_VALUES:
            return False
    return None


def mapping_result_bool(mapping: dict[str, Any]) -> bool | None:
    for key, value in mapping.items():
        normalized = str(key).strip().lower()
        if normalized in VALIDATOR_RESULT_KEYS:
            result = explicit_result_bool(value)
            if result is not None:
                return result
    return None


def collect_result_bools(value: Any) -> list[bool]:
    results: list[bool] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            result = mapping_result_bool(item)
            if result is not None:
                results.append(result)
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return results


def first_int_by_key(mapping: dict[str, Any], keys: set[str]) -> int | None:
    for key, value in mapping.items():
        if str(key).strip().lower() not in keys:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def validator_integrity_gate(*values: Any) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    def inspect(item: Any, path: str = "$") -> None:
        if isinstance(item, dict):
            top_result = mapping_result_bool(item)
            child_results: list[bool] = []
            for key in VALIDATOR_CHILD_KEYS:
                child = item.get(key)
                if isinstance(child, (dict, list)):
                    child_results.extend(collect_result_bools(child))
            if top_result is True and any(result is False for result in child_results):
                findings.append(
                    {
                        "kind": "integrity_mismatch",
                        "path": path,
                        "top_level_result": True,
                        "embedded_result_count": len(child_results),
                        "embedded_failed_count": sum(1 for result in child_results if result is False),
                    }
                )
            declared = first_int_by_key(item, POPULATION_COUNT_KEYS)
            inspected = first_int_by_key(item, INSPECTED_COUNT_KEYS)
            if declared is not None and inspected is not None and declared > 0 and inspected < declared:
                findings.append(
                    {
                        "kind": "under_detection",
                        "path": path,
                        "declared_population_count": declared,
                        "inspected_count": inspected,
                    }
                )
            for key, child in item.items():
                inspect(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                inspect(child, f"{path}[{index}]")

    for value in values:
        inspect(value)
    mismatch = any(item["kind"] == "integrity_mismatch" for item in findings)
    under_detection = any(item["kind"] == "under_detection" for item in findings)
    blocked = mismatch or under_detection
    return {
        "gate": "G-INTEGRITY",
        "validator_integrity": "mismatch" if mismatch else "ok",
        "validator_coverage": "under_detection" if under_detection else "ok",
        "status": "block" if blocked else "ok",
        "hard_stop_required": blocked,
        "constrains_disposition": blocked,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "findings": findings[:20],
    }


def classify_task_correction(
    *,
    current_check_ids: set[str],
    current_frontiers: set[str],
    provider_request_count: int,
    changed_vs_previous: bool,
    semantic_progress: bool,
    values: list[Any],
) -> str:
    text = " ".join(scalar_strings(values)).lower()
    detection = bool(current_check_ids or current_frontiers or DETECTION_TERMS_RE.search(text))
    correction = bool(
        provider_request_count > 0
        or changed_vs_previous
        or semantic_progress
        or CORRECTION_TERMS_RE.search(text)
    )
    if detection and correction:
        return "mixed"
    if detection:
        return "detection"
    if correction:
        return "correction"
    return "unknown"


def detection_only_streak(rows: list[dict[str, Any]], root_family_key: str, current_detection_only: bool) -> int:
    streak = 1 if current_detection_only else 0
    if not current_detection_only:
        return 0
    for row in reversed(rows):
        if row_root_family(row) != root_family_key:
            continue
        if bool_value(row.get("detection_only")) and not bool_value(row.get("semantic_progress")):
            streak += 1
            continue
        break
    return streak


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def active_advice_hashes(root: Path) -> set[str]:
    hashes: set[str] = set()
    active_dir = root / ".agent_advice" / "active"
    for path in sorted(active_dir.glob("*.md")) if active_dir.is_dir() else []:
        digest = sha256_file(path)
        if digest:
            hashes.add(digest)
    index_path = root / ".agent_advice" / "index.jsonl"
    for event in read_jsonl(index_path):
        if str(event.get("status") or "").lower() != "active":
            continue
        for key in ("path", "raw_source_path"):
            raw_path = event.get(key)
            if not raw_path:
                continue
            path = Path(str(raw_path))
            if not path.is_absolute():
                path = root / path
            digest = sha256_file(path)
            if digest:
                hashes.add(digest)
    return hashes


def advice_coherence_finding(root: Path) -> dict[str, Any] | None:
    root_docs = [root / name for name in sorted(ROOT_STEERING_DOC_NAMES) if (root / name).is_file()]
    if not root_docs:
        return None
    known_hashes = active_advice_hashes(root)
    orphans: list[str] = []
    for path in root_docs:
        digest = sha256_file(path)
        if digest and digest in known_hashes:
            continue
        orphans.append(rel_path(root, path))
    if not orphans:
        return None
    return {
        "severity": "warn",
        "code": "orphan_advice_not_intaken",
        "message": "root steering advice exists but is not represented in .agent_advice/active; intake it before relying on derive to consume it.",
        "evidence": {"orphans": orphans, "active_advice_dir": ".agent_advice/active"},
        "action": "$manage-external-advice intake",
    }


def semantic_progress_value(value: Any) -> bool | None:
    if not isinstance(value, dict):
        return None
    for key in ("semantic_progress", "checks.semantic_progress", "output_delta.semantic_progress"):
        current: Any = value
        for part in key.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if current is not None:
            return bool_value(current)
    return None


def validator_disagreement_finding(runner_validation: Any, output_delta: Any) -> dict[str, Any] | None:
    runner_sp = semantic_progress_value(runner_validation)
    delta_sp = semantic_progress_value(output_delta)
    if runner_sp is True and delta_sp is False:
        return {
            "severity": "block",
            "code": "validator_disagreement",
            "message": (
                "strict runner validator and output_delta disagree on semantic_progress; "
                "use the conservative output_delta verdict and do not treat runner pass as goal-productive evidence."
            ),
            "evidence": {"runner_semantic_progress": runner_sp, "output_delta_semantic_progress": delta_sp},
        }
    return None


def quality_metric_value(quality: dict[str, Any], key: str) -> float:
    aliases = {
        "causal_edge_count": ("causal_edge_count", "causal_or_temporal_edge_count", "causal_temporal_edge_count"),
        "windows_covered": ("windows_covered", "source_windows_covered", "window_count", "selected_source_window_count"),
    }
    for candidate in aliases.get(key, (key,)):
        if candidate in quality:
            return float_value(quality.get(candidate))
    return 0.0


def high_water_metric_value(high_water: dict[str, Any], key: str) -> float:
    aliases = {
        "causal_edge_count": ("causal_edge_count", "causal_or_temporal_edge_count", "ever_causal_edge"),
        "windows_covered": ("windows_covered", "source_windows_covered", "window_count"),
    }
    for candidate in aliases.get(key, (key,)):
        if candidate in high_water:
            return float_value(high_water.get(candidate))
    return 0.0


def coverage_quality_delta_gate(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    epsilon: float,
) -> dict[str, Any]:
    current = {key: quality_metric_value(quality, key) for key in QUALITY_DELTA_KEYS}
    previous = {key: high_water_metric_value(prev_high, key) for key in QUALITY_DELTA_KEYS}
    improved_fields = [
        key
        for key in QUALITY_DELTA_KEYS
        if current[key] > previous[key] + (epsilon if key.endswith("_ratio") else 0.0)
    ]
    provider_dispatch_delta = provider_request_count > 0 and not bool_value(prev_high.get("ever_provider_dispatch"))
    previous_high_water_all_zero = all(previous[key] <= 0 for key in QUALITY_DELTA_KEYS)
    current_quality_all_zero = all(current[key] <= 0 for key in QUALITY_DELTA_KEYS)
    return {
        "gate": "G-COV",
        "quality_delta_pass": bool(improved_fields),
        "improved_fields": improved_fields,
        "current_quality_vector": current,
        "previous_high_water_vector": previous,
        "provider_dispatch_delta": provider_dispatch_delta,
        "previous_high_water_all_zero": previous_high_water_all_zero,
        "current_quality_all_zero": current_quality_all_zero,
        "high_water_all_zero": previous_high_water_all_zero and current_quality_all_zero,
        "status": "pass" if improved_fields else "block",
    }


def provider_scale_dispatch_gate(
    prev_high: dict[str, Any],
    coverage_gate: dict[str, Any],
    provider_request_count: int,
) -> dict[str, Any]:
    dispatch_required = (
        not bool_value(prev_high.get("ever_provider_dispatch"))
        and bool_value(coverage_gate.get("high_water_all_zero"))
        and provider_request_count == 0
    )
    return {
        "gate": "G-DISPATCH",
        "ever_provider_dispatch": bool_value(prev_high.get("ever_provider_dispatch")) or provider_request_count > 0,
        "provider_request_count": provider_request_count,
        "high_water_all_zero": bool_value(coverage_gate.get("high_water_all_zero")),
        "dispatch_required": dispatch_required,
        "hard_stop_required": dispatch_required,
        "constrains_disposition": dispatch_required,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "blocked_surface_only_work": dispatch_required,
        "status": "block" if dispatch_required else "ok",
    }


def row_vector_delta_passed(row: dict[str, Any]) -> bool:
    coverage_gate = row.get("coverage_quality_delta_gate")
    substance_gate = row.get("substance_delta_gate")
    return any(
        (
            bool_value(row.get("semantic_progress")),
            isinstance(coverage_gate, dict) and bool_value(coverage_gate.get("quality_delta_pass")),
            isinstance(substance_gate, dict) and bool_value(substance_gate.get("substance_delta_pass")),
        )
    )


def adapter_contract_unmet_fields(
    *,
    facet_root_map_missing: bool,
    substance_gate: dict[str, Any],
    quality: dict[str, Any],
) -> list[str]:
    unmet: list[str] = []
    if facet_root_map_missing:
        unmet.append("facet_root_map")
    if str(substance_gate.get("status") or "").lower() == "missing" or not numeric_vector(
        substance_gate.get("current_substance_vector")
    ):
        unmet.append("substance_metrics")
    if not numeric_vector(quality):
        unmet.append("quality_vector")
    return sorted(dict.fromkeys(unmet))


def row_adapter_contract_unmet(row: dict[str, Any]) -> list[str]:
    if isinstance(row.get("adapter_contract_unmet"), list):
        return list_values(row.get("adapter_contract_unmet"))
    substance_gate = row.get("substance_delta_gate") if isinstance(row.get("substance_delta_gate"), dict) else {}
    return adapter_contract_unmet_fields(
        facet_root_map_missing=bool_value(row.get("facet_root_map_missing")),
        substance_gate=substance_gate,
        quality=row.get("quality_vector") if isinstance(row.get("quality_vector"), dict) else {},
    )


def adapter_missing_streak(
    rows: list[dict[str, Any]],
    artifact_family: str,
    current_contract_unmet: list[str],
    current_no_delta: bool,
) -> int:
    if not current_contract_unmet or not current_no_delta:
        return 0
    streak = 1
    for row in reversed(rows):
        if str(row.get("artifact_family") or "") != artifact_family:
            continue
        if row_adapter_contract_unmet(row) and not row_vector_delta_passed(row):
            streak += 1
            continue
        break
    return streak


def adapter_mandate_gate(
    rows: list[dict[str, Any]],
    *,
    artifact_family: str,
    contract_unmet: list[str],
    current_no_delta: bool,
    cap: int,
) -> dict[str, Any]:
    streak = adapter_missing_streak(rows, artifact_family, contract_unmet, current_no_delta)
    required = bool(contract_unmet) and current_no_delta and streak >= max(1, cap)
    return {
        "gate": "G-ADAPTER",
        "adapter_mandate_required": required,
        "adapter_missing_streak": streak,
        "adapter_missing_streak_cap": max(1, cap),
        "adapter_contract_unmet": contract_unmet,
        "quality_high_water_unimproved": current_no_delta,
        "status": "block" if required else ("warn" if contract_unmet else "ok"),
        "constrains_disposition": required,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }


def adapter_wiring_gate(
    *,
    registered: bool,
    loaded: bool,
    expected_path: str | None,
    loaded_path: str | None,
    load_error: str | None,
) -> dict[str, Any]:
    defect = registered and not loaded
    return {
        "gate": "G-ADAPTER-WIRING",
        "adapter_registered": registered,
        "adapter_loaded": loaded,
        "adapter_expected_path": expected_path,
        "adapter_path": loaded_path or expected_path,
        "adapter_load_error": load_error,
        "adapter_wiring_defect": defect,
        "self_inflicted_gate_defect": defect,
        "local": defect,
        "in_scope": defect,
        "actionable": defect,
        "status": "block" if defect else ("ok" if loaded else "not_applicable"),
        "constrains_disposition": defect,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": ["adapter_wiring_fix", "adapter_load_fix"],
        "recommended_disposition": "self_inflicted_gate_defect" if defect else None,
    }


def cumulative_goal_distance_scope_key(artifact_family: str, root_family_key: str, facet_root_map_missing: bool) -> str:
    if facet_root_map_missing:
        return f"artifact_family:{normalize_root_family_key(artifact_family)}"
    return f"root_family:{normalize_root_family_key(root_family_key)}"


def row_goal_distance_scope(row: dict[str, Any], artifact_family: str, root_family_key: str, facet_root_map_missing: bool) -> str:
    existing = str(row.get("cumulative_goal_distance_scope_key") or "").strip()
    if existing:
        return existing
    if facet_root_map_missing:
        return f"artifact_family:{normalize_root_family_key(row.get('artifact_family') or artifact_family)}"
    return f"root_family:{normalize_root_family_key(row.get('root_family_key') or row.get('blocker_root_family') or root_family_key)}"


def cumulative_goal_distance_gate(
    rows: list[dict[str, Any]],
    *,
    artifact_family: str,
    root_family_key: str,
    facet_root_map_missing: bool,
    current_no_delta: bool,
    high_water: dict[str, Any],
    current_cycle_id: str,
    cap: int,
) -> dict[str, Any]:
    scope_key = cumulative_goal_distance_scope_key(artifact_family, root_family_key, facet_root_map_missing)
    if not current_no_delta:
        return {
            "gate": "G-CHAIN",
            "cumulative_goal_distance_scope_key": scope_key,
            "cumulative_goal_distance_stall_streak": 0,
            "cumulative_goal_distance_stall_cap": max(1, cap),
            "cumulative_goal_distance_stalled": False,
            "high_water_vector": numeric_vector(high_water),
            "high_water_last_improved_cycle": current_cycle_id,
            "status": "ok",
            "constrains_disposition": False,
            "allowed_dispositions": ["terminal_blocked", "user_escalation"],
        }
    streak = 1 if current_no_delta else 0
    last_improved_cycle = current_cycle_id if not current_no_delta else None
    for row in reversed(rows):
        if row_goal_distance_scope(row, artifact_family, root_family_key, facet_root_map_missing) != scope_key:
            continue
        if row_vector_delta_passed(row):
            last_improved_cycle = str(row.get("cycle_id") or "") or None
            break
        streak += 1
    stalled = current_no_delta and streak >= max(1, cap)
    return {
        "gate": "G-CHAIN",
        "cumulative_goal_distance_scope_key": scope_key,
        "cumulative_goal_distance_stall_streak": streak,
        "cumulative_goal_distance_stall_cap": max(1, cap),
        "cumulative_goal_distance_stalled": stalled,
        "high_water_vector": numeric_vector(high_water),
        "high_water_last_improved_cycle": last_improved_cycle,
        "status": "block" if stalled else "ok",
        "constrains_disposition": stalled,
        "allowed_dispositions": ["terminal_blocked", "user_escalation"],
    }


def first_actionable_capability_ladder_option(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    items: list[Any]
    if isinstance(value, dict):
        raw_items = (
            value.get("rungs")
            or value.get("items")
            or value.get("options")
            or value.get("capability_ladder")
            or value.get("next_rungs")
        )
        items = raw_items if isinstance(raw_items, list) else [value]
    elif isinstance(value, list):
        items = value
    else:
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if bool_value(item.get("satisfied") or item.get("complete") or item.get("blocked")):
            continue
        actionable_value = item.get("actionable")
        if actionable_value is not None and not bool_value(actionable_value):
            continue
        kind = normalize_task_kind(
            item.get("selected_task_kind")
            or item.get("task_kind")
            or item.get("kind")
            or item.get("rung")
            or item.get("name")
        )
        if not kind:
            continue
        return {
            "selected_task_kind": kind,
            "task_kind": kind,
            "rung": item.get("rung") or item.get("name") or kind,
            "provider_dependency": item.get("provider_dependency"),
            "authority_allowed": item.get("authority_allowed"),
            "uses_only_local_data": item.get("uses_only_local_data"),
            "source": "capability_ladder",
        }
    return None


def chain_stall_forced_retarget_gate(
    chain_gate: dict[str, Any],
    *,
    blocker_mutation: str,
    adapter_gate: dict[str, Any],
    capability_ladder_option: dict[str, Any] | None,
) -> dict[str, Any]:
    stalled = bool_value(chain_gate.get("cumulative_goal_distance_stalled"))
    streak = int_metric(chain_gate.get("cumulative_goal_distance_stall_streak"))
    cap = max(1, int_metric(chain_gate.get("cumulative_goal_distance_stall_cap")) or 1)
    lateral = blocker_mutation in {"facet_rename", "lateral", "repeat"}
    force = stalled and lateral and streak >= cap * 2
    options: list[dict[str, Any]] = []
    if force and bool_value(adapter_gate.get("adapter_wiring_defect")):
        options.append(
            {
                "selected_task_kind": "adapter_wiring_fix",
                "task_kind": "adapter_wiring_fix",
                "source": "adapter_wiring_gate",
                "actionable": True,
            }
        )
    if force and capability_ladder_option:
        options.append({**capability_ladder_option, "actionable": True})
    return {
        "gate": "G-CHAIN-FORCED-RETARGET",
        "chain_stall_force_retarget": force,
        "cumulative_goal_distance_stall_streak": streak,
        "cumulative_goal_distance_stall_cap": cap,
        "blocker_mutation_kind": blocker_mutation,
        "forced_selected_task_options": options,
        "forced_selected_task": options[0] if options else None,
        "status": "block" if force and options else ("warn" if force else "ok"),
        "constrains_disposition": force and bool(options),
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "allowed_task_kinds": [option["selected_task_kind"] for option in options if option.get("selected_task_kind")],
    }


def semantic_progress_from_high_water(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    epsilon: float,
) -> bool:
    if quality.get("quality_signal_confidence") == "low":
        return False
    return bool(coverage_quality_delta_gate(quality, prev_high, provider_request_count, epsilon)["quality_delta_pass"])


def updated_high_water(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    allowed_quality_keys: set[str] | None = None,
) -> dict[str, Any]:
    def updated(key: str) -> bool:
        return allowed_quality_keys is None or key in allowed_quality_keys

    return {
        "event_named_ratio": (
            max(high_water_metric_value(prev_high, "event_named_ratio"), quality_metric_value(quality, "event_named_ratio"))
            if updated("event_named_ratio")
            else high_water_metric_value(prev_high, "event_named_ratio")
        ),
        "proper_noun_character_ratio": max(
            high_water_metric_value(prev_high, "proper_noun_character_ratio"),
            quality_metric_value(quality, "proper_noun_character_ratio"),
        )
        if updated("proper_noun_character_ratio")
        else high_water_metric_value(prev_high, "proper_noun_character_ratio"),
        "coreference_resolved_ratio": max(
            high_water_metric_value(prev_high, "coreference_resolved_ratio"),
            quality_metric_value(quality, "coreference_resolved_ratio"),
        )
        if updated("coreference_resolved_ratio")
        else high_water_metric_value(prev_high, "coreference_resolved_ratio"),
        "causal_edge_count": max(
            int_metric(high_water_metric_value(prev_high, "causal_edge_count")),
            int_metric(quality_metric_value(quality, "causal_edge_count")),
        )
        if updated("causal_edge_count")
        else int_metric(high_water_metric_value(prev_high, "causal_edge_count")),
        "windows_covered": max(
            int_metric(high_water_metric_value(prev_high, "windows_covered")),
            int_metric(quality_metric_value(quality, "windows_covered")),
        )
        if updated("windows_covered")
        else int_metric(high_water_metric_value(prev_high, "windows_covered")),
        "ever_causal_edge": bool_value(prev_high.get("ever_causal_edge"))
        or (updated("causal_edge_count") and bool_value(quality.get("causal_edge_present"))),
        "ever_provider_dispatch": bool_value(prev_high.get("ever_provider_dispatch")) or provider_request_count > 0,
    }


def previous_primary_metric_value(latest: dict[str, Any] | None) -> float:
    if not isinstance(latest, dict):
        return 0.0
    gate = latest.get("primary_metric_gate")
    if isinstance(gate, dict):
        for key in ("primary_metric_high_water", "primary_metric_value", "value"):
            if key in gate:
                return float_value(gate.get(key))
    for key in ("primary_metric_high_water", "primary_metric_value"):
        if key in latest:
            return float_value(latest.get(key))
    return 0.0


def primary_metric_zero_movement_streak(
    rows: list[dict[str, Any]],
    scope_key: str,
    moved: bool,
) -> int:
    if moved:
        return 0
    streak = 1
    for row in reversed(rows):
        gate = row.get("primary_metric_gate")
        if not isinstance(gate, dict):
            continue
        row_scope = str(gate.get("primary_metric_scope_key") or row.get("cumulative_goal_distance_scope_key") or "")
        if row_scope != scope_key:
            continue
        if bool_value(gate.get("primary_metric_high_water_moved")):
            break
        streak += 1
    return streak


def normalize_primary_metric_gate(
    value: Any,
    *,
    previous_value: float,
    rows: list[dict[str, Any]],
    scope_key: str,
    cap: int,
    epsilon: float,
    provenance: dict[str, str],
    provenance_hook_provided: bool,
) -> dict[str, Any]:
    if value is None:
        return {
            "gate": "G-CHAIN-PRIMARY-METRIC",
            "evaluation_status": "not_evaluated",
            "status": "not_evaluated",
            "constrains_disposition": False,
        }
    source = value
    if isinstance(value, dict) and isinstance(value.get("primary_metric"), dict):
        source = value["primary_metric"]
    if not isinstance(source, dict):
        source = {"value": value}
    metric_id = str(source.get("metric_id") or source.get("name") or "primary_metric")
    current_value = float_value(
        source.get("value")
        if "value" in source
        else source.get("primary_metric_value")
        if "primary_metric_value" in source
        else source.get("current")
    )
    previous = float_value(source.get("previous_value") or source.get("previous_primary_metric") or previous_value)
    raw_moved = (
        bool_value(source.get("primary_metric_high_water_moved"))
        if "primary_metric_high_water_moved" in source
        else current_value > previous + epsilon
    )
    metric_provenance = normalize_provenance_label(
        source.get("evidence_provenance")
        or source.get("provenance")
        or provenance_for_metric(metric_id, provenance, provenance_hook_provided)
        or provenance_for_metric("primary_metric", provenance, provenance_hook_provided)
    )
    independent = not provenance_hook_provided or metric_provenance == "independently_verified"
    moved = raw_moved and independent
    attested_only = raw_moved and not independent
    zero_streak = primary_metric_zero_movement_streak(rows, scope_key, moved)
    adapter_stalled = bool_value(
        source.get("primary_metric_stalled")
        or (value.get("primary_metric_stalled") if isinstance(value, dict) else False)
    )
    stalled = adapter_stalled or (not moved and zero_streak >= max(1, cap))
    return {
        "gate": "G-CHAIN-PRIMARY-METRIC",
        "metric_id": metric_id,
        "primary_metric_value": current_value,
        "previous_primary_metric_value": previous,
        "primary_metric_high_water": max(previous, current_value) if moved else previous,
        "primary_metric_high_water_moved": moved,
        "raw_primary_metric_high_water_moved": raw_moved,
        "evidence_provenance": metric_provenance,
        "attested_only_movement": attested_only,
        "primary_metric_scope_key": scope_key,
        "primary_metric_zero_movement_streak": zero_streak,
        "primary_metric_stall_cap": max(1, cap),
        "primary_metric_stalled": stalled,
        "evaluation_status": "pass" if moved else "fail",
        "status": "block" if stalled else ("warn" if attested_only else ("pass" if moved else "ok")),
        "constrains_disposition": stalled,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }


def evaluate(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    root = Path(args.root).resolve()
    registry_path = Path(args.registry_path)
    if not registry_path.is_absolute():
        registry_path = root / registry_path
    legacy_family_key = normalize_family_key(args.artifact_family, args.semantic_signature)
    family_key = legacy_family_key
    registry_rows = load_registry(registry_path)
    existing_cycle = next(
        (row for row in reversed(registry_rows) if row.get("family_key") == family_key and row.get("cycle_id") == args.cycle_id),
        None,
    )
    latest = next((row for row in reversed(registry_rows) if row.get("family_key") == family_key), None)
    prev_high = dict((latest or {}).get("high_water_mark") or default_high_water())
    prev_count = int((latest or {}).get("micro_hardening_count") or 0)
    prev_fingerprint = (latest or {}).get("current_output_fingerprint")

    paths = load_artifact_paths(root, args.artifact_paths_json, args.artifact_path)
    changed_files = load_changed_files(
        root,
        getattr(args, "changed_files_json", None),
        getattr(args, "changed_file", []) or [],
    )
    adapter_candidates = domain_adapter_candidate_paths(root, getattr(args, "domain_adapter", None))
    adapter_registered = bool(adapter_candidates)
    adapter_expected_path = adapter_candidates[0].expanduser().resolve().as_posix() if adapter_candidates else None
    domain_adapter, domain_adapter_path, domain_adapter_error = load_domain_adapter(root, getattr(args, "domain_adapter", None))
    adapter_load_gate = adapter_wiring_gate(
        registered=adapter_registered,
        loaded=domain_adapter is not None,
        expected_path=adapter_expected_path,
        loaded_path=domain_adapter_path,
        load_error=domain_adapter_error,
    )
    quality, evidence_paths, insufficient_reason = (
        ({}, [], domain_adapter_error)
        if domain_adapter_error
        else compute_quality(root, paths, domain_adapter)
    )
    provider_request_count = max(0, int(args.provider_request_count or 0))
    gate_inputs: list[dict[str, Any]] = []
    if bool_value(adapter_load_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "adapter_wiring_gate", **adapter_load_gate})
    for raw_gate in getattr(args, "gate_state_json", []) or []:
        gate_inputs.extend(extract_disposition_gates(load_json_value(root, raw_gate)))
    runner_validation = load_json_value(root, getattr(args, "runner_validation_json", None))
    output_delta = load_json_value(root, getattr(args, "output_delta_json", None))
    failure_autopsies = load_json_values(root, getattr(args, "failure_autopsy_json", []) or [])
    validator_gate = validator_integrity_gate(runner_validation, output_delta, gate_inputs)
    if bool_value(validator_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "validator_integrity_gate", **validator_gate})
    measurement_ids_value = load_json_value(root, getattr(args, "measurement_check_ids_json", None))
    current_root_key = (
        args.root_key
        or first_named_value([runner_validation, output_delta, quality, gate_inputs], ROOT_KEY_KEYS)
        or family_key
    )
    repo_owned_source_roots_value, repo_owned_source_roots_error = call_adapter(
        domain_adapter,
        "repo_owned_source_roots",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
    )
    repo_owned_source_roots = normalize_repo_owned_source_roots(repo_owned_source_roots_value)
    repo_owned_source_roots_status = (
        "provided"
        if repo_owned_source_roots
        else ("error" if repo_owned_source_roots_error else "not_provided")
    )
    previous_baseline_source = "registry_latest"
    previous_baseline_error: str | None = None
    previous_baseline_value, previous_baseline_call_error = call_adapter(
        domain_adapter,
        "previous_accepted_fp",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        registry_latest=latest,
    )
    previous_adapter_fp, previous_adapter_high, previous_adapter_reason = normalize_previous_accepted_baseline(previous_baseline_value)
    if previous_baseline_call_error:
        previous_baseline_error = previous_baseline_call_error
    elif previous_adapter_reason:
        previous_baseline_error = previous_adapter_reason
    if previous_adapter_fp:
        prev_fingerprint = previous_adapter_fp
        previous_baseline_source = "domain_adapter.previous_accepted_fp"
    if previous_adapter_high:
        prev_high = {**prev_high, **previous_adapter_high}
        previous_baseline_source = "domain_adapter.previous_accepted_fp"
    changed_vs_previous = bool(prev_fingerprint and quality.get("current_output_fingerprint") != prev_fingerprint)
    facet_map_error: str | None = None
    facet_map_value = load_json_value(root, getattr(args, "facet_root_map_json", None))
    if facet_map_value is None:
        facet_map_value, facet_map_error = call_adapter(
            domain_adapter,
            "facet_root_map",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
        )
        if facet_map_error:
            facet_map_value = None
    facet_root_map = normalize_facet_root_map(facet_map_value)
    preliminary_changed = bool(prev_fingerprint and quality.get("current_output_fingerprint") != prev_fingerprint)
    preliminary_semantic = False if insufficient_reason else semantic_progress_from_high_water(quality, prev_high, provider_request_count, args.epsilon)
    current_terminal_outcome_key = terminal_outcome_key(output_delta, preliminary_changed, preliminary_semantic)
    raw_root_family_key = collapse_root_family(facet_root_map, current_root_key, args.semantic_signature, args.artifact_family)
    terminal_family_key, terminal_family_source, terminal_family_fallback = terminal_outcome_root_family(
        facet_root_map,
        artifact_family=args.artifact_family,
        outcome_key=current_terminal_outcome_key,
        root_key=current_root_key,
        semantic_signature=args.semantic_signature,
    )
    facet_root_map_missing = not bool(facet_root_map)
    current_root_family_key = terminal_family_key if facet_root_map_missing else raw_root_family_key
    latest_terminal_family = latest_root_family_row(registry_rows, current_root_family_key)
    if facet_root_map_missing:
        family_key = terminal_family_key
        existing_cycle = existing_cycle or next(
            (row for row in reversed(registry_rows) if row.get("family_key") == family_key and row.get("cycle_id") == args.cycle_id),
            None,
        )
        latest = latest_terminal_family or latest
        prev_count = max(prev_count, int((latest or {}).get("micro_hardening_count") or 0))
    failure_contexts = [runner_validation, output_delta, quality, gate_inputs, *failure_autopsies]
    root_dominant_parameter_key = (
        first_named_value(failure_contexts, {"root_dominant_parameter_key", "dominant_parameter_key", "deficit_axis"})
        or current_root_key
    )
    execution_stage_ladder_value, execution_stage_ladder_error = call_adapter(
        domain_adapter,
        "execution_stage_ladder",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        failure_autopsies=failure_autopsies,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
    )
    if execution_stage_ladder_value is None:
        execution_stage_ladder_value = first_field_value(failure_contexts, {"execution_stage_ladder", "stage_ladder"})
    terminal_stage_map_value, terminal_stage_map_error = call_adapter(
        domain_adapter,
        "terminal_classification_stage_map",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        failure_autopsies=failure_autopsies,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
    )
    failure_surface_gate = terminal_stage_resolution_gate(
        ladder_value=execution_stage_ladder_value,
        classification_map_value=terminal_stage_map_value,
        contexts=failure_contexts,
        root_family_key=current_root_family_key,
        dominant_parameter=str(root_dominant_parameter_key),
    )
    if execution_stage_ladder_error:
        failure_surface_gate["execution_stage_ladder_error"] = execution_stage_ladder_error
    if terminal_stage_map_error:
        failure_surface_gate["terminal_classification_stage_map_error"] = terminal_stage_map_error
    effective_count_key = str(failure_surface_gate.get("failure_surface_count_key") or current_root_family_key)
    if bool_value(failure_surface_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "failure_surface_stage_gate", **failure_surface_gate})
    input_contract_gate = same_input_contract_gate(failure_contexts)
    if bool_value(input_contract_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "same_input_contract_gate", **input_contract_gate})
    instrumentation_threshold_value, instrumentation_threshold_error = call_adapter(
        domain_adapter,
        "instrumentation_trigger_threshold",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        failure_autopsies=failure_autopsies,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
    )
    instrumentation_threshold = (
        int(float_value(instrumentation_threshold_value))
        or int(getattr(args, "instrumentation_trigger_threshold", INSTRUMENTATION_TRIGGER_THRESHOLD_DEFAULT))
        or INSTRUMENTATION_TRIGGER_THRESHOLD_DEFAULT
    )
    diagnostics_gate = diagnostics_unavailable_gate(
        registry_rows=registry_rows,
        failure_surface_count_key=failure_surface_gate.get("failure_surface_count_key"),
        contexts=failure_contexts,
        threshold=instrumentation_threshold,
    )
    if instrumentation_threshold_error:
        diagnostics_gate["adapter_error"] = instrumentation_threshold_error
    if bool_value(diagnostics_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "diagnostics_unavailable_gate", **diagnostics_gate})
    current_check_ids = set(getattr(args, "measurement_check_id", []) or [])
    current_check_ids.update(extract_check_ids(measurement_ids_value, runner_validation, output_delta, quality, gate_inputs))
    current_frontiers = {frontier_key(item) for item in getattr(args, "measurement_frontier", []) or [] if item}
    current_frontiers.update(extract_frontier_observations(runner_validation, output_delta, quality, gate_inputs))
    coverage_gate = coverage_quality_delta_gate(quality, prev_high, provider_request_count, args.epsilon)
    substance_value = load_json_value(root, getattr(args, "substance_metrics_json", None))
    if substance_value is None:
        substance_value, substance_error = call_adapter(
            domain_adapter,
            "substance_metrics",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
        )
        if substance_error:
            substance_value = {"substance_metrics_error": substance_error}
    if isinstance(substance_value, dict) and isinstance(substance_value.get("substance_metrics"), dict):
        current_substance = substance_value["substance_metrics"]
    elif isinstance(substance_value, dict) and isinstance(substance_value.get("current_substance_vector"), dict):
        current_substance = substance_value["current_substance_vector"]
    else:
        current_substance = substance_value if isinstance(substance_value, dict) else {}
    previous_substance = (
        (latest or {}).get("substance_metrics")
        or (latest or {}).get("current_substance_vector")
        or ((latest or {}).get("substance_delta_gate") or {}).get("current_substance_vector")
        or {}
    )
    substance_gate = vector_delta_gate(
        gate_name="G-SUBSTANCE",
        current=current_substance,
        previous=previous_substance,
        pass_field="substance_delta_pass",
        current_field="current_substance_vector",
        previous_field="previous_substance_vector",
        epsilon=args.epsilon,
    )
    evidence_provenance_value, evidence_provenance_error = call_adapter(
        domain_adapter,
        "evidence_provenance",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        substance_metrics=current_substance,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        candidate_metric_keys=[*QUALITY_DELTA_KEYS, *sorted(numeric_vector(current_substance))],
    )
    evidence_provenance, evidence_provenance_provided = normalize_evidence_provenance(evidence_provenance_value)
    coverage_gate, independent_coverage_fields, attested_coverage_fields = apply_evidence_provenance_filter(
        coverage_gate,
        improved_key="improved_fields",
        pass_key="quality_delta_pass",
        provenance=evidence_provenance,
        hook_provided=evidence_provenance_provided,
    )
    substance_gate, independent_substance_fields, attested_substance_fields = apply_evidence_provenance_filter(
        substance_gate,
        improved_key="improved_axes",
        pass_key="substance_delta_pass",
        provenance=evidence_provenance,
        hook_provided=evidence_provenance_provided,
    )
    source_separation_gate = verification_source_separation_gate(
        provenance_value=evidence_provenance_value,
        verified_artifact_paths=[rel_path(root, path) for path in paths],
        independently_verified_fields=[*independent_coverage_fields, *independent_substance_fields],
    )
    downgraded_fields = set(source_separation_gate.get("independently_verified_downgraded_fields") or [])
    if downgraded_fields:
        coverage_downgraded = [field for field in independent_coverage_fields if field in downgraded_fields]
        substance_downgraded = [field for field in independent_substance_fields if field in downgraded_fields]
        independent_coverage_fields = [field for field in independent_coverage_fields if field not in downgraded_fields]
        independent_substance_fields = [field for field in independent_substance_fields if field not in downgraded_fields]
        attested_coverage_fields = sorted(set(attested_coverage_fields + coverage_downgraded))
        attested_substance_fields = sorted(set(attested_substance_fields + substance_downgraded))
        if coverage_downgraded:
            coverage_gate["improved_fields"] = independent_coverage_fields
            coverage_gate["quality_delta_pass"] = bool(independent_coverage_fields)
            coverage_gate["status"] = "pass" if independent_coverage_fields else "block"
            coverage_gate["independently_verified_fields"] = independent_coverage_fields
            coverage_gate["producer_attested_fields"] = attested_coverage_fields
            coverage_gate["attested_only_movement"] = bool(attested_coverage_fields and not independent_coverage_fields)
        if substance_downgraded:
            substance_gate["improved_axes"] = independent_substance_fields
            substance_gate["substance_delta_pass"] = bool(independent_substance_fields)
            substance_gate["status"] = "pass" if independent_substance_fields else "block"
            substance_gate["independently_verified_fields"] = independent_substance_fields
            substance_gate["producer_attested_fields"] = attested_substance_fields
            substance_gate["attested_only_movement"] = bool(attested_substance_fields and not independent_substance_fields)
    evidence_gate = evidence_provenance_gate(
        hook_provided=evidence_provenance_provided,
        provenance=evidence_provenance,
        independent_fields=[*independent_coverage_fields, *independent_substance_fields],
        attested_fields=[*attested_coverage_fields, *attested_substance_fields],
        adapter_error=evidence_provenance_error,
        source_separation_gate=source_separation_gate,
    )
    output_delta_coverage_gate = find_coverage_quality_delta_gate(output_delta)
    coverage_reconciliation_gate = coverage_quality_delta_reconciliation_gate(coverage_gate, output_delta_coverage_gate, args.epsilon)
    coverage_reconciliation_blocks = bool_value(coverage_reconciliation_gate.get("constrains_disposition"))
    if coverage_reconciliation_blocks:
        gate_inputs.append({"name": "coverage_quality_delta_reconciliation_gate", **coverage_reconciliation_gate})
    dispatch_gate = provider_scale_dispatch_gate(prev_high, coverage_gate, provider_request_count)
    if bool_value(dispatch_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "provider_scale_dispatch_gate", **dispatch_gate})
    if bool_value(substance_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "substance_delta_gate", **substance_gate})
    corrective_value = load_json_value(root, getattr(args, "corrective_resolution_json", None))
    if corrective_value is None:
        corrective_value, corrective_error = call_adapter(
            domain_adapter,
            "corrective_resolution",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
        )
        if corrective_error:
            corrective_value = {"corrective_resolution_error": corrective_error}
    corrective_gate = vacuous_corrective_gate(corrective_value)
    if bool_value(corrective_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "vacuous_corrective_gate", **corrective_gate})
    acceptance_value = load_json_value(root, getattr(args, "acceptance_reachability_json", None))
    acceptance_error: str | None = None
    if acceptance_value is None:
        acceptance_value, acceptance_error = call_adapter(
            domain_adapter,
            "acceptance_reachability",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
            family_key=family_key,
            root_key=current_root_key,
        )
    target_required_verifier_error: str | None = None
    target_required_verifier_value, target_required_verifier_error = call_adapter(
        domain_adapter,
        "target_required_verifier",
        root=root,
        target=acceptance_target_from_value(acceptance_value),
        acceptance=acceptance_value,
        acceptance_reachability=acceptance_value,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
    )
    if target_required_verifier_value is not None:
        acceptance_value = merge_acceptance_verifier_contract(acceptance_value, target_required_verifier_value)
    reachability_gate = acceptance_reachability_gate(acceptance_value)
    if bool_value(reachability_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "acceptance_reachability_gate", **reachability_gate})
    metric_validity_value = load_json_value(root, getattr(args, "metric_validity_json", None))
    metric_validity_error: str | None = None
    if metric_validity_value is None:
        metric_validity_value, metric_validity_error = call_adapter(
            domain_adapter,
            "metric_validity_self_check",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
            family_key=family_key,
            root_key=current_root_key,
        )
    metric_validity_gate = oracle_metric_validity_gate(metric_validity_value)
    if bool_value(metric_validity_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "oracle_metric_validity_gate", **metric_validity_gate})
    adapter_fingerprint_value, adapter_fingerprint_error = call_adapter(
        domain_adapter,
        "output_fingerprint",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
    )
    if adapter_fingerprint_value and not quality.get("current_output_fingerprint"):
        quality["current_output_fingerprint"] = str(adapter_fingerprint_value)
    advice_gate = advice_freshness_gate(root, quality.get("current_output_fingerprint"), [gate_inputs, runner_validation, output_delta])
    structure_value, structure_error = call_adapter(
        domain_adapter,
        "structure_metrics",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
    )
    if structure_error:
        structure_value = {"structure_metrics_error": structure_error}
    structure_gate = structure_metrics_gate(structure_value)
    measurement_details = measurement_progress_details(
        registry_rows,
        family_key,
        current_root_key,
        current_root_family_key,
        current_check_ids,
        current_frontiers,
    )
    measurement_progress = bool_value(measurement_details["measurement_progress"])
    measurement_streak_value = int(measurement_details["measurement_streak"])
    measurement_progress_allowed = (
        measurement_progress
        and measurement_streak_value <= args.measurement_streak_cap
        and bool_value(coverage_gate.get("quality_delta_pass"))
        and bool_value(substance_gate.get("substance_delta_pass"))
        and not coverage_reconciliation_blocks
    )
    if bool_value(metric_validity_gate.get("metric_goal_productive_excluded")):
        measurement_progress_allowed = False
    blocker_sources: list[Any] = [runner_validation, output_delta, quality, gate_inputs, args.semantic_signature, args.artifact_family]
    current_blocker_signature = (
        args.blocker_signature
        or first_named_value(blocker_sources, BLOCKER_SIGNATURE_KEYS)
        or args.semantic_signature
        or "unknown"
    )
    blocker_root_family = current_root_family_key if facet_root_map_missing else collapse_root_family(facet_root_map, current_root_key, current_blocker_signature)
    latest_blocker = next((row for row in reversed(registry_rows) if row_root_family(row) == blocker_root_family), latest_terminal_family or latest)
    current_rung = normalize_ladder_rung(args.blocker_rung) or infer_ladder_rung(*blocker_sources)
    mutation_kind = blocker_mutation_kind(current_blocker_signature, current_rung, blocker_root_family, latest_blocker)
    previous_forward_count = forward_mutation_streak(registry_rows, family_key)
    current_forward_count = previous_forward_count + (1 if mutation_kind == "forward_mutation" else 0)
    forward_budget_remaining = max(0, args.max_forward_mutations - current_forward_count)
    force_implementation_cycle = mutation_kind == "forward_mutation" and forward_budget_remaining == 0
    disagreement = validator_disagreement_finding(runner_validation, output_delta)
    substance_delta_pass = bool_value(substance_gate.get("substance_delta_pass"))

    if insufficient_reason:
        semantic_progress = False
        evidence_class = "insufficient_evidence"
        high_water = prev_high
        count = previous_micro_hardening_count_for_count_key(registry_rows, effective_count_key) + 1
        disposition = "conservative_hold"
        hard_stop = True
    else:
        semantic_progress = bool_value(coverage_gate.get("quality_delta_pass"))
        evidence_class = "computed"
        allowed_high_water_keys = set(coverage_gate.get("improved_fields") or []) if evidence_provenance_provided else None
        high_water = (
            updated_high_water(quality, prev_high, provider_request_count, allowed_high_water_keys)
            if semantic_progress
            else prev_high
        )
        previous_family_count = previous_micro_hardening_count_for_count_key(registry_rows, effective_count_key)
        count = 0 if semantic_progress else previous_family_count + 1
        if semantic_progress:
            disposition = "open"
            hard_stop = False
        elif count >= args.threshold:
            disposition = "provider_or_semantic_transition_or_terminal"
            hard_stop = True
        else:
            disposition = "prefer_provider_or_semantic"
            hard_stop = False

    outcome_changed = terminal_outcome_changed(output_delta, changed_vs_previous, semantic_progress)
    delta_class = observed_delta_class(output_delta, changed_vs_previous, semantic_progress)
    forward_mutation_vacuous = mutation_kind == "forward_mutation" and not outcome_changed
    if forward_mutation_vacuous:
        hard_stop = True
    if mutation_kind == "forward_mutation" and outcome_changed and not disagreement and not coverage_reconciliation_blocks:
        changed_vs_previous = True
        count = 0
        hard_stop = False
        if disposition in {"conservative_hold", "provider_or_semantic_transition_or_terminal"}:
            disposition = "forward_mutation_goal_productive_candidate"
    if measurement_progress_allowed:
        hard_stop = False
        if disposition in {"conservative_hold", "provider_or_semantic_transition_or_terminal"}:
            disposition = "measurement_progress_goal_productive_candidate"
    if coverage_reconciliation_blocks:
        hard_stop = True
    if disagreement:
        hard_stop = True
    if bool_value(validator_gate.get("hard_stop_required")):
        hard_stop = True

    task_correction_class = classify_task_correction(
        current_check_ids=current_check_ids,
        current_frontiers=current_frontiers,
        provider_request_count=provider_request_count,
        changed_vs_previous=changed_vs_previous,
        semantic_progress=semantic_progress,
        values=[runner_validation, output_delta, quality, gate_inputs, args.semantic_signature, args.artifact_family],
    )
    detection_only = task_correction_class == "detection" and not semantic_progress
    detection_streak = detection_only_streak(registry_rows, blocker_root_family, detection_only)
    requires_correction_or_terminal = detection_streak >= args.detection_only_streak_cap and not semantic_progress
    if requires_correction_or_terminal:
        hard_stop = True
    current_no_goal_distance_delta = not (
        bool_value(coverage_gate.get("quality_delta_pass"))
        or bool_value(substance_gate.get("substance_delta_pass"))
    )
    partial_progress_value, partial_progress_error = call_adapter(
        domain_adapter,
        "partial_progress_axes",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        current_no_goal_distance_delta=current_no_goal_distance_delta,
    )
    partial_progress_gate = partial_progress_axes_gate(partial_progress_value, current_no_goal_distance_delta)
    partial_progress_gate["adapter_error"] = partial_progress_error
    adapter_contract_unmet = adapter_contract_unmet_fields(
        facet_root_map_missing=facet_root_map_missing,
        substance_gate=substance_gate,
        quality=quality,
    )
    adapter_gate = adapter_mandate_gate(
        registry_rows,
        artifact_family=args.artifact_family,
        contract_unmet=adapter_contract_unmet,
        current_no_delta=current_no_goal_distance_delta,
        cap=getattr(args, "adapter_mandate_streak_cap", ADAPTER_MANDATE_STREAK_CAP_DEFAULT),
    )
    if bool_value(adapter_load_gate.get("adapter_wiring_defect")):
        adapter_gate["adapter_mandate_required"] = False
        adapter_gate["status"] = "ok"
        adapter_gate["adapter_wiring_defect_supersedes_adapter_mandate"] = True
    if bool_value(adapter_load_gate.get("adapter_wiring_defect")):
        hard_stop = True
        disposition = "self_inflicted_gate_defect"
    elif bool_value(adapter_gate.get("adapter_mandate_required")):
        hard_stop = True
        disposition = "adapter_mandate_required"
        gate_inputs.append({"name": "adapter_mandate_gate", **adapter_gate})
    chain_gate = cumulative_goal_distance_gate(
        registry_rows,
        artifact_family=args.artifact_family,
        root_family_key=current_root_family_key,
        facet_root_map_missing=facet_root_map_missing,
        current_no_delta=current_no_goal_distance_delta,
        high_water=high_water,
        current_cycle_id=args.cycle_id,
        cap=getattr(args, "cumulative_chain_streak_cap", CUMULATIVE_CHAIN_STREAK_CAP_DEFAULT),
    )
    primary_metric_value, primary_metric_error = call_adapter(
        domain_adapter,
        "primary_metric",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        substance_metrics=current_substance,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
        previous_primary_metric=previous_primary_metric_value(latest),
        evidence_provenance=evidence_provenance,
    )
    primary_metric_gate = normalize_primary_metric_gate(
        primary_metric_value,
        previous_value=previous_primary_metric_value(latest),
        rows=registry_rows,
        scope_key=str(chain_gate.get("cumulative_goal_distance_scope_key") or family_key),
        cap=getattr(args, "cumulative_chain_streak_cap", CUMULATIVE_CHAIN_STREAK_CAP_DEFAULT),
        epsilon=args.epsilon,
        provenance=evidence_provenance,
        provenance_hook_provided=evidence_provenance_provided,
    )
    if primary_metric_error:
        primary_metric_gate["adapter_error"] = primary_metric_error
    capability_ladder_value, capability_ladder_error = call_adapter(
        domain_adapter,
        "capability_ladder",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
        high_water=high_water,
    )
    capability_ladder_option = first_actionable_capability_ladder_option(capability_ladder_value)
    forced_retarget_gate = chain_stall_forced_retarget_gate(
        chain_gate,
        blocker_mutation=mutation_kind,
        adapter_gate=adapter_load_gate,
        capability_ladder_option=capability_ladder_option,
    )
    if capability_ladder_error:
        forced_retarget_gate["capability_ladder_error"] = capability_ladder_error
    if bool_value(forced_retarget_gate.get("constrains_disposition")):
        chain_gate["allowed_dispositions"] = ["goal_productive", "terminal_blocked", "user_escalation"]
        chain_gate["allowed_task_kinds"] = forced_retarget_gate.get("allowed_task_kinds") or []
        gate_inputs.append({"name": "chain_stall_forced_retarget_gate", **forced_retarget_gate})
    c4_user_escalation_backstop_required = False
    if bool_value(primary_metric_gate.get("primary_metric_stalled")):
        forced_task_kinds = normalize_task_kinds(forced_retarget_gate.get("allowed_task_kinds") or [])
        if forced_task_kinds:
            primary_metric_gate["allowed_task_kinds"] = sorted(forced_task_kinds)
        else:
            c4_user_escalation_backstop_required = True
            primary_metric_gate["c4_user_escalation_backstop_required"] = True
            primary_metric_gate["allowed_dispositions"] = ["user_escalation"]
        gate_inputs.append({"name": "primary_metric_gate", **primary_metric_gate})
    if (
        bool_value(chain_gate.get("cumulative_goal_distance_stalled"))
        and not bool_value(adapter_gate.get("adapter_mandate_required"))
        and not bool_value(adapter_load_gate.get("adapter_wiring_defect"))
    ):
        hard_stop = True
        disposition = "goal_productive" if bool_value(forced_retarget_gate.get("constrains_disposition")) else "terminal_blocked"
        gate_inputs.append({"name": "cumulative_goal_distance_gate", **chain_gate})
    if bool_value(reachability_gate.get("acceptance_unreachable_under_frozen_config")):
        hard_stop = True
        if not bool_value(adapter_gate.get("adapter_mandate_required")) and not bool_value(
            chain_gate.get("cumulative_goal_distance_stalled")
        ):
            disposition = "relaxation_or_escalation_required"
    if bool_value(reachability_gate.get("unverifiable_acceptance_contract")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "verifier_contract_required"
    if bool_value(metric_validity_gate.get("metric_goal_productive_excluded")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "metric_definition_correction_required"
    if bool_value(primary_metric_gate.get("primary_metric_stalled")):
        hard_stop = True
        if c4_user_escalation_backstop_required:
            disposition = "user_escalation"
        elif disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "primary_metric_forced_retarget_required"
    if bool_value(failure_surface_gate.get("terminal_classification_stage_contradiction")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "terminal_classification_stage_repair_required"
    if bool_value(input_contract_gate.get("same_input_contract_violation")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "input_set_contract_repair_required"
    if bool_value(diagnostics_gate.get("instrumentation_supply_required")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "instrumentation_supply_required"
    verifier_source_value, verifier_source_error = call_adapter(
        domain_adapter,
        "verifier_source_paths",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        changed_files=changed_files,
        gate_results=gate_inputs,
        quality_vector=quality,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
    )
    verifier_source_map, verifier_source_hook_provided = normalize_verifier_source_paths(verifier_source_value)
    verifier_coupling_gate = coupled_verifier_gate(
        changed_files=changed_files,
        verifier_source_map=verifier_source_map,
        hook_provided=verifier_source_hook_provided,
        gates=[
            adapter_load_gate,
            validator_gate,
            coverage_gate,
            coverage_reconciliation_gate,
            dispatch_gate,
            substance_gate,
            corrective_gate,
            reachability_gate,
            metric_validity_gate,
            advice_gate,
            structure_gate,
            adapter_gate,
            chain_gate,
            forced_retarget_gate,
            primary_metric_gate,
            *gate_inputs,
        ],
    )
    if verifier_source_error:
        verifier_coupling_gate["adapter_error"] = verifier_source_error
    if bool_value(verifier_coupling_gate.get("pass_with_coupled_verifier")):
        hard_stop = True
        if disposition in {"open", "prefer_provider_or_semantic", "measurement_progress_goal_productive_candidate"}:
            disposition = "coupled_verifier_revalidation_required"
        gate_inputs.append({"name": "coupled_verifier_gate", **verifier_coupling_gate})
    envelope_thaw_streak = 0
    if bool_value(reachability_gate.get("envelope_thaw_item_required")):
        envelope_thaw_streak = 1
        for prior_row in reversed(registry_rows):
            if row_root_family(prior_row) != current_root_family_key:
                continue
            if bool_value(prior_row.get("envelope_thaw_item_required")):
                envelope_thaw_streak += 1
                continue
            break
    forced_task_options = list(forced_retarget_gate.get("forced_selected_task_options") or [])
    if bool_value(diagnostics_gate.get("instrumentation_supply_required")):
        existing_forced_kinds = gate_allowed_task_kinds({"forced_selected_task_options": forced_task_options})
        if not existing_forced_kinds.intersection({"instrumentation_supply", "execution_diagnostics_supply"}):
            forced_task_options.append(
                {
                    "selected_task_kind": "instrumentation_supply",
                    "task_kind": "instrumentation_supply",
                    "source": "diagnostics_unavailable_gate",
                    "actionable": True,
                    "failure_surface_count_key": failure_surface_gate.get("failure_surface_count_key"),
                    "diagnostics_unavailable_streak": diagnostics_gate.get("diagnostics_unavailable_streak"),
                    "instrumentation_trigger_threshold": diagnostics_gate.get("instrumentation_trigger_threshold"),
                }
            )
    forced_selected_task = forced_retarget_gate.get("forced_selected_task") or (forced_task_options[0] if forced_task_options else None)

    row = {
        "schema_version": SCHEMA_VERSION,
        "step": "loopback_audit",
        "cycle_id": args.cycle_id,
        "task_id": args.task_id,
        "family_key": family_key,
        "legacy_family_key": legacy_family_key,
        "root_key": current_root_key,
        "root_family_key": current_root_family_key,
        "artifact_family": args.artifact_family,
        "semantic_signature": args.semantic_signature,
        "provider_request_count": provider_request_count,
        "quality_vector": quality,
        "previous_high_water_mark": prev_high,
        "high_water_mark": high_water,
        "coverage_quality_delta_gate": coverage_gate,
        "coverage_quality_delta_reconciliation_gate": coverage_reconciliation_gate,
        "substance_metrics": numeric_vector(current_substance),
        "substance_delta_gate": substance_gate,
        "vacuous_corrective_gate": corrective_gate,
        "adapter_mandate_gate": adapter_gate,
        "adapter_mandate_required": bool_value(adapter_gate.get("adapter_mandate_required")),
        "adapter_missing_streak": adapter_gate.get("adapter_missing_streak"),
        "adapter_contract_unmet": adapter_contract_unmet,
        "adapter_wiring_gate": adapter_load_gate,
        "adapter_wiring_defect": bool_value(adapter_load_gate.get("adapter_wiring_defect")),
        "adapter_loaded": domain_adapter is not None,
        "adapter_registered": adapter_registered,
        "adapter_path": domain_adapter_path or adapter_expected_path,
        "adapter_expected_path": adapter_expected_path,
        "cumulative_goal_distance_gate": chain_gate,
        "cumulative_goal_distance_scope_key": chain_gate.get("cumulative_goal_distance_scope_key"),
        "cumulative_goal_distance_stall_streak": chain_gate.get("cumulative_goal_distance_stall_streak"),
        "cumulative_goal_distance_stalled": bool_value(chain_gate.get("cumulative_goal_distance_stalled")),
        "chain_stall_forced_retarget_gate": forced_retarget_gate,
        "forced_selected_task": forced_selected_task,
        "forced_selected_task_options": forced_task_options,
        "high_water_vector": chain_gate.get("high_water_vector"),
        "high_water_last_improved_cycle": chain_gate.get("high_water_last_improved_cycle"),
        "acceptance_reachability_gate": reachability_gate,
        "acceptance_unreachable_under_frozen_config": bool_value(
            reachability_gate.get("acceptance_unreachable_under_frozen_config")
        ),
        "acceptance_verifier_not_evaluated": bool_value(
            reachability_gate.get("acceptance_verifier_not_evaluated")
        ),
        "unverifiable_acceptance_contract": bool_value(
            reachability_gate.get("unverifiable_acceptance_contract")
        ),
        "relaxation_or_escalation_required": bool_value(
            reachability_gate.get("relaxation_or_escalation_required")
        ),
        "residual_gap_policy": reachability_gate.get("residual_gap_policy"),
        "residual_gap_ratio": reachability_gate.get("residual_gap_ratio"),
        "marginal_repair": bool_value(reachability_gate.get("marginal_repair")),
        "oracle_metric_validity_gate": metric_validity_gate,
        "metric_verifier_not_evaluated": bool_value(
            metric_validity_gate.get("metric_verifier_not_evaluated")
        ),
        "repo_owned_source_roots": repo_owned_source_roots,
        "repo_owned_source_roots_status": repo_owned_source_roots_status,
        "repo_owned_source_roots_error": repo_owned_source_roots_error,
        "facet_root_map_applied": bool(facet_root_map),
        "facet_root_map_missing": facet_root_map_missing,
        "facet_root_map_size": len(facet_root_map),
        "raw_root_family_key": raw_root_family_key,
        "terminal_outcome_key": current_terminal_outcome_key,
        "terminal_outcome_family_key": terminal_family_key,
        "terminal_outcome_family_source": terminal_family_source,
        "terminal_outcome_family_fallback_applied": terminal_family_fallback,
        "terminal_outcome_family_previous_count": previous_micro_hardening_count(registry_rows, current_root_family_key),
        "terminal_outcome_family_previous_cycle_id": (latest_terminal_family or {}).get("cycle_id"),
        "advice_freshness_gate": advice_gate,
        "partial_progress_axes_gate": partial_progress_gate,
        "structure_metrics_gate": structure_gate,
        "structure_high_water_key_scope": structure_gate.get("structure_high_water_key_scope"),
        "structure_global_invariant_metrics": structure_gate.get("structure_global_invariant_metrics") or {},
        "provider_scale_dispatch_gate": dispatch_gate,
        "changed_vs_previous": changed_vs_previous,
        "semantic_progress": semantic_progress,
        "same_family_micro_hardening_count": count,
        "micro_hardening_count": count,
        "recommended_disposition": disposition,
        "hard_stop_required": hard_stop,
        "evidence_class": evidence_class,
        "insufficient_evidence_reason": insufficient_reason,
        "measurement_progress": measurement_progress,
        "measurement_progress_allowed": measurement_progress_allowed,
        "measurement_streak": measurement_streak_value,
        "measurement_progress_streak_for_root_key": measurement_details["measurement_progress_streak_for_root_key"],
        "measurement_progress_streak_for_root_family": measurement_details["measurement_progress_streak_for_root_family"],
        "measurement_streak_cap": args.measurement_streak_cap,
        "measurement_check_ids": sorted(current_check_ids),
        "measurement_frontiers_observed": sorted(current_frontiers),
        "measurement_progress_basis": measurement_details["measurement_progress_basis"],
        "blocker_signature": current_blocker_signature,
        "blocker_root_family": blocker_root_family,
        "blocker_ladder_rung": current_rung,
        "blocker_mutation_kind": mutation_kind,
        "forward_mutation_budget_remaining": forward_budget_remaining,
        "terminal_outcome_changed": outcome_changed,
        "observed_delta_class": delta_class,
        "forward_mutation_vacuous": forward_mutation_vacuous,
        "force_implementation_cycle": force_implementation_cycle,
        "task_correction_class": task_correction_class,
        "detection_only": detection_only,
        "detection_only_streak_for_root_family": detection_streak,
        "detection_only_streak_cap": args.detection_only_streak_cap,
        "requires_correction_or_terminal": requires_correction_or_terminal,
        "validator_integrity_gate": validator_gate,
        "evidence_provenance_gate": evidence_gate,
        "producer_attested_fields": evidence_gate.get("producer_attested_fields") or [],
        "independently_verified_fields": evidence_gate.get("independently_verified_fields") or [],
        "attested_only_movement": bool_value(evidence_gate.get("attested_only_movement")),
        "primary_metric_gate": primary_metric_gate,
        "primary_metric_high_water_moved": bool_value(primary_metric_gate.get("primary_metric_high_water_moved")),
        "primary_metric_zero_movement_streak": primary_metric_gate.get("primary_metric_zero_movement_streak"),
        "primary_metric_stalled": bool_value(primary_metric_gate.get("primary_metric_stalled")),
        "c4_user_escalation_backstop_required": c4_user_escalation_backstop_required,
        "failure_surface_stage_gate": failure_surface_gate,
        "execution_stage_ladder_status": failure_surface_gate.get("execution_stage_ladder_status"),
        "last_successful_stage": failure_surface_gate.get("last_successful_stage"),
        "failure_surface_stage": failure_surface_gate.get("failure_surface_stage"),
        "failure_surface_count_key": failure_surface_gate.get("failure_surface_count_key"),
        "terminal_classification_stage_contradiction": bool_value(
            failure_surface_gate.get("terminal_classification_stage_contradiction")
        ),
        "terminal_classification_invalid_for_counting": bool_value(
            failure_surface_gate.get("terminal_classification_invalid_for_counting")
        ),
        "same_input_contract_gate": input_contract_gate,
        "same_input_contract_violation": bool_value(input_contract_gate.get("same_input_contract_violation")),
        "diagnostics_unavailable_gate": diagnostics_gate,
        "diagnostics_unavailable": bool_value(diagnostics_gate.get("diagnostics_unavailable")),
        "diagnostics_unavailable_streak": diagnostics_gate.get("diagnostics_unavailable_streak"),
        "instrumentation_supply_required": bool_value(diagnostics_gate.get("instrumentation_supply_required")),
        "verification_source_separation_gate": source_separation_gate,
        "independent_source_separation_status": source_separation_gate.get("independent_source_separation_status"),
        "independently_verified_downgraded_fields": source_separation_gate.get("independently_verified_downgraded_fields") or [],
        "root_dominant_parameter_key": root_dominant_parameter_key,
        "effective_count_key": effective_count_key,
        "envelope_thaw_item_required": bool_value(reachability_gate.get("envelope_thaw_item_required")),
        "envelope_thaw_item": reachability_gate.get("envelope_thaw_item"),
        "envelope_thaw_streak": envelope_thaw_streak,
        "coupled_verifier_gate": verifier_coupling_gate,
        "pass_with_coupled_verifier": bool_value(verifier_coupling_gate.get("pass_with_coupled_verifier")),
        "changed_verifier_source_paths": verifier_coupling_gate.get("changed_verifier_source_paths") or [],
        "previous_output_fingerprint": prev_fingerprint,
        "current_output_fingerprint": quality.get("current_output_fingerprint"),
        "previous_accepted_baseline": {
            "source": previous_baseline_source,
            "error": previous_baseline_error,
            "fingerprint": prev_fingerprint,
            "quality_vector_override_applied": bool(previous_adapter_high),
        },
        "domain_adapter": {
            "path": domain_adapter_path or adapter_expected_path,
            "expected_path": adapter_expected_path,
            "registered": adapter_registered,
            "loaded": domain_adapter is not None,
            "status": "loaded" if domain_adapter is not None else ("error" if domain_adapter_error else "legacy_fallback"),
            "error": domain_adapter_error,
            "legacy_quality_fallback": domain_adapter is None,
        },
        "registry_path": rel_path(root, registry_path),
        "evidence_paths": evidence_paths,
        "not_goal_truth": True,
        "not_gold": True,
        "not_ready": True,
        "updated_at": now_iso(),
    }
    root_cause_ledger_path = Path(getattr(args, "root_cause_ledger_path", ROOT_CAUSE_LEDGER_REL_PATH))
    if not root_cause_ledger_path.is_absolute():
        root_cause_ledger_path = root / root_cause_ledger_path
    hypotheses_value = load_json_value(root, getattr(args, "root_cause_hypotheses_json", None))
    root_cause_adapter_error: str | None = None
    if hypotheses_value is None:
        hypotheses_value, root_cause_adapter_error = call_adapter(
            domain_adapter,
            "root_cause_hypotheses",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
            family_key=family_key,
            root_key=current_root_key,
            root_family_key=current_root_family_key,
            blocker_signature=current_blocker_signature,
            blocker_ladder_rung=current_rung,
        )
    hypotheses = normalize_root_cause_hypotheses(hypotheses_value)
    if getattr(args, "hypothesized_root_cause", None):
        hypotheses.append(
            {
                "hypothesized_root_cause": normalize_root_cause_slug(args.hypothesized_root_cause),
                "repair_attempted": bool_value(getattr(args, "root_cause_repair_attempted", False)),
                "repair_task_id": getattr(args, "root_cause_repair_task_id", None),
                "actionable": bool_value(getattr(args, "root_cause_actionable", False)),
            }
        )
    ledger_entries: list[dict[str, Any]] = []
    for hypothesis in hypotheses:
        repair_task_id_raw = (
            hypothesis.get("repair_task_id")
            or hypothesis.get("task_id")
            or getattr(args, "root_cause_repair_task_id", None)
        )
        repair_task_id = str(repair_task_id_raw).strip() if repair_task_id_raw is not None else ""
        if repair_task_id.lower() in {"", "unknown", "none", "null"}:
            repair_task_id = ""
        repair_attempted = (
            bool_value(hypothesis.get("repair_attempted"))
            or bool_value(getattr(args, "root_cause_repair_attempted", False))
            or bool(repair_task_id)
        )
        hypothesis_evidence_paths = sorted(set(string_list(hypothesis.get("evidence_paths")) + evidence_paths))
        entry: dict[str, Any] = {
            "schema_version": "root-cause-hypothesis-ledger-v1",
            "cycle_id": args.cycle_id,
            "family_key": str(hypothesis.get("family_key") or family_key),
            "root_key": str(hypothesis.get("root_key") or current_root_key),
            "root_family_key": str(hypothesis.get("root_family_key") or current_root_family_key),
            "hypothesized_root_cause": normalize_root_cause_slug(hypothesis.get("hypothesized_root_cause")),
            "target_surface": str(hypothesis.get("target_surface") or current_blocker_signature or current_root_key),
            "blocker_signature": current_blocker_signature,
            "repair_attempted": repair_attempted,
            "repair_task_id": repair_task_id or None,
            "terminal_outcome_changed": outcome_changed,
            "observed_delta_class": hypothesis.get("observed_delta_class") or delta_class,
            "local": bool_value(hypothesis.get("local")),
            "bounded": bool_value(hypothesis.get("bounded")),
            "provider_free": bool_value(hypothesis.get("provider_free") or hypothesis.get("provider-free")),
            "in_scope": bool_value(hypothesis.get("in_scope")),
            "authority_allowed": bool_value(hypothesis.get("authority_allowed")),
            "actionable": bool_value(hypothesis.get("actionable") or hypothesis.get("root_cause_actionable")),
            "provenance_refs": root_cause_provenance_refs({**hypothesis, "evidence_paths": hypothesis_evidence_paths}),
            "evidence_paths": hypothesis_evidence_paths,
            "updated_at": now_iso(),
        }
        actionability = harden_repo_owned_actionability(
            entry,
            root=root,
            repo_owned_source_roots=repo_owned_source_roots,
        )
        entry["actionability_status"] = actionability["status"]
        entry["actionability_basis"] = actionability["basis"]
        ledger_entries.append(entry)
    existing_root_cause_rows = read_jsonl(root_cause_ledger_path)
    root_cause_rows = [*existing_root_cause_rows, *ledger_entries]
    root_cause_ledger_updated = False
    if getattr(args, "write_registry", False) and ledger_entries:
        root_cause_rows, root_cause_ledger_updated = append_root_cause_ledger(
            root_cause_ledger_path,
            ledger_entries,
            args.max_root_cause_rows_per_family,
        )
    root_cause_gate = root_cause_hypothesis_gate(
        root_cause_rows,
        family_key,
        current_root_key,
        current_root_family_key,
        args.untried_promotion_budget,
        root=root,
        repo_owned_source_roots=repo_owned_source_roots,
    )
    untried = root_cause_gate["untried_root_cause_hypotheses"]
    row["root_cause_ledger_path"] = rel_path(root, root_cause_ledger_path)
    row["root_cause_ledger_status"] = "recorded" if ledger_entries else "not_applicable_no_hypotheses"
    row["root_cause_ledger_updated"] = root_cause_ledger_updated
    row["root_cause_ledger_entries"] = ledger_entries
    row["root_cause_unverified_hypotheses"] = root_cause_gate["root_cause_unverified_hypotheses"][:10]
    row["root_cause_duplicate_hypotheses"] = root_cause_gate["root_cause_duplicate_hypotheses"][:10]
    row["untried_promotion_budget"] = root_cause_gate["untried_promotion_budget"]
    row["vacuous_untried_attempt_count"] = root_cause_gate["vacuous_untried_attempt_count"]
    row["vacuous_untried_streak"] = root_cause_gate["vacuous_untried_streak"]
    row["hypothesis_exhausted"] = root_cause_gate["hypothesis_exhausted"]
    row["untried_actionable_root_cause_exists"] = bool(untried)
    row["untried_root_cause_hypotheses"] = untried[:10]
    chain_untried_override = (
        bool(untried)
        and bool_value(row.get("cumulative_goal_distance_stalled"))
        and not bool_value(row.get("adapter_mandate_required"))
    )
    row["cumulative_untried_chain_without_quality_delta"] = chain_untried_override
    row["untried_veto_overridden_by_chain_stall"] = chain_untried_override
    row["terminal_blocked_invalid_due_to_untried_root_cause"] = bool(untried) and not chain_untried_override
    if root_cause_adapter_error:
        row["root_cause_ledger_adapter_error"] = root_cause_adapter_error
    if row["hypothesis_exhausted"] and getattr(args, "write_registry", False):
        row["hypothesis_exhaustion_seal_path"] = feed_exhausted_family_seal(root, row)

    effective_allowed, basis = effective_allowed_dispositions(gate_inputs)
    recent_progress = load_json_value(root, getattr(args, "recent_progress_json", None))
    if isinstance(recent_progress, dict):
        recent_progress = recent_progress.get("progress_items") or recent_progress.get("evidence") or recent_progress.get("items")
    if not isinstance(recent_progress, list):
        recent_progress = []
    streak = consolidation_streak([item for item in recent_progress if isinstance(item, dict)])
    row["effective_allowed_dispositions"] = effective_allowed
    row["disposition_intersection_basis"] = basis
    row["consolidation_streak"] = streak
    row["consolidation_reduces_goal_distance"] = False
    row["consolidation_streak_cap"] = args.consolidation_streak_cap
    findings = list(row.get("findings") or [])
    rejected_self_reports = [
        {
            "hypothesized_root_cause": entry.get("hypothesized_root_cause"),
            "self_report_rejected_fields": entry.get("self_report_rejected_fields"),
            "repo_owned_source_refs": entry.get("repo_owned_source_refs"),
            "target_surface": entry.get("target_surface"),
        }
        for entry in ledger_entries
        if isinstance(entry, dict) and entry.get("self_report_rejected_fields")
    ]
    if rejected_self_reports:
        findings.append(
            {
                "severity": "warn",
                "code": "repo_owned_source_self_report_rejected",
                "message": "root-cause actionability was derived from repo-owned source provenance; conflicting producer self-report fields were ignored.",
                "evidence": {"root_cause_ledger_entries": rejected_self_reports[:5]},
            }
        )
    if row["adapter_wiring_defect"]:
        findings.append(
            {
                "severity": "block",
                "code": "adapter_wiring_defect",
                "message": "a registered repository domain adapter did not load; treat this as a self-inflicted workflow wiring/load defect, not adapter absence.",
                "evidence": row["adapter_wiring_gate"],
            }
        )
    if row["pass_with_coupled_verifier"]:
        findings.append(
            {
                "severity": "block",
                "code": "pass_with_coupled_verifier",
                "message": "a passing verifier gate was modified in the same change set; do not read this pass as completion or goal-productive evidence until a non-coupled revalidation or independent evidence recalculation exists.",
                "evidence": row["coupled_verifier_gate"],
            }
        )
    if row["terminal_classification_stage_contradiction"]:
        findings.append(
            {
                "severity": "block",
                "code": "terminal_classification_stage_contradiction",
                "message": "terminal classification contradicts the adapter-owned execution stage observation; do not use that classification for counting or close.",
                "evidence": row["failure_surface_stage_gate"],
            }
        )
    if row["same_input_contract_violation"]:
        findings.append(
            {
                "severity": "block",
                "code": "same_input_contract_violation",
                "message": "a same-condition comparison changed the input set size; the comparison conclusion is not valid close evidence.",
                "evidence": row["same_input_contract_gate"],
            }
        )
    if row["instrumentation_supply_required"]:
        findings.append(
            {
                "severity": "block",
                "code": "instrumentation_supply_required",
                "message": "diagnostics were unavailable for the same failure surface across the configured threshold; derive must enumerate instrumentation supply before another hypothesis repair can count.",
                "evidence": row["diagnostics_unavailable_gate"],
            }
        )
    elif row["diagnostics_unavailable"]:
        findings.append(
            {
                "severity": "warn",
                "code": "diagnostics_unavailable",
                "message": "failure autopsy explicitly reported missing post-failure scalar diagnostics; this is trace evidence for instrumentation-first derivation if it repeats.",
                "evidence": row["diagnostics_unavailable_gate"],
            }
        )
    if row["independently_verified_downgraded_fields"]:
        findings.append(
            {
                "severity": "warn",
                "code": "independent_verification_source_not_disjoint",
                "message": "independently_verified fields were downgraded because verification inputs were missing or overlapped the verified artifacts.",
                "evidence": row["verification_source_separation_gate"],
            }
        )
    if verifier_source_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_verifier_source_paths_failed",
                "message": "domain adapter verifier_source_paths() failed; verifier-source coupling was not applied.",
                "evidence": {"error": verifier_source_error},
            }
        )
    if row["attested_only_movement"]:
        findings.append(
            {
                "severity": "warn",
                "code": "attested_only_movement",
                "message": "metric movement was producer-attested only; it did not update high-water state or reset stall counters.",
                "evidence": row["evidence_provenance_gate"],
            }
        )
    if evidence_provenance_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_evidence_provenance_failed",
                "message": "domain adapter evidence_provenance() failed; legacy progress accounting was used where no explicit provenance packet was supplied.",
                "evidence": {"error": evidence_provenance_error},
            }
        )
    if row["primary_metric_stalled"]:
        findings.append(
            {
                "severity": "block",
                "code": "primary_metric_stalled",
                "message": "adapter-owned primary metric high-water did not move; C4 forced retargeting remains active and label churn cannot reset the stall.",
                "evidence": row["primary_metric_gate"],
            }
        )
    elif bool_value(primary_metric_gate.get("attested_only_movement")):
        findings.append(
            {
                "severity": "warn",
                "code": "primary_metric_attested_only_movement",
                "message": "primary metric movement was producer-attested only; it did not move primary-metric high-water.",
                "evidence": row["primary_metric_gate"],
            }
        )
    if primary_metric_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_primary_metric_failed",
                "message": "domain adapter primary_metric() failed; primary-metric C4 trigger fell back to existing chain-stall behavior.",
                "evidence": {"error": primary_metric_error},
            }
        )
    if row["adapter_mandate_required"]:
        findings.append(
            {
                "severity": "block",
                "code": "adapter_mandate_required",
                "message": "domain adapter contract is unmet across the configured no-quality-delta streak; derive must select adapter registration or adapter strengthening before another domain micro-repair can count as goal-productive.",
                "evidence": row["adapter_mandate_gate"],
            }
        )
    if bool_value(row.get("cumulative_goal_distance_stalled")) and not row["adapter_mandate_required"]:
        findings.append(
            {
                "severity": "block",
                "code": "cumulative_goal_distance_stalled",
                "message": "quality/substance high-water has not improved across the configured cumulative chain cap, independent of blocker label or terminal-outcome churn.",
                "evidence": row["cumulative_goal_distance_gate"],
            }
        )
    if bool_value(forced_retarget_gate.get("chain_stall_force_retarget")):
        findings.append(
            {
                "severity": "block" if forced_retarget_gate.get("forced_selected_task") else "warn",
                "code": "chain_stall_forced_retarget",
                "message": "cumulative goal-distance stall exceeded the forced-retarget threshold; derive must select an actionable listed alternative before terminal/user escalation when one exists.",
                "evidence": forced_retarget_gate,
            }
        )
    if row["acceptance_unreachable_under_frozen_config"]:
        findings.append(
            {
                "severity": "block",
                "code": "acceptance_unreachable_under_frozen_config",
                "message": "acceptance minimum output is unreachable under the frozen envelope; derive must choose constraint relaxation or user escalation instead of envelope-internal micro-repair.",
                "evidence": reachability_gate,
            }
        )
    envelope_thaw_cap = int(getattr(args, "envelope_thaw_streak_cap", ENVELOPE_THAW_STREAK_CAP_DEFAULT)) or ENVELOPE_THAW_STREAK_CAP_DEFAULT
    if row["envelope_thaw_item_required"]:
        findings.append(
            {
                "severity": "block" if envelope_thaw_streak >= envelope_thaw_cap else "warn",
                "code": "envelope_thaw_item_required",
                "message": "acceptance is unreachable under a frozen envelope and no thaw item is reserved; preserve a thaw condition or staged thaw schedule before another envelope-internal task.",
                "evidence": {
                    "acceptance_reachability_gate": reachability_gate,
                    "envelope_thaw_streak": envelope_thaw_streak,
                    "cap": envelope_thaw_cap,
                },
            }
        )
    if row["unverifiable_acceptance_contract"]:
        findings.append(
            {
                "severity": "block",
                "code": "unverifiable_acceptance_contract",
                "message": "a measurable acceptance target requires a live verifier, but the verifier was not evaluated; not_evaluated is not a pass.",
                "evidence": reachability_gate,
            }
        )
    if bool_value(metric_validity_gate.get("metric_goal_productive_excluded")):
        findings.append(
            {
                "severity": "block",
                "code": "metric_validity_tautological",
                "message": "oracle or metric validity self-check is tautological; exclude that metric pass from goal-productive evidence and require metric correction or independent output-delta evidence.",
                "evidence": metric_validity_gate,
            }
        )
    elif measurement_progress and not bool_value(metric_validity_gate.get("metric_validity_self_check_provided")):
        findings.append(
            {
                "severity": "warn",
                "code": "metric_validity_self_check_missing",
                "message": "measurement or oracle progress was observed without an adapter metric_validity_self_check; treat metric validity as warning-only unless another gate blocks.",
                "evidence": metric_validity_gate,
            }
        )
    if acceptance_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_acceptance_reachability_failed",
                "message": "domain adapter acceptance_reachability() failed; G-REACH remained indeterminate unless explicit reachability input was supplied.",
                "evidence": {"error": acceptance_error},
            }
        )
    if target_required_verifier_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_target_required_verifier_failed",
                "message": "domain adapter target_required_verifier() failed; measurable acceptance verifier mapping was not applied.",
                "evidence": {"error": target_required_verifier_error},
            }
        )
    if metric_validity_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_metric_validity_failed",
                "message": "domain adapter metric_validity_self_check() failed; G-OENV remained warning-only unless explicit metric validity input was supplied.",
                "evidence": {"error": metric_validity_error},
            }
        )
    if row["hypothesis_exhausted"]:
        row["hard_stop_required"] = True
        row["recommended_disposition"] = "terminal_blocked"
        findings.append(
            {
                "severity": "block",
                "code": "root_cause_hypothesis_exhausted",
                "message": "root-cause untried promotion budget is exhausted without terminal_outcome_changed; derive must not promote another same-family untried repair without supplied input delta.",
                "evidence": {
                    "root_cause_ledger_path": row["root_cause_ledger_path"],
                    "untried_promotion_budget": row["untried_promotion_budget"],
                    "vacuous_untried_attempt_count": row["vacuous_untried_attempt_count"],
                    "hypothesis_exhaustion_seal_path": row.get("hypothesis_exhaustion_seal_path"),
                },
            }
        )
    elif chain_untried_override:
        row["hard_stop_required"] = True
        row["recommended_disposition"] = "terminal_blocked"
        findings.append(
            {
                "severity": "block",
                "code": "cumulative_untried_chain_without_quality_delta",
                "message": "distinct untried root-cause hypotheses no longer override terminal/user escalation because the same goal-distance scope has not improved its quality or substance high-water vector across the configured chain cap.",
                "evidence": {
                    "cumulative_goal_distance_gate": row.get("cumulative_goal_distance_gate"),
                    "root_cause_ledger_path": row["root_cause_ledger_path"],
                    "untried_root_cause_hypotheses": untried[:5],
                },
            }
        )
    elif untried:
        row["hard_stop_required"] = True
        row["recommended_disposition"] = "untried_root_cause_repair_required"
        if "goal_productive" not in row["effective_allowed_dispositions"]:
            row["effective_allowed_dispositions"] = sorted(set(row["effective_allowed_dispositions"]) | {"goal_productive"})
        findings.append(
            {
                "severity": "block",
                "code": "untried_actionable_root_cause",
                "message": "terminal_blocked is invalid while an actionable root-cause hypothesis remains untried; derive must promote that hypothesis as the next goal-productive repair task.",
                "evidence": {
                    "root_cause_ledger_path": row["root_cause_ledger_path"],
                    "untried_root_cause_hypotheses": untried[:5],
                },
            }
        )
    if row["root_cause_unverified_hypotheses"]:
        findings.append(
            {
                "severity": "warn",
                "code": "root_cause_actionability_unverified",
                "message": "root-cause hypotheses with only self-asserted actionability were excluded from untried promotion.",
                "evidence": {"root_cause_unverified_hypotheses": row["root_cause_unverified_hypotheses"][:5]},
            }
        )
    if row["root_cause_duplicate_hypotheses"]:
        findings.append(
            {
                "severity": "warn",
                "code": "root_cause_duplicate_or_rename",
                "message": "root-cause hypotheses equivalent to prior attempted hypotheses were excluded from untried promotion.",
                "evidence": {"root_cause_duplicate_hypotheses": row["root_cause_duplicate_hypotheses"][:5]},
            }
        )
    if streak >= args.consolidation_streak_cap and "consolidation" in row["effective_allowed_dispositions"]:
        row["effective_allowed_dispositions"] = [item for item in row["effective_allowed_dispositions"] if item != "consolidation"]
        findings.append(
            {
                "severity": "block",
                "code": "consolidation_streak_capped",
                "message": "consolidation is governance-only and does not reduce goal distance; repeated consolidation is capped.",
                "evidence": {"consolidation_streak": streak, "cap": args.consolidation_streak_cap},
            }
        )
    if bool_value(dispatch_gate.get("dispatch_required")):
        row["hard_stop_required"] = True
        if row["recommended_disposition"] in {"open", "prefer_provider_or_semantic"}:
            row["recommended_disposition"] = "provider_scale_dispatch_required"
        findings.append(
            {
                "severity": "block",
                "code": "provider_scale_dispatch_required",
                "message": "no provider dispatch and all coverage high-water marks are zero; derive must select bounded extraction/scale work if authority permits, or terminal/user-escalate with the missing authority/input.",
                "evidence": dispatch_gate,
            }
        )
    if measurement_progress and not measurement_progress_allowed:
        row["measurement_goal_productive_allowed"] = False
        row["requires_non_measurement_goal_productive"] = True
        reason = "measurement_without_coverage_quality_delta"
        if measurement_streak_value > args.measurement_streak_cap:
            reason = "measurement_streak_capped"
        elif coverage_reconciliation_blocks:
            reason = "coverage_quality_delta_reconciliation_failed"
        elif not substance_delta_pass:
            reason = "measurement_without_substance_delta"
        findings.append(
            {
                "severity": "block",
                "code": reason,
                "message": (
                    "measurement/oracle work cannot be promoted to goal_productive without both G-COV and G-SUBSTANCE deltas, "
                    "and is capped to one measurement transition per root_key/root_family."
                ),
                "evidence": {
                    "root_key": current_root_key,
                    "measurement_streak": measurement_streak_value,
                    "cap": args.measurement_streak_cap,
                    "coverage_quality_delta_gate": coverage_gate,
                    "coverage_quality_delta_reconciliation_gate": coverage_reconciliation_gate,
                    "substance_delta_gate": substance_gate,
                },
            }
        )
    if measurement_progress_allowed and not disagreement:
        if "goal_productive" not in row["effective_allowed_dispositions"]:
            row["effective_allowed_dispositions"] = sorted(set(row["effective_allowed_dispositions"]) | {"goal_productive"})
        findings.append(
            {
                "severity": "info",
                "code": "measurement_progress_allowed",
                "message": "new measurement/oracle coverage is allowed because G-COV also observed a coverage or quality delta.",
                "evidence": {
                    "measurement_progress_basis": row["measurement_progress_basis"],
                    "coverage_quality_delta_gate": coverage_gate,
                },
            }
        )
    if bool_value(validator_gate.get("hard_stop_required")):
        findings.append(
            {
                "severity": "block",
                "code": "validator_integrity_or_coverage_failed",
                "message": "validator top-level result disagrees with embedded sub-results, or declared population coverage is incomplete; do not count the validator pass as goal-productive progress.",
                "evidence": validator_gate,
            }
        )
    if requires_correction_or_terminal:
        findings.append(
            {
                "severity": "block",
                "code": "detection_only_streak_capped",
                "message": "detection-only work repeated for the same root blocker family while semantic progress remains false; the next task must be correction, terminal_blocked, or user_escalation.",
                "evidence": {
                    "blocker_root_family": blocker_root_family,
                    "task_correction_class": task_correction_class,
                    "detection_only_streak": detection_streak,
                    "cap": args.detection_only_streak_cap,
                },
            }
        )
    if mutation_kind == "forward_mutation" and not disagreement and outcome_changed and not coverage_reconciliation_blocks:
        if "goal_productive" not in row["effective_allowed_dispositions"]:
            row["effective_allowed_dispositions"] = sorted(set(row["effective_allowed_dispositions"]) | {"goal_productive"})
        findings.append(
            {
                "severity": "info" if not force_implementation_cycle else "warn",
                "code": "blocker_forward_mutation",
                "message": "blocker moved forward within the capability ladder and strict output-delta evidence changed the terminal outcome; treat it as changed rather than a same-family repeat.",
                "evidence": {
                    "blocker_signature": current_blocker_signature,
                    "blocker_ladder_rung": current_rung,
                    "terminal_outcome_changed": outcome_changed,
                    "observed_delta_class": delta_class,
                    "forward_mutation_budget_remaining": forward_budget_remaining,
                    "force_implementation_cycle": force_implementation_cycle,
                },
            }
        )
    elif mutation_kind == "forward_mutation" and (not outcome_changed or coverage_reconciliation_blocks):
        if not outcome_changed:
            row["force_substance_progress"] = True
        if coverage_reconciliation_blocks:
            row["force_gcov_reconciliation"] = True
        reason = "forward_mutation_vacuous"
        message = "capability-ladder movement cannot be promoted when the observed terminal outcome did not change; require strict changed-and-semantic primary-output evidence."
        if coverage_reconciliation_blocks:
            reason = "forward_mutation_with_gcov_disagreement"
            message = "capability-ladder movement cannot be promoted while output_delta and loopback G-COV disagree."
        findings.append(
            {
                "severity": "block",
                "code": reason,
                "message": message,
                "evidence": {
                    "blocker_signature": current_blocker_signature,
                    "blocker_ladder_rung": current_rung,
                    "terminal_outcome_changed": outcome_changed,
                    "observed_delta_class": delta_class,
                    "coverage_quality_delta_reconciliation_gate": coverage_reconciliation_gate,
                    "substance_delta_gate": substance_gate,
                },
            }
        )
    if coverage_reconciliation_blocks:
        row["hard_stop_required"] = True
        findings.append(
            {
                "severity": "block",
                "code": "coverage_quality_delta_gate_disagreement",
                "message": "output_delta and loopback G-COV disagree or expose conflicting values for the same metric key; use the conservative block verdict.",
                "evidence": coverage_reconciliation_gate,
            }
        )
    if bool_value(corrective_gate.get("surface_corrective_noop")):
        findings.append(
            {
                "severity": "block",
                "code": "vacuous_corrective_noop",
                "message": "corrective/backfill rows attempted work without resolving any lane; exclude those rows from produced or semantic delta evidence.",
                "evidence": corrective_gate,
            }
        )
    if bool_value(advice_gate.get("advice_metrics_stale")):
        findings.append(
            {
                "severity": "warn",
                "code": "advice_metrics_stale",
                "message": "advice declares output fingerprint claims that do not match the current adapter/output fingerprint; refresh or reclassify the advice before relying on its headline metrics.",
                "evidence": advice_gate,
            }
        )
    if bool_value(advice_gate.get("gate_result_regression_stale")):
        findings.append(
            {
                "severity": "warn",
                "code": "gate_result_regression_stale",
                "message": "a gate verdict regressed from passed to blocked under a stable environment fingerprint; route through the existing advice-freshness/self-check path before trusting stale headline gate state.",
                "evidence": advice_gate,
            }
        )
    if str(partial_progress_gate.get("status")) == "warn":
        findings.append(
            {
                "severity": "warn",
                "code": "partial_progress_axes_flatlined",
                "message": "adapter-reported partial progress axes exist while quality/substance high-water remains flat; recommend decomposing all-or-nothing gates rather than adding another detector.",
                "evidence": partial_progress_gate,
            }
        )
    if adapter_fingerprint_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_output_fingerprint_failed",
                "message": "domain adapter output_fingerprint() failed; advice freshness can only use the quality vector fingerprint.",
                "evidence": {"error": adapter_fingerprint_error},
            }
        )
    if previous_baseline_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_previous_accepted_fp_failed",
                "message": "domain adapter previous_accepted_fp() failed or returned an unusable baseline; registry fallback was used where available.",
                "evidence": {"error": previous_baseline_error, "baseline_source": previous_baseline_source},
            }
        )
    if bool_value(structure_gate.get("structure_consolidation_recommended")):
        findings.append(
            {
                "severity": "warn",
                "code": "structure_consolidation_recommended",
                "message": "domain adapter structure metrics recommend Class C consolidation or module-boundary work.",
                "evidence": structure_gate,
            }
        )
    if structure_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_structure_metrics_failed",
                "message": "domain adapter structure_metrics() failed; structure consolidation signal was skipped.",
                "evidence": {"error": structure_error},
            }
        )
    if facet_map_error:
        findings.append(
            {
                "severity": "warn",
                "code": "domain_adapter_facet_root_map_failed",
                "message": "domain adapter facet_root_map() failed; terminal-outcome fallback grouped this cycle by artifact family and terminal outcome.",
                "evidence": {
                    "error": facet_map_error,
                    "terminal_outcome_key": current_terminal_outcome_key,
                    "terminal_outcome_family_key": terminal_family_key,
                },
            }
        )
    elif facet_root_map_missing:
        findings.append(
            {
                "severity": "warn",
                "code": "facet_root_map_missing",
                "message": "facet_root_map is unavailable; terminal-outcome fallback grouped this cycle by artifact family and terminal outcome so proximate blocker mutations cannot reset same-family caps.",
                "evidence": {
                    "terminal_outcome_key": current_terminal_outcome_key,
                    "terminal_outcome_family_key": terminal_family_key,
                    "raw_root_family_key": raw_root_family_key,
                    "previous_cycle_id": (latest_terminal_family or {}).get("cycle_id"),
                },
            }
        )
    orphan_advice = advice_coherence_finding(root)
    if orphan_advice:
        findings.append(orphan_advice)
    if disagreement:
        findings.append(disagreement)
        row["authoritative_semantic_progress"] = False
        row["hard_stop_required"] = True
    if findings:
        row["findings"] = findings
    if existing_cycle:
        row["registry_idempotent_replay"] = True
        row["same_family_micro_hardening_count"] = existing_cycle.get("same_family_micro_hardening_count", count)
        row["micro_hardening_count"] = existing_cycle.get("micro_hardening_count", row["same_family_micro_hardening_count"])
        row["high_water_mark"] = existing_cycle.get("high_water_mark", high_water)
        row["semantic_progress"] = bool_value(existing_cycle.get("semantic_progress"))
        row["changed_vs_previous"] = bool_value(existing_cycle.get("changed_vs_previous"))
        row["recommended_disposition"] = existing_cycle.get("recommended_disposition", disposition)
        row["hard_stop_required"] = bool_value(existing_cycle.get("hard_stop_required"))
        for key in IDEMPOTENT_REPLAY_KEYS:
            if key in existing_cycle:
                row[key] = existing_cycle[key]
        if disagreement:
            existing_codes = {
                str(finding.get("code") or "")
                for finding in row.get("findings", [])
                if isinstance(finding, dict)
            }
            if "validator_disagreement" not in existing_codes:
                row.setdefault("findings", []).append(disagreement)
            row["authoritative_semantic_progress"] = False
            row["hard_stop_required"] = True
        return row, registry_rows, False
    registry_row = dict(row)
    return row, compact_registry([*registry_rows, registry_row], args.max_rows_per_family), True


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
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    json.dump(packet, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if packet.get("evidence_class") == "computed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
