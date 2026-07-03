from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from .constants import *
from .values import *
from .io_utils import *
from .registry import *
from .terminal import *
from .dispositions import *
from .gates import *
from .evidence import *

def candidate_files(root: Path) -> list[Path]:
    groups = [root / ".task" / "validation", root / ".task" / "task_miss", root / ".agent_log", root / ".issue"]
    files: list[Path] = []
    for group in groups:
        if group.is_dir():
            files.extend(path for path in group.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".json", ".jsonl"})
    if (root / "task.md").is_file():
        files.append(root / "task.md")
    return sorted(files, key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)

class EvidenceCollectionMixin:
    def _collect_evidence(self) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = structured_evidence(self.root, max(1, self.recent))
        registry = load_symbol_registry(self.root)
        seen_paths = {item.get("path") for item in evidence}
        for path in candidate_files(self.root)[: max(1, self.recent)]:
            if rel_path(self.root, path) in seen_paths:
                continue
            evidence.append(self._fallback_evidence_item(path, registry))
            if len(evidence) >= self.recent:
                break
        return evidence

    def _fallback_evidence_item(self, path: Path, registry: dict[str, dict[str, Any]]) -> dict[str, Any]:
        text = read_text(path)
        progress = classify_progress(text)
        blockers = extract_blockers(text)
        lowered = text.lower()
        pseudo_value: dict[str, Any] = {"evidence_family": "regex_text_fallback"}
        if blockers:
            pseudo_value["blocker_taxonomy"] = blockers[:3]
        if "produced_domain_delta=false" in lowered:
            pseudo_value["produced_domain_delta"] = False
        if "produced_domain_delta=true" in lowered:
            pseudo_value["produced_domain_delta"] = True
        if "metadata-only" in lowered or "metadata_only" in lowered:
            pseudo_value["metadata_only"] = True
        if request_match := PROVIDER_REQUEST_COUNT_RE.search(text):
            pseudo_value["provider_request_count"] = int(request_match.group(1))
        if failure_match := FAILURE_CLASS_RE.search(text):
            pseudo_value["failure_class"] = failure_match.group(1).lower()
        if "authority_allows_retry=true" in lowered or "provider_retry_allowed=true" in lowered:
            pseudo_value["authority_allows_retry"] = True
        attempted = self._fallback_mitigations(lowered)
        if attempted:
            pseudo_value["mitigations_attempted"] = attempted
        item = evidence_item_from_value(
            self.root,
            path,
            "regex_text_fallback",
            "low",
            pseudo_value,
            progress,
            blockers[:5],
            registry,
        )
        fallback_kind = progress_kind(pseudo_value, progress, lowered)
        if not (item.get("output_delta_gate") or {}).get("observed_override_applied") and fallback_kind:
            item["progress_kind"] = fallback_kind
        item["new_input_kinds"] = extract_input_kinds(text)
        item["positive_input_delta_required"] = "positive_input_delta_required" in lowered or "positive input delta" in lowered
        item["metadata_only"] = bool((item.get("output_delta_gate") or {}).get("metadata_only")) or item.get("progress_kind") == "governance_only"
        item["task_correction_class"] = task_correction_class(
            pseudo_value,
            item.get("output_delta_gate") or {},
            item.get("coverage_quality_delta_gate") or {},
            item.get("provider_scale_dispatch_gate") or {},
            lowered,
        )
        item["detection_only"] = item["task_correction_class"] == "detection" and item.get("progress_kind") != "goal_productive"
        item["has_no_live_language"] = any(term in lowered for term in ("no-live", "fail-closed", "non-dispatchable", "safety_only"))
        item["has_source_backed_language"] = has_positive_source_backed_signal(lowered)
        return item

    def _fallback_mitigations(self, lowered: str) -> list[str]:
        attempted = []
        for name in ("structured_output", "window_reduce", "timeout_budget_increase", "model_fallback"):
            if name in lowered or name.replace("_", "-") in lowered:
                attempted.append(name)
        if any(token in lowered for token in ("backoff_retry", "backoff retry", "retries>=3", "retry>=3")):
            attempted.append("backoff_retry>=3")
        return sorted(set(attempted))
