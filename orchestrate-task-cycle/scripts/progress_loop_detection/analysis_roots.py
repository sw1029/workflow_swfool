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



class RootMetricMixin:
    def _derive_root_metrics(self) -> None:
        progress_items = self.state["progress_items"]
        counters = self.state["counters"]
        primary_root_axis = next((str(item.get("root_axis")) for item in progress_items if item.get("root_axis")), None)
        if primary_root_axis is None and counters["root_axis"]:
            primary_root_axis = counters["root_axis"].most_common(1)[0][0]
        primary_root_key = next((str(item.get("root_key")) for item in progress_items if item.get("root_key")), None)
        if primary_root_key is None and counters["root_key"]:
            primary_root_key = counters["root_key"].most_common(1)[0][0]
        primary_root_family = next((str(item.get("blocker_root_family")) for item in progress_items if item.get("blocker_root_family")), None)
        if primary_root_family is None and counters["root_family"]:
            primary_root_family = counters["root_family"].most_common(1)[0][0]
        root_axis_items = [item for item in progress_items if item.get("root_axis") == primary_root_axis] if primary_root_axis else []
        root_key_items = [item for item in progress_items if item.get("root_key") == primary_root_key] if primary_root_key else []
        root_family_items = [item for item in progress_items if item.get("blocker_root_family") == primary_root_family] if primary_root_family else []
        root_axis_delta = self._has_domain_delta(root_axis_items)
        root_key_delta = self._has_domain_delta(root_key_items)
        root_family_delta = self._has_domain_delta(root_family_items)
        root_axis_gov_count = sum(1 for item in root_axis_items if item.get("progress_kind") == "governance_only" or item.get("metadata_only"))
        root_key_gov_count = sum(1 for item in root_key_items if item.get("progress_kind") == "governance_only" or item.get("metadata_only"))
        detection_streak = self._detection_only_streak(progress_items, primary_root_family)
        self.state.update(
            {
                "primary_root_axis": primary_root_axis,
                "primary_root_key": primary_root_key,
                "primary_root_family": primary_root_family,
                "root_axis_governance_only_count": root_axis_gov_count,
                "root_axis_provider_neutral_count": sum(1 for item in root_axis_items if "provider_neutral" in json.dumps(item, ensure_ascii=False, sort_keys=True).lower()),
                "root_axis_produced_domain_delta": root_axis_delta,
                "root_key_governance_only_count": root_key_gov_count,
                "root_key_produced_domain_delta": root_key_delta,
                "root_family_produced_domain_delta": root_family_delta,
                "detection_only_streak_count": detection_streak,
                "detection_balance_required": bool(primary_root_family)
                and self.detection_only_streak_cap is not None
                and detection_streak >= self.detection_only_streak_cap
                and not root_family_delta,
                "root_axis_disabled": bool(primary_root_axis)
                and self.root_axis_threshold is not None
                and root_axis_gov_count >= self.root_axis_threshold
                and not root_axis_delta,
                "root_key_disabled": bool(primary_root_key)
                and self.root_axis_threshold is not None
                and root_key_gov_count >= self.root_axis_threshold
                and not root_key_delta,
            }
        )
        self.state["autonomous_retarget_disabled"] = self.state["root_axis_disabled"] or self.state["root_key_disabled"]
        self.state["repeated_root_keys"] = [
            {"root_key": key, "count": count}
            for key, count in counters["root_key"].most_common()
            if self.recurrence_threshold is not None and count >= self.recurrence_threshold
        ]

    def _has_domain_delta(self, items: list[dict[str, Any]]) -> bool:
        return any(
            boolish((item.get("output_delta_gate") or {}).get("produced_domain_delta")) and item.get("confidence") in {"high", "medium"}
            for item in items
        )

    def _detection_only_streak(self, progress_items: list[dict[str, Any]], root_family: str | None) -> int:
        count = 0
        for item in progress_items:
            if root_family and item.get("blocker_root_family") != root_family:
                continue
            if boolish(item.get("detection_only")) and item.get("progress_kind") != "goal_productive":
                count += 1
                continue
            break
        return count
