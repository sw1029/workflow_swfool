#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any


GT_FILES = (
    ".agent_goal/agent_authority.md",
    ".agent_goal/conventions.md",
    ".agent_goal/final_goal.md",
    ".agent_goal/goal_schema_contract.md",
)

TASK_CONTEXT_RE = re.compile(
    r"(provider_terminal|sealed_blocker_families|"
    r"terminally?\s+seal|terminal[-_\s]?blocked\s+pending\s+credential|bounded\s+retry|"
    r"retry/probe|credential[-_\s]dependent|credential\s+blocker|provider\s+credential|"
    r"api\s+credential|no[-_\s]?provider|no[-_\s]?env|no[-_\s]?credential|"
    r"credential\s+lookup|authority_policy)",
    re.IGNORECASE,
)
LATEST_USER_OVERRIDE_RE = re.compile(
    r"(newest|latest|newer|explicit)\s+user\s+(instruction|direction)|"
    r"(사용자\s+최신|명시적\s+사용자|최신\s+사용자)",
    re.IGNORECASE,
)
OVERRIDE_SOURCE_PATH_RE = re.compile(
    r"(?:source|citation|evidence|log|transcript|chat\s*log|출처|근거|대화\s*기록)"
    r"[^.\n]{0,120}(\.agent_log/|\.task/|transcript|conversation|chat\s*log)",
    re.IGNORECASE,
)
OVERRIDE_TIMESTAMP_RE = re.compile(
    r"(?:timestamp|time|date|at|일시|시각|날짜)[^.\n]{0,80}"
    r"(20\d{2}[-/.]?\d{2}[-/.]?\d{2}(?:[- T:.]?\d{2}[:.]?\d{2}(?::?\d{2})?)?|\b20\d{6,12}\b)",
    re.IGNORECASE,
)
OVERRIDE_QUOTE_RE = re.compile(r"(?:원문|quote|quoted|instruction\s+text|지시\s*문구)\s*[:：]\s*([\"'“”‘’`].{10,}[\"'“”‘’`]|.{10,})", re.IGNORECASE)
DEFAULT_ACTION_SPECS: dict[str, dict[str, tuple[str, ...]]] = {
    "runtime_env_credential_read": {
        "allowed": (
            r"reading\s+[`']?\.env[`']?.{0,120}(credential|api\s*key)",
            r"\.env.{0,80}(runtime|런타임).{0,80}(read|읽)",
            r"(credential|api\s*key).{0,120}(read|읽).{0,80}\.env",
        ),
        "required": (
            r"provider\s+api.{0,120}\.env.{0,120}(must|해야|읽어야)",
            r"(credential|api\s*key).{0,80}(read|읽).{0,80}(runtime|런타임).{0,80}\.env",
            r"user-authorized\s+provider.{0,160}credentials\s+read\s+at\s+runtime\s+from\s+[`']?\.env",
        ),
        "forbidden": (
            r"do\s+not\s+read\s+[`']?\.env[`']?",
            r"no\s+[`']?\.env[`']?\s+read",
            r"env_file_read\s*=\s*false",
            r"\.env\s+reads?.{0,80}(forbidden|blocked|prohibited)",
            r"(forbid|forbidden|blocked|prohibit|금지).{0,80}\.env",
            r"\.env.{0,80}(금지|읽지\s+않)",
        ),
    },
    "bounded_provider_retry_probe": {
        "allowed": (
            r"bounded\s+(retry|probe|retry/probe).{0,160}(expected|required|before|전)",
            r"(retry|probe|retry/probe).{0,160}before\s+terminal",
            r"terminal.{0,120}bounded\s+(retry|probe|retry/probe)",
            r"단일\s+provider.{0,120}terminal.{0,120}하지\s+않",
        ),
        "required": (
            r"bounded\s+(retry|probe|retry/probe)\s+is\s+expected\s+before\s+terminal",
            r"terminal\s+classification\s+must\s+include\s+bounded\s+(retry|probe|retry/probe)",
            r"terminal\s+전\s+bounded\s+(retry|probe|retry/probe|재시도)",
        ),
        "forbidden": (
            r"do\s+not\s+call\s+providers?",
            r"no\s+provider\s+dispatch",
            r"provider_dispatch_performed\s*=\s*false",
            r"provider.{0,80}(dispatch|call).{0,80}(forbidden|blocked|금지)",
        ),
    },
    "provider_dispatch": {
        "allowed": (
            r"provider\s+api\s+calls?.{0,160}(allowed|허용)",
            r"default\s+policy:\s+[`']?allowed_when_task_requires[`']?",
            r"provider/external\s+actions\s+that\s+a\s+current\s+task\s+requires",
        ),
        "required": (),
        "forbidden": (
            r"do\s+not\s+call\s+providers?",
            r"no\s+provider\s+dispatch",
            r"provider_dispatch_performed\s*=\s*false",
        ),
    },
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


def read_json_arg(root: Path, value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    stripped = value.strip()
    if stripped.startswith("{"):
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    path = Path(stripped)
    if not path.is_absolute():
        path = root / path
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def deep_get(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_present(data: dict[str, Any], paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = deep_get(data, path) if "." in path else data.get(path)
        if value is None:
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "present", "allowed", "complete"}
    return False


def int_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def list_value(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def line_for_offset(text: str, offset: int) -> tuple[int, str]:
    line_no = text.count("\n", 0, offset) + 1
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end].strip()
    return line_no, line[:240]


def collect_matches(root: Path, path: Path, text: str, action: str, disposition: str, patterns: tuple[str, ...]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            line_no, line = line_for_offset(text, match.start())
            matches.append(
                {
                    "action": action,
                    "disposition": disposition,
                    "path": rel_path(root, path),
                    "line": line_no,
                    "pattern": pattern,
                    "excerpt": line,
                }
            )
    return matches


def string_items(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_action_specs(policy: dict[str, Any] | None) -> dict[str, dict[str, tuple[str, ...]]]:
    specs = {
        action: {key: tuple(patterns) for key, patterns in dispositions.items()}
        for action, dispositions in DEFAULT_ACTION_SPECS.items()
    }
    supplied = (policy or {}).get("action_specs")
    if not isinstance(supplied, dict):
        return specs
    for action, dispositions in supplied.items():
        if not isinstance(dispositions, dict):
            continue
        action_id = str(action).strip()
        if not action_id:
            continue
        specs[action_id] = {
            disposition: tuple(string_items(dispositions.get(disposition)))
            for disposition in ("allowed", "required", "forbidden")
        }
    return specs


def normalize_generalization_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    value = (policy or {}).get("generalization")
    if not isinstance(value, dict):
        return {}
    required_patterns = string_items(value.get("required_patterns") or value.get("scope_patterns"))
    single_unit_patterns = string_items(value.get("single_unit_patterns"))
    if not required_patterns:
        return {}
    return {
        "action": str(value.get("action") or "generalization").strip() or "generalization",
        "required_patterns": required_patterns,
        "single_unit_patterns": single_unit_patterns,
        "selected_count_paths": string_items(value.get("selected_count_paths")),
        "target_count_paths": string_items(value.get("target_count_paths")),
        "streak_paths": string_items(value.get("streak_paths")),
        "streak_threshold_paths": string_items(value.get("streak_threshold_paths")),
        "unit_ids_paths": string_items(value.get("unit_ids_paths")),
        "single_unit_flag_paths": string_items(value.get("single_unit_flag_paths")),
        "default_streak_threshold": int_value(value.get("default_streak_threshold")) or 3,
        "reason": str(value.get("reason") or "single_unit_invariant_blocks_generalization"),
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
    root: Path,
    action_specs: dict[str, dict[str, tuple[str, ...]]],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for rel in GT_FILES:
        path = root / rel
        if not path.is_file():
            continue
        text = read_text(path)
        for action, spec in action_specs.items():
            matches.extend(collect_matches(root, path, text, action, "allowed", spec.get("allowed", ())))
            matches.extend(collect_matches(root, path, text, action, "required", spec.get("required", ())))
    return matches


def generalization_sources(
    root: Path,
    task_path: Path,
    task_text: str,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    if not policy:
        return []
    sources: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()

    def add_source(path_text: str, line_no: int, line: str, disposition: str) -> None:
        key = (path_text, line_no, line)
        if key in seen:
            return
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
    root: Path,
    task_path: Path,
    action_specs: dict[str, dict[str, tuple[str, ...]]],
) -> list[dict[str, Any]]:
    text = read_text(task_path)
    matches: list[dict[str, Any]] = []
    for action, spec in action_specs.items():
        matches.extend(collect_matches(root, task_path, text, action, "forbidden", spec.get("forbidden", ())))
    return matches


def relevant_task_context(
    task_text: str,
    action_specs: dict[str, dict[str, tuple[str, ...]]],
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


def latest_user_override_evidence(task_text: str, forbidden: dict[str, Any]) -> dict[str, Any]:
    excerpt = str(forbidden.get("excerpt") or "")
    detected = bool(LATEST_USER_OVERRIDE_RE.search(excerpt) or LATEST_USER_OVERRIDE_RE.search(task_text))
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
            start = max(0, match.start() - 240)
            end = min(len(text), match.end() + 240)
            windows.append(text[start:end])
    source_text = "\n".join(windows)
    has_source_path = bool(OVERRIDE_SOURCE_PATH_RE.search(source_text))
    has_timestamp = bool(OVERRIDE_TIMESTAMP_RE.search(source_text))
    has_quote = bool(OVERRIDE_QUOTE_RE.search(source_text))
    return {
        "latest_user_override_detected": True,
        "latest_user_override_citation_verified": (has_source_path or has_timestamp) and has_quote,
        "has_source_path": has_source_path,
        "has_timestamp": has_timestamp,
        "has_quote": has_quote,
    }


def behavior_conflicts(by_action: dict[str, dict[str, list[dict[str, Any]]]], behavior: dict[str, Any]) -> list[dict[str, Any]]:
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
    provider_gt = by_action.get("provider_dispatch", {}).get("gt", []) + by_action.get("bounded_provider_retry_probe", {}).get("gt", [])
    if provider_gt and provider_request_count == 0 and not (legitimate_terminal or bounded_retry_evidence):
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
    if env_gt and env_file_read is False and provider_request_count == 0 and not legitimate_terminal:
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
    selected_unit_count = int_value(first_present(behavior, tuple(policy["selected_count_paths"])))
    target_unit_count = int_value(first_present(behavior, tuple(policy["target_count_paths"])))
    explicit_streak = int_value(first_present(behavior, tuple(policy["streak_paths"])))
    threshold = (
        int_value(first_present(behavior, tuple(policy["streak_threshold_paths"])))
        or policy["default_streak_threshold"]
    )
    output_unit_ids = list_value(first_present(behavior, tuple(policy["unit_ids_paths"])))
    single_unit_flag = boolish(
        first_present(behavior, tuple(policy["single_unit_flag_paths"]))
    )
    task_single_unit_language = bool(regex_matches(policy["single_unit_patterns"], task_text))
    observed_single_unit = (
        single_unit_flag
        or task_single_unit_language
        or selected_unit_count == 1
        or (len({str(item) for item in output_unit_ids if item is not None}) == 1)
    )
    repeated_single_unit = (explicit_streak or 0) >= threshold
    multiple_units_expected = (target_unit_count or 0) >= 2
    if not (observed_single_unit and (repeated_single_unit or multiple_units_expected)):
        return []
    return [
        {
            "action": policy["action"],
            "severity": "block",
            "reason": policy["reason"],
            "observed_behavior": {
                "single_unit_flag": single_unit_flag,
                "task_single_unit_language": task_single_unit_language,
                "selected_unit_count": selected_unit_count,
                "target_unit_count": target_unit_count,
                "output_unit_ids": output_unit_ids[:10],
                "single_unit_streak": explicit_streak,
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
    policy = policy or (behavior.get("gt_constraint_policy") if isinstance(behavior.get("gt_constraint_policy"), dict) else {})
    action_specs = normalize_action_specs(policy)
    generalization_policy = normalize_generalization_policy(policy)
    task_text = read_text(task_path)
    task_context_in_scope = relevant_task_context(task_text, action_specs)
    gt = goal_truth_matches(root, action_specs)
    scope_sources = generalization_sources(root, task_path, task_text, generalization_policy)
    forbidden = task_forbidden_matches(root, task_path, action_specs)

    by_action: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for item in gt:
        by_action.setdefault(item["action"], {"gt": [], "task": []})["gt"].append(item)
    for item in forbidden:
        by_action.setdefault(item["action"], {"gt": [], "task": []})["task"].append(item)

    conflicts: list[dict[str, Any]] = []
    for action, grouped in sorted(by_action.items()):
        gt_items = grouped["gt"]
        task_items = grouped["task"]
        if not gt_items or not task_items:
            continue
        if not task_context_in_scope:
            continue
        override_packets = [latest_user_override_evidence(task_text, item) for item in task_items]
        override = any(item["latest_user_override_detected"] for item in override_packets)
        citation_verified = any(item["latest_user_override_citation_verified"] for item in override_packets)
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
    conflicts.extend(single_unit_generalization_conflicts(task_text, behavior, scope_sources, generalization_policy))

    status = "ok"
    if any(item["severity"] == "block" for item in conflicts):
        status = "block"
    elif conflicts:
        status = "warn"

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
        "latest_user_override_detected": any(item.get("latest_user_override_detected") for item in conflicts),
        "latest_user_override_citation_verified": any(item.get("latest_user_override_citation_verified") for item in conflicts),
        "evidence_paths": sorted({item["path"] for item in [*gt, *forbidden, *scope_sources]}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect task constraints that contradict allowed or required goal-truth actions.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    parser.add_argument("--task", default="task.md", help="Task Markdown path, relative to --root unless absolute.")
    parser.add_argument("--behavior-json", help="JSON object or path with safe scalar run behavior.")
    parser.add_argument("--behavior-path", help="Path to JSON with safe scalar run behavior.")
    parser.add_argument("--policy-json", help="Explicit repository-adapter GT constraint policy JSON object or path.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    task_path = Path(args.task)
    if not task_path.is_absolute():
        task_path = root / task_path
    behavior = read_json_arg(root, args.behavior_json) or read_json_arg(root, args.behavior_path)
    policy = read_json_arg(root, args.policy_json)
    result = analyze(root, task_path, behavior, policy)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["status"] != "block" else 2


if __name__ == "__main__":
    raise SystemExit(main())
