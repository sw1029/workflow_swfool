"""Independent integrity checks for canonical compiler-first scan results."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .event_batch_validation import validate_event_batch
from .events import load_events_read_only, merge_state
from .render import _markdown_projection_matches
from .scan_integrity import _is_digest, _validate_binding, preflight_scan_apply
from .scan_projection_repair import (
    expected_projection_sha256,
    validate_projection_repair_receipt,
)
from .storage import jsonl_path, markdown_path, sha256_file
from .transition_plan_contract import (
    canonical_bytes,
    receipt_for_plan,
    receipt_status,
    regular_payload,
    sha256_bytes,
    workspace_path,
)
from .transition_recovery import event_payload


SCAN_RESULT_FIELDS = frozenset("""schema_version artifact_kind operation effect_status
completed_at compilation plan transition_receipt subject projection
logical_update_count event_batch focus_results post_check result_sha256""".split())
_EVENT_BATCH_FIELDS = frozenset(
    {"plan_id", "before_event_count", "event_count", "event_payload_sha256"}
)
_POST_CHECK_FIELDS = frozenset(
    {"would_change", "logical_update_count", "event_count", "inventory_sha256"}
)


def _validate_envelope(
    binding: dict[str, str],
    payload: bytes,
    result: dict[str, Any],
    compilation_binding: dict[str, str],
    compilation: dict[str, Any],
) -> None:
    body = {key: value for key, value in result.items() if key != "result_sha256"}
    expected_ref = f".task/scan_receipts/{compilation['compilation_id']}.json"
    if (
        set(result) != SCAN_RESULT_FIELDS
        or result.get("schema_version") != 2
        or result.get("artifact_kind") != "task_state_index_scan_result"
        or result.get("operation") != "scan"
        or result.get("completed_at") != compilation["created_at"]
        or result.get("compilation") != compilation_binding
        or binding != {"ref": expected_ref, "sha256": sha256_bytes(payload)}
        or result.get("result_sha256") != sha256_bytes(canonical_bytes(body))
        or payload != canonical_bytes(result) + b"\n"
    ):
        raise ValueError("Task-state scan result integrity check failed")
    if (
        result.get("logical_update_count") != compilation["logical_update_count"]
        or result.get("focus_results") != compilation["focus_results"]
        or not isinstance(result.get("event_batch"), dict)
        or set(result["event_batch"]) != _EVENT_BATCH_FIELDS
        or not isinstance(result.get("post_check"), dict)
        or set(result["post_check"]) != _POST_CHECK_FIELDS
    ):
        raise ValueError("Task-state scan result derived fields are not closed")


def _non_event_boundary(
    root: Path,
    compilation: dict[str, Any],
    events: list[dict[str, Any]],
    before_event_count: Any,
) -> int:
    if (
        isinstance(before_event_count, bool)
        or not isinstance(before_event_count, int)
        or before_event_count < 0
        or before_event_count > len(events)
    ):
        raise ValueError("Task-state non-batch scan boundary count is invalid")
    expected = compilation["index_revision"]["sha256"]
    if expected is None:
        if before_event_count != 0:
            raise ValueError("Task-state non-batch scan missing-ledger boundary is invalid")
    else:
        ledger = regular_payload(jsonl_path(root), missing=b"")
        seen = 0
        offset = 0
        if before_event_count:
            for raw_line in ledger.splitlines(keepends=True):
                offset += len(raw_line)
                if raw_line.strip():
                    seen += 1
                if seen == before_event_count:
                    break
        if seen != before_event_count:
            raise ValueError("Task-state non-batch scan ledger prefix is incomplete")
        prefix = ledger[:offset] if before_event_count else b""
        candidates = [prefix]
        if prefix.endswith(b"\n"):
            candidates.append(prefix[:-1])
        if all(sha256_bytes(candidate) != expected for candidate in candidates):
            raise ValueError("Task-state non-batch scan ledger prefix differs")
    try:
        validate_event_batch(
            events[:before_event_count], events[before_event_count:],
            source=jsonl_path(root),
        )
    except ValueError as exc:
        raise ValueError("Task-state non-batch scan descendant suffix is invalid") from exc
    return len(events) - before_event_count


def _validate_non_event(
    root: Path,
    result: dict[str, Any],
    compilation_binding: dict[str, str],
    compilation: dict[str, Any],
    events: list[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    mode = compilation["effect_mode"]
    if result.get("plan") is not None:
        raise ValueError("Task-state non-batch scan result must not bind a plan")
    projection_digest = sha256_file(markdown_path(root))
    if not _markdown_projection_matches(root, merge_state(events)):
        raise ValueError("Task-state non-batch scan current projection is stale")
    before_projection = compilation["projection_revision"]["sha256"]
    effect = "confirmed_no_effect" if mode == "no_effect" else "confirmed_effect"
    projection = result.get("projection")
    after_projection = (
        projection.get("after_sha256") if isinstance(projection, dict) else None
    )
    if (
        (mode == "no_effect" and before_projection != after_projection)
        or (mode == "projection_repair" and (
            before_projection == after_projection or not _is_digest(after_projection)
        ))
    ):
        raise ValueError("Task-state non-batch scan effect is not independently observed")
    batch = result["event_batch"]
    descendants = _non_event_boundary(
        root, compilation, events, batch.get("before_event_count")
    )
    prefix_events = events[:batch["before_event_count"]]
    if mode == "projection_repair":
        expected_after = expected_projection_sha256(
            prefix_events, compilation["created_at"]
        )
        if after_projection != expected_after:
            raise ValueError(
                "Task-state projection repair after digest is not independently derived"
            )
        transition = _validate_binding(
            result.get("transition_receipt"), "projection repair receipt"
        )
        validate_projection_repair_receipt(
            root,
            transition,
            compilation_binding,
            compilation,
            prefix_events,
        )
    elif result.get("transition_receipt") is not None:
        raise ValueError("Task-state no-effect scan result must not bind a receipt")
    ledger_digest = compilation["index_revision"]["sha256"] or sha256_bytes(b"")
    expected_batch = {
        "plan_id": compilation["compilation_id"],
        "before_event_count": batch["before_event_count"],
        "event_count": 0,
        "event_payload_sha256": sha256_bytes(b""),
    }
    expected_post = {
        "would_change": False,
        "logical_update_count": 0,
        "event_count": 0,
        "inventory_sha256": compilation["inventory"]["sha256"],
    }
    if (
        result.get("effect_status") != effect
        or (descendants == 0 and projection_digest != after_projection)
        or result.get("subject") != {
            "kind": "task_index", "ref": ".task/index.jsonl",
            "before_sha256": ledger_digest, "after_sha256": ledger_digest,
        }
        or result.get("projection") != {
            "ref": ".task/index.md", "before_sha256": before_projection,
            "after_sha256": after_projection,
        }
        or result["event_batch"] != expected_batch
        or result["post_check"] != expected_post
    ):
        raise ValueError("Task-state non-batch scan result differs from current evidence")
    return expected_batch, descendants


def _validate_event_batch(
    root: Path,
    result: dict[str, Any],
    compilation: dict[str, Any],
    events: list[dict[str, Any]],
    current_index: str | None,
) -> tuple[dict[str, Any], int]:
    if result.get("plan") != compilation["plan_binding"]:
        raise ValueError("Task-state scan result plan binding differs")
    plan, exact = preflight_scan_apply(root, compilation, events, current_index)
    if plan is None or not exact:
        raise ValueError("Task-state scan result has no exact committed event batch")
    transition = _validate_binding(result.get("transition_receipt"), "transition receipt")
    expected_ref = f".task/transition_receipts/{plan['plan_id']}.json"
    expected_receipt = receipt_for_plan(
        plan, compilation["plan_binding"]["ref"], compilation["plan_binding"]["sha256"]
    )
    status, receipt_digest = receipt_status(
        workspace_path(root, transition["ref"]), expected_receipt
    )
    if (
        transition["ref"] != expected_ref
        or status != "current"
        or receipt_digest != transition["sha256"]
    ):
        raise ValueError("Task-state scan transition receipt differs")
    if not _markdown_projection_matches(root, merge_state(events)):
        raise ValueError("Task-state scan result current projection is stale")
    descendants = (
        len(events) - plan["ledger"]["before_event_count"]
        - plan["ledger"]["event_count"]
    )
    batch = {
        "plan_id": plan["plan_id"],
        "before_event_count": plan["ledger"]["before_event_count"],
        "event_count": plan["ledger"]["event_count"],
        "event_payload_sha256": sha256_bytes(event_payload(plan["events"])),
    }
    if (
        result.get("effect_status") != "confirmed_effect"
        or result.get("subject") != {
            "kind": "task_index", "ref": ".task/index.jsonl",
            "before_sha256": plan["ledger"]["before_sha256"],
            "after_sha256": plan["ledger"]["after_sha256"],
        }
        or result.get("projection") != {
            "ref": ".task/index.md",
            "before_sha256": plan["markdown"]["before_sha256"],
            "after_sha256": plan["markdown"]["after_sha256"],
        }
        or result["event_batch"] != batch
        or result["post_check"] != {
            "would_change": False, "logical_update_count": 0, "event_count": 0,
            "inventory_sha256": compilation["inventory"]["sha256"],
        }
    ):
        raise ValueError("Task-state scan result differs from its exact batch")
    return batch, descendants


def validate_scan_result_evidence(
    root: Path,
    binding: dict[str, str],
    payload: bytes,
    result: dict[str, Any],
    compilation_binding: dict[str, str],
    compilation: dict[str, Any],
) -> dict[str, Any]:
    """Recompute a canonical scan result from immutable and current evidence."""

    _validate_envelope(
        binding, payload, result, compilation_binding, compilation
    )
    events, current_index = load_events_read_only(root)
    if compilation["effect_mode"] == "event_batch":
        batch, descendants = _validate_event_batch(
            root, result, compilation, events, current_index
        )
    else:
        batch, descendants = _validate_non_event(
            root, result, compilation_binding, compilation, events
        )
    return {
        "effect_status": result["effect_status"],
        "subject": result["subject"],
        "projection": result["projection"],
        "plan": result["plan"],
        "event_batch": batch,
        "descendant_event_count": descendants,
        "validated_at": result["completed_at"],
    }


def load_existing_scan_result(
    root: Path,
    path: Path,
    compilation_binding: dict[str, str],
    compilation: dict[str, Any],
) -> dict[str, Any] | None:
    """Load and fully validate an existing canonical scan receipt for replay."""

    if not path.exists() and not path.is_symlink():
        return None
    payload = regular_payload(path)
    try:
        result = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Task-state scan result is not canonical JSON") from exc
    if not isinstance(result, dict):
        raise ValueError("Task-state scan result must be a JSON object")
    binding = {
        "ref": f".task/scan_receipts/{compilation['compilation_id']}.json",
        "sha256": sha256_bytes(payload),
    }
    validate_scan_result_evidence(
        root, binding, payload, result, compilation_binding, compilation
    )
    return result


__all__ = (
    "SCAN_RESULT_FIELDS", "load_existing_scan_result",
    "validate_scan_result_evidence",
)
