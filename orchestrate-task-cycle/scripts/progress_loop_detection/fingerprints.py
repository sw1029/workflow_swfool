from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import *
from .values import *
from .io_utils import *
from .provider import provider_failure_class

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
            for pattern in ("kg_nodes.jsonl", "kg_edges.jsonl"):
                found = 0
                for discovered in path.rglob(pattern):
                    candidates.append(discovered)
                    found += 1
                    if found >= 80:
                        break
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
