from __future__ import annotations

from typing import Any
from pathlib import Path
import json
import re
from .common import (
    CHECK_ID_KEYS,
    FAIL_STATUS_VALUES,
    FRONTIER_CHECK_KEYS,
    PASS_STATUS_VALUES,
    ROOT_STEERING_DOC_NAMES,
)
from . import families as _families
from . import io_utils as _io_utils
from . import values as _values
from . import vectors as _vectors


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
    for key in (
        "artifact_id",
        "artifact_sha256",
        "production_lane_identity",
        "body_projection_fingerprint",
        "verification_input_ids",
        "input_fingerprints",
    ):
        if key not in quality and key in value:
            quality[key] = value[key]
    evidence_paths = _vectors.string_list(value.get("evidence_paths"))
    evidence_paths.extend(_vectors.string_list(value.get("artifact_paths")))
    reason = value.get("insufficient_reason") or value.get("blocked_reason")
    status = str(value.get("status") or "").lower()
    if not reason and status in {"missing", "blocked", "fail", "failed", "insufficient_evidence"}:
        reason = f"domain_adapter_quality_vector_{status}"
    return quality, sorted({_io_utils.rel_path(root, root / item) if not Path(item).is_absolute() else _io_utils.rel_path(root, Path(item)) for item in evidence_paths}), str(reason) if reason else None

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
        normalized[_families.normalize_root_family_key(source)] = target
    return normalized

def collapse_root_family(facet_map: dict[str, str], *values: Any) -> str:
    raw = "|".join(str(value or "") for value in values if value is not None and str(value).strip())
    normalized = _families.normalize_root_family_key(raw)
    if not facet_map:
        return normalized
    lowered = raw.lower()
    if normalized in facet_map:
        return _families.normalize_root_family_key(facet_map[normalized])
    if lowered in facet_map:
        return _families.normalize_root_family_key(facet_map[lowered])
    for facet, root in facet_map.items():
        if facet and facet in lowered:
            return _families.normalize_root_family_key(root)
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
        attempted = _values.int_metric(item.get("attempted") or item.get("attempted_count") or item.get("rows") or 0)
        resolved = _values.int_metric(item.get("resolved") or item.get("resolved_count") or item.get("fixed") or 0)
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
        env_changed = _values.bool_value(item.get("env_fingerprint_changed") or item.get("environment_changed"))
        env_stable = _values.bool_value(item.get("env_fingerprint_stable") or item.get("same_env_fingerprint")) or (
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
        axes = {str(key): child for key, child in axes_value.items() if _values.truthy_observation(child)}
    elif isinstance(axes_value, list):
        axes = {str(item): True for item in axes_value if _values.truthy_observation(item)}
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
        row = {"path": _io_utils.rel_path(root, path), "declared_output_fingerprints": fingerprints}
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
                if normalized in FRONTIER_CHECK_KEYS and _values.truthy_observation(child):
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
