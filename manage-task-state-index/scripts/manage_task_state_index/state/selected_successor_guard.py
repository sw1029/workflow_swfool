"""Durable authority lease guard for selected-successor owner effects.

The legacy process-local token remains importable for compatibility diagnostics,
but it is deliberately not an authorization mechanism.  Every effect reopens a
content-addressed execution-lease epoch and revalidates all three current
authority reservations while holding the authority owner lock.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterator


ACTIONS = (
    "apply_task_state_plan_pending",
    "publish_selected_successor_topology",
    "settle_selected_successor_task_state",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LEASE_REF = re.compile(
    r"^\.task/selection_publication/successor_execution_leases/"
    r"sha256/([0-9a-f]{64})\.json$"
)
_LEASE_KEYS = {
    "schema_version",
    "artifact_kind",
    "lease_id",
    "lease_epoch",
    "bundle",
    "authority_gate",
    "authority_proofs",
    "execution_order",
    "action",
    "prior_checkpoint",
    "skills_root",
}
_ROW_KEYS = {
    "step",
    "action",
    "operation",
    "subject",
    "idempotency_key",
    "required_inputs",
    "expected_result",
    "authority_bindings",
}
_PROOF_KEYS = {
    "reservation",
    "pre_commit_verification",
    "expected_version",
}

# Compatibility symbol only.  Passing this object never authorizes an effect.
_SELECTED_SUCCESSOR_EXECUTION_TOKEN = object()

def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise ValueError(f"{label} requires exactly ref and sha256")
    ref = value.get("ref")
    digest = value.get("sha256")
    if (
        not isinstance(ref, str)
        or not ref
        or not isinstance(digest, str)
        or not _SHA256.fullmatch(digest)
    ):
        raise ValueError(f"{label} binding is invalid")
    return {"ref": ref, "sha256": digest}


def _read_binding(
    root: Path,
    value: Any,
    label: str,
    *,
    max_bytes: int = 512 * 1024,
) -> tuple[dict[str, str], bytes]:
    from manage_agent_authority.canonical import resolve_workspace_path
    from manage_agent_authority.stable_store import read_regular

    binding = _binding(value, label)
    path = resolve_workspace_path(root, binding["ref"], f"{label}.ref")
    payload = read_regular(path, label=label, max_bytes=max_bytes)
    assert payload is not None
    if hashlib.sha256(payload).hexdigest() != binding["sha256"]:
        raise ValueError(f"{label} bytes differ from their binding")
    return binding, payload


def _closed_rows(value: Any) -> list[dict[str, Any]]:
    if (
        not isinstance(value, list)
        or len(value) != len(ACTIONS)
        or any(not isinstance(row, dict) or set(row) != _ROW_KEYS for row in value)
        or [row["step"] for row in value] != [1, 2, 3]
        or [row["action"] for row in value] != list(ACTIONS)
    ):
        raise ValueError("selected-successor execution lease order is invalid")
    rows: list[dict[str, Any]] = []
    for row in value:
        if (
            not isinstance(row.get("operation"), dict)
            or not isinstance(row.get("subject"), dict)
            or not isinstance(row.get("required_inputs"), dict)
            or not isinstance(row.get("idempotency_key"), str)
            or not row["idempotency_key"]
            or row.get("authority_bindings")
            != {
                "reservation": {"required_keys": ["ref", "sha256"]},
                "pre_commit_verification": {
                    "required_keys": ["ref", "sha256"]
                },
                "must_be_validated_before_first_effect": True,
            }
        ):
            raise ValueError("selected-successor execution lease row is invalid")
        _binding(row["expected_result"], f"{row['action']} expected result")
        rows.append(dict(row))
    return rows


def _closed_proofs(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != set(ACTIONS):
        raise ValueError("selected-successor execution lease requires all three proofs")
    proofs: dict[str, dict[str, Any]] = {}
    for action in ACTIONS:
        proof = value[action]
        if not isinstance(proof, dict) or set(proof) != _PROOF_KEYS:
            raise ValueError(f"selected-successor {action} proof is invalid")
        version = proof["expected_version"]
        if type(version) is not int or version < 0:
            raise ValueError(f"selected-successor {action} proof version is invalid")
        proofs[action] = {
            "reservation": _binding(
                proof["reservation"], f"{action} authority reservation"
            ),
            "pre_commit_verification": _binding(
                proof["pre_commit_verification"],
                f"{action} pre-commit verification",
            ),
            "expected_version": version,
        }
    return proofs


def _gate_operations(
    rows: list[dict[str, Any]], proofs: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    return [
        {
            "action": row["action"],
            "operation": row["operation"],
            "subject": row["subject"],
            "idempotency_key": row["idempotency_key"],
            "reservation": proofs[row["action"]]["reservation"],
            "pre_commit_verification": proofs[row["action"]][
                "pre_commit_verification"
            ],
            "expected_version": proofs[row["action"]]["expected_version"],
        }
        for row in rows
    ]


def _validate_gate(
    root: Path,
    value: Any,
    *,
    bundle: dict[str, str],
    rows: list[dict[str, Any]],
    proofs: dict[str, dict[str, Any]],
) -> dict[str, str]:
    binding, payload = _read_binding(
        root, value, "selected-successor authority gate"
    )
    try:
        gate = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("selected-successor authority gate is unreadable") from exc
    if not isinstance(gate, dict) or payload != _canonical_json(gate):
        raise ValueError("selected-successor authority gate is not canonical")
    body = {
        key: item for key, item in gate.items() if key != "gate_content_sha256"
    }
    if (
        set(gate)
        != {
            "schema_version",
            "artifact_kind",
            "gate_status",
            "bundle",
            "checked_operations",
            "gate_content_sha256",
        }
        or gate.get("schema_version") != 1
        or gate.get("artifact_kind") != "selected_successor_authority_gate"
        or gate.get("gate_status")
        != "per_effect_current_authority_lease_required"
        or gate.get("bundle") != bundle
        or gate.get("checked_operations") != _gate_operations(rows, proofs)
        or gate.get("gate_content_sha256")
        != hashlib.sha256(_canonical_json(body)).hexdigest()
    ):
        raise ValueError("selected-successor authority gate is invalid")
    return binding


def load_selected_successor_execution_lease(
    root: Path, value: Any
) -> dict[str, Any]:
    """Boundedly reopen and structurally validate one exact lease epoch."""

    root = root.expanduser().resolve(strict=True)
    binding, payload = _read_binding(
        root, value, "selected-successor execution lease"
    )
    match = _LEASE_REF.fullmatch(binding["ref"])
    if match is None or match.group(1) != binding["sha256"]:
        raise ValueError(
            "selected-successor execution lease path is not content-addressed"
        )
    try:
        lease = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("selected-successor execution lease is unreadable") from exc
    if (
        not isinstance(lease, dict)
        or set(lease) != _LEASE_KEYS
        or payload != _canonical_json(lease)
        or lease.get("schema_version") != 1
        or lease.get("artifact_kind") != "selected_successor_execution_lease"
    ):
        raise ValueError("selected-successor execution lease is invalid")
    rows = _closed_rows(lease["execution_order"])
    proofs = _closed_proofs(lease["authority_proofs"])
    bundle = _binding(lease["bundle"], "selected-successor bundle")
    from orchestrate_task_cycle.selected_successor import (
        load_selected_successor_bundle,
    )

    selected_bundle = load_selected_successor_bundle(root, bundle)
    if selected_bundle.get("execution_order") != rows:
        raise ValueError(
            "selected-successor execution lease rows differ from the exact bundle"
        )
    action = lease.get("action")
    epoch = lease.get("lease_epoch")
    if (
        action not in ACTIONS
        or type(epoch) is not int
        or epoch != ACTIONS.index(action)
    ):
        raise ValueError("selected-successor execution lease epoch is invalid")
    prior = lease.get("prior_checkpoint")
    expected_prior = None if epoch == 0 else rows[epoch - 1]["expected_result"]
    if prior != expected_prior:
        raise ValueError(
            "selected-successor execution lease prior checkpoint is invalid"
        )
    if prior is not None:
        _read_binding(root, prior, "selected-successor prior checkpoint")
    core = {key: item for key, item in lease.items() if key != "lease_id"}
    if lease.get("lease_id") != (
        "ssel-" + hashlib.sha256(_canonical_json(core)).hexdigest()[:32]
    ):
        raise ValueError("selected-successor execution lease identity is invalid")
    _validate_gate(
        root,
        lease["authority_gate"],
        bundle=bundle,
        rows=rows,
        proofs=proofs,
    )
    skills_root = lease.get("skills_root")
    if skills_root is not None and (
        not isinstance(skills_root, str)
        or not Path(skills_root).is_absolute()
        or not Path(skills_root).is_dir()
    ):
        raise ValueError("selected-successor execution lease skills root is invalid")
    return lease


def _validate_effect_inputs(
    row: dict[str, Any], action: str, actual: dict[str, Any]
) -> None:
    expected = row["required_inputs"]
    if action == ACTIONS[0]:
        keys = {"plan", "external_prepare"}
        if set(actual) != keys or set(expected) != keys or any(
            _binding(actual[key], f"{action} {key}") != expected.get(key)
            for key in keys
        ):
            raise ValueError("selected-successor index lease binds other inputs")
    elif action == ACTIONS[1]:
        prepare = _binding(actual.get("prepare"), f"{action} prepare")
        transaction_id = actual.get("transaction_id")
        if (
            set(expected) != {"prepare", "pending"}
            or _binding(expected.get("pending"), f"{action} pending")
            != expected["pending"]
            or prepare != expected.get("prepare")
            or not isinstance(transaction_id, str)
            or prepare["ref"]
            != (
                ".task/selection_publication/transactions/"
                f"{transaction_id}/prepare.json"
            )
        ):
            raise ValueError("selected-successor publication lease binds other inputs")
    else:
        keys = {"plan", "pending", "publication"}
        if set(actual) != keys or set(expected) != keys or any(
            _binding(actual[key], f"{action} {key}") != expected.get(key)
            for key in keys
        ):
            raise ValueError("selected-successor settlement lease binds other inputs")


def _validate_current_authority(root: Path, lease: dict[str, Any]) -> None:
    from manage_agent_authority.execution_results import (
        validate_pre_commit_verification,
    )
    from manage_agent_authority.historical_proof_chain import (
        validate_historical_proof_chains,
    )

    rows = _closed_rows(lease["execution_order"])
    proofs = _closed_proofs(lease["authority_proofs"])
    skills_root = (
        Path(lease["skills_root"]) if lease.get("skills_root") is not None else None
    )
    chains = validate_historical_proof_chains(
        root,
        [
            (
                proofs[action]["reservation"],
                proofs[action]["pre_commit_verification"],
                proofs[action]["expected_version"],
            )
            for action in ACTIONS
        ],
        skills_root=skills_root,
    )
    for row, chain in zip(rows, chains):
        action = row["action"]
        proof = proofs[action]
        reservation = chain["reservation"]
        state = chain["current_state"]
        request = chain["decision"].get("request")
        operation = row["operation"]
        expected_operation = {
            key: operation.get(key)
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        }
        if (
            chain["reservation_binding"] != proof["reservation"]
            or chain["verification_binding"]
            != proof["pre_commit_verification"]
            or state.get("status") != "reserved"
            or state.get("version") != proof["expected_version"]
            or not isinstance(request, dict)
            or any(
                request.get(key) != value
                for key, value in expected_operation.items()
            )
            or request.get("subject") != row["subject"]
            or request.get("idempotency_key") != row["idempotency_key"]
            or reservation.get("idempotency_key") != row["idempotency_key"]
        ):
            raise ValueError(
                f"selected-successor {action} authority is not current"
            )
        validate_pre_commit_verification(
            root,
            reservation,
            proof["reservation"],
            proof["pre_commit_verification"],
            expected_version=proof["expected_version"],
            require_current_state=True,
        )


def _selected_successor_effect_hook(stage: str, root: Path, action: str) -> None:
    """Test seam used to force a reservation race before revalidation."""

    _ = stage, root, action


@contextmanager
def guard_selected_successor_effect(
    root: Path,
    execution_lease: Any,
    *,
    action: str,
    effect_inputs: dict[str, Any],
    legacy_token: object | None = None,
) -> Iterator[dict[str, Any]]:
    """Hold authority current from exact lease validation through owner effect."""

    if execution_lease is None:
        suffix = (
            "; an imported legacy token is not authority"
            if legacy_token is not None
            else ""
        )
        raise ValueError(
            "Selected-successor owner effect requires an exact durable execution lease"
            + suffix
        )
    if action not in ACTIONS:
        raise ValueError("selected-successor effect action is invalid")
    root = root.expanduser().resolve(strict=True)
    from manage_agent_authority.canonical import authority_lock

    with authority_lock(root):
        _selected_successor_effect_hook(
            "before_current_authority_revalidation", root, action
        )
        lease = load_selected_successor_execution_lease(root, execution_lease)
        if lease["action"] != action:
            raise ValueError("selected-successor execution lease authorizes another action")
        row = lease["execution_order"][lease["lease_epoch"]]
        _validate_effect_inputs(row, action, effect_inputs)
        _validate_current_authority(root, lease)
        yield lease
        _read_binding(
            root,
            row["expected_result"],
            f"{action} exact result checkpoint",
        )


def plan_requires_selected_successor_lease(plan: dict[str, Any]) -> bool:
    """Classify task-alias activation batches as selected-successor effects."""

    request = plan.get("request")
    if (
        plan.get("schema_version") == 2
        and isinstance(request, dict)
        and request.get("external_settlement_kind") == "selection_publication"
    ):
        return True
    events = plan.get("events")
    return bool(
        isinstance(events, list)
        and any(
            isinstance(event, dict)
            and isinstance(event.get("fields"), dict)
            and any(
                key in event["fields"]
                for key in (
                    "selection_decision_id",
                    "selection_decision_ref",
                    "selection_decision_sha256",
                )
            )
            for event in events
        )
    )


__all__ = (
    "ACTIONS",
    "guard_selected_successor_effect",
    "load_selected_successor_execution_lease",
    "plan_requires_selected_successor_lease",
)
