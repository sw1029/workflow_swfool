from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import (
    GT_FILES,
    LATEST_USER_OVERRIDE_RE,
    OVERRIDE_QUOTE_RE,
    OVERRIDE_SOURCE_PATH_RE,
    OVERRIDE_TIMESTAMP_RE,
    TASK_CONTEXT_RE,
    boolish,
    collect_matches,
    first_present,
    int_value,
    line_for_offset,
    list_value,
    normalize_action_specs,
    now_iso,
    read_text,
    rel_path,
    string_items,
)


def normalize_generalization_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    value = (policy or {}).get("generalization")
    if not isinstance(value, dict):
        return {}
    required_patterns = string_items(
        value.get("required_patterns") or value.get("scope_patterns")
    )
    single_unit_patterns = string_items(value.get("single_unit_patterns"))
    if not required_patterns:
        return {}
    return {
        "action": str(value.get("action") or "generalization").strip()
        or "generalization",
        "required_patterns": required_patterns,
        "single_unit_patterns": single_unit_patterns,
        "selected_count_paths": string_items(value.get("selected_count_paths")),
        "target_count_paths": string_items(value.get("target_count_paths")),
        "streak_paths": string_items(value.get("streak_paths")),
        "streak_threshold_paths": string_items(value.get("streak_threshold_paths")),
        "unit_ids_paths": string_items(value.get("unit_ids_paths")),
        "single_unit_flag_paths": string_items(value.get("single_unit_flag_paths")),
        "default_streak_threshold": int_value(value.get("default_streak_threshold"))
        or 3,
        "reason": str(
            value.get("reason") or "single_unit_invariant_blocks_generalization"
        ),
    }


def regex_matches(patterns: list[str], text: str) -> list[re.Match[str]]:
    matches: list[re.Match[str]] = []
    for pattern in patterns:
        try:
            matches.extend(re.finditer(pattern, text, re.IGNORECASE | re.DOTALL))
        except re.error:
            continue
    return matches


def goal_truth_matches(
    root: Path, action_specs: dict[str, dict[str, tuple[str, ...]]]
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for rel in GT_FILES:
        path = root / rel
        if not path.is_file():
            continue
        text = read_text(path)
        for action, spec in action_specs.items():
            matches.extend(
                collect_matches(
                    root, path, text, action, "allowed", spec.get("allowed", ())
                )
            )
            matches.extend(
                collect_matches(
                    root, path, text, action, "required", spec.get("required", ())
                )
            )
    return matches


def generalization_sources(
    root: Path, task_path: Path, task_text: str, policy: dict[str, Any]
) -> list[dict[str, Any]]:
    if not policy:
        return []
    sources: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()

    def add_source(path_text: str, line_no: int, line: str, disposition: str) -> None:
        key = (path_text, line_no, line)
        if key not in seen:
            seen.add(key)
            sources.append(
                {
                    "action": policy["action"],
                    "disposition": disposition,
                    "path": path_text,
                    "line": line_no,
                    "excerpt": line,
                }
            )

    for rel in GT_FILES:
        path = root / rel
        if not path.is_file():
            continue
        text = read_text(path)
        for match in regex_matches(policy["required_patterns"], text):
            line_no, line = line_for_offset(text, match.start())
            add_source(rel_path(root, path), line_no, line, "required_or_implied")
    for match in regex_matches(policy["required_patterns"], task_text):
        line_no, line = line_for_offset(task_text, match.start())
        add_source(rel_path(root, task_path), line_no, line, "task_scope")
    return sources


def task_forbidden_matches(
    root: Path, task_path: Path, action_specs: dict[str, dict[str, tuple[str, ...]]]
) -> list[dict[str, Any]]:
    text = read_text(task_path)
    matches: list[dict[str, Any]] = []
    for action, spec in action_specs.items():
        matches.extend(
            collect_matches(
                root, task_path, text, action, "forbidden", spec.get("forbidden", ())
            )
        )
    return matches


def relevant_task_context(
    task_text: str, action_specs: dict[str, dict[str, tuple[str, ...]]]
) -> bool:
    if TASK_CONTEXT_RE.search(task_text):
        return True
    patterns = [
        pattern
        for spec in action_specs.values()
        for disposition in ("allowed", "required", "forbidden")
        for pattern in spec.get(disposition, ())
    ]
    return bool(regex_matches(patterns, task_text))


def latest_user_override_evidence(
    task_text: str, forbidden: dict[str, Any]
) -> dict[str, Any]:
    excerpt = str(forbidden.get("excerpt") or "")
    detected = bool(
        LATEST_USER_OVERRIDE_RE.search(excerpt)
        or LATEST_USER_OVERRIDE_RE.search(task_text)
    )
    if not detected:
        return {
            "latest_user_override_detected": False,
            "latest_user_override_citation_verified": False,
            "has_source_path": False,
            "has_timestamp": False,
            "has_quote": False,
        }
    windows: list[str] = []
    for text in (excerpt, task_text):
        for match in LATEST_USER_OVERRIDE_RE.finditer(text):
            windows.append(
                text[max(0, match.start() - 240) : min(len(text), match.end() + 240)]
            )
    source_text = "\n".join(windows)
    has_source_path = bool(OVERRIDE_SOURCE_PATH_RE.search(source_text))
    has_timestamp = bool(OVERRIDE_TIMESTAMP_RE.search(source_text))
    has_quote = bool(OVERRIDE_QUOTE_RE.search(source_text))
    return {
        "latest_user_override_detected": True,
        "latest_user_override_citation_verified": (has_source_path or has_timestamp)
        and has_quote,
        "has_source_path": has_source_path,
        "has_timestamp": has_timestamp,
        "has_quote": has_quote,
    }


def behavior_conflicts(
    by_action: dict[str, dict[str, list[dict[str, Any]]]], behavior: dict[str, Any]
) -> list[dict[str, Any]]:
    if not behavior:
        return []
    provider_request_count = int_value(
        first_present(
            behavior,
            (
                "provider_request_count",
                "run.provider_request_count",
                "failure_autopsy.provider_request_count",
                "failure_autopsy_packet.provider_request_count",
                "result.provider_request_count",
            ),
        )
    )
    env_file_read = first_present(
        behavior,
        (
            "env_file_read",
            "runtime_env_read",
            "credential_read_performed",
            "run.env_file_read",
            "result.env_file_read",
        ),
    )
    legitimate_terminal = boolish(
        first_present(
            behavior,
            (
                "legitimate_terminal",
                "provider_terminal_legitimate",
                "terminal_legitimate",
                "result.legitimate_terminal",
            ),
        )
    )
    bounded_retry_evidence = boolish(
        first_present(
            behavior,
            (
                "bounded_retry_evidence",
                "retry_probe_evidence",
                "provider_retry_exhausted",
                "result.bounded_retry_evidence",
            ),
        )
    )
    conflicts: list[dict[str, Any]] = []
    provider_gt = by_action.get("provider_dispatch", {}).get("gt", []) + by_action.get(
        "bounded_provider_retry_probe", {}
    ).get("gt", [])
    if (
        provider_gt
        and provider_request_count == 0
        and not (legitimate_terminal or bounded_retry_evidence)
    ):
        conflicts.append(
            {
                "action": "provider_dispatch",
                "severity": "block",
                "reason": "behavior_avoids_goal_truth_provider_path",
                "observed_behavior": {
                    "provider_request_count": provider_request_count,
                    "legitimate_terminal": legitimate_terminal,
                    "bounded_retry_evidence": bounded_retry_evidence,
                },
                "allowed_or_required_sources": provider_gt,
                "task_forbidden_sources": [],
            }
        )
    env_gt = by_action.get("runtime_env_credential_read", {}).get("gt", [])
    if (
        env_gt
        and env_file_read is False
        and provider_request_count == 0
        and not legitimate_terminal
    ):
        conflicts.append(
            {
                "action": "runtime_env_credential_read",
                "severity": "block",
                "reason": "behavior_avoids_goal_truth_runtime_env_credential_read",
                "observed_behavior": {
                    "env_file_read": env_file_read,
                    "provider_request_count": provider_request_count,
                    "legitimate_terminal": legitimate_terminal,
                },
                "allowed_or_required_sources": env_gt,
                "task_forbidden_sources": [],
            }
        )
    return conflicts


def single_unit_generalization_conflicts(
    task_text: str,
    behavior: dict[str, Any],
    sources: list[dict[str, Any]],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    if not sources or not policy:
        return []
    selected = int_value(first_present(behavior, tuple(policy["selected_count_paths"])))
    target = int_value(first_present(behavior, tuple(policy["target_count_paths"])))
    streak = int_value(first_present(behavior, tuple(policy["streak_paths"])))
    threshold = (
        int_value(first_present(behavior, tuple(policy["streak_threshold_paths"])))
        or policy["default_streak_threshold"]
    )
    unit_ids = list_value(first_present(behavior, tuple(policy["unit_ids_paths"])))
    single_flag = boolish(
        first_present(behavior, tuple(policy["single_unit_flag_paths"]))
    )
    task_single = bool(regex_matches(policy["single_unit_patterns"], task_text))
    observed = (
        single_flag
        or task_single
        or selected == 1
        or len({str(item) for item in unit_ids if item is not None}) == 1
    )
    if not (observed and ((streak or 0) >= threshold or (target or 0) >= 2)):
        return []
    return [
        {
            "action": policy["action"],
            "severity": "block",
            "reason": policy["reason"],
            "observed_behavior": {
                "single_unit_flag": single_flag,
                "task_single_unit_language": task_single,
                "selected_unit_count": selected,
                "target_unit_count": target,
                "output_unit_ids": unit_ids[:10],
                "single_unit_streak": streak,
                "threshold": threshold,
            },
            "allowed_or_required_sources": sources,
            "task_forbidden_sources": [],
        }
    ]


def analyze(
    root: Path,
    task_path: Path,
    behavior: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    behavior = behavior or {}
    policy = policy or (
        behavior.get("gt_constraint_policy")
        if isinstance(behavior.get("gt_constraint_policy"), dict)
        else {}
    )
    action_specs = normalize_action_specs(policy)
    generalization_policy = normalize_generalization_policy(policy)
    task_text = read_text(task_path)
    task_context_in_scope = relevant_task_context(task_text, action_specs)
    gt = goal_truth_matches(root, action_specs)
    scope_sources = generalization_sources(
        root, task_path, task_text, generalization_policy
    )
    forbidden = task_forbidden_matches(root, task_path, action_specs)
    by_action: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for item in gt:
        by_action.setdefault(item["action"], {"gt": [], "task": []})["gt"].append(item)
    for item in forbidden:
        by_action.setdefault(item["action"], {"gt": [], "task": []})["task"].append(
            item
        )
    conflicts: list[dict[str, Any]] = []
    for action, grouped in sorted(by_action.items()):
        gt_items, task_items = grouped["gt"], grouped["task"]
        if not gt_items or not task_items or not task_context_in_scope:
            continue
        override_packets = [
            latest_user_override_evidence(task_text, item) for item in task_items
        ]
        override = any(
            item["latest_user_override_detected"] for item in override_packets
        )
        citation_verified = any(
            item["latest_user_override_citation_verified"] for item in override_packets
        )
        conflicts.append(
            {
                "action": action,
                "severity": "warn" if override and citation_verified else "block",
                "latest_user_override_detected": override,
                "latest_user_override_citation_verified": citation_verified,
                "latest_user_override_evidence": override_packets,
                "reason": "task_forbids_action_allowed_or_required_by_goal_truth",
                "allowed_or_required_sources": gt_items,
                "task_forbidden_sources": task_items,
            }
        )
    conflicts.extend(behavior_conflicts(by_action, behavior))
    conflicts.extend(
        single_unit_generalization_conflicts(
            task_text, behavior, scope_sources, generalization_policy
        )
    )
    status = (
        "block"
        if any(item["severity"] == "block" for item in conflicts)
        else ("warn" if conflicts else "ok")
    )
    return {
        "status": status,
        "checked_at": now_iso(),
        "workspace": str(root),
        "task_path": rel_path(root, task_path),
        "task_context_in_scope": task_context_in_scope,
        "allowed_or_required_actions": gt,
        "gt_constraint_policy_supplied": bool(policy),
        "generalization_policy_supplied": bool(generalization_policy),
        "generalization_sources": scope_sources,
        "task_forbidden_actions": forbidden,
        "conflicts": conflicts,
        "behavior_evidence": behavior,
        "requires_conflict_resolution_task": status == "block",
        "latest_user_override_detected": any(
            item.get("latest_user_override_detected") for item in conflicts
        ),
        "latest_user_override_citation_verified": any(
            item.get("latest_user_override_citation_verified") for item in conflicts
        ),
        "evidence_paths": sorted(
            {item["path"] for item in [*gt, *forbidden, *scope_sources]}
        ),
    }
