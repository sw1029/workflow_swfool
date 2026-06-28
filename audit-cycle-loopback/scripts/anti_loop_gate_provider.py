#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
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
LEGACY_QUALITY_ENV = "NOVEL_KG_QUALITY_METRICS_PATH"
DISPOSITION_UNIVERSE = {"goal_productive", "consolidation", "terminal_blocked", "user_escalation"}
SAFETY_VALVES = {"terminal_blocked", "user_escalation"}
CONSOLIDATION_STREAK_CAP_DEFAULT = 2
MEASUREMENT_STREAK_CAP_DEFAULT = 1
MAX_FORWARD_MUTATIONS_DEFAULT = 3
DETECTION_ONLY_STREAK_CAP_DEFAULT = 2
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
    "facet_root_map_size",
    "advice_freshness_gate",
    "structure_metrics_gate",
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
    "untried_actionable_root_cause_exists",
    "untried_root_cause_hypotheses",
    "terminal_blocked_invalid_due_to_untried_root_cause",
    "force_implementation_cycle",
    "task_correction_class",
    "detection_only",
    "detection_only_streak_for_root_family",
    "detection_only_streak_cap",
    "requires_correction_or_terminal",
    "validator_integrity_gate",
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


def load_domain_adapter(root: Path, explicit_path: str | None) -> tuple[Any | None, str | None, str | None]:
    global _DOMAIN_ADAPTER_MODULE
    if _DOMAIN_ADAPTER_MODULE is not None:
        return _DOMAIN_ADAPTER_MODULE, None, None
    candidates: list[Path] = []
    for raw in (explicit_path, os.environ.get(DOMAIN_ADAPTER_ENV), os.environ.get("DOMAIN_ADAPTER_PATH")):
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        candidates.append(candidate)
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
    if explicit_path or os.environ.get(DOMAIN_ADAPTER_ENV) or os.environ.get("DOMAIN_ADAPTER_PATH"):
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


def append_root_cause_ledger(path: Path, entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
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
        write_registry(path, rows)
    return rows, changed


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


def normalize_root_cause_slug(value: Any) -> str:
    return normalize_root_family_key(str(value or "unknown_root_cause"))


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


def root_cause_actionable(entry: dict[str, Any]) -> bool:
    if bool_value(entry.get("actionable")) or bool_value(entry.get("root_cause_actionable")):
        return True
    return all(
        bool_value(entry.get(field))
        for field in ("local", "bounded", "provider_free", "in_scope", "authority_allowed")
    )


def same_root_cause_scope(row: dict[str, Any], family_key: str, root_key: str, root_family_key: str) -> bool:
    if str(row.get("family_key") or "") == family_key:
        return True
    if root_key and str(row.get("root_key") or "") == root_key:
        return True
    if root_family_key and str(row.get("root_family_key") or row.get("blocker_root_family") or "") == root_family_key:
        return True
    return False


def untried_root_cause_hypotheses(
    rows: list[dict[str, Any]],
    family_key: str,
    root_key: str,
    root_family_key: str,
) -> list[dict[str, Any]]:
    latest_by_root: dict[str, dict[str, Any]] = {}
    attempted: set[str] = set()
    for row in rows:
        if not same_root_cause_scope(row, family_key, root_key, root_family_key):
            continue
        root = normalize_root_cause_slug(row.get("hypothesized_root_cause"))
        latest_by_root[root] = row
        if bool_value(row.get("repair_attempted")):
            attempted.add(root)
    untried = []
    for root, row in sorted(latest_by_root.items()):
        if root in attempted or not root_cause_actionable(row):
            continue
        untried.append(
            {
                "family_key": row.get("family_key"),
                "root_key": row.get("root_key"),
                "root_family_key": row.get("root_family_key"),
                "hypothesized_root_cause": root,
                "repair_attempted": False,
                "repair_task_id": row.get("repair_task_id"),
                "terminal_outcome_changed": bool_value(row.get("terminal_outcome_changed")),
                "observed_delta_class": row.get("observed_delta_class"),
                "cycle_id": row.get("cycle_id"),
                "actionable": True,
            }
        )
    return untried


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
        metrics = value["structure_metrics"]
    elif isinstance(value, dict):
        metrics = value
    else:
        metrics = {}
    recommended = any(
        bool_value(metrics.get(key))
        for key in (
            "structure_consolidation_recommended",
            "consolidation_recommended",
            "budget_exceeded",
            "over_budget",
        )
    )
    return {
        "gate": "S-STRUCT",
        "structure_metrics": numeric_vector(metrics),
        "structure_consolidation_recommended": recommended,
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


def advice_freshness_gate(root: Path, current_output_fingerprint: Any) -> dict[str, Any]:
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
    return {
        "gate": "G-ADVICE-FRESH",
        "current_output_fingerprint": current or None,
        "declared_fingerprint_claims": claimed,
        "advice_metrics_stale": bool(stale),
        "stale_advice": stale,
        "status": "warn" if stale else ("not_applicable" if not claimed else "pass"),
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


def gate_allowed_dispositions(name: str, gate: dict[str, Any]) -> set[str]:
    explicit = normalize_dispositions(gate.get("allowed_dispositions"))
    if explicit:
        return explicit
    if bool_value(gate.get("requires_goal_productive_next")) or bool_value(gate.get("requires_goal_productive_or_user_escalation")):
        return {"goal_productive", "terminal_blocked", "user_escalation"}
    if name == "command_surface_budget" and (bool_value(gate.get("hard_gate")) or bool_value(gate.get("budget_exceeded"))):
        return {"consolidation", "terminal_blocked"}
    return set(DISPOSITION_UNIVERSE)


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


def semantic_progress_from_high_water(
    quality: dict[str, Any],
    prev_high: dict[str, Any],
    provider_request_count: int,
    epsilon: float,
) -> bool:
    if quality.get("quality_signal_confidence") == "low":
        return False
    return bool(coverage_quality_delta_gate(quality, prev_high, provider_request_count, epsilon)["quality_delta_pass"])


def updated_high_water(quality: dict[str, Any], prev_high: dict[str, Any], provider_request_count: int) -> dict[str, Any]:
    return {
        "event_named_ratio": max(high_water_metric_value(prev_high, "event_named_ratio"), quality_metric_value(quality, "event_named_ratio")),
        "proper_noun_character_ratio": max(
            high_water_metric_value(prev_high, "proper_noun_character_ratio"),
            quality_metric_value(quality, "proper_noun_character_ratio"),
        ),
        "coreference_resolved_ratio": max(
            high_water_metric_value(prev_high, "coreference_resolved_ratio"),
            quality_metric_value(quality, "coreference_resolved_ratio"),
        ),
        "causal_edge_count": max(
            int_metric(high_water_metric_value(prev_high, "causal_edge_count")),
            int_metric(quality_metric_value(quality, "causal_edge_count")),
        ),
        "windows_covered": max(
            int_metric(high_water_metric_value(prev_high, "windows_covered")),
            int_metric(quality_metric_value(quality, "windows_covered")),
        ),
        "ever_causal_edge": bool_value(prev_high.get("ever_causal_edge")) or bool_value(quality.get("causal_edge_present")),
        "ever_provider_dispatch": bool_value(prev_high.get("ever_provider_dispatch")) or provider_request_count > 0,
    }


def evaluate(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    root = Path(args.root).resolve()
    registry_path = Path(args.registry_path)
    if not registry_path.is_absolute():
        registry_path = root / registry_path
    family_key = normalize_family_key(args.artifact_family, args.semantic_signature)
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
    domain_adapter, domain_adapter_path, domain_adapter_error = load_domain_adapter(root, getattr(args, "domain_adapter", None))
    quality, evidence_paths, insufficient_reason = (
        ({}, [], domain_adapter_error)
        if domain_adapter_error
        else compute_quality(root, paths, domain_adapter)
    )
    provider_request_count = max(0, int(args.provider_request_count or 0))
    gate_inputs: list[dict[str, Any]] = []
    for raw_gate in getattr(args, "gate_state_json", []) or []:
        gate_inputs.extend(extract_disposition_gates(load_json_value(root, raw_gate)))
    runner_validation = load_json_value(root, getattr(args, "runner_validation_json", None))
    output_delta = load_json_value(root, getattr(args, "output_delta_json", None))
    validator_gate = validator_integrity_gate(runner_validation, output_delta, gate_inputs)
    if bool_value(validator_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "validator_integrity_gate", **validator_gate})
    measurement_ids_value = load_json_value(root, getattr(args, "measurement_check_ids_json", None))
    current_root_key = (
        args.root_key
        or first_named_value([runner_validation, output_delta, quality, gate_inputs], ROOT_KEY_KEYS)
        or family_key
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
    current_root_family_key = collapse_root_family(facet_root_map, current_root_key, args.semantic_signature, args.artifact_family)
    current_check_ids = set(getattr(args, "measurement_check_id", []) or [])
    current_check_ids.update(extract_check_ids(measurement_ids_value, runner_validation, output_delta, quality, gate_inputs))
    current_frontiers = {frontier_key(item) for item in getattr(args, "measurement_frontier", []) or [] if item}
    current_frontiers.update(extract_frontier_observations(runner_validation, output_delta, quality, gate_inputs))
    coverage_gate = coverage_quality_delta_gate(quality, prev_high, provider_request_count, args.epsilon)
    output_delta_coverage_gate = find_coverage_quality_delta_gate(output_delta)
    coverage_reconciliation_gate = coverage_quality_delta_reconciliation_gate(coverage_gate, output_delta_coverage_gate, args.epsilon)
    coverage_reconciliation_blocks = bool_value(coverage_reconciliation_gate.get("constrains_disposition"))
    if coverage_reconciliation_blocks:
        gate_inputs.append({"name": "coverage_quality_delta_reconciliation_gate", **coverage_reconciliation_gate})
    dispatch_gate = provider_scale_dispatch_gate(prev_high, coverage_gate, provider_request_count)
    if bool_value(dispatch_gate.get("constrains_disposition")):
        gate_inputs.append({"name": "provider_scale_dispatch_gate", **dispatch_gate})
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
    adapter_fingerprint_value, adapter_fingerprint_error = call_adapter(
        domain_adapter,
        "output_fingerprint",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
    )
    if adapter_fingerprint_value and not quality.get("current_output_fingerprint"):
        quality["current_output_fingerprint"] = str(adapter_fingerprint_value)
    advice_gate = advice_freshness_gate(root, quality.get("current_output_fingerprint"))
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
    blocker_sources: list[Any] = [runner_validation, output_delta, quality, gate_inputs, args.semantic_signature, args.artifact_family]
    current_blocker_signature = (
        args.blocker_signature
        or first_named_value(blocker_sources, BLOCKER_SIGNATURE_KEYS)
        or args.semantic_signature
        or "unknown"
    )
    blocker_root_family = collapse_root_family(facet_root_map, current_root_key, current_blocker_signature)
    latest_blocker = next((row for row in reversed(registry_rows) if row_root_family(row) == blocker_root_family), latest)
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
        count = prev_count
        disposition = "conservative_hold"
        hard_stop = True
    else:
        semantic_progress = semantic_progress_from_high_water(quality, prev_high, provider_request_count, args.epsilon)
        evidence_class = "computed"
        high_water = updated_high_water(quality, prev_high, provider_request_count) if semantic_progress else prev_high
        count = 0 if semantic_progress else prev_count + 1
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

    row = {
        "schema_version": SCHEMA_VERSION,
        "step": "loopback_audit",
        "cycle_id": args.cycle_id,
        "task_id": args.task_id,
        "family_key": family_key,
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
        "facet_root_map_applied": bool(facet_root_map),
        "facet_root_map_size": len(facet_root_map),
        "advice_freshness_gate": advice_gate,
        "structure_metrics_gate": structure_gate,
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
        "previous_output_fingerprint": prev_fingerprint,
        "current_output_fingerprint": quality.get("current_output_fingerprint"),
        "previous_accepted_baseline": {
            "source": previous_baseline_source,
            "error": previous_baseline_error,
            "fingerprint": prev_fingerprint,
            "quality_vector_override_applied": bool(previous_adapter_high),
        },
        "domain_adapter": {
            "path": domain_adapter_path,
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
        entry: dict[str, Any] = {
            "schema_version": "root-cause-hypothesis-ledger-v1",
            "cycle_id": args.cycle_id,
            "family_key": str(hypothesis.get("family_key") or family_key),
            "root_key": str(hypothesis.get("root_key") or current_root_key),
            "root_family_key": str(hypothesis.get("root_family_key") or current_root_family_key),
            "hypothesized_root_cause": normalize_root_cause_slug(hypothesis.get("hypothesized_root_cause")),
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
            "evidence_paths": evidence_paths,
            "updated_at": now_iso(),
        }
        ledger_entries.append(entry)
    existing_root_cause_rows = read_jsonl(root_cause_ledger_path)
    root_cause_rows = [*existing_root_cause_rows, *ledger_entries]
    root_cause_ledger_updated = False
    if getattr(args, "write_registry", False) and ledger_entries:
        root_cause_rows, root_cause_ledger_updated = append_root_cause_ledger(root_cause_ledger_path, ledger_entries)
    untried = untried_root_cause_hypotheses(root_cause_rows, family_key, current_root_key, current_root_family_key)
    row["root_cause_ledger_path"] = rel_path(root, root_cause_ledger_path)
    row["root_cause_ledger_status"] = "recorded" if ledger_entries else "not_applicable_no_hypotheses"
    row["root_cause_ledger_updated"] = root_cause_ledger_updated
    row["root_cause_ledger_entries"] = ledger_entries
    row["untried_actionable_root_cause_exists"] = bool(untried)
    row["untried_root_cause_hypotheses"] = untried[:10]
    row["terminal_blocked_invalid_due_to_untried_root_cause"] = bool(untried)
    if root_cause_adapter_error:
        row["root_cause_ledger_adapter_error"] = root_cause_adapter_error

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
    if untried:
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
                "message": "domain adapter facet_root_map() failed; root-family normalization used only the conservative built-in suffix/facet collapse.",
                "evidence": {"error": facet_map_error},
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
    parser.add_argument("--gate-state-json", action="append", default=[], help="Path or JSON containing disposition gates from loop detection or portfolio planning.")
    parser.add_argument("--recent-progress-json", help="Path or JSON containing recent progress items for consolidation-streak calculation.")
    parser.add_argument("--runner-validation-json", help="Path or JSON for strict runner validation, used only to detect semantic-progress disagreement.")
    parser.add_argument("--output-delta-json", help="Path or JSON for output-delta packet, used only to detect semantic-progress disagreement.")
    parser.add_argument("--substance-metrics-json", help="Path or JSON object with adapter-compatible substance_metrics/current_substance_vector values.")
    parser.add_argument("--corrective-resolution-json", help="Path or JSON with corrective lane attempted/resolved counts.")
    parser.add_argument("--facet-root-map-json", help="Path or JSON mapping facet labels to root families.")
    parser.add_argument("--root-cause-hypotheses-json", help="Path or JSON list/dict of root-cause hypotheses for the generic root-cause ledger.")
    parser.add_argument("--hypothesized-root-cause", help="Single root-cause hypothesis slug to record when no JSON/adapter list is supplied.")
    parser.add_argument("--root-cause-repair-attempted", action="store_true", help="Mark the supplied root-cause hypothesis as explicitly attempted by this cycle.")
    parser.add_argument("--root-cause-repair-task-id", help="Task id for the repair attempt targeting the supplied root-cause hypothesis.")
    parser.add_argument("--root-cause-actionable", action="store_true", help="Mark the supplied root-cause hypothesis as local, bounded, provider-free, in-scope, and authority-allowed.")
    parser.add_argument("--measurement-check-id", action="append", default=[], help="Stable check/oracle ID introduced or exercised by this cycle.")
    parser.add_argument("--measurement-check-ids-json", help="Path or JSON list/dict containing check or oracle IDs.")
    parser.add_argument("--measurement-frontier", action="append", default=[], help="Named measurement frontier observed by this cycle.")
    parser.add_argument("--measurement-streak-cap", type=int, default=MEASUREMENT_STREAK_CAP_DEFAULT)
    parser.add_argument("--detection-only-streak-cap", type=int, default=DETECTION_ONLY_STREAK_CAP_DEFAULT)
    parser.add_argument("--blocker-signature", help="Stable current blocker signature before suffix normalization.")
    parser.add_argument("--blocker-rung", help="Current capability-ladder rung for the blocker family.")
    parser.add_argument("--max-forward-mutations", type=int, default=MAX_FORWARD_MUTATIONS_DEFAULT)
    parser.add_argument("--consolidation-streak-cap", type=int, default=CONSOLIDATION_STREAK_CAP_DEFAULT)
    parser.add_argument("--registry-path", default=REGISTRY_REL_PATH)
    parser.add_argument("--root-cause-ledger-path", default=ROOT_CAUSE_LEDGER_REL_PATH)
    parser.add_argument("--threshold", type=int, default=3)
    parser.add_argument("--epsilon", type=float, default=1e-9)
    parser.add_argument("--max-rows-per-family", type=int, default=200)
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
