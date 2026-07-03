from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import *
from .values import *
from .io_utils import *

def load_symbol_registry(root: Path) -> dict[str, dict[str, Any]]:
    registry_path = root / REGISTRY_REL_PATH
    latest: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(registry_path):
        symbol = record.get("symbol")
        if isinstance(symbol, str) and symbol:
            latest[symbol] = record
    return latest


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
