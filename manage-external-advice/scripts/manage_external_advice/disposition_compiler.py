"""Build evidence-bound directive dispositions from a small decision map."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Any

from .directive_dispositions import validate_directive_dispositions
from .packet_contract import clause_id_sets


TEMPLATE_KIND = "external_advice_disposition_template"
COMPILATION_KIND = "external_advice_disposition_compilation"
SCHEMA_VERSION = 1
DECISION_FIELDS = {"disposition", "evidence_ref"}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load_json(value: str) -> Any:
    if value == "-":
        payload = sys.stdin.read()
    elif value.lstrip().startswith("{"):
        payload = value
    else:
        path = Path(value)
        if not path.exists() and not path.is_symlink():
            raise SystemExit(
                "Decision map must be JSON text, '-', or an existing input file."
            )
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise SystemExit("Decision map path must be a regular non-symlink file.")
        payload = path.read_text(encoding="utf-8")
    try:
        return json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid directive decision map JSON: {exc}") from exc


def _canonical_ref(value: Any, label: str = "Decision evidence_ref") -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise SystemExit(f"{label} must be canonical workspace-relative text.")
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or candidate.as_posix() != value
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise SystemExit(f"{label} must be canonical workspace-relative text.")
    return value


def _active_item(item: dict[str, Any]) -> None:
    if item.get("status") != "active":
        raise SystemExit("Directive dispositions can only be compiled for active advice.")


def _regular_workspace_file(root: Path, ref: str, label: str) -> Path:
    current = root.resolve()
    for part in PurePosixPath(ref).parts:
        current /= part
        if current.exists() or current.is_symlink():
            mode = current.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise SystemExit(f"{label} path contains a symlink: {ref}")
    if not current.is_file():
        raise SystemExit(f"{label} is not a regular file: {ref}")
    return current


def _verify_source_binding(root: Path, item: dict[str, Any]) -> None:
    ref = _canonical_ref(item.get("path"), "Active advice source ref")
    path = _regular_workspace_file(root, ref, "Active advice source")
    expected = str(item.get("content_sha256") or "")
    observed = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected != observed:
        raise SystemExit("Active advice source binding is stale; re-read the registry.")


def render_disposition_template(
    item: dict[str, Any], *, root: Path | None = None
) -> dict[str, Any]:
    """Render all actionable IDs without copying directive or source body text."""

    _active_item(item)
    if root is not None:
        _verify_source_binding(root.resolve(), item)
    _declared, actionable = clause_id_sets(item)
    binding = {
        "schema_version": SCHEMA_VERSION,
        "result_kind": TEMPLATE_KIND,
        "advice_id": str(item.get("advice_id") or ""),
        "source_binding": {
            "ref": str(item.get("path") or ""),
            "sha256": str(item.get("content_sha256") or ""),
        },
        "actionable_directive_ids": actionable,
    }
    return {
        **binding,
        "decisions": {
            directive_id: {"disposition": None, "evidence_ref": None}
            for directive_id in actionable
        },
        "template_sha256": _digest(binding),
    }


def _decision_map(
    value: str, item: dict[str, Any]
) -> dict[str, dict[str, str]]:
    raw = _load_json(value)
    if (
        isinstance(raw, dict)
        and set(raw) == {"decisions"}
        and isinstance(raw["decisions"], dict)
        and set(raw["decisions"]) != DECISION_FIELDS
    ):
        raw = raw["decisions"]
    elif (
        isinstance(raw, dict)
        and raw.get("result_kind") == TEMPLATE_KIND
        and "decisions" in raw
    ):
        expected = render_disposition_template(item)
        if set(raw) != set(expected):
            raise SystemExit("Filled disposition template has unsupported fields.")
        for field in (
            "schema_version",
            "result_kind",
            "advice_id",
            "source_binding",
            "actionable_directive_ids",
            "template_sha256",
        ):
            if raw.get(field) != expected[field]:
                raise SystemExit("Filled disposition template binding is stale or invalid.")
        raw = raw["decisions"]
    if not isinstance(raw, dict):
        raise SystemExit("Directive decision map must be an object keyed by directive_id.")
    decisions: dict[str, dict[str, str]] = {}
    for directive_id, row in raw.items():
        if (
            not isinstance(directive_id, str)
            or not directive_id
            or not isinstance(row, dict)
            or set(row) != DECISION_FIELDS
        ):
            raise SystemExit("Every directive decision must have exact disposition/evidence_ref fields.")
        disposition = row.get("disposition")
        if not isinstance(disposition, str) or not disposition:
            raise SystemExit("Every directive decision requires a disposition.")
        decisions[directive_id] = {
            "disposition": disposition,
            "evidence_ref": _canonical_ref(row.get("evidence_ref")),
        }
    return decisions


def compile_dispositions(
    root: Path, item: dict[str, Any], decision_map: str
) -> dict[str, Any]:
    """Compile decisions, deriving every evidence digest from the workspace."""

    _active_item(item)
    _verify_source_binding(root.resolve(), item)
    decisions = _decision_map(decision_map, item)
    _declared, actionable = clause_id_sets(item)
    expected = set(actionable)
    observed = set(decisions)
    if observed != expected:
        raise SystemExit(
            "Directive decision map must cover every actionable directive; "
            f"missing={sorted(expected - observed)}, extra={sorted(observed - expected)}"
        )
    rows: list[dict[str, str]] = []
    for directive_id in actionable:
        decision = decisions[directive_id]
        path = _regular_workspace_file(
            root, decision["evidence_ref"], "Directive disposition evidence"
        )
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise SystemExit(
                f"Directive disposition evidence escapes workspace: {decision['evidence_ref']}"
            ) from exc
        evidence_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(
            {
                "directive_id": directive_id,
                "disposition": decision["disposition"],
                "evidence_ref": decision["evidence_ref"],
                "evidence_sha256": evidence_sha256,
            }
        )
    validated = validate_directive_dispositions(
        root.resolve(), item, json.dumps(rows, ensure_ascii=False)
    )
    body = {
        "schema_version": SCHEMA_VERSION,
        "result_kind": COMPILATION_KIND,
        "advice_id": str(item.get("advice_id") or ""),
        "actionable_directive_ids": actionable,
        "decision_map_sha256": _digest(decisions),
        "rows": validated,
    }
    return {**body, "compilation_sha256": _digest(body)}


def cmd_render_disposition_template(args: argparse.Namespace) -> None:
    from .lifecycle import find_item

    root = Path(args.root).resolve()
    item = find_item(root, args.advice_id)
    print(
        json.dumps(
            render_disposition_template(item, root=root),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


def cmd_compile_dispositions(args: argparse.Namespace) -> None:
    from .lifecycle import find_item

    root = Path(args.root).resolve()
    item = find_item(root, args.advice_id)
    print(
        json.dumps(
            compile_dispositions(root, item, args.decision_map),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


__all__ = (
    "compile_dispositions",
    "cmd_compile_dispositions",
    "cmd_render_disposition_template",
    "render_disposition_template",
)
