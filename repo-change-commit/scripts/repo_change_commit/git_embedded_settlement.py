"""Self-contained pre-commit anchor with post-commit read-only verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any


CONTRACT_ID = "git_embedded_settlement@v1"
VERIFICATION_ID = "git_embedded_settlement_verification@v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_OPAQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,255}$")
_TREE_FIELDS = {"path", "mode", "object_id", "object_type"}
_DIFF_FIELDS = {
    "path",
    "status",
    "before_mode",
    "before_object_id",
    "after_mode",
    "after_object_id",
}


class GitEmbeddedSettlementError(ValueError):
    """Raised when final Git state differs from the exact pre-commit intent."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def canonical_file_bytes(value: Any) -> bytes:
    return canonical_bytes(value) + b"\n"


def _opaque(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    normalized = str(value or "").strip()
    if not _OPAQUE.fullmatch(normalized):
        raise GitEmbeddedSettlementError(
            f"{label} must be a bounded opaque identifier"
        )
    return normalized


def _object_id(value: Any, label: str) -> str:
    normalized = str(value or "").lower()
    if not _OBJECT_ID.fullmatch(normalized):
        raise GitEmbeddedSettlementError(f"{label} must be a Git object id")
    return normalized


def _sha(value: Any, label: str) -> str:
    normalized = str(value or "").removeprefix("sha256:").lower()
    if not _SHA256.fullmatch(normalized):
        raise GitEmbeddedSettlementError(f"{label} must be a SHA-256 digest")
    return normalized


def _path(value: Any, label: str) -> str:
    raw = str(value or "").strip()
    path = PurePosixPath(raw)
    if (
        not raw
        or len(raw.encode("utf-8")) > 1024
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in raw
    ):
        raise GitEmbeddedSettlementError(f"{label} must be repository relative")
    return path.as_posix()


def _binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise GitEmbeddedSettlementError(f"{label} must be a ref/sha256 binding")
    return {
        "ref": _path(value.get("ref"), f"{label}.ref"),
        "sha256": _sha(value.get("sha256"), f"{label}.sha256"),
    }


def _tree_rows(
    value: Any, *, anchor_path: str
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise GitEmbeddedSettlementError("tree_entries must be a list")
    rows: list[dict[str, str]] = []
    paths: set[str] = set()
    for index, row in enumerate(value):
        if not isinstance(row, dict) or set(row) != _TREE_FIELDS:
            raise GitEmbeddedSettlementError(f"tree_entries[{index}] is not closed")
        path = _path(row.get("path"), "tree path")
        if path == anchor_path:
            raise GitEmbeddedSettlementError(
                "payload tree must exclude the settlement anchor"
            )
        if path in paths:
            raise GitEmbeddedSettlementError("payload tree paths must be unique")
        paths.add(path)
        mode = str(row.get("mode") or "")
        if mode not in {"100644", "100755", "120000", "160000"}:
            raise GitEmbeddedSettlementError("payload tree mode is invalid")
        object_type = str(row.get("object_type") or "")
        if object_type not in {"blob", "commit"}:
            raise GitEmbeddedSettlementError("payload object type is invalid")
        if mode == "160000" and object_type != "commit":
            raise GitEmbeddedSettlementError("gitlink must use commit object type")
        rows.append(
            {
                "path": path,
                "mode": mode,
                "object_id": _object_id(row.get("object_id"), "payload object id"),
                "object_type": object_type,
            }
        )
    return sorted(rows, key=lambda item: item["path"])


def _nullable_object(value: Any, label: str) -> str | None:
    return None if value is None else _object_id(value, label)


def _nullable_mode(value: Any, label: str) -> str | None:
    if value is None:
        return None
    mode = str(value)
    if mode not in {"100644", "100755", "120000", "160000"}:
        raise GitEmbeddedSettlementError(f"{label} is invalid")
    return mode


def _diff_rows(
    value: Any, *, anchor_path: str
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise GitEmbeddedSettlementError("diff_entries must be a list")
    rows: list[dict[str, Any]] = []
    paths: set[str] = set()
    for index, row in enumerate(value):
        if not isinstance(row, dict) or set(row) != _DIFF_FIELDS:
            raise GitEmbeddedSettlementError(f"diff_entries[{index}] is not closed")
        path = _path(row.get("path"), "diff path")
        if path == anchor_path:
            raise GitEmbeddedSettlementError(
                "payload diff must exclude the settlement anchor"
            )
        if path in paths:
            raise GitEmbeddedSettlementError("payload diff paths must be unique")
        paths.add(path)
        status = str(row.get("status") or "")
        if status not in {"A", "M", "D", "T"}:
            raise GitEmbeddedSettlementError("payload diff status is invalid")
        before_mode = _nullable_mode(row.get("before_mode"), "before_mode")
        after_mode = _nullable_mode(row.get("after_mode"), "after_mode")
        before_oid = _nullable_object(row.get("before_object_id"), "before_object_id")
        after_oid = _nullable_object(row.get("after_object_id"), "after_object_id")
        if status == "A" and (before_mode is not None or before_oid is not None):
            raise GitEmbeddedSettlementError("added path cannot have a before object")
        if status == "D" and (after_mode is not None or after_oid is not None):
            raise GitEmbeddedSettlementError("deleted path cannot have an after object")
        rows.append(
            {
                "path": path,
                "status": status,
                "before_mode": before_mode,
                "before_object_id": before_oid,
                "after_mode": after_mode,
                "after_object_id": after_oid,
            }
        )
    return sorted(rows, key=lambda item: item["path"])


def build_payload_projection(
    *,
    anchor_path: str,
    payload_tree_oid: str,
    tree_entries: list[dict[str, Any]],
    diff_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    anchor = _path(anchor_path, "anchor_path")
    tree = _tree_rows(tree_entries, anchor_path=anchor)
    diff = _diff_rows(diff_entries, anchor_path=anchor)
    return {
        "payload_tree_oid": _object_id(payload_tree_oid, "payload_tree_oid"),
        "payload_tree_sha256": sha256(tree),
        "payload_paths_sha256": sha256([row["path"] for row in tree]),
        "payload_diff_sha256": sha256(diff),
        "payload_path_count": len(tree),
        "payload_changed_path_count": len(diff),
    }


def _identity(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in value if key not in {"settlement_id"}}


def settlement_anchor_path(cycle_id: Any) -> str:
    """Return the only tracked anchor location for one workflow cycle."""

    identifier = _opaque(cycle_id, "cycle_id")
    return f".task/authorization/settlements/{identifier}.json"


def _raw_settlement(
    *,
    anchor_path: str,
    parent_head: str,
    commit_message_sha256: str,
    commit_role: str,
    goal_id: str | None,
    task_id: str | None,
    cycle_id: str | None,
    session_id: str | None,
    authority_request: dict[str, str],
    authority_reservation: dict[str, str],
    precommit_evidence: dict[str, str],
    payload_projection: dict[str, Any],
) -> dict[str, Any]:
    if commit_role not in {"implementation", "closeout"}:
        raise GitEmbeddedSettlementError(
            "commit_role must be implementation or closeout"
        )
    cycle = _opaque(cycle_id, "cycle_id")
    anchor = _path(anchor_path, "anchor_path")
    if anchor != settlement_anchor_path(cycle):
        raise GitEmbeddedSettlementError(
            "settlement anchor must use the reserved cycle path"
        )
    value = {
        "contract_id": CONTRACT_ID,
        "anchor_path": anchor,
        "parent_head": _object_id(parent_head, "parent_head"),
        "commit_message_sha256": _sha(
            commit_message_sha256, "commit_message_sha256"
        ),
        "commit_role": commit_role,
        "goal_id": _opaque(goal_id, "goal_id", nullable=True),
        "task_id": _opaque(task_id, "task_id", nullable=True),
        "cycle_id": cycle,
        "session_id": _opaque(session_id, "session_id", nullable=True),
        "authority_request": _binding(authority_request, "authority_request"),
        "authority_reservation": _binding(
            authority_reservation, "authority_reservation"
        ),
        "precommit_evidence": _binding(
            precommit_evidence, "precommit_evidence"
        ),
        **payload_projection,
    }
    value["settlement_id"] = f"git-settlement-{sha256(value)[:32]}"
    return value


def build_git_embedded_settlement(
    *,
    anchor_path: str,
    parent_head: str,
    commit_message_sha256: str,
    commit_role: str,
    goal_id: str | None,
    task_id: str | None,
    cycle_id: str | None,
    session_id: str | None,
    authority_request: dict[str, str],
    authority_reservation: dict[str, str],
    precommit_evidence: dict[str, str],
    payload_projection: dict[str, Any],
) -> dict[str, Any]:
    expected_payload_fields = {
        "payload_tree_oid",
        "payload_tree_sha256",
        "payload_paths_sha256",
        "payload_diff_sha256",
        "payload_path_count",
        "payload_changed_path_count",
    }
    if set(payload_projection) != expected_payload_fields:
        raise GitEmbeddedSettlementError("payload projection is not closed")
    value = _raw_settlement(
        anchor_path=anchor_path,
        parent_head=parent_head,
        commit_message_sha256=commit_message_sha256,
        commit_role=commit_role,
        goal_id=goal_id,
        task_id=task_id,
        cycle_id=cycle_id,
        session_id=session_id,
        authority_request=authority_request,
        authority_reservation=authority_reservation,
        precommit_evidence=precommit_evidence,
        payload_projection=payload_projection,
    )
    return validate_git_embedded_settlement(value)


def validate_git_embedded_settlement(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GitEmbeddedSettlementError("Git settlement must be an object")
    fields = {
        "contract_id",
        "settlement_id",
        "anchor_path",
        "parent_head",
        "commit_message_sha256",
        "commit_role",
        "goal_id",
        "task_id",
        "cycle_id",
        "session_id",
        "authority_request",
        "authority_reservation",
        "precommit_evidence",
        "payload_tree_oid",
        "payload_tree_sha256",
        "payload_paths_sha256",
        "payload_diff_sha256",
        "payload_path_count",
        "payload_changed_path_count",
    }
    if set(value) != fields or value.get("contract_id") != CONTRACT_ID:
        raise GitEmbeddedSettlementError("Git settlement contract is not closed")
    counts = {}
    for field in ("payload_path_count", "payload_changed_path_count"):
        count = value.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise GitEmbeddedSettlementError(f"{field} must be non-negative")
        counts[field] = count
    normalized = _raw_settlement(
        anchor_path=value["anchor_path"],
        parent_head=value["parent_head"],
        commit_message_sha256=value["commit_message_sha256"],
        commit_role=value["commit_role"],
        goal_id=value["goal_id"],
        task_id=value["task_id"],
        cycle_id=value["cycle_id"],
        session_id=value["session_id"],
        authority_request=value["authority_request"],
        authority_reservation=value["authority_reservation"],
        precommit_evidence=value["precommit_evidence"],
        payload_projection={
            "payload_tree_oid": _object_id(
                value["payload_tree_oid"], "payload_tree_oid"
            ),
            "payload_tree_sha256": _sha(
                value["payload_tree_sha256"], "payload_tree_sha256"
            ),
            "payload_paths_sha256": _sha(
                value["payload_paths_sha256"], "payload_paths_sha256"
            ),
            "payload_diff_sha256": _sha(
                value["payload_diff_sha256"], "payload_diff_sha256"
            ),
            **counts,
        },
    )
    expected = f"git-settlement-{sha256(_identity(normalized))[:32]}"
    if value.get("settlement_id") != expected:
        raise GitEmbeddedSettlementError("Git settlement identity mismatch")
    return {**_identity(normalized), "settlement_id": expected}


def verify_final_commit(
    settlement: dict[str, Any], observation: dict[str, Any]
) -> dict[str, Any]:
    anchor = validate_git_embedded_settlement(settlement)
    fields = {
        "commit_oid",
        "parent_heads",
        "commit_message_sha256",
        "anchor_path",
        "anchor_blob_sha256",
        "payload_tree_oid",
        "tree_entries",
        "diff_entries",
    }
    if not isinstance(observation, dict) or set(observation) != fields:
        raise GitEmbeddedSettlementError("final commit observation is not closed")
    parents = observation.get("parent_heads")
    if not isinstance(parents, list) or len(parents) != 1:
        raise GitEmbeddedSettlementError("settled closeout commits must not be merges")
    if _object_id(parents[0], "parent head") != anchor["parent_head"]:
        raise GitEmbeddedSettlementError("final commit parent does not match intent")
    if _sha(
        observation.get("commit_message_sha256"), "observed message digest"
    ) != anchor["commit_message_sha256"]:
        raise GitEmbeddedSettlementError("final commit message does not match intent")
    if _path(observation.get("anchor_path"), "observed anchor path") != anchor["anchor_path"]:
        raise GitEmbeddedSettlementError("final commit anchor path changed")
    expected_blob = hashlib.sha256(canonical_file_bytes(anchor)).hexdigest()
    if _sha(observation.get("anchor_blob_sha256"), "anchor blob digest") != expected_blob:
        raise GitEmbeddedSettlementError("final commit anchor blob changed")
    payload = build_payload_projection(
        anchor_path=anchor["anchor_path"],
        payload_tree_oid=str(observation.get("payload_tree_oid") or ""),
        tree_entries=observation.get("tree_entries"),
        diff_entries=observation.get("diff_entries"),
    )
    for field, expected in payload.items():
        if anchor[field] != expected:
            raise GitEmbeddedSettlementError(
                f"final commit {field} does not match intent"
            )
    commit_oid = _object_id(observation.get("commit_oid"), "commit_oid")
    verification = {
        "contract_id": VERIFICATION_ID,
        "settlement_id": anchor["settlement_id"],
        "commit_oid": commit_oid,
        "terminal": True,
        "tracked_post_commit_receipt_required": False,
    }
    verification["verification_sha256"] = sha256(verification)
    return verification


__all__ = (
    "CONTRACT_ID",
    "GitEmbeddedSettlementError",
    "build_git_embedded_settlement",
    "build_payload_projection",
    "canonical_file_bytes",
    "settlement_anchor_path",
    "validate_git_embedded_settlement",
    "verify_final_commit",
)
