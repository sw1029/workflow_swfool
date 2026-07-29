"""Read-only proof bridge from a sealed selection to one successor cycle."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from ..cycle_ledger import read_events
from ..ledger.support import read_initialization_metadata
from ..selection_decision_store import (
    normalize_binding,
    read_bound_bytes,
    read_bound_json,
)
from ..selection_publication_store import _canonical_json
from ..selection_publication_v2 import _selected_source
from ..selected_successor import load_selected_successor_bundle
from ..selected_successor_execution import _proofs
from ..selected_successor_execution_support import ACTIONS, checkpoint_states
from .successor_authority_proof import (
    _default_skills_root,
    _session_envelope,
    _session_unchanged,
    _settlements,
)


def _time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("successor proof timestamps must include a timezone")
    return parsed


def _derive_selection_candidate(
    root: Path, cycle_id: str
) -> tuple[dict[str, str], dict[str, Any], str]:
    derives = [
        row
        for row in read_events(root, cycle_id)
        if row.get("step") == "derive"
        and str(row.get("status") or "").lower()
        in {"complete", "completed", "passed", "success"}
    ]
    if not derives:
        raise ValueError("no completed derive selection exists")
    derive = derives[-1]
    binding = normalize_binding(
        derive.get("selection_receipt"), "derive selection receipt"
    )
    _path, receipt = read_bound_json(
        root, binding, "derive selection receipt"
    )
    if (
        receipt.get("artifact_kind") != "selection_decision_receipt"
        or receipt.get("outcome") != "selected"
        or not isinstance(receipt.get("selected_task_id"), str)
    ):
        raise ValueError("derive outcome did not select a successor")
    task_id = str(receipt["selected_task_id"])
    declared = derive.get("next_task_id")
    if declared is not None and declared != task_id:
        raise ValueError("derive next_task_id differs from its selection receipt")
    return binding, receipt, task_id


def _selection(
    root: Path,
    cycle_id: str,
    *,
    bundle: dict[str, Any] | None = None,
) -> tuple[dict[str, str], dict[str, Any], str]:
    binding, candidate, task_id = _derive_selection_candidate(root, cycle_id)
    if candidate.get("schema_version") == 2 and bundle is not None:
        from .successor_selection_proof import (
            validate_historical_selection_v2,
        )

        validated_binding = binding
        validated = validate_historical_selection_v2(
            root,
            binding,
            candidate,
            cycle_id=cycle_id,
            bundle=bundle,
        )
    else:
        validated_binding, validated = _selected_source(root, binding)
    if (
        validated_binding != binding
        or validated.get("outcome") != "selected"
        or validated.get("selected_task_id") != task_id
    ):
        raise ValueError("derive selection receipt binding changed")
    return binding, validated, task_id


def _selected_task(root: Path, cycle_id: str) -> str | None:
    """Compatibility reader retained for callers that need only the task ID."""

    try:
        return _selection(root, cycle_id)[2]
    except (OSError, ValueError, SystemExit):
        return None


def _binding_for(root: Path, path: Path) -> dict[str, str]:
    raw = path.read_bytes()
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _matching_bundles(
    root: Path, selection: dict[str, str], task_id: str
) -> list[tuple[dict[str, str], dict[str, Any]]]:
    directory = (
        root
        / ".task"
        / "selection_publication"
        / "successor_bundles"
        / "sha256"
    )
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("selected-successor bundle store is unsafe")
    matches: list[tuple[dict[str, str], dict[str, Any]]] = []
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise ValueError("selected-successor bundle store is not closed")
        binding = _binding_for(root, path)
        bundle = load_selected_successor_bundle(root, binding)
        if (
            bundle["source_decision"] == selection
            and bundle["selected_task_id"] == task_id
        ):
            matches.append((binding, bundle))
    return matches


def _lease_core(lease: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in lease.items() if key != "lease_id"}


def _validate_gate(
    root: Path,
    binding: dict[str, str],
    bundle_binding: dict[str, str],
    rows: list[dict[str, Any]],
    proofs: dict[str, dict[str, Any]],
) -> None:
    path, gate = read_bound_json(
        root, binding, "selected-successor authority gate"
    )
    body = {
        "schema_version": 1,
        "artifact_kind": "selected_successor_authority_gate",
        "gate_status": "per_effect_current_authority_lease_required",
        "bundle": bundle_binding,
        "checked_operations": [
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
        ],
    }
    digest = hashlib.sha256(_canonical_json(body)).hexdigest()
    expected = {**body, "gate_content_sha256": digest}
    expected_ref = (
        ".task/selection_publication/successor_authority_gates/"
        f"sha256/{digest}.json"
    )
    if gate != expected or path.relative_to(root).as_posix() != expected_ref:
        raise ValueError("selected-successor authority gate is cross-bound")


def _execution_leases(
    root: Path,
    bundle_binding: dict[str, str],
    bundle: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], tuple[dict[str, str], ...]]:
    directory = (
        root
        / ".task"
        / "selection_publication"
        / "successor_execution_leases"
        / "sha256"
    )
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("selected-successor execution leases are absent")
    rows, states = checkpoint_states(root, bundle)
    if states != ["exact", "exact", "exact"]:
        raise ValueError("selected-successor checkpoints are incomplete")
    found: dict[str, tuple[dict[str, str], dict[str, Any]]] = {}
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise ValueError("selected-successor execution-lease store is unsafe")
        binding = _binding_for(root, path)
        _opened, raw = read_bound_bytes(
            root, binding, "selected-successor execution lease"
        )
        try:
            lease = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("selected-successor execution lease is unreadable") from exc
        if not isinstance(lease, dict) or raw != _canonical_json(lease):
            raise ValueError("selected-successor execution lease is not canonical")
        if lease.get("bundle") != bundle_binding:
            continue
        expected_keys = {
            "schema_version",
            "artifact_kind",
            "lease_epoch",
            "bundle",
            "authority_gate",
            "authority_proofs",
            "execution_order",
            "action",
            "prior_checkpoint",
            "skills_root",
            "lease_id",
        }
        action = str(lease.get("action") or "")
        if (
            set(lease) != expected_keys
            or lease.get("schema_version") != 1
            or lease.get("artifact_kind") != "selected_successor_execution_lease"
            or action not in ACTIONS
            or lease.get("lease_epoch") != ACTIONS.index(action)
            or lease.get("execution_order") != rows
            or lease.get("prior_checkpoint")
            != (
                None
                if action == ACTIONS[0]
                else rows[ACTIONS.index(action) - 1]["expected_result"]
            )
            or lease.get("lease_id")
            != "ssel-"
            + hashlib.sha256(_canonical_json(_lease_core(lease))).hexdigest()[:32]
            or path.stem != binding["sha256"]
        ):
            raise ValueError("selected-successor execution lease is cross-bound")
        if action in found:
            raise ValueError("selected-successor execution lease is ambiguous")
        found[action] = (binding, lease)
    if set(found) != set(ACTIONS):
        raise ValueError("selected-successor requires all three execution leases")
    proof_values = [found[action][1]["authority_proofs"] for action in ACTIONS]
    if any(value != proof_values[0] for value in proof_values[1:]):
        raise ValueError("selected-successor execution leases disagree on authority")
    proofs = _proofs(proof_values[0])
    gates = [found[action][1]["authority_gate"] for action in ACTIONS]
    if any(gate != gates[0] for gate in gates[1:]):
        raise ValueError("selected-successor execution leases disagree on their gate")
    gate = normalize_binding(gates[0], "selected-successor authority gate")
    _validate_gate(root, gate, bundle_binding, rows, proofs)
    return proofs, tuple(found[action][0] for action in ACTIONS)


def _successor_cycles(
    root: Path,
    cycle_id: str,
    task_id: str,
    *,
    after: datetime,
) -> list[tuple[datetime, str]]:
    current = read_initialization_metadata(root, cycle_id)
    current_at = _time(current["initialized_at"])
    directory = root / ".task" / "cycle"
    candidates: list[tuple[datetime, str]] = []
    for path in sorted(directory.glob("*/initialization.json")):
        if path.is_symlink() or not path.is_file():
            raise ValueError("cycle initialization store is unsafe")
        candidate_id = path.parent.name
        metadata = read_initialization_metadata(root, candidate_id)
        initialized = _time(metadata["initialized_at"])
        if (
            candidate_id != cycle_id
            and metadata.get("task_id") == task_id
            and initialized > current_at
            and initialized > after
        ):
            candidates.append((initialized, candidate_id))
    return candidates


def _bindings_unchanged(
    root: Path, bindings: tuple[dict[str, str], ...]
) -> bool:
    try:
        for binding in bindings:
            read_bound_bytes(root, binding, "successor proof replay")
    except ValueError:
        return False
    return True


def _settled_successor_proof(
    root: Path,
    cycle_id: str,
    *,
    session_id: str,
    goal_id: str | None = None,
    task_family: str | None = None,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Resolve and replay the exact proof that permits one successor."""

    workspace = root.expanduser().resolve(strict=True)
    lease, lease_sha = _session_envelope(
        workspace, session_id, goal_id, task_family
    )
    selection, _candidate, task_id = _derive_selection_candidate(
        workspace, cycle_id
    )
    bundles = _matching_bundles(workspace, selection, task_id)
    if len(bundles) != 1:
        raise ValueError("selected-successor bundle is absent or ambiguous")
    bundle_binding, bundle = bundles[0]
    exact_selection, receipt, exact_task = _selection(
        workspace,
        cycle_id,
        bundle=bundle,
    )
    if exact_selection != selection or exact_task != task_id:
        raise ValueError("selected-successor selection changed")
    proofs, execution_leases = _execution_leases(
        workspace, bundle_binding, bundle
    )
    settled_at, use_receipts = _settlements(
        workspace,
        bundle,
        proofs,
        lease,
        session_id=session_id,
        skills_root=skills_root or _default_skills_root(),
    )
    barrier = max(settled_at, _time(bundle["created_at"]))
    if (
        _matching_bundles(workspace, selection, task_id)
        != [(bundle_binding, bundle)]
        or _selection(workspace, cycle_id, bundle=bundle)
        != (selection, receipt, task_id)
        or _execution_leases(workspace, bundle_binding, bundle)[1]
        != execution_leases
        or not _session_unchanged(workspace, session_id, lease_sha)
        or not _bindings_unchanged(workspace, use_receipts)
    ):
        raise ValueError("selected-successor proof changed during replay")
    return {
        "lease": lease,
        "lease_sha256": lease_sha,
        "selection": selection,
        "selection_receipt": receipt,
        "task_id": task_id,
        "bundle": bundle_binding,
        "execution_leases": execution_leases,
        "use_receipts": use_receipts,
        "barrier": barrier,
    }


def _selected_result(
    proof: dict[str, Any], cycle_id: str
) -> dict[str, Any]:
    lease = proof["lease"]
    return {
        "outcome": "selected",
        "cycle_id": cycle_id,
        "task_id": proof["task_id"],
        "goal_id": lease["goal_id"],
        "task_family": lease["task_family"],
        "risk_envelope_match": True,
    }


def selected_initialized_successor(
    root: Path,
    cycle_id: str,
    *,
    session_id: str | None = None,
    goal_id: str | None = None,
    task_family: str | None = None,
    skills_root: Path | None = None,
) -> dict[str, Any] | None:
    """Return one successor only after exact selection, effects, and settlement."""

    if not session_id:
        return None
    try:
        proof = _settled_successor_proof(
            root,
            cycle_id,
            session_id=session_id,
            goal_id=goal_id,
            task_family=task_family,
            skills_root=skills_root,
        )
        workspace = root.expanduser().resolve(strict=True)
        successors = _successor_cycles(
            workspace,
            cycle_id,
            proof["task_id"],
            after=proof["barrier"],
        )
        replayed = _settled_successor_proof(
            workspace,
            cycle_id,
            session_id=session_id,
            goal_id=goal_id,
            task_family=task_family,
            skills_root=skills_root,
        )
        if len(successors) != 1:
            return None
        if (
            replayed != proof
            or _successor_cycles(
                workspace,
                cycle_id,
                proof["task_id"],
                after=proof["barrier"],
            )
            != successors
        ):
            return None
        _initialized, next_cycle = successors[0]
        return _selected_result(proof, next_cycle)
    except (OSError, ValueError, SystemExit, json.JSONDecodeError):
        return None


__all__ = ("selected_initialized_successor",)
