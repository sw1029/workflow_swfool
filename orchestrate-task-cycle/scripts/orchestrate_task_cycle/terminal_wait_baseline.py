"""Authority-settled terminal-wait selection-baseline owner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .authority_artifacts import validate_authority_use_receipt_settlement
from .terminal_wait_baseline_build import (
    activation_body,
    pointer_body,
    predict_artifacts,
)
from .terminal_wait_baseline_contract import (
    normalize_plan,
    validate_authority_phase,
    validate_selection_packet,
    validate_sources,
)
from .terminal_wait_baseline_store import (
    artifact_ref,
    display_bytes,
    mutation_lock,
    read_bound_json,
    read_current_bytes,
    scan_category,
    sha256_bytes,
    sha256_file,
    write_current,
    write_once,
)
from .terminal_wait_baseline_subject import (
    materialize_terminal_wait_authority_subject,
)
from .terminal_wait_baseline_validation import (
    load_current_pointer,
    validate_activation_binding,
    validate_completion_binding,
)
from .terminal_wait_baseline_retirement import (
    active_current_pointer as _active_current_pointer,
    inactive_pointer as _inactive_pointer,
    retire_terminal_wait_baseline,
)


def _current_snapshot_sha256(root: Path) -> str | None:
    current = _active_current_pointer(root, require_current_task=False)
    return None if current is None else current[0]["snapshot"]["sha256"]


def _require_expected_current(root: Path, expected: str | None) -> None:
    observed = _current_snapshot_sha256(root)
    if observed != expected:
        raise ValueError(
            "terminal-wait baseline CAS conflict: expected current snapshot does not match"
        )


def prepare_terminal_wait_baseline(
    root: Path, raw_plan: dict[str, Any], *, dry_run: bool = False
) -> dict[str, Any]:
    """Prepare one immutable baseline completion without exposing it as current."""

    root = root.expanduser().resolve(strict=True)
    plan = normalize_plan(raw_plan)
    packet, packet_projection = validate_sources(root, plan)
    authority_packet, _ = validate_authority_phase(root, plan)
    if packet.get("packet_id") != packet_projection["packet_id"]:
        raise ValueError("selection baseline projection changed during preparation")
    predicted = predict_artifacts(plan, packet_projection)
    if dry_run:
        _require_expected_current(root, plan["expected_current_snapshot_sha256"])
        return {
            "status": "dry_run",
            "mutation_performed": False,
            "transaction_id": predicted["transaction_id"],
            "snapshot": predicted["snapshot_binding"],
            "execution_result": predicted["completion_binding"],
        }
    with mutation_lock(root):
        packet, packet_projection = validate_sources(root, plan)
        authority_packet, _ = validate_authority_phase(root, plan)
        if packet.get("packet_id") != packet_projection["packet_id"]:
            raise ValueError("selection baseline projection changed during preparation")
        predicted = predict_artifacts(plan, packet_projection)
        _require_expected_current(root, plan["expected_current_snapshot_sha256"])
        if (
            write_once(
                root,
                "prepares",
                predicted["transaction_id"],
                display_bytes(predicted["prepare"]),
            )
            != predicted["prepare_binding"]
        ):
            raise ValueError("terminal-wait baseline prepare binding drifted")
        validate_sources(root, plan)
        validate_authority_phase(root, plan)
        if (
            write_once(
                root,
                "snapshots",
                predicted["snapshot_binding"]["sha256"],
                predicted["snapshot_body"],
            )
            != predicted["snapshot_binding"]
        ):
            raise ValueError("terminal-wait baseline snapshot binding drifted")
        _require_expected_current(root, plan["expected_current_snapshot_sha256"])
        if (
            write_once(
                root,
                "completions",
                predicted["transaction_id"],
                display_bytes(predicted["completion"]),
            )
            != predicted["completion_binding"]
        ):
            raise ValueError("terminal-wait baseline completion binding drifted")
        validate_completion_binding(root, predicted["completion_binding"])
        return {
            "status": "pending_settlement",
            "mutation_performed": True,
            "transaction_id": predicted["transaction_id"],
            "binding_id": predicted["snapshot"]["binding_id"],
            "snapshot": predicted["snapshot_binding"],
            "execution_result": predicted["completion_binding"],
            "authority_consume": {
                "reservation_id": (
                    authority_packet.get("reservation_binding") or {}
                ).get("reservation_id"),
                "idempotency_key": plan["consume_idempotency_key"],
                "execution_result": predicted["completion_binding"],
            },
            "current_pointer_exposed": False,
            "next_action": "consume_reserved_authority_then_activate",
        }


def activate_terminal_wait_baseline(
    root: Path,
    completion_binding: dict[str, str],
    use_receipt_binding: dict[str, str],
) -> dict[str, Any]:
    """Activate one settled completion through an exact current-pointer CAS."""

    root = root.expanduser().resolve(strict=True)
    with mutation_lock(root):
        completion, snapshot, plan = validate_completion_binding(
            root, completion_binding
        )
        _, use_receipt = read_bound_json(
            root,
            use_receipt_binding,
            "authority use receipt",
            expected_prefix=".task/authorization/use_receipts",
        )
        body = activation_body(
            completion_binding,
            completion["snapshot"],
            use_receipt_binding,
            plan["expected_current_snapshot_sha256"],
            use_receipt.get("consumed_at"),
        )
        activation_binding = {
            "ref": artifact_ref("activations", body["activation_id"]),
            "sha256": sha256_bytes(display_bytes(body)),
        }
        current = _active_current_pointer(root, require_current_task=False)
        if current is not None and current[0]["snapshot"] == completion["snapshot"]:
            if current[0]["activation"] != activation_binding:
                raise ValueError("current snapshot has a conflicting activation")
            resolved = resolve_terminal_wait_baseline(root)
            return {**resolved, "status": "active", "idempotent": True}
        _require_expected_current(root, plan["expected_current_snapshot_sha256"])
        _, authority_packet = read_bound_json(
            root, plan["authority_packet"], "authority packet"
        )
        findings = validate_authority_use_receipt_settlement(
            authority_packet,
            use_receipt_binding,
            root,
            execution_result=completion_binding,
            idempotency_key=plan["consume_idempotency_key"],
            phase="activation",
        )
        if findings:
            codes = ", ".join(str(row.get("code")) for row in findings)
            raise ValueError(f"authority settlement validation failed: {codes}")
        activation_binding = write_once(
            root,
            "activations",
            body["activation_id"],
            display_bytes(body),
        )
        validate_activation_binding(root, activation_binding, phase="historical")
        _require_expected_current(root, plan["expected_current_snapshot_sha256"])
        pointer = pointer_body(
            activation_binding,
            completion_binding,
            completion["snapshot"],
            snapshot,
            use_receipt_binding,
        )
        pointer_binding = write_current(root, display_bytes(pointer))
        verified = load_current_pointer(root, require_current_task=True)
        if verified is None or verified[1] != pointer_binding["sha256"]:
            raise ValueError("activated terminal-wait baseline did not verify")
        return {
            "status": "active",
            "mutation_performed": True,
            "idempotent": False,
            "binding_id": snapshot["binding_id"],
            "snapshot": completion["snapshot"],
            "activation": activation_binding,
            "current_pointer": pointer_binding,
            "authority_use_receipt": use_receipt_binding,
            "current_pointer_exposed": True,
        }


def resolve_terminal_wait_baseline(root: Path) -> dict[str, Any]:
    """Resolve and reverify the current binding without returning source bodies."""

    root = root.expanduser().resolve(strict=True)
    before = read_current_bytes(root)
    if before is None:
        return {
            "status": "empty",
            "mutation_performed": False,
            "current_pointer": None,
        }
    inactive = _inactive_pointer(root)
    if inactive is not None:
        pointer, digest = inactive
        return {
            "status": "inactive",
            "mutation_performed": False,
            "binding_id": None,
            "task_id": pointer["task_id"],
            "task_sha256": pointer["task_sha256"],
            "snapshot": pointer["snapshot"],
            "retirement": pointer["retirement"],
            "publication": pointer["publication"],
            "current_pointer": {
                "ref": ".task/terminal_wait_baseline/current.json",
                "sha256": digest,
            },
        }
    resolved = load_current_pointer(root, require_current_task=True)
    after = read_current_bytes(root)
    if resolved is None or before != after:
        raise ValueError(
            "terminal-wait baseline current pointer changed during resolve"
        )
    pointer, pointer_sha256, snapshot = resolved
    return {
        "status": "resolved",
        "mutation_performed": False,
        "binding_id": pointer["binding_id"],
        "task_id": pointer["task_id"],
        "task_sha256": pointer["task_sha256"],
        "snapshot": pointer["snapshot"],
        "activation": pointer["activation"],
        "completion": pointer["completion"],
        "authority_use_receipt": pointer["authority_use_receipt"],
        "source_derive": snapshot["source_derive"],
        "transition_evidence": snapshot["transition_evidence"],
        "selection_baseline": snapshot["selection_baseline"],
        "authority_subject": snapshot["authority_subject"],
        "predecessor_snapshot_sha256": snapshot["predecessor_snapshot_sha256"],
        "current_pointer": {
            "ref": ".task/terminal_wait_baseline/current.json",
            "sha256": pointer_sha256,
        },
    }


def current_selection_tick_packet(root: Path) -> dict[str, Any] | None:
    """Return the verified current tick packet for internal re-entry consumption."""

    root = root.expanduser().resolve(strict=True)
    current = _active_current_pointer(root, require_current_task=True)
    if current is None:
        return None
    pointer, _pointer_sha256, snapshot = current
    source = snapshot.get("selection_baseline") or {}
    baseline_binding = {key: source.get(key) for key in ("ref", "sha256")}
    _, packet = read_bound_json(root, baseline_binding, "selection baseline")
    validate_selection_packet(packet, root=root)
    return packet


def audit_terminal_wait_baseline(root: Path) -> dict[str, Any]:
    """Audit current and append-only artifacts without copying their source bodies."""

    root = root.expanduser().resolve(strict=True)
    findings: list[dict[str, str]] = []
    counts: dict[str, int] = {}
    paths: dict[str, list[Path]] = {}
    for category in (
        "subjects",
        "prepares",
        "snapshots",
        "completions",
        "activations",
    ):
        try:
            paths[category] = scan_category(root, category)
            counts[category] = len(paths[category])
        except (OSError, ValueError) as exc:
            paths[category] = []
            counts[category] = 0
            findings.append({"code": "store_invalid", "message": str(exc)})
    completion_refs: set[str] = set()
    linked_prepares: set[str] = set()
    linked_snapshots: set[str] = set()
    activation_counts: dict[str, int] = {}
    for path in paths["completions"]:
        artifact = {
            "ref": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
        }
        try:
            completion, _, _ = validate_completion_binding(
                root,
                artifact,
                require_current_task=False,
                allow_legacy_selection_v1=True,
            )
            completion_refs.add(artifact["ref"])
            linked_prepares.add(completion["prepare"]["ref"])
            linked_snapshots.add(completion["snapshot"]["ref"])
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            findings.append({"code": "completion_invalid", "message": str(exc)})
    for path in paths["activations"]:
        artifact = {
            "ref": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
        }
        try:
            activation, _, _ = validate_activation_binding(
                root,
                artifact,
                phase="historical",
                require_current_task=False,
            )
            completion_ref = activation["completion"]["ref"]
            activation_counts[completion_ref] = (
                activation_counts.get(completion_ref, 0) + 1
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            findings.append({"code": "activation_invalid", "message": str(exc)})
    for completion_ref in sorted(completion_refs):
        count = activation_counts.get(completion_ref, 0)
        if count != 1:
            findings.append(
                {
                    "code": "authority_settlement_pending"
                    if count == 0
                    else "multiple_activations",
                    "message": (
                        "Each committed baseline requires exactly one settled activation."
                    ),
                }
            )
    for path in paths["prepares"]:
        ref = path.relative_to(root).as_posix()
        if ref not in linked_prepares:
            findings.append(
                {
                    "code": "orphan_prepare",
                    "message": "Prepared baseline has no valid completion.",
                }
            )
    for path in paths["snapshots"]:
        ref = path.relative_to(root).as_posix()
        if ref not in linked_snapshots:
            findings.append(
                {
                    "code": "orphan_snapshot",
                    "message": "Baseline snapshot has no valid completion.",
                }
            )
    try:
        current = resolve_terminal_wait_baseline(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        current = None
        findings.append({"code": "current_pointer_invalid", "message": str(exc)})
    if (
        isinstance(current, dict)
        and current.get("status") == "empty"
        and paths["activations"]
    ):
        findings.append(
            {
                "code": "activation_not_published",
                "message": "Settled activation exists but no current pointer exposes it.",
            }
        )
    return {
        "status": "block" if findings else "ok",
        "mutation_performed": False,
        "artifact_counts": counts,
        "current": current,
        "findings": findings,
    }


__all__ = (
    "activate_terminal_wait_baseline",
    "audit_terminal_wait_baseline",
    "current_selection_tick_packet",
    "materialize_terminal_wait_authority_subject",
    "prepare_terminal_wait_baseline",
    "retire_terminal_wait_baseline",
    "resolve_terminal_wait_baseline",
)
