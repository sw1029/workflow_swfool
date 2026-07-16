from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


GT_FILES = (
    ".agent_goal/agent_authority.md",
    ".agent_goal/conventions.md",
    ".agent_goal/final_goal.md",
    ".agent_goal/goal_schema_contract.md",
)
TASK_CONTEXT_RE = re.compile(
    r"(provider_terminal|sealed_blocker_families|terminally?\s+seal|terminal[-_\s]?blocked\s+pending\s+credential|bounded\s+retry|retry/probe|credential[-_\s]dependent|credential\s+blocker|provider\s+credential|api\s+credential|no[-_\s]?provider|no[-_\s]?env|no[-_\s]?credential|credential\s+lookup|authority_policy)",
    re.IGNORECASE,
)
LATEST_USER_OVERRIDE_RE = re.compile(
    r"(newest|latest|newer|explicit)\s+user\s+(instruction|direction)|(사용자\s+최신|명시적\s+사용자|최신\s+사용자)",
    re.IGNORECASE,
)
OVERRIDE_SOURCE_PATH_RE = re.compile(
    r"(?:source|citation|evidence|log|transcript|chat\s*log|출처|근거|대화\s*기록)[^.\n]{0,120}(\.agent_log/|\.task/|transcript|conversation|chat\s*log)",
    re.IGNORECASE,
)
OVERRIDE_TIMESTAMP_RE = re.compile(
    r"(?:timestamp|time|date|at|일시|시각|날짜)[^.\n]{0,80}(20\d{2}[-/.]?\d{2}[-/.]?\d{2}(?:[- T:.]?\d{2}[:.]?\d{2}(?::?\d{2})?)?|\b20\d{6,12}\b)",
    re.IGNORECASE,
)
OVERRIDE_QUOTE_RE = re.compile(
    r"(?:원문|quote|quoted|instruction\s+text|지시\s*문구)\s*[:：]\s*([\"'“”‘’`].{10,}[\"'“”‘’`]|.{10,})",
    re.IGNORECASE,
)
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
        if (
            value is None
            or (isinstance(value, (list, dict)) and not value)
            or (isinstance(value, str) and not value.strip())
        ):
            continue
        return value
    return None


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "yes",
            "1",
            "present",
            "allowed",
            "complete",
        }
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
    return [] if value is None else [value]


def line_for_offset(text: str, offset: int) -> tuple[int, str]:
    line_no = text.count("\n", 0, offset) + 1
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    if line_end < 0:
        line_end = len(text)
    return line_no, text[line_start:line_end].strip()[:240]


def collect_matches(
    root: Path,
    path: Path,
    text: str,
    action: str,
    disposition: str,
    patterns: tuple[str, ...],
) -> list[dict[str, Any]]:
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


def normalize_action_specs(
    policy: dict[str, Any] | None,
) -> dict[str, dict[str, tuple[str, ...]]]:
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
        if action_id:
            specs[action_id] = {
                disposition: tuple(string_items(dispositions.get(disposition)))
                for disposition in ("allowed", "required", "forbidden")
            }
    return specs
