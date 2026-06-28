#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROGRESS_RE = re.compile(r"progress[_ -]?verdict\s*[:|-]\s*(advanced|safety_only|no_progress|regressed)", re.IGNORECASE)
ISSUE_RE = re.compile(r"(\.issue/[^\s)>\]]+|issue-[0-9A-Za-z_.-]+|#[0-9]+)")
BLOCKER_RE = re.compile(r"(?:blocker|blocking finding|남은 blocker)\s*[:|-]\s*(.+)", re.IGNORECASE)
INPUT_KIND_RE = re.compile(r"(?:new_input_kind|required_new_input_kind|input kind|input_kind)\s*[:=]\s*([A-Za-z0-9_.:-]+)", re.IGNORECASE)
PROVIDER_REQUEST_COUNT_RE = re.compile(r"\bprovider_request_count\s*[=:]\s*([0-9]+)\b", re.IGNORECASE)
FAILURE_CLASS_RE = re.compile(r"\bfailure_class\s*[=:]\s*([A-Za-z0-9_.:-]+)\b", re.IGNORECASE)
COMMAND_SURFACE_RE = re.compile(
    r"\b(?:build|validate|run|preflight)-[A-Za-z0-9_.:-]*[-_]v\d+[A-Za-z0-9_.:-]*"
    r"(?:contract|handoff|packet|gate|preflight|check|locator|resolution|recovery)?[A-Za-z0-9_.:-]*",
    re.IGNORECASE,
)
SIGNATURE_TOKEN_RE = re.compile(r"[^a-z0-9가-힣_.:/#-]+", re.IGNORECASE)
VOLATILE_SIGNATURE_RE = re.compile(
    r"(?:(?:20\d{2}[-_.]?\d{2}[-_.]?\d{2}(?:[-_.]?\d{2}[-_.]?\d{2}[-_.]?\d{2})?)|"
    r"(?:\b\d{8,14}\b)|(?:\b[0-9a-f]{7,40}\b)|(?:\bcycle[-_.]?[0-9a-z_.-]+\b)|"
    r"(?:\brun[-_.]?[0-9a-z_.-]+\b)|(?:\btask[-_.]?\d+[0-9a-z_.-]*\b)|"
    r"(?:\bafter[-_.][a-z0-9_.-]+\b)|(?:[-_.]?v\d+\b))",
    re.IGNORECASE,
)

SEMANTIC_AXIS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("hash_reconcile", r"hash|digest|checksum|reconcile|rename|renam"),
    ("evidence_anchor", r"evidence[-_ ]?anchor|anchor|source[-_ ]?backed|source[-_ ]?evidence"),
    ("provider_terminal", r"provider|runtime|dispatch|live[-_ ]?provider|api|external[-_ ]?service|provider[-_ ]?terminal|runtime[-_ ]?terminal"),
    ("task_state_digest", r"task[-_ ]?state|index|candidate|task[_-]?miss|past[_-]?task|ledger"),
    ("oom_rebuild", r"oom|memory|rebuild|cache"),
    ("validation_set", r"validation[-_ ]?set|oracle|split|leakage|holdout|gold"),
    ("quality_review", r"quality|review|semantic[-_ ]?quality|reviewable[-_ ]?output"),
    ("kg_core", r"\bkg\b|knowledge[-_ ]?graph|graph|entity|relation"),
    ("claim_rights", r"claim|rights|policy|license|zkp|commitment"),
)

ROOT_AXIS_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "source_to_llm_output_execution",
        r"openai|provider|credential|dispatch|llm|api|source[-_ ]?backed|"
        r"provider[-_ ]?neutral.*(?:kg|validation[-_ ]?set|oracle|quality)",
    ),
    ("validation_oracle_quality", r"validation[-_ ]?set|oracle|split|leakage|holdout|quality[-_ ]?review"),
    ("kg_evidence_anchor", r"\bkg\b|knowledge[-_ ]?graph|evidence[-_ ]?anchor|preimage|source[-_ ]?locator|same[-_ ]?preimage"),
    ("task_state_lifecycle", r"task[-_ ]?state|index|candidate|task[_-]?miss|past[_-]?task|ledger|sealed"),
    ("claim_rights_commitment", r"claim|rights|policy|license|zkp|commitment"),
)
REGISTRY_REL_PATH = ".task/dedup_symbol_registry.jsonl"
DISPOSITION_UNIVERSE = {"goal_productive", "consolidation", "terminal_blocked", "user_escalation"}
SAFETY_VALVES = {"terminal_blocked", "user_escalation"}
CONSOLIDATION_STREAK_CAP = 2
QUALITY_DELTA_KEYS = (
    "event_named_ratio",
    "proper_noun_character_ratio",
    "coreference_resolved_ratio",
    "causal_edge_count",
    "windows_covered",
)
KG_NODE_EDGE_FILES = {"kg_nodes.jsonl", "kg_edges.jsonl"}
INPUT_MANIFEST_NAMES = {"input_manifest.json", "hash_summary.json"}
PATH_FIELD_NAMES = {
    "artifact_path",
    "artifact_paths",
    "artifacts",
    "changed_files",
    "command_log_paths",
    "evidence_path",
    "evidence_paths",
    "generated_artifacts",
    "input_artifact_paths",
    "input_manifest_path",
    "input_manifest_paths",
    "output_artifact_paths",
    "output_layer_path",
    "output_layer_paths",
    "processed_output_dir",
    "processed_output_path",
    "processed_candidate_dir",
    "run_artifact_dir",
    "task_local_artifacts_dir",
}
INPUT_PATH_FIELD_NAMES = {
    "input_artifact_paths",
    "input_manifest_path",
    "input_manifest_paths",
    "hash_summary_path",
    "hash_summary_paths",
    "manifest_path",
    "source_manifest_path",
    "supplied_input_artifact_paths",
}
TARGET_UNIT_KEYS = {
    "chunk_id",
    "chunk_ids",
    "document_id",
    "document_ids",
    "edge_id",
    "edge_ids",
    "evidence_id",
    "evidence_ids",
    "node_id",
    "node_ids",
    "preimage_id",
    "preimage_ids",
    "row_id",
    "row_ids",
    "source_window_id",
    "source_window_ids",
    "target_id",
    "target_ids",
    "target_unit_id",
    "target_unit_ids",
    "work_id",
    "work_ids",
}
NODE_ID_KEYS = ("id", "node_id", "entity_id", "canonical_id")
EDGE_ID_KEYS = ("id", "edge_id", "relation_id")
EDGE_ENDPOINT_KEYS = ("source", "source_id", "from", "target", "target_id", "to", "type", "relation", "predicate")
DETECTION_ONLY_STREAK_CAP = 2
TERMINAL_QUIESCENCE_STREAK_DEFAULT = 2
FACET_SUFFIX_RE = re.compile(
    r"([_.:/|-])(?:v\d+|ver\d+|version\d+|facet|variant|case|mode|phase|stage|"
    r"vocab|pov|timing|typing|schema|contract|gate|metric|oracle|validator|lineage|"
    r"coverage|preflight|handoff|packet|dashboard|report|field|scalar|check|review|surface)$",
    re.IGNORECASE,
)
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


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


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


def read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def stable_digest(parts: list[str] | tuple[str, ...] | set[str]) -> str:
    digest = hashlib.sha256()
    for part in sorted(str(item) for item in parts if item is not None and str(item) != ""):
        digest.update(part.encode("utf-8", errors="replace"))
        digest.update(b"\0")
    return digest.hexdigest()


def file_digest(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def scalar_values(value: Any) -> list[str]:
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(scalar_values(item))
        return items
    if isinstance(value, dict):
        items: list[str] = []
        for item in value.values():
            items.extend(scalar_values(item))
        return items
    return []


def collect_by_key(value: Any, keys: set[str]) -> list[str]:
    collected: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key.lower() in keys:
                    collected.extend(scalar_values(child))
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return sorted(set(collected))


def resolve_existing_paths(root: Path, raw_paths: list[str], limit: int = 160) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for item in raw_paths:
        if len(paths) >= limit:
            break
        if not item or "://" in item or "*" in item:
            continue
        path = Path(item)
        if not path.is_absolute():
            path = root / path
        try:
            exists = path.exists()
        except OSError:
            exists = False
        if not exists:
            continue
        key = path.resolve().as_posix()
        if key in seen:
            continue
        paths.append(path)
        seen.add(key)
    return paths


def collect_path_values(value: Any, keys: set[str]) -> list[str]:
    return collect_by_key(value, keys | PATH_FIELD_NAMES)


def input_fingerprint(root: Path, value: dict[str, Any]) -> dict[str, Any]:
    raw_paths = collect_path_values(value, INPUT_PATH_FIELD_NAMES)
    existing = resolve_existing_paths(root, raw_paths)
    digest_parts: list[str] = []
    source_paths: list[str] = []
    for path in existing:
        candidates = [path]
        if path.is_dir():
            candidates = [path / name for name in INPUT_MANIFEST_NAMES]
        for candidate in candidates:
            if not candidate.is_file() or candidate.name not in INPUT_MANIFEST_NAMES:
                continue
            digest = file_digest(candidate)
            if digest:
                source_paths.append(rel_path(root, candidate))
                digest_parts.append(f"{rel_path(root, candidate)}:{digest}")
    inline_parts: list[str] = []
    for key in ("input_manifest", "hash_summary", "source_manifest", "input_lineage"):
        raw = value.get(key)
        if isinstance(raw, (dict, list)):
            try:
                inline_parts.append(json.dumps(raw, ensure_ascii=False, sort_keys=True))
            except TypeError:
                continue
    if inline_parts:
        digest_parts.append(f"inline:{stable_digest(inline_parts)}")
    fingerprint = stable_digest(digest_parts)[:32] if digest_parts else "none"
    return {
        "consumed_input_fp": fingerprint,
        "input_manifest_paths": source_paths[:12],
        "input_manifest_count": len(source_paths),
    }


def target_unit_fingerprint(value: dict[str, Any]) -> dict[str, Any]:
    values = collect_by_key(value, TARGET_UNIT_KEYS)
    fingerprint = stable_digest(values)[:32] if values else "none"
    return {
        "target_unit_fp": fingerprint,
        "target_unit_count": len(values),
        "target_unit_sample_digest": stable_digest(values[:12])[:16] if values else None,
    }


def workflow_feature_symbol(root: Path, value: dict[str, Any], blockers: list[str], axis: str | None) -> dict[str, Any]:
    input_part = input_fingerprint(root, value)
    target_part = target_unit_fingerprint(value)
    blocker_root_axis = axis or "unknown"
    symbol = stable_digest([input_part["consumed_input_fp"], target_part["target_unit_fp"], blocker_root_axis])[:24]
    return {
        "symbol": f"wf:{symbol}",
        "scope": "workflow_loop",
        "consumed_input_fp": input_part["consumed_input_fp"],
        "input_manifest_paths": input_part["input_manifest_paths"],
        "input_manifest_count": input_part["input_manifest_count"],
        "target_unit_fp": target_part["target_unit_fp"],
        "target_unit_count": target_part["target_unit_count"],
        "target_unit_sample_digest": target_part["target_unit_sample_digest"],
        "blocker_root_axis": blocker_root_axis,
        "blocker_count": len(blockers),
    }


def load_symbol_registry(root: Path) -> dict[str, dict[str, Any]]:
    registry_path = root / REGISTRY_REL_PATH
    latest: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(registry_path):
        symbol = record.get("symbol")
        if isinstance(symbol, str) and symbol:
            latest[symbol] = record
    return latest


def output_candidate_paths(root: Path, value: dict[str, Any]) -> list[Path]:
    raw_paths = collect_path_values(value, PATH_FIELD_NAMES)
    existing = resolve_existing_paths(root, raw_paths)
    candidates: list[Path] = []
    seen: set[str] = set()
    for path in existing:
        expanded = [path]
        if path.is_file() and path.name == "done.ok":
            expanded.append(path.parent)
        for item in expanded:
            key = item.resolve().as_posix()
            if key not in seen:
                candidates.append(item)
                seen.add(key)
    return candidates


def kg_identity(record: Any, kind: str) -> str | None:
    if not isinstance(record, dict):
        return None
    keys = NODE_ID_KEYS if kind == "nodes" else EDGE_ID_KEYS
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    if kind == "edges":
        values = [str(record.get(key)).strip() for key in EDGE_ENDPOINT_KEYS if record.get(key) is not None and str(record.get(key)).strip()]
        if len(values) >= 3:
            return "|".join(values)
    return None


def jsonl_identity_summary(path: Path, kind: str) -> dict[str, Any]:
    count = 0
    identities: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                count += 1
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                identity = kg_identity(value, kind)
                if identity:
                    identities.append(identity)
    except OSError:
        return {"count": 0, "identity_digest": None}
    return {
        "count": count,
        "identity_digest": stable_digest(identities)[:32] if identities else None,
    }


def kg_node_edge_summary(root: Path, paths: list[Path]) -> dict[str, Any]:
    kg_paths: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        candidates: list[Path] = []
        if path.is_file() and path.name in KG_NODE_EDGE_FILES:
            candidates.append(path)
        elif path.is_file() and path.name == "done.ok":
            candidates.extend([path.parent / "kg_nodes.jsonl", path.parent / "kg_edges.jsonl"])
        elif path.is_dir():
            candidates.extend([path / "kg_nodes.jsonl", path / "kg_edges.jsonl"])
            if path.name != "novel_kg_candidate":
                candidates.extend(list(path.rglob("kg_nodes.jsonl"))[:80])
                candidates.extend(list(path.rglob("kg_edges.jsonl"))[:80])
        for candidate in candidates:
            if not candidate.is_file():
                continue
            key = candidate.resolve().as_posix()
            if key not in seen:
                kg_paths.append(candidate)
                seen.add(key)

    node_count = 0
    edge_count = 0
    fingerprint_parts: list[str] = []
    for path in sorted(kg_paths):
        kind = "nodes" if path.name == "kg_nodes.jsonl" else "edges"
        summary = jsonl_identity_summary(path, kind)
        if kind == "nodes":
            node_count += int(summary["count"])
        else:
            edge_count += int(summary["count"])
        fingerprint_parts.append(
            f"{rel_path(root, path)}:{kind}:{summary['count']}:{summary.get('identity_digest') or 'no_ids'}"
        )
    return {
        "kg_paths": [rel_path(root, path) for path in sorted(kg_paths)],
        "node_count": node_count,
        "edge_count": edge_count,
        "node_edge_record_count": node_count + edge_count,
        "node_edge_fingerprint": stable_digest(fingerprint_parts)[:32] if fingerprint_parts else None,
    }


def node_edge_counts_from_value(value: dict[str, Any]) -> dict[str, int]:
    counts = first_value(value, ("output_delta.counts", "counts", "validation_summary", "implementation_summary.output_counts"))
    if not isinstance(counts, dict):
        return {"node_count": 0, "edge_count": 0}
    node_count = number_value(counts.get("kg_nodes") or counts.get("kg_node_count") or counts.get("node_count") or counts.get("character_node_count")) or 0
    edge_count = number_value(counts.get("kg_edges") or counts.get("kg_edge_count") or counts.get("edge_count")) or 0
    return {"node_count": node_count, "edge_count": edge_count}


def terminal_record_like(value: dict[str, Any]) -> bool:
    if boolish(value.get("legitimate_terminal_blocker")) or boolish(value.get("terminal_blocker")):
        return True
    status = first_value(value, ("output_delta_status", "output_delta.status", "validation_verdict", "completion_status", "result_status"))
    if isinstance(status, str) and any(token in status.lower() for token in ("terminal", "fail_closed", "fail-closed", "blocked_provider")):
        return True
    failure = provider_failure_class(value)
    request_count = number_value(first_value(value, ("provider_request_count", "failure_autopsy.provider_request_count", "result.provider_request_count")))
    return bool(failure and request_count and request_count > 1)


def terminal_progress_item(item: dict[str, Any]) -> bool:
    for key in ("selected_task_source", "selected_task_kind", "disposition", "progress_target"):
        value = str(item.get(key) or "").strip().lower()
        if "terminal" in value:
            return True
    observed = item.get("observed_output")
    if isinstance(observed, dict) and str(observed.get("observed_output_class") or "").lower() == "terminal_record":
        return True
    return False


def terminal_quiescence_gate(progress_items: list[dict[str, Any]], has_supplied_input_delta: bool, threshold: int) -> dict[str, Any]:
    first_terminal = next((item for item in progress_items if terminal_progress_item(item)), None)
    if not first_terminal:
        return {
            "gate": "T-QUIESCENCE",
            "status": "not_applicable",
            "threshold": threshold,
            "terminal_streak": 0,
            "quiescence_required": False,
            "commit_skipped_reason": None,
            "terminal_root_key": None,
            "has_supplied_input_delta": has_supplied_input_delta,
        }
    root_key_value = str(first_terminal.get("root_key") or first_terminal.get("semantic_signature") or first_terminal.get("blocker_signature") or "unknown")
    streak = 0
    evidence_paths: list[str] = []
    for item in progress_items:
        item_root = str(item.get("root_key") or item.get("semantic_signature") or item.get("blocker_signature") or "unknown")
        if item_root != root_key_value or not terminal_progress_item(item):
            break
        streak += 1
        if item.get("path"):
            evidence_paths.append(str(item["path"]))
    required = streak >= threshold and not has_supplied_input_delta
    return {
        "gate": "T-QUIESCENCE",
        "status": "block" if required else "ok",
        "threshold": threshold,
        "terminal_streak": streak,
        "terminal_root_key": root_key_value,
        "quiescence_required": required,
        "has_supplied_input_delta": has_supplied_input_delta,
        "commit_skipped_reason": "terminal_quiescence" if required else None,
        "allowed_dispositions": ["terminal_blocked", "user_escalation"],
        "evidence_paths": evidence_paths[:10],
        "handoff_only": required,
        "closeout_reproduction_allowed": not required,
        "overridden_by_untried_root_cause": False,
    }


def observed_output_class(root: Path, value: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    paths = output_candidate_paths(root, value)
    summary = kg_node_edge_summary(root, paths)
    count_fallback = node_edge_counts_from_value(value)
    previous_fingerprint = (previous or {}).get("node_edge_fingerprint")
    previous_count_fingerprint = (previous or {}).get("node_edge_count_fingerprint")
    count_fingerprint = stable_digest([str(count_fallback["node_count"]), str(count_fallback["edge_count"])])[:32]
    output_class = "unknown"
    reason = "no_observable_output_artifact"
    if summary["node_edge_record_count"] > 0:
        if previous_fingerprint and previous_fingerprint == summary["node_edge_fingerprint"]:
            output_class = "metadata_only"
            reason = "node_edge_paths_unchanged_since_registry"
        else:
            output_class = "node_edge_delta"
            reason = "node_edge_paths_observed"
    elif count_fallback["node_count"] + count_fallback["edge_count"] > 0:
        if previous_count_fingerprint and previous_count_fingerprint == count_fingerprint:
            output_class = "metadata_only"
            reason = "node_edge_counts_unchanged_since_registry"
        else:
            output_class = "node_edge_delta"
            reason = "node_edge_counts_observed"
    elif paths:
        output_class = "terminal_record" if terminal_record_like(value) else "metadata_only"
        reason = "artifacts_present_without_node_edge_delta"
    elif terminal_record_like(value):
        output_class = "terminal_record"
        reason = "terminal_record_observed"
    return {
        "observed_output_class": output_class,
        "observed_output_reason": reason,
        "observable_artifact_paths": [rel_path(root, path) for path in paths[:20]],
        "node_edge_fingerprint": summary["node_edge_fingerprint"],
        "node_edge_count_fingerprint": count_fingerprint if count_fallback["node_count"] + count_fallback["edge_count"] > 0 else None,
        "node_count": summary["node_count"] or count_fallback["node_count"],
        "edge_count": summary["edge_count"] or count_fallback["edge_count"],
        "node_edge_record_count": summary["node_edge_record_count"] or count_fallback["node_count"] + count_fallback["edge_count"],
        "kg_paths": summary["kg_paths"],
    }


def terminal_history_matches(root: Path, feature: dict[str, Any]) -> list[dict[str, Any]]:
    axis = str(feature.get("blocker_root_axis") or "")
    if not axis or axis == "unknown":
        return []
    candidates: list[Path] = []
    for group in (
        root / ".task" / "cycle",
        root / ".task" / "task_miss",
    ):
        if group.is_dir():
            candidates.extend(
                path
                for path in group.rglob("*")
                if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".md"}
            )
    sealed = root / ".task" / "sealed_blocker_families.json"
    if sealed.is_file():
        candidates.append(sealed)
    matches: list[dict[str, Any]] = []
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)[:240]:
        text = read_text(path).lower()
        if axis not in text:
            continue
        reason = None
        for token in ("no_material_miss", "no-material-miss", "fail_closed", "fail-closed", "terminal", "sealed"):
            if token in text:
                reason = token
                break
        if reason:
            matches.append({"path": rel_path(root, path), "reason_code": reason})
        if len(matches) >= 10:
            break
    return matches


def append_feature_symbol_registry(root: Path, current_item: dict[str, Any]) -> dict[str, Any]:
    feature = current_item.get("feature_symbol")
    observed = current_item.get("observed_output")
    if not isinstance(feature, dict) or not isinstance(observed, dict) or not feature.get("symbol"):
        return {"write_enabled": True, "updated": False, "reason": "missing_feature_symbol"}
    registry = load_symbol_registry(root)
    previous = registry.get(str(feature["symbol"])) or {}
    observed_class = str(observed.get("observed_output_class") or "unknown")
    prior_classes = [str(item) for item in previous.get("observed_output_classes", []) if item is not None]
    if observed_class == "node_edge_delta":
        occurrence_count = 1
        status = "observed_delta"
    else:
        occurrence_count = int(number_value(previous.get("occurrence_count")) or 0) + 1
        status = "recurring_no_delta" if occurrence_count >= 2 else "seen"
    record = {
        "symbol": feature["symbol"],
        "scope": "workflow_loop",
        "first_seen_cycle": previous.get("first_seen_cycle") or current_item.get("path"),
        "occurrence_count": occurrence_count,
        "consumed_input_fp": feature.get("consumed_input_fp"),
        "target_unit_fp": feature.get("target_unit_fp"),
        "target_unit_count": feature.get("target_unit_count"),
        "blocker_root_axis": feature.get("blocker_root_axis"),
        "observed_output_classes": [*prior_classes, observed_class][-12:],
        "last_observed_output_class": observed_class,
        "last_observed_node_edge_delta": int(observed.get("node_edge_record_count") or 0),
        "node_edge_fingerprint": observed.get("node_edge_fingerprint") or previous.get("node_edge_fingerprint"),
        "node_edge_count_fingerprint": observed.get("node_edge_count_fingerprint") or previous.get("node_edge_count_fingerprint"),
        "last_evidence_path": current_item.get("path"),
        "status": status,
        "updated_at": now_iso(),
    }
    registry_path = root / REGISTRY_REL_PATH
    try:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        with registry_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError as exc:
        return {"write_enabled": True, "updated": False, "reason": f"write_failed:{exc.__class__.__name__}", "path": REGISTRY_REL_PATH}
    return {
        "write_enabled": True,
        "updated": True,
        "path": REGISTRY_REL_PATH,
        "symbol": feature["symbol"],
        "occurrence_count": occurrence_count,
        "status": status,
    }


def candidate_files(root: Path) -> list[Path]:
    groups = [
        root / ".task" / "validation",
        root / ".task" / "task_miss",
        root / ".agent_log",
        root / ".issue",
    ]
    files: list[Path] = []
    for group in groups:
        if group.is_dir():
            files.extend(path for path in group.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".json", ".jsonl"})
    if (root / "task.md").is_file():
        files.append(root / "task.md")
    return sorted(files, key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)


def list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item) != ""]
    if isinstance(value, str) and value:
        return [value]
    return []


def normalize_dispositions(value: Any) -> set[str]:
    return {item.strip().lower() for item in list_values(value) if item.strip().lower() in DISPOSITION_UNIVERSE}


def gate_allowed_dispositions(name: str, gate: dict[str, Any]) -> set[str]:
    explicit = normalize_dispositions(gate.get("allowed_dispositions"))
    if explicit:
        return explicit
    if boolish(gate.get("requires_goal_productive_next")) or boolish(gate.get("requires_goal_productive_or_user_escalation")):
        return {"goal_productive", "terminal_blocked", "user_escalation"}
    if name == "command_surface_budget" and (boolish(gate.get("hard_gate")) or boolish(gate.get("budget_exceeded"))):
        return {"consolidation", "terminal_blocked"}
    return set(DISPOSITION_UNIVERSE)


def gate_constrains_disposition(name: str, gate: dict[str, Any]) -> bool:
    return any(
        (
            boolish(gate.get("constrains_disposition")),
            boolish(gate.get("hard_stop_required")),
            boolish(gate.get("hard_gate")),
            boolish(gate.get("requires_goal_productive_next")),
            boolish(gate.get("requires_goal_productive_or_user_escalation")),
            str(gate.get("status") or "").lower() == "block",
            name == "command_surface_budget" and boolish(gate.get("budget_exceeded")),
        )
    )


def effective_allowed_dispositions(gates: list[tuple[str, dict[str, Any]]]) -> tuple[list[str], dict[str, Any]]:
    constraining: list[set[str]] = []
    basis: dict[str, Any] = {}
    for name, gate in gates:
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
        effective = str(first_value(item, ("effective_progress_kind", "progress_kind")) or "").strip().lower()
        if effective and effective != "governance_only":
            break
        streak += 1
    return streak


def structured_progress(value: dict[str, Any]) -> str | None:
    for key in ("progress_verdict", "progress", "progress_status"):
        raw = value.get(key)
        if isinstance(raw, dict):
            raw = raw.get("verdict") or raw.get("progress_verdict")
        if isinstance(raw, str) and raw.lower() in {"advanced", "safety_only", "no_progress", "regressed"}:
            return raw.lower()
    return None


def structured_blockers(value: dict[str, Any]) -> list[str]:
    blockers = []
    for key in ("blockers", "remaining_blockers", "blocking_findings"):
        blockers.extend(list_values(value.get(key)))
    return blockers[:5]


def list_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "required", "present", "added"}
    return False


def number_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def float_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def value_at(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_value(value: dict[str, Any], paths: tuple[str, ...]) -> Any:
    for path in paths:
        current = value_at(value, path) if "." in path else value.get(path)
        if current is None:
            continue
        if isinstance(current, (list, dict)) and not current:
            continue
        if isinstance(current, str) and not current.strip():
            continue
        return current
    return None


def first_mapping(value: dict[str, Any], paths: tuple[str, ...]) -> dict[str, Any]:
    for path in paths:
        current = value_at(value, path) if "." in path else value.get(path)
        if isinstance(current, dict) and current:
            return current
    return {}


def list_field_paths(value: dict[str, Any], paths: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    for path in paths:
        raw = value_at(value, path) if "." in path else value.get(path)
        items.extend(list_field(raw))
    return sorted(set(items))


def normalize_root_family_key(*values: Any) -> str:
    raw = "|".join(str(value or "") for value in values if value is not None and str(value).strip()).lower()
    if not raw:
        return "unknown"
    raw = VOLATILE_SIGNATURE_RE.sub("-", raw)
    raw = re.sub(r"\bv\d+\b|[-_]v\d+\b", "vnnn", raw)
    raw = SIGNATURE_TOKEN_RE.sub("-", raw).strip("-_.:/|")
    for _ in range(6):
        updated = FACET_SUFFIX_RE.sub("", raw).strip("-_.:/|")
        if updated == raw:
            break
        raw = updated
    tokens = [token for token in re.split(r"[|._:/-]+", raw) if token and not token.isdigit()]
    return "_".join(dict.fromkeys(tokens[:16]))[:200] or "unknown"


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
        if str(key).strip().lower() in VALIDATOR_RESULT_KEYS:
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


def first_count_by_key(mapping: dict[str, Any], keys: set[str]) -> int | None:
    for key, value in mapping.items():
        if str(key).strip().lower() not in keys:
            continue
        count = number_value(value)
        if count is not None:
            return count
    return None


def validator_integrity_gate(value: Any) -> dict[str, Any]:
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
            declared = first_count_by_key(item, POPULATION_COUNT_KEYS)
            inspected = first_count_by_key(item, INSPECTED_COUNT_KEYS)
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


def existing_artifact_paths(root: Path, paths: list[str]) -> list[str]:
    existing: list[str] = []
    for item in paths:
        if not item or "://" in item:
            continue
        path = Path(item)
        if not path.is_absolute():
            path = root / path
        try:
            if path.is_file() and path.stat().st_size > 0:
                existing.append(rel_path(root, path))
        except OSError:
            continue
    return sorted(set(existing))


def artifact_role_paths(value: Any, roles: set[str]) -> list[str]:
    if not roles:
        return []
    paths: list[str] = []
    normalized_roles = {role.strip().lower() for role in roles if role and role.strip()}

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            role = str(item.get("role") or item.get("artifact_role") or "").strip().lower()
            artifact_path = item.get("artifact_path") or item.get("path")
            exists = item.get("exists")
            if role in normalized_roles and artifact_path and exists is not False:
                paths.extend(list_field(artifact_path))
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return sorted(set(paths))


def artifact_summary_role_paths(root: Path, paths: list[str], roles: set[str]) -> list[str]:
    if not roles:
        return []
    collected: list[str] = []
    for item in paths:
        if not item or "://" in item:
            continue
        path = Path(item)
        if not path.is_absolute():
            path = root / path
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        if path.suffix.lower() == ".jsonl":
            for record in read_jsonl(path):
                collected.extend(artifact_role_paths(record, roles))
        else:
            summary = read_json(path)
            if summary is not None:
                collected.extend(artifact_role_paths(summary, roles))
    return sorted(set(collected))


def output_delta_gate(value: dict[str, Any], observed: dict[str, Any] | None = None) -> dict[str, Any]:
    produced = first_value(
        value,
        (
            "produced_domain_delta",
            "output_delta.produced_domain_delta",
            "output_delta_gate.produced_domain_delta",
            "quality_review.produced_domain_delta",
            "result.output_delta.produced_domain_delta",
        ),
    )
    metadata_only = first_value(
        value,
        (
            "metadata_only",
            "output_delta.metadata_only",
            "output_delta_gate.metadata_only",
            "quality_review.metadata_only",
            "result.output_delta.metadata_only",
        ),
    )
    status = first_value(
        value,
        (
            "output_delta_status",
            "output_delta.status",
            "output_delta_gate.output_delta_status",
            "quality_review.output_delta_status",
            "result.output_delta.output_delta_status",
        ),
    )
    effective = first_value(
        value,
        (
            "effective_progress_kind",
            "output_delta.effective_progress_kind",
            "output_delta_gate.effective_progress_kind",
            "result.output_delta.effective_progress_kind",
        ),
    )
    changed = first_value(
        value,
        (
            "changed_vs_previous",
            "output_delta.changed_vs_previous",
            "output_delta_gate.changed_vs_previous",
            "quality_review.changed_vs_previous",
            "result.output_delta.changed_vs_previous",
        ),
    )
    semantic = first_value(
        value,
        (
            "semantic_progress",
            "output_delta.semantic_progress",
            "output_delta_gate.semantic_progress",
            "quality_review.semantic_progress",
            "result.output_delta.semantic_progress",
        ),
    )
    declared_produced = boolish(produced)
    declared_metadata_only = boolish(metadata_only)
    declared_changed = boolish(changed)
    declared_semantic = boolish(semantic)
    has_strict_delta_fields = produced is not None and (changed is not None or semantic is not None)
    observed_class = (observed or {}).get("observed_output_class")
    override_applied = observed_class in {"node_edge_delta", "metadata_only", "terminal_record"}
    if override_applied:
        declared_status = str(status) if status is not None else None
        observed_produced = observed_class == "node_edge_delta"
        produced_value = observed_produced and (not has_strict_delta_fields or (declared_changed and declared_semantic))
        metadata_value = observed_class != "node_edge_delta" or (observed_produced and not produced_value)
        effective_value = "goal_productive" if produced_value else "governance_only"
        status_value = declared_status or f"observed_{observed_class}"
    else:
        produced_value = declared_produced and (not has_strict_delta_fields or (declared_changed and declared_semantic))
        metadata_value = declared_metadata_only or (declared_produced and has_strict_delta_fields and not produced_value)
        effective_value = str(effective).lower() if isinstance(effective, str) else None
        status_value = str(status) if status is not None else None
    return {
        "output_delta_status": status_value,
        "produced_domain_delta": produced_value,
        "changed_vs_previous": declared_changed,
        "semantic_progress": declared_semantic,
        "metadata_only": metadata_value,
        "effective_progress_kind": effective_value,
        "declared_produced_domain_delta": declared_produced,
        "declared_changed_vs_previous": declared_changed,
        "declared_semantic_progress": declared_semantic,
        "declared_metadata_only": declared_metadata_only,
        "observed_output_class": observed_class,
        "observed_output_reason": (observed or {}).get("observed_output_reason"),
        "observed_override_applied": override_applied,
        "observed_output": observed or {},
        "has_output_delta_fields": produced is not None or metadata_only is not None or status is not None or effective is not None,
    }


def coverage_quality_delta_gate(value: dict[str, Any]) -> dict[str, Any]:
    gate = first_mapping(
        value,
        (
            "coverage_quality_delta_gate",
            "quality_delta_gate",
            "output_delta.coverage_quality_delta_gate",
            "output_delta_gate.coverage_quality_delta_gate",
            "anti_loop_progress_gate.coverage_quality_delta_gate",
            "result.coverage_quality_delta_gate",
        ),
    )
    if gate:
        return gate
    quality = first_mapping(value, ("quality_vector", "output_delta.quality_vector", "output_delta_gate.quality_vector"))
    previous = first_mapping(
        value,
        ("previous_quality_vector", "output_delta.previous_quality_vector", "output_delta_gate.previous_quality_vector"),
    )
    if not quality:
        return {}
    def metric(mapping: dict[str, Any], key: str) -> float:
        aliases = {
            "causal_edge_count": ("causal_edge_count", "causal_or_temporal_edge_count", "causal_temporal_edge_count"),
            "windows_covered": ("windows_covered", "source_windows_covered", "window_count", "selected_source_window_count"),
        }
        for candidate in aliases.get(key, (key,)):
            if candidate in mapping:
                return float_number(mapping.get(candidate)) or 0.0
        return 0

    current = {key: metric(quality, key) for key in QUALITY_DELTA_KEYS}
    previous_values = {key: metric(previous, key) for key in QUALITY_DELTA_KEYS}
    improved = [key for key in QUALITY_DELTA_KEYS if current[key] > previous_values[key]]
    return {
        "gate": "G-COV",
        "quality_delta_pass": bool(improved),
        "improved_fields": improved,
        "current_quality_vector": current,
        "previous_quality_vector": previous_values,
        "status": "pass" if improved else "block",
    }


def provider_scale_dispatch_gate(value: dict[str, Any], coverage_gate: dict[str, Any]) -> dict[str, Any]:
    gate = first_mapping(
        value,
        (
            "provider_scale_dispatch_gate",
            "dispatch_gate",
            "anti_loop_progress_gate.provider_scale_dispatch_gate",
            "loop_breaker_packet.provider_scale_dispatch_gate",
            "result.provider_scale_dispatch_gate",
        ),
    )
    if gate:
        return gate
    provider_count = number_value(
        first_value(
            value,
            (
                "provider_request_count",
                "failure_autopsy.provider_request_count",
                "failure_autopsy_packet.provider_request_count",
                "run.provider_request_count",
                "result.provider_request_count",
            ),
        )
    )
    provider_count = provider_count or 0
    current = coverage_gate.get("current_quality_vector") if isinstance(coverage_gate.get("current_quality_vector"), dict) else {}
    current_all_zero = bool(current) and all((number_value(current.get(key)) or 0) <= 0 for key in QUALITY_DELTA_KEYS)
    previous_all_zero = boolish(coverage_gate.get("previous_high_water_all_zero") or coverage_gate.get("high_water_all_zero"))
    dispatch_required = provider_count == 0 and previous_all_zero and current_all_zero
    return {
        "gate": "G-DISPATCH",
        "provider_request_count": provider_count,
        "high_water_all_zero": previous_all_zero and current_all_zero,
        "dispatch_required": dispatch_required,
        "hard_stop_required": dispatch_required,
        "constrains_disposition": dispatch_required,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "status": "block" if dispatch_required else "ok",
    }


def supplied_input_delta_gate(root: Path, value: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    raw_paths = list_field_paths(
        value,
        (
            "supplied_input_artifact_paths",
            "input_artifact_paths",
            "new_input_artifact_paths",
            "positive_input_delta_gate.supplied_input_artifact_paths",
            "positive_input_delta_gate.input_artifact_paths",
            "loop_breaker_packet.supplied_input_artifact_paths",
            "loop_breaker_packet.positive_input_delta_gate.supplied_input_artifact_paths",
            "result.positive_input_delta_gate.supplied_input_artifact_paths",
        ),
    )
    input_roles = {
        role.strip().lower()
        for role in list_field_paths(
            value,
            (
                "new_input_kinds",
                "input_kinds",
                "required_new_input_kinds",
                "introduced_input_kinds",
                "positive_input_delta_gate.new_input_kinds",
                "positive_input_delta_gate.input_kinds",
                "positive_input_delta_gate.required_new_input_kinds",
                "loop_breaker_packet.new_input_kinds",
                "loop_breaker_packet.required_new_input_kinds",
                "result.positive_input_delta_gate.new_input_kinds",
                "result.positive_input_delta_gate.required_new_input_kinds",
            ),
        )
        if role.strip()
    }
    role_paths = artifact_role_paths(value, input_roles)
    role_paths.extend(artifact_summary_role_paths(root, raw_paths, input_roles))
    existing_paths = existing_artifact_paths(root, raw_paths + role_paths)
    produced = boolish(delta.get("produced_domain_delta"))
    return {
        "has_supplied_input_delta": produced or bool(existing_paths),
        "supplied_input_artifact_paths": existing_paths,
        "missing_or_empty_input_artifact_paths": sorted(set(raw_paths + role_paths) - set(existing_paths)),
        "produced_domain_delta": produced,
    }


TRANSIENT_PROVIDER_FAILURE_CLASSES = {
    "empty",
    "parse",
    "parse_error",
    "parsing",
    "malformed",
    "rate_limit",
    "timeout",
    "transient",
    "incomplete",
}
PERMANENT_PROVIDER_FAILURE_CLASSES = {"auth", "permanent", "policy", "forbidden", "invalid_request"}
MITIGATION_REQUIREMENTS: dict[str, set[str]] = {
    "empty": {"structured_output"},
    "parse": {"structured_output"},
    "parse_error": {"structured_output"},
    "parsing": {"structured_output"},
    "malformed": {"structured_output"},
    "timeout": {"window_reduce", "timeout_budget_increase", "backoff_retry>=3", "model_fallback"},
    "transient": {"window_reduce", "timeout_budget_increase", "backoff_retry>=3", "model_fallback"},
    "rate_limit": {"backoff_retry>=3", "model_fallback"},
    "incomplete": {"structured_output", "window_reduce"},
}


def provider_failure_class(value: dict[str, Any]) -> str | None:
    explicit = first_value(
        value,
        (
            "failure_class",
            "failure_autopsy.failure_class",
            "failure_autopsy_packet.failure_class",
            "provider_failure_class",
            "provider.failure_class",
            "run.failure_autopsy.failure_class",
            "result.failure_autopsy.failure_class",
        ),
    )
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    http_status = first_value(value, ("http_status", "failure_autopsy.http_status", "result.failure_autopsy.http_status"))
    statuses = http_status if isinstance(http_status, list) else [http_status]
    for status in statuses:
        code = number_value(status)
        if code == 429:
            return "rate_limit"
        if code in {408, 504}:
            return "timeout"
        if code is not None and 500 <= code <= 599:
            return "transient"
        if code in {401, 403}:
            return "auth"
    if boolish(first_value(value, ("provider_response_empty", "empty_provider_response", "result.provider_response_empty"))):
        return "empty"
    if boolish(first_value(value, ("provider_response_parse_failed", "provider_parse_failed", "result.provider_response_parse_failed"))):
        return "parse"
    status = first_value(value, ("provider_status", "provider.status", "runtime_status", "result.provider_status"))
    if isinstance(status, str):
        lowered = status.lower()
        if "empty" in lowered:
            return "empty"
        if "parse" in lowered or "malformed" in lowered:
            return "parse"
        if "timeout" in lowered:
            return "timeout"
        if "rate" in lowered:
            return "rate_limit"
        if "incomplete" in lowered:
            return "incomplete"
        if "auth" in lowered:
            return "auth"
    return None


def normalized_mitigation_name(value: str) -> str | None:
    lowered = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not lowered:
        return None
    if lowered in {"structured_output", "json_schema", "response_format"}:
        return "structured_output"
    if lowered in {"window_reduce", "window_reduced", "smaller_window"}:
        return "window_reduce"
    if lowered in {"timeout_budget_increase", "timeout_increase", "timeout_extended", "longer_timeout"}:
        return "timeout_budget_increase"
    if lowered in {"backoff_retry>=3", "backoff_retry_3", "retry>=3", "retries>=3"}:
        return "backoff_retry>=3"
    if lowered in {"model_fallback", "fallback_model", "alternate_model"}:
        return "model_fallback"
    if "structured" in lowered:
        return "structured_output"
    if "window" in lowered and ("reduce" in lowered or "smaller" in lowered):
        return "window_reduce"
    if "timeout" in lowered and any(token in lowered for token in ("increase", "extend", "budget", "longer")):
        return "timeout_budget_increase"
    if "backoff" in lowered or "retry" in lowered:
        return "backoff_retry>=3" if any(token in lowered for token in (">=3", "_3", "3")) else None
    if "model" in lowered and "fallback" in lowered:
        return "model_fallback"
    return None


def mitigation_list(value: Any) -> list[str]:
    raw_items: list[str] = []
    if isinstance(value, list):
        raw_items = [str(item) for item in value if item is not None]
    elif isinstance(value, str):
        raw_items = re.split(r"[,;\s]+", value)
    names = [name for item in raw_items if (name := normalized_mitigation_name(item))]
    return sorted(set(names))


def provider_mitigation_gate(value: dict[str, Any], failure_class: str | None, request_count: int | None) -> dict[str, Any]:
    attempted = mitigation_list(
        first_value(
            value,
            (
                "mitigations_attempted",
                "failure_autopsy.mitigations_attempted",
                "failure_autopsy_packet.mitigations_attempted",
                "run.failure_autopsy.mitigations_attempted",
                "result.failure_autopsy.mitigations_attempted",
            ),
        )
    )
    unavailable = mitigation_list(
        first_value(
            value,
            (
                "mitigations_unavailable",
                "failure_autopsy.mitigations_unavailable",
                "failure_autopsy_packet.mitigations_unavailable",
                "run.failure_autopsy.mitigations_unavailable",
                "result.failure_autopsy.mitigations_unavailable",
            ),
        )
    )
    if request_count is not None and request_count >= 3:
        attempted = sorted(set([*attempted, "backoff_retry>=3"]))
    required = sorted(MITIGATION_REQUIREMENTS.get(failure_class or "", set()))
    covered = set(attempted) | set(unavailable)
    missing = sorted(set(required) - covered)
    transient_failure = failure_class in TRANSIENT_PROVIDER_FAILURE_CLASSES
    return {
        "mitigations_attempted": attempted,
        "mitigations_unavailable": unavailable,
        "required_mitigations": required,
        "missing_mitigations": missing,
        "mitigation_required": transient_failure and bool(required),
        "mitigation_exhausted": transient_failure and bool(required) and not missing,
    }


def provider_reattempt_gate(value: dict[str, Any]) -> dict[str, Any]:
    request_count = number_value(
        first_value(
            value,
            (
                "provider_request_count",
                "provider.request_count",
                "failure_autopsy.provider_request_count",
                "failure_autopsy_packet.provider_request_count",
                "run.provider_request_count",
                "result.provider_request_count",
            ),
        )
    )
    failure_class = provider_failure_class(value)
    mitigation = provider_mitigation_gate(value, failure_class, request_count)
    authority_allows_retry = boolish(
        first_value(
            value,
            (
                "authority_allows_retry",
                "provider_retry_allowed",
                "retry_allowed",
                "authority.provider_retry_allowed",
                "authority_policy.provider_retry_allowed",
                "failure_autopsy_packet.authority_allows_retry",
                "loop_breaker_packet.authority_allows_retry",
            ),
        )
    )
    transient_failure = failure_class in TRANSIENT_PROVIDER_FAILURE_CLASSES
    permanent_failure = failure_class in PERMANENT_PROVIDER_FAILURE_CLASSES
    mitigation_missing = transient_failure and mitigation["mitigation_required"] and not mitigation["mitigation_exhausted"]
    reattempt_required = transient_failure and mitigation_missing and authority_allows_retry
    seal_allowed = permanent_failure or not mitigation_missing
    return {
        "provider_request_count": request_count,
        "failure_class": failure_class,
        "authority_allows_retry": authority_allows_retry,
        "transient_failure": transient_failure,
        "permanent_failure": permanent_failure,
        **mitigation,
        "provider_mitigation_required": mitigation_missing,
        "provider_reattempt_required": reattempt_required,
        "provider_retreat_allowed": permanent_failure or (transient_failure and not mitigation_missing),
        "provider_terminal_seal_allowed": seal_allowed,
        "provider_terminal_seal_denied_reason": "provider_failure_mitigation_unexhausted" if mitigation_missing else None,
    }


def normalized_signature(value: dict[str, Any], blockers: list[str]) -> str | None:
    explicit = value.get("blocker_signature") or value.get("normalized_blocker_signature")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    parts: list[str] = []
    for key in ("blocker_taxonomy", "issue_path", "task_miss_path", "target_surface", "provider_dependency", "missing_input_kind", "evidence_family"):
        parts.extend(list_field(value.get(key)))
    if not parts:
        parts.extend(blockers[:3])
    if not parts:
        return None
    text = "|".join(part.strip().lower() for part in parts if part and str(part).strip())
    text = SIGNATURE_TOKEN_RE.sub("-", text).strip("-")
    return text[:240] or None


def semantic_signature(value: dict[str, Any], blockers: list[str]) -> str | None:
    explicit = value.get("semantic_signature") or value.get("normalized_semantic_signature")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()

    raw_parts: list[str] = []
    for key in (
        "blocker_taxonomy",
        "issue_path",
        "task_miss_path",
        "provider_dependency",
        "missing_input_kind",
        "evidence_family",
        "target_surface",
        "blocker_signature",
    ):
        raw_parts.extend(list_field(value.get(key)))
    raw_parts.extend(blockers[:3])

    normalized = normalized_signature(value, blockers)
    if normalized:
        raw_parts.append(normalized)
    if not raw_parts:
        return None

    raw_text = "|".join(str(part).strip().lower() for part in raw_parts if str(part).strip())
    stable_text = VOLATILE_SIGNATURE_RE.sub("-", raw_text)
    stable_text = SIGNATURE_TOKEN_RE.sub("-", stable_text).strip("-")

    axes = [axis for axis, pattern in SEMANTIC_AXIS_PATTERNS if re.search(pattern, raw_text, re.IGNORECASE)]
    taxonomies = list_field(value.get("blocker_taxonomy"))[:2]
    provider_dependency = list_field(value.get("provider_dependency"))[:1]
    missing_kind = list_field(value.get("missing_input_kind"))[:1]

    parts = [*(item.lower() for item in taxonomies), *axes, *(item.lower() for item in provider_dependency), *(item.lower() for item in missing_kind)]
    if not parts and stable_text:
        tokens = [token for token in stable_text.split("-") if token and not token.isdigit()]
        parts = tokens[:8]
    text = "|".join(dict.fromkeys(parts))
    return text[:200] or None


def root_axis(value: dict[str, Any], blockers: list[str], semantic: str | None, signature: str | None) -> str | None:
    explicit = value.get("root_axis") or value.get("goal_root_axis") or value.get("loop_root_axis")
    if isinstance(explicit, str) and explicit.strip():
        return SIGNATURE_TOKEN_RE.sub("_", explicit.strip().lower()).strip("_")[:120] or None

    parts: list[str] = []
    for key in (
        "root_axis",
        "goal_axis",
        "blocker_taxonomy",
        "issue_path",
        "task_miss_path",
        "provider_dependency",
        "missing_input_kind",
        "evidence_family",
        "target_surface",
        "semantic_signature",
        "blocker_signature",
        "task_id",
        "output_delta_kind",
    ):
        parts.extend(list_field(value.get(key)))
    parts.extend(blockers[:5])
    if semantic:
        parts.append(semantic)
    if signature:
        parts.append(signature)
    if not parts:
        return None

    raw_text = "|".join(str(part).strip().lower() for part in parts if str(part).strip())
    for axis, pattern in ROOT_AXIS_PATTERNS:
        if re.search(pattern, raw_text, re.IGNORECASE):
            return axis

    stable_text = VOLATILE_SIGNATURE_RE.sub("-", raw_text)
    stable_text = SIGNATURE_TOKEN_RE.sub("-", stable_text).strip("-")
    tokens = [token for token in stable_text.split("-") if token and not token.isdigit()]
    return "_".join(tokens[:6])[:120] or None


def root_key(value: dict[str, Any], blockers: list[str], semantic: str | None, signature: str | None) -> str | None:
    explicit = value.get("root_key") or value.get("semantic_root_key") or value.get("loop_root_key")
    raw_parts: list[str] = []
    if isinstance(explicit, str) and explicit.strip():
        raw_parts.append(explicit)
    for item in (semantic, signature):
        if item:
            raw_parts.append(item)
    for key in (
        "semantic_signature",
        "normalized_semantic_signature",
        "blocker_signature",
        "target_surface",
        "evidence_family",
        "blocker_taxonomy",
        "issue_path",
        "task_miss_path",
    ):
        raw_parts.extend(list_field(value.get(key)))
    raw_parts.extend(blockers[:3])
    if not raw_parts:
        return None
    raw_text = "|".join(str(part).strip().lower() for part in raw_parts if str(part).strip())
    stable_text = VOLATILE_SIGNATURE_RE.sub("-", raw_text)
    stable_text = re.sub(r"(?:^|[-_.|:/])(?:v|ver|version)[-_.]?\d+\b", "-", stable_text, flags=re.IGNORECASE)
    stable_text = re.sub(r"(?:^|[-_.|:/])(?:\d{8,14}|\d{4}[-_.]?\d{2}[-_.]?\d{2})\b", "-", stable_text)
    stable_text = SIGNATURE_TOKEN_RE.sub("-", stable_text).strip("-_./:")
    tokens = [token for token in re.split(r"[-_/.:]+", stable_text) if token and not token.isdigit()]
    if not tokens:
        return None
    return "_".join(dict.fromkeys(tokens[:16]))[:200] or None


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
    return {
        "path": rel_path(root, path),
        "source": source,
        "confidence": confidence,
        "progress_verdict": progress,
        "progress_kind": kind,
        "progress_target": first_value(value, ("progress_target", "target_progress", "selected_progress_target")),
        "selected_task_source": first_value(value, ("selected_task_source", "derive.selected_task_source")),
        "selected_task_kind": first_value(value, ("selected_task_kind", "derive.selected_task_kind")),
        "disposition": first_value(value, ("selected_disposition", "disposition")),
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


def analyze(
    root: Path,
    recent: int,
    strict: bool,
    goal_productive_threshold: int,
    root_axis_threshold: int = 6,
    feature_symbol_threshold: int = 6,
    terminal_quiescence_threshold: int = TERMINAL_QUIESCENCE_STREAK_DEFAULT,
    write_registry: bool = False,
) -> dict[str, Any]:
    evidence: list[dict[str, Any]] = structured_evidence(root, max(1, recent))
    registry = load_symbol_registry(root)
    seen_paths = {item.get("path") for item in evidence}
    for path in candidate_files(root)[: max(1, recent)]:
        if rel_path(root, path) in seen_paths:
            continue
        text = read_text(path)
        progress = classify_progress(text)
        blockers = extract_blockers(text)
        lowered = text.lower()
        pseudo_value = {"evidence_family": "regex_text_fallback"}
        if blockers:
            pseudo_value["blocker_taxonomy"] = blockers[:3]
        if "produced_domain_delta=false" in lowered:
            pseudo_value["produced_domain_delta"] = False
        if "produced_domain_delta=true" in lowered:
            pseudo_value["produced_domain_delta"] = True
        if "metadata-only" in lowered or "metadata_only" in lowered:
            pseudo_value["metadata_only"] = True
        request_match = PROVIDER_REQUEST_COUNT_RE.search(text)
        if request_match:
            pseudo_value["provider_request_count"] = int(request_match.group(1))
        failure_match = FAILURE_CLASS_RE.search(text)
        if failure_match:
            pseudo_value["failure_class"] = failure_match.group(1).lower()
        if "authority_allows_retry=true" in lowered or "provider_retry_allowed=true" in lowered:
            pseudo_value["authority_allows_retry"] = True
        attempted = []
        for name in ("structured_output", "window_reduce", "timeout_budget_increase", "model_fallback"):
            if name in lowered or name.replace("_", "-") in lowered:
                attempted.append(name)
        if "backoff_retry" in lowered or "backoff retry" in lowered or "retries>=3" in lowered or "retry>=3" in lowered:
            attempted.append("backoff_retry>=3")
        if attempted:
            pseudo_value["mitigations_attempted"] = sorted(set(attempted))
        fallback_item = evidence_item_from_value(root, path, "regex_text_fallback", "low", pseudo_value, progress, blockers[:5], registry)
        fallback_kind = progress_kind(pseudo_value, progress, lowered)
        if not (fallback_item.get("output_delta_gate") or {}).get("observed_override_applied") and fallback_kind:
            fallback_item["progress_kind"] = fallback_kind
        fallback_item["new_input_kinds"] = extract_input_kinds(text)
        fallback_item["positive_input_delta_required"] = "positive_input_delta_required" in lowered or "positive input delta" in lowered
        fallback_item["metadata_only"] = bool((fallback_item.get("output_delta_gate") or {}).get("metadata_only")) or fallback_item.get("progress_kind") == "governance_only"
        fallback_item["task_correction_class"] = task_correction_class(
            pseudo_value,
            fallback_item.get("output_delta_gate") or {},
            fallback_item.get("coverage_quality_delta_gate") or {},
            fallback_item.get("provider_scale_dispatch_gate") or {},
            lowered,
        )
        fallback_item["detection_only"] = fallback_item["task_correction_class"] == "detection" and fallback_item.get("progress_kind") != "goal_productive"
        fallback_item["has_no_live_language"] = any(term in lowered for term in ("no-live", "fail-closed", "non-dispatchable", "safety_only"))
        fallback_item["has_source_backed_language"] = has_positive_source_backed_signal(lowered)
        evidence.append(fallback_item)
        if len(evidence) >= recent:
            break

    progress_items = [item for item in evidence if item.get("progress_verdict")]
    last_two = progress_items[:2]
    blocker_counter: Counter[str] = Counter()
    signature_counter: Counter[str] = Counter()
    semantic_counter: Counter[str] = Counter()
    root_axis_counter: Counter[str] = Counter()
    root_key_counter: Counter[str] = Counter()
    root_family_counter: Counter[str] = Counter()
    feature_symbol_counter: Counter[str] = Counter()
    feature_symbol_no_delta_counter: Counter[str] = Counter()
    feature_symbol_output_class_counter: Counter[str] = Counter()
    input_kind_counter: Counter[str] = Counter()
    supplied_input_paths: set[str] = set()
    provider_reattempt_records: list[dict[str, Any]] = []
    for item in progress_items:
        blocker_counter.update(item.get("blockers") or [])
        if item.get("blocker_signature"):
            signature_counter.update([str(item["blocker_signature"])])
        if item.get("semantic_signature"):
            semantic_counter.update([str(item["semantic_signature"])])
        if item.get("root_axis"):
            root_axis_counter.update([str(item["root_axis"])])
        if item.get("root_key"):
            root_key_counter.update([str(item["root_key"])])
        if item.get("blocker_root_family"):
            root_family_counter.update([str(item["blocker_root_family"])])
        feature = item.get("feature_symbol")
        observed = item.get("observed_output")
        if isinstance(feature, dict) and feature.get("symbol"):
            symbol = str(feature["symbol"])
            feature_symbol_counter.update([symbol])
            observed_class = str((observed or {}).get("observed_output_class") or "unknown")
            feature_symbol_output_class_counter.update([observed_class])
            if observed_class in {"metadata_only", "terminal_record"}:
                feature_symbol_no_delta_counter.update([symbol])
        input_kind_counter.update(item.get("new_input_kinds") or [])
        supplied_input_paths.update(str(path) for path in item.get("supplied_input_artifact_paths") or [])
        provider_gate = item.get("provider_reattempt_gate")
        if isinstance(provider_gate, dict) and (
            provider_gate.get("provider_reattempt_required") or provider_gate.get("provider_mitigation_required")
        ):
            provider_reattempt_records.append(
                {
                    "path": item.get("path"),
                    "provider_request_count": provider_gate.get("provider_request_count"),
                    "failure_class": provider_gate.get("failure_class"),
                    "authority_allows_retry": provider_gate.get("authority_allows_retry"),
                    "provider_mitigation_required": provider_gate.get("provider_mitigation_required"),
                    "missing_mitigations": provider_gate.get("missing_mitigations"),
                    "mitigations_attempted": provider_gate.get("mitigations_attempted"),
                    "mitigations_unavailable": provider_gate.get("mitigations_unavailable"),
                    "provider_terminal_seal_allowed": provider_gate.get("provider_terminal_seal_allowed"),
                }
            )
    repeated_blockers = [{"blocker": key, "count": count} for key, count in blocker_counter.most_common() if count >= 2]
    repeated_signatures = [{"blocker_signature": key, "count": count} for key, count in signature_counter.most_common() if count >= 2]
    repeated_semantic_signatures = [{"semantic_signature": key, "count": count} for key, count in semantic_counter.most_common() if count >= 2]
    repeated_feature_symbols = [{"feature_symbol": key, "count": count} for key, count in feature_symbol_counter.most_common() if count >= 2]
    recurring_no_delta_feature_symbols = [
        {"feature_symbol": key, "count": count}
        for key, count in feature_symbol_no_delta_counter.most_common()
        if count >= 2
    ]
    over_threshold_feature_symbols = [
        {"feature_symbol": key, "count": count}
        for key, count in feature_symbol_no_delta_counter.most_common()
        if count >= feature_symbol_threshold
    ]
    feature_terminal_history: list[dict[str, Any]] = []
    for repeated in recurring_no_delta_feature_symbols[:3]:
        symbol = repeated["feature_symbol"]
        source_item = next(
            (item for item in progress_items if isinstance(item.get("feature_symbol"), dict) and item["feature_symbol"].get("symbol") == symbol),
            None,
        )
        if source_item and isinstance(source_item.get("feature_symbol"), dict):
            for match in terminal_history_matches(root, source_item["feature_symbol"]):
                feature_terminal_history.append({"feature_symbol": symbol, **match})
    safety_count = sum(1 for item in progress_items if item.get("progress_verdict") == "safety_only")
    governance_only_count = sum(1 for item in progress_items if item.get("progress_kind") == "governance_only")
    metadata_only_count = sum(1 for item in progress_items if item.get("metadata_only"))
    no_live_count = sum(1 for item in evidence if item.get("has_no_live_language"))
    source_backed_count = sum(1 for item in evidence if item.get("has_source_backed_language"))
    positive_delta_required_count = sum(1 for item in evidence if item.get("positive_input_delta_required"))
    has_positive_input_delta = bool(input_kind_counter)
    has_positive_output_delta = any(
        boolish((item.get("output_delta_gate") or {}).get("produced_domain_delta"))
        and item.get("confidence") in {"high", "medium"}
        for item in progress_items
    )
    coverage_delta_items = [
        item.get("coverage_quality_delta_gate")
        for item in progress_items
        if isinstance(item.get("coverage_quality_delta_gate"), dict)
    ]
    coverage_quality_delta_gate_result = {
        "gate": "G-COV",
        "quality_delta_pass": any(boolish(item.get("quality_delta_pass")) for item in coverage_delta_items),
        "improved_fields": sorted(
            {
                str(field)
                for item in coverage_delta_items
                for field in (item.get("improved_fields") or [])
                if field
            }
        ),
        "status": "pass" if any(boolish(item.get("quality_delta_pass")) for item in coverage_delta_items) else "block",
    }
    dispatch_items = [
        item.get("provider_scale_dispatch_gate")
        for item in progress_items
        if isinstance(item.get("provider_scale_dispatch_gate"), dict)
    ]
    provider_scale_dispatch_gate_result = {
        "gate": "G-DISPATCH",
        "dispatch_required": any(boolish(item.get("dispatch_required")) for item in dispatch_items),
        "hard_stop_required": any(boolish(item.get("hard_stop_required")) for item in dispatch_items),
        "constrains_disposition": any(boolish(item.get("constrains_disposition")) for item in dispatch_items),
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "records": dispatch_items[:10],
        "status": "block" if any(boolish(item.get("dispatch_required")) for item in dispatch_items) else "ok",
    }
    has_supplied_input_delta = has_positive_output_delta or bool(supplied_input_paths)
    goal_productive_this_cycle = bool(progress_items and progress_items[0].get("progress_kind") == "goal_productive")
    cycles_since_goal_productive_output = 0
    for item in progress_items:
        if item.get("progress_kind") == "goal_productive":
            break
        cycles_since_goal_productive_output += 1
    sealed_families = collect_sealed_families(root)
    sealed_semantic = {str(item.get("semantic_signature")) for item in sealed_families if item.get("semantic_signature")}
    sealed_blocker = {str(item.get("blocker_signature")) for item in sealed_families if item.get("blocker_signature")}
    sealed_matches = sorted(set(semantic_counter) & sealed_semantic)
    sealed_blocker_matches = sorted(set(signature_counter) & sealed_blocker)
    surface_budget = command_surface_budget(root, threshold=12, metadata_only_count=metadata_only_count)
    repeated_root_keys = [{"root_key": key, "count": count} for key, count in root_key_counter.most_common() if count >= 2]
    primary_root_axis = next((str(item.get("root_axis")) for item in progress_items if item.get("root_axis")), None)
    if primary_root_axis is None and root_axis_counter:
        primary_root_axis = root_axis_counter.most_common(1)[0][0]
    primary_root_key = next((str(item.get("root_key")) for item in progress_items if item.get("root_key")), None)
    if primary_root_key is None and root_key_counter:
        primary_root_key = root_key_counter.most_common(1)[0][0]
    root_axis_items = [item for item in progress_items if item.get("root_axis") == primary_root_axis] if primary_root_axis else []
    root_key_items = [item for item in progress_items if item.get("root_key") == primary_root_key] if primary_root_key else []
    primary_root_family = next((str(item.get("blocker_root_family")) for item in progress_items if item.get("blocker_root_family")), None)
    if primary_root_family is None and root_family_counter:
        primary_root_family = root_family_counter.most_common(1)[0][0]
    root_family_items = [
        item for item in progress_items if item.get("blocker_root_family") == primary_root_family
    ] if primary_root_family else []
    root_axis_governance_only_count = sum(
        1 for item in root_axis_items if item.get("progress_kind") == "governance_only" or item.get("metadata_only")
    )
    root_axis_provider_neutral_count = sum(
        1
        for item in root_axis_items
        if "provider_neutral" in json.dumps(item, ensure_ascii=False, sort_keys=True).lower()
    )
    root_axis_produced_domain_delta = any(
        boolish((item.get("output_delta_gate") or {}).get("produced_domain_delta"))
        and item.get("confidence") in {"high", "medium"}
        for item in root_axis_items
    )
    root_key_governance_only_count = sum(
        1 for item in root_key_items if item.get("progress_kind") == "governance_only" or item.get("metadata_only")
    )
    root_key_produced_domain_delta = any(
        boolish((item.get("output_delta_gate") or {}).get("produced_domain_delta"))
        and item.get("confidence") in {"high", "medium"}
        for item in root_key_items
    )
    root_family_produced_domain_delta = any(
        boolish((item.get("output_delta_gate") or {}).get("produced_domain_delta"))
        and item.get("confidence") in {"high", "medium"}
        for item in root_family_items
    )
    detection_only_streak_count = 0
    for item in progress_items:
        if primary_root_family and item.get("blocker_root_family") != primary_root_family:
            continue
        if boolish(item.get("detection_only")) and item.get("progress_kind") != "goal_productive":
            detection_only_streak_count += 1
            continue
        break
    detection_balance_required = (
        bool(primary_root_family)
        and detection_only_streak_count >= DETECTION_ONLY_STREAK_CAP
        and not root_family_produced_domain_delta
    )
    root_axis_disabled = (
        bool(primary_root_axis)
        and root_axis_governance_only_count >= root_axis_threshold
        and not root_axis_produced_domain_delta
    )
    root_key_disabled = (
        bool(primary_root_key)
        and root_key_governance_only_count >= root_axis_threshold
        and not root_key_produced_domain_delta
    )
    autonomous_retarget_disabled = root_axis_disabled or root_key_disabled
    surface_budget["hard_gate"] = bool(surface_budget.get("consolidation_candidate_required"))
    surface_budget["strict_output_delta_present"] = has_positive_output_delta
    surface_budget["allowed_dispositions"] = (
        ["consolidation", "goal_productive", "terminal_blocked"]
        if has_positive_output_delta
        else ["consolidation", "terminal_blocked"]
    )
    surface_budget["constrains_disposition"] = bool(surface_budget.get("hard_gate"))
    goal_distance_requires = cycles_since_goal_productive_output > goal_productive_threshold
    feature_symbol_gate = {
        "registry_path": REGISTRY_REL_PATH,
        "registry_write_enabled": write_registry,
        "threshold": feature_symbol_threshold,
        "feature_symbol_counts": dict(feature_symbol_counter),
        "feature_symbol_no_delta_counts": dict(feature_symbol_no_delta_counter),
        "observed_output_class_counts": dict(feature_symbol_output_class_counter),
        "recurring_no_delta_feature_symbols": recurring_no_delta_feature_symbols[:10],
        "over_threshold_feature_symbols": over_threshold_feature_symbols[:10],
        "terminal_history_matches": feature_terminal_history[:10],
        "hard_stop_required": bool(over_threshold_feature_symbols or feature_terminal_history),
        "constrains_disposition": bool(over_threshold_feature_symbols or feature_terminal_history),
        "allowed_dispositions": ["goal_productive", "consolidation", "terminal_blocked", "user_escalation"],
    }
    root_axis_gate = {
        "root_axis": primary_root_axis,
        "root_key": primary_root_key,
        "threshold": root_axis_threshold,
        "root_axis_counts": dict(root_axis_counter),
        "root_key_counts": dict(root_key_counter),
        "root_axis_governance_only_count": root_axis_governance_only_count,
        "root_axis_provider_neutral_count": root_axis_provider_neutral_count,
        "root_axis_produced_domain_delta": root_axis_produced_domain_delta,
        "root_key_governance_only_count": root_key_governance_only_count,
        "root_key_produced_domain_delta": root_key_produced_domain_delta,
        "root_axis_disabled": root_axis_disabled,
        "root_key_disabled": root_key_disabled,
        "autonomous_retarget_disabled": autonomous_retarget_disabled,
        "hard_stop_required": autonomous_retarget_disabled,
        "constrains_disposition": autonomous_retarget_disabled,
        "requires_goal_productive_or_user_escalation": autonomous_retarget_disabled,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }
    goal_distance_gate = {
        "threshold": goal_productive_threshold,
        "cycles_since_goal_productive_output": cycles_since_goal_productive_output,
        "goal_productive_this_cycle": goal_productive_this_cycle,
        "requires_goal_productive_next": goal_distance_requires,
        "constrains_disposition": goal_distance_requires,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }
    validator_gate_records = [
        item.get("validator_integrity_gate")
        for item in progress_items
        if isinstance(item.get("validator_integrity_gate"), dict)
        and boolish((item.get("validator_integrity_gate") or {}).get("hard_stop_required"))
    ]
    validator_integrity_gate_result = {
        "gate": "G-INTEGRITY",
        "hard_stop_required": bool(validator_gate_records),
        "constrains_disposition": bool(validator_gate_records),
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "records": validator_gate_records[:10],
        "status": "block" if validator_gate_records else "ok",
    }
    detection_balance_gate = {
        "gate": "G-BALANCE",
        "root_family": primary_root_family,
        "detection_only_streak": detection_only_streak_count,
        "detection_only_streak_cap": DETECTION_ONLY_STREAK_CAP,
        "root_family_produced_domain_delta": root_family_produced_domain_delta,
        "requires_correction_or_terminal": detection_balance_required,
        "allowed_task_classes": ["correction", "terminal_blocked", "user_escalation"],
        "hard_stop_required": detection_balance_required,
        "constrains_disposition": detection_balance_required,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "status": "block" if detection_balance_required else "ok",
    }
    terminal_quiescence_gate_result = terminal_quiescence_gate(
        progress_items,
        has_supplied_input_delta,
        max(1, terminal_quiescence_threshold),
    )
    effective_allowed, disposition_basis = effective_allowed_dispositions(
        [
            ("command_surface_budget", surface_budget),
            ("feature_symbol_gate", feature_symbol_gate),
            ("root_axis_gate", root_axis_gate),
            ("goal_distance_gate", goal_distance_gate),
            ("provider_scale_dispatch_gate", provider_scale_dispatch_gate_result),
            ("validator_integrity_gate", validator_integrity_gate_result),
            ("detection_balance_gate", detection_balance_gate),
            ("terminal_quiescence_gate", terminal_quiescence_gate_result),
        ]
    )
    consolidation_streak_count = consolidation_streak(progress_items)

    findings: list[dict[str, Any]] = []
    if len(last_two) == 2 and all(item.get("progress_verdict") == "safety_only" for item in last_two):
        severity = "block" if strict and repeated_blockers else "warn"
        findings.append(
            {
                "severity": severity,
                "code": "consecutive_safety_only",
                "message": "The two most recent progress-bearing artifacts are `safety_only`.",
                "evidence": last_two,
            }
        )
    if repeated_blockers:
        findings.append(
            {
                "severity": "warn",
                "code": "repeated_blocker",
                "message": "The same blocker appears in multiple recent artifacts.",
                "evidence": repeated_blockers[:5],
            }
        )
    if repeated_signatures:
        severity = "block" if strict and not has_supplied_input_delta else "warn"
        findings.append(
            {
                "severity": severity,
                "code": "repeated_blocker_signature",
                "message": "The same normalized blocker signature appears in multiple recent artifacts.",
                "evidence": repeated_signatures[:5],
            }
        )
    if repeated_semantic_signatures:
        severity = "block" if strict and not has_supplied_input_delta else "warn"
        findings.append(
            {
                "severity": severity,
                "code": "repeated_semantic_signature",
                "message": "The same semantic blocker family appears in multiple recent artifacts.",
                "evidence": repeated_semantic_signatures[:5],
            }
        )
    if recurring_no_delta_feature_symbols:
        threshold_hit = bool(over_threshold_feature_symbols)
        terminal_hit = bool(feature_terminal_history)
        severity = "block" if (threshold_hit or terminal_hit or strict) and not has_supplied_input_delta else "warn"
        findings.append(
            {
                "severity": severity,
                "code": "repeated_feature_symbol_no_delta",
                "message": "The same observed-over-declared workflow feature symbol recurred without observed node/edge delta; labels, version suffixes, and self-declared produced_domain_delta do not reset this counter.",
                "evidence": {
                    "recurring_no_delta_feature_symbols": recurring_no_delta_feature_symbols[:5],
                    "over_threshold_feature_symbols": over_threshold_feature_symbols[:5],
                    "terminal_history_matches": feature_terminal_history[:10],
                    "threshold": feature_symbol_threshold,
                },
            }
        )
    if repeated_root_keys:
        severity = "block" if strict and not has_supplied_input_delta else "warn"
        findings.append(
            {
                "severity": severity,
                "code": "repeated_root_key",
                "message": "The same suffix-normalized root key appears in multiple recent artifacts; version/date/sequence suffixes do not reset the loop counter.",
                "evidence": repeated_root_keys[:5],
            }
        )
    if len(last_two) == 2 and all(item.get("progress_kind") == "governance_only" for item in last_two):
        findings.append(
            {
                "severity": "block" if strict else "warn",
                "code": "consecutive_governance_only",
                "message": "The two most recent progress-bearing artifacts are governance-only, not goal-productive.",
                "evidence": last_two,
            }
        )
    if len(last_two) == 2 and all(item.get("metadata_only") for item in last_two):
        findings.append(
            {
                "severity": "block" if strict else "warn",
                "code": "consecutive_metadata_only",
                "message": "The two most recent progress-bearing artifacts are metadata-only after output-delta review.",
                "evidence": last_two,
                "recommendation": "resume_primary_output",
            }
        )
    if cycles_since_goal_productive_output > goal_productive_threshold:
        findings.append(
            {
                "severity": "block" if strict else "warn",
                "code": "goal_productive_output_stale",
                "message": "Recent cycles exceed the goal-productive output threshold.",
                "evidence": {
                    "cycles_since_goal_productive_output": cycles_since_goal_productive_output,
                    "threshold": goal_productive_threshold,
                },
            }
        )
    if autonomous_retarget_disabled:
        findings.append(
            {
                "severity": "block",
                "code": "autonomous_retarget_disabled",
                "message": "The same root axis or suffix-normalized root key has exceeded the autonomous governance-only/provider-neutral retarget threshold without a high-confidence domain delta.",
                "evidence": {
                    "root_axis": primary_root_axis,
                    "root_key": primary_root_key,
                    "threshold": root_axis_threshold,
                    "root_axis_disabled": root_axis_disabled,
                    "root_key_disabled": root_key_disabled,
                    "root_axis_governance_only_count": root_axis_governance_only_count,
                    "root_axis_provider_neutral_count": root_axis_provider_neutral_count,
                    "root_axis_produced_domain_delta": root_axis_produced_domain_delta,
                    "root_key_governance_only_count": root_key_governance_only_count,
                    "root_key_produced_domain_delta": root_key_produced_domain_delta,
                },
            }
        )
    if (sealed_matches or sealed_blocker_matches) and not has_supplied_input_delta:
        findings.append(
            {
                "severity": "block" if strict else "warn",
                "code": "sealed_semantic_family_without_input_delta",
                "message": "A sealed blocker family recurred without a supplied input artifact or positive output delta.",
                "evidence": {"semantic_matches": sealed_matches, "blocker_matches": sealed_blocker_matches},
            }
        )
    if positive_delta_required_count and not has_supplied_input_delta:
        findings.append(
            {
                "severity": "block" if strict else "warn",
                "code": "positive_input_delta_missing",
                "message": "Recent evidence requires a positive input delta, but no non-empty supplied artifact or positive output delta was detected.",
                "evidence": {"positive_delta_required_count": positive_delta_required_count},
            }
        )
    if has_positive_input_delta and not has_supplied_input_delta:
        findings.append(
            {
                "severity": "block" if strict else "warn",
                "code": "named_only_input_delta",
                "message": "`has_new_input_kind` is present, but no non-empty supplied input artifact or positive output delta proves a real input delta.",
                "evidence": {"new_input_kinds": sorted(input_kind_counter), "supplied_input_artifact_paths": sorted(supplied_input_paths)},
            }
        )
    if provider_reattempt_records:
        findings.append(
            {
                "severity": "block" if strict else "warn",
                "code": "provider_reattempt_required",
                "message": "A transient provider failure cannot be treated as provider-terminal while required mitigations remain unexhausted.",
                "evidence": provider_reattempt_records[:5],
            }
        )
    if surface_budget.get("consolidation_candidate_required"):
        findings.append(
            {
                "severity": "block",
                "code": "command_surface_budget_exceeded",
                "message": "Contract/preflight command surface is over budget while recent progress is metadata-only; derive must register/select consolidation, select goal-productive work, or record terminal state.",
                "evidence": surface_budget,
            }
        )
    if provider_scale_dispatch_gate_result["dispatch_required"]:
        findings.append(
            {
                "severity": "block",
                "code": "provider_scale_dispatch_required",
                "message": "No provider dispatch occurred and coverage/quality high-water evidence remains all-zero; derive must choose bounded dispatch/scale work if authority permits, or terminal/user-escalate with missing authority/input.",
                "evidence": provider_scale_dispatch_gate_result,
            }
        )
    if validator_gate_records:
        findings.append(
            {
                "severity": "block",
                "code": "validator_integrity_or_coverage_failed",
                "message": "A validator reported a top-level pass despite embedded failures, or inspected fewer items than its declared population.",
                "evidence": validator_integrity_gate_result,
            }
        )
    if detection_balance_required:
        findings.append(
            {
                "severity": "block",
                "code": "detection_only_streak_capped",
                "message": "Detection-only work repeated for the same root blocker family without primary-output delta; derive must select correction, terminal_blocked, or user_escalation.",
                "evidence": detection_balance_gate,
            }
        )
    if terminal_quiescence_gate_result.get("quiescence_required"):
        findings.append(
            {
                "severity": "block",
                "code": "terminal_quiescence_required",
                "message": "The same terminal root recurred without supplied input delta; orchestrator must stop automatic domain-cycle restart and record only one user handoff note.",
                "evidence": terminal_quiescence_gate_result,
            }
        )
    if consolidation_streak_count >= CONSOLIDATION_STREAK_CAP:
        if "consolidation" in effective_allowed:
            effective_allowed = [item for item in effective_allowed if item != "consolidation"]
        findings.append(
            {
                "severity": "block",
                "code": "consolidation_streak_capped",
                "message": "Consecutive governance-only consolidation reached the cap; the next disposition must reduce goal distance or terminal/user-escalate.",
                "evidence": {"consolidation_streak": consolidation_streak_count, "cap": CONSOLIDATION_STREAK_CAP},
            }
        )
    if no_live_count >= 2 and source_backed_count == 0:
        findings.append(
            {
                "severity": "warn",
                "code": "no_live_micro_contract_loop",
                "message": "Recent artifacts repeatedly use no-live/fail-closed language without source-backed or bounded-preflight evidence language.",
                "evidence": {"no_live_count": no_live_count, "source_backed_count": source_backed_count},
            }
        )
    if any(item.get("confidence") == "low" for item in evidence):
        findings.append(
            {
                "severity": "info",
                "code": "regex_low_confidence_fallback_used",
                "message": "Some progress evidence came from text regex fallback because structured ledger/index/validation evidence was insufficient.",
            }
        )

    terminal_blocker_candidate = None
    if (
        repeated_root_keys
        or repeated_semantic_signatures
        or repeated_signatures
        or recurring_no_delta_feature_symbols
        or sealed_matches
        or sealed_blocker_matches
    ) and not has_supplied_input_delta and not provider_reattempt_records:
        key = repeated_root_keys[0]["root_key"] if repeated_root_keys else None
        semantic = repeated_semantic_signatures[0]["semantic_signature"] if repeated_semantic_signatures else (sealed_matches[0] if sealed_matches else None)
        blocker = repeated_signatures[0]["blocker_signature"] if repeated_signatures else (sealed_blocker_matches[0] if sealed_blocker_matches else None)
        terminal_blocker_candidate = {
            "root_key": key,
            "semantic_signature": semantic,
            "blocker_signature": blocker,
            "feature_symbol": recurring_no_delta_feature_symbols[0]["feature_symbol"] if recurring_no_delta_feature_symbols else None,
            "reason": "Repeated suffix-normalized root key, semantic blocker family, or blocker signature without a detected positive input delta.",
            "required_handoff": "Provide a new input kind, authority change, external-state change, or a safe provider-neutral task-pack item.",
            "recent_evidence_paths": [item.get("path") for item in evidence[:recent] if item.get("path")],
            "seal_family_path": ".task/sealed_blocker_families.json",
        }

    status = "ok"
    if any(item["severity"] == "block" for item in findings):
        status = "block"
    elif findings:
        status = "warn"
    registry_update = append_feature_symbol_registry(root, progress_items[0]) if write_registry and progress_items else {"write_enabled": write_registry, "updated": False}
    return {
        "status": status,
        "checked_at": now_iso(),
        "workspace": str(root),
        "recent_limit": recent,
        "safety_only_count": safety_count,
        "governance_only_count": governance_only_count,
        "metadata_only_count": metadata_only_count,
        "repeated_blocker_signatures": repeated_signatures[:5],
        "repeated_semantic_signatures": repeated_semantic_signatures[:5],
        "repeated_root_keys": repeated_root_keys[:5],
        "root_family_counts": dict(root_family_counter),
        "repeated_feature_symbols": repeated_feature_symbols[:5],
        "feature_symbol_gate": feature_symbol_gate,
        "feature_symbol_registry_update": registry_update,
        "coverage_quality_delta_gate": coverage_quality_delta_gate_result,
        "provider_scale_dispatch_gate": provider_scale_dispatch_gate_result,
        "validator_integrity_gate": validator_integrity_gate_result,
        "detection_balance_gate": detection_balance_gate,
        "terminal_quiescence_gate": terminal_quiescence_gate_result,
        "root_axis_gate": root_axis_gate,
        "autonomous_retarget_disabled": autonomous_retarget_disabled,
        "hard_stop_required": (
            autonomous_retarget_disabled
            or provider_scale_dispatch_gate_result["dispatch_required"]
            or validator_integrity_gate_result["hard_stop_required"]
            or detection_balance_gate["hard_stop_required"]
            or terminal_quiescence_gate_result["quiescence_required"]
        ),
        "requires_goal_productive_or_user_escalation": autonomous_retarget_disabled
        or provider_scale_dispatch_gate_result["dispatch_required"]
        or detection_balance_gate["hard_stop_required"],
        "semantic_signature_gate": {
            "preferred_for_loop_comparison": True,
            "sealed_matches": sealed_matches,
            "sealed_blocker_matches": sealed_blocker_matches,
            "sealed_family_records": sealed_families[:10],
        },
        "goal_distance_gate": goal_distance_gate,
        "effective_allowed_dispositions": effective_allowed,
        "disposition_intersection_basis": disposition_basis,
        "consolidation_streak": consolidation_streak_count,
        "consolidation_reduces_goal_distance": False,
        "consolidation_streak_cap": CONSOLIDATION_STREAK_CAP,
        "positive_input_delta_gate": {
            "required_count": positive_delta_required_count,
            "has_new_input_kind": has_positive_input_delta,
            "new_input_kinds": sorted(input_kind_counter),
            "has_positive_output_delta": has_positive_output_delta,
            "has_supplied_input_delta": has_supplied_input_delta,
            "supplied_input_artifact_paths": sorted(supplied_input_paths),
        },
        "provider_reattempt_gate": {
            "provider_reattempt_required": any(bool(item.get("authority_allows_retry")) for item in provider_reattempt_records),
            "provider_mitigation_required": bool(provider_reattempt_records),
            "provider_terminal_seal_allowed": not bool(provider_reattempt_records),
            "records": provider_reattempt_records[:10],
        },
        "command_surface_budget": surface_budget,
        "terminal_blocker_candidate": terminal_blocker_candidate,
        "findings": findings,
        "evidence": evidence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect repeated safety-only/no-live progress loops before task derivation.")
    parser.add_argument("--root", default=".", help="Workspace root to inspect.")
    parser.add_argument("--recent", type=int, default=8, help="Number of recent evidence files to inspect.")
    parser.add_argument("--strict", action="store_true", help="Return block when consecutive safety_only evidence repeats the same blocker.")
    parser.add_argument("--goal-productive-threshold", type=int, default=5, help="Warn/block when this many recent progress cycles lack goal-productive output.")
    parser.add_argument("--root-axis-threshold", type=int, default=6, help="Hard-stop after this many same-root-axis governance-only/provider-neutral records without domain delta.")
    parser.add_argument("--feature-symbol-threshold", type=int, default=6, help="Hard-stop after this many same-feature-symbol records without observed node/edge delta.")
    parser.add_argument("--terminal-quiescence-threshold", type=int, default=TERMINAL_QUIESCENCE_STREAK_DEFAULT, help="Stop automatic domain-cycle restart after this many same-root terminal records without input delta.")
    parser.add_argument("--write-registry", action="store_true", help=f"Append the newest progress feature symbol to {REGISTRY_REL_PATH}.")
    args = parser.parse_args(argv)

    result = analyze(
        Path(args.root).resolve(),
        max(1, args.recent),
        args.strict,
        max(1, args.goal_productive_threshold),
        max(1, args.root_axis_threshold),
        max(1, args.feature_symbol_threshold),
        max(1, args.terminal_quiescence_threshold),
        args.write_registry,
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["status"] != "block" else 2


if __name__ == "__main__":
    raise SystemExit(main())
