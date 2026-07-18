"""Crash-safe apply facade for canonical task transitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import require
from .task_transition_contract import (
    effect_receipt,
    expected_intent,
    no_effect_receipt,
)
from .task_transition_store import (
    file_bytes,
    load_task_transition_plan,
    owned_ref,
    publish_immutable,
    replace_canonical_task,
    transition_lock,
)
from .task_transition_verification import (
    archive_state,
    binding,
    canonical_observation,
    inspect_transition,
    intent_state,
    matches,
    prospective_observation,
    sha256_bytes,
    snapshot_state,
    verify_task_transition_execution,
)


def _publish_effect_receipt(
    root: Path, plan: dict[str, Any], plan_binding: dict[str, str],
    intent_digest: str, successor_digest: str, archive_digest: str | None,
) -> tuple[bool, str]:
    receipt = effect_receipt(
        plan,
        plan_binding,
        binding(
            owned_ref(plan["transition_id"], "intents", "json"), intent_digest
        ),
        binding(
            owned_ref(plan["transition_id"], "successors", "md"),
            successor_digest,
        ),
        (
            binding(str(plan["archive_task"]["ref"]), str(archive_digest))
            if archive_digest is not None else None
        ),
    )
    return publish_immutable(
        root, owned_ref(plan["transition_id"], "receipts", "json"), receipt
    )


def _effect_evidence_complete(
    plan: dict[str, Any], successor: str, successor_digest: str | None,
    archive: str,
) -> bool:
    return (
        successor == "current"
        and successor_digest is not None
        and (
            (not plan["archive_task"]["required"] and archive == "missing")
            or (plan["archive_task"]["required"] and archive == "current")
        )
    )


def _apply_from_intent(
    root: Path, plan: dict[str, Any], plan_binding: dict[str, str],
    intent_digest: str, prospective_payload: bytes | None,
) -> tuple[bool, bool, str]:
    canonical = canonical_observation(root)
    archive, archive_digest = archive_state(root, plan)
    successor, successor_digest = snapshot_state(
        root, plan, "successors", plan["after_task"]["sha256"]
    )
    canonical_after = matches(canonical, {"exists": True, **plan["after_task"]})
    if canonical_after:
        require(
            _effect_evidence_complete(plan, successor, successor_digest, archive),
            "task_transition_recovery_required",
            "canonical task changed but immutable successor/archive evidence is incomplete",
            next_action="recover_task_transition",
        )
        assert successor_digest is not None
        created, receipt_digest = _publish_effect_receipt(
            root, plan, plan_binding, intent_digest, successor_digest, archive_digest
        )
        return created, True, receipt_digest
    require(matches(canonical, plan["before_task"]),
            "task_transition_recovery_required",
            "intent exists but canonical task matches neither planned state",
            next_action="recover_task_transition")
    require(prospective_payload is not None
            and sha256_bytes(prospective_payload) == plan["after_task"]["sha256"],
            "task_transition_recovery_required",
            "intent exists but exact prospective bytes are unavailable",
            next_action="restore_prospective_task")
    _successor_created, successor_digest = publish_immutable(
        root, owned_ref(plan["transition_id"], "successors", "md"),
        prospective_payload,
    )
    if plan["archive_task"]["required"]:
        predecessor = file_bytes(root, "task.md", "canonical predecessor task")
        assert predecessor is not None
        _archive_created, archive_digest = publish_immutable(
            root, str(plan["archive_task"]["ref"]), predecessor
        )
    else:
        require(archive == "missing", "task_transition_recovery_required",
                "initial transition has an unexpected predecessor archive")
    replace_canonical_task(
        root, prospective_payload, plan["before_task"], plan["after_task"]["sha256"]
    )
    created, receipt_digest = _publish_effect_receipt(
        root, plan, plan_binding, intent_digest, successor_digest, archive_digest
    )
    return created, False, receipt_digest


def _settle_pre_intent_no_effect(
    root: Path, plan: dict[str, Any], plan_binding: dict[str, str],
    canonical: dict[str, Any], prospective: dict[str, Any],
) -> tuple[bool, str]:
    observation, observation_digest = snapshot_state(
        root, plan, "observations", None
    )
    observation_binding: dict[str, str] | None = None
    if observation == "current":
        assert observation_digest is not None
        canonical = {"exists": True, "sha256": observation_digest}
        observation_binding = binding(
            owned_ref(plan["transition_id"], "observations", "md"),
            observation_digest,
        )
    elif canonical["exists"]:
        current_payload = file_bytes(root, "task.md", "canonical task")
        assert current_payload is not None
        _created, observation_digest = publish_immutable(
            root, owned_ref(plan["transition_id"], "observations", "md"),
            current_payload,
        )
        observation_binding = binding(
            owned_ref(plan["transition_id"], "observations", "md"),
            observation_digest,
        )
    reasons: list[str] = []
    if not matches(canonical, plan["before_task"]):
        reasons.append("canonical_prestate_stale")
    if prospective["state"] == "missing":
        reasons.append("prospective_missing")
    elif prospective["state"] == "digest_mismatch":
        reasons.append("prospective_digest_mismatch")
    if not reasons and observation_binding is not None:
        reasons.append("interrupted_pre_intent_no_effect")
    require(bool(reasons), "invalid_owner_result",
            "a ready task transition cannot settle as no effect")
    receipt = no_effect_receipt(
        plan, plan_binding, canonical, prospective, reasons, observation_binding
    )
    return publish_immutable(
        root, owned_ref(plan["transition_id"], "receipts", "json"), receipt
    )


def _result(
    root: Path, plan: dict[str, Any], plan_ref: str,
    plan_file_sha256: str, *, replay: bool, recovered: bool,
    mutation_performed: bool,
) -> dict[str, Any]:
    verification = verify_task_transition_execution(root, plan_ref, phase="apply")
    require(verification["status"] in {"already_applied", "settled_no_effect"},
            "task_transition_recovery_required",
            "task transition did not reach one verified terminal state")
    return {
        "result_kind": "task_transition_apply_result",
        "schema_version": 1,
        "status": verification["status"],
        "apply_status": (
            "already_applied"
            if replay and verification["status"] == "already_applied"
            else "settled_no_effect"
            if verification["status"] == "settled_no_effect"
            else "applied"
        ),
        "effect_status": verification["effect_status"],
        "transition_id": plan["transition_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "execution_result_binding": {
            "ref": verification["receipt_ref"],
            "sha256": verification["receipt_file_sha256"],
        },
        "idempotent_replay": replay,
        "publication_recovered": recovered,
        "mutation_performed": mutation_performed,
    }


def _recover_pre_intent_observation(
    root: Path, plan: dict[str, Any], plan_binding: dict[str, str],
    prospective: dict[str, Any], archive: str, successor: str, observation: str,
) -> tuple[bool, str] | None:
    if (archive != "missing" or successor != "missing"
            or observation != "current"):
        return None
    return _settle_pre_intent_no_effect(
        root, plan, plan_binding, canonical_observation(root), prospective
    )


def apply_task_transition_plan(
    root: Path, path_value: str | Path,
) -> dict[str, Any]:
    """Apply, replay, or conservatively recover one exact task transition."""

    root = root.resolve()
    _path, initial_plan, initial_digest, initial_ref = load_task_transition_plan(
        root, path_value
    )
    transition_id = initial_plan["transition_id"]
    with transition_lock(root, transition_id):
        _path, plan, plan_file_sha256, plan_ref = load_task_transition_plan(
            root, initial_ref
        )
        require(plan == initial_plan and plan_file_sha256 == initial_digest,
                "invalid_owner_plan", "task transition plan changed while locking")
        plan_binding = binding(plan_ref, plan_file_sha256)
        observed = inspect_transition(root, plan, plan_binding, "apply")
        if observed["status"] in {"already_applied", "settled_no_effect"}:
            return _result(
                root, plan, plan_ref, plan_file_sha256, replay=True,
                recovered=False, mutation_performed=False,
            )
        require(observed["status"] != "conflict", "task_transition_conflict",
                "task transition artifacts or canonical effect are ambiguous",
                next_action="inspect_task_transition")
        prospective, payload = prospective_observation(root, plan)
        intent, _intent_value, intent_digest = intent_state(
            root, plan, plan_binding
        )
        archive, _archive_digest = archive_state(root, plan)
        successor, _successor_digest = snapshot_state(
            root, plan, "successors", plan["after_task"]["sha256"]
        )
        observation, _observation_digest = snapshot_state(
            root, plan, "observations", None
        )
        if intent == "current" and intent_digest is not None:
            _receipt_created, recovered, _receipt_digest = _apply_from_intent(
                root, plan, plan_binding, intent_digest, payload
            )
            return _result(
                root, plan, plan_ref, plan_file_sha256, replay=False,
                recovered=recovered, mutation_performed=True,
            )
        if intent == "missing":
            recovered_no_effect = _recover_pre_intent_observation(
                root, plan, plan_binding, prospective, archive, successor,
                observation,
            )
            if recovered_no_effect is not None:
                created, _receipt_digest = recovered_no_effect
                return _result(
                    root, plan, plan_ref, plan_file_sha256, replay=False,
                    recovered=True, mutation_performed=created,
                )
        require(intent == "missing" and archive == "missing"
                and successor == "missing" and observation == "missing",
                "task_transition_recovery_required",
                "partial task transition artifacts require reconciliation",
                next_action="recover_task_transition")
        canonical = canonical_observation(root)
        canonical_after = matches(
            canonical, {"exists": True, **plan["after_task"]}
        )
        require(not canonical_after, "task_transition_conflict",
                "planned after bytes exist without a plan-bound intent",
                next_action="inspect_task_transition")
        if (not matches(canonical, plan["before_task"])
                or prospective["state"] != "exact"):
            created, _receipt_digest = _settle_pre_intent_no_effect(
                root, plan, plan_binding, canonical, prospective
            )
            return _result(
                root, plan, plan_ref, plan_file_sha256, replay=False,
                recovered=False, mutation_performed=created,
            )
        intent_body = expected_intent(plan, plan_binding)
        _intent_created, intent_digest = publish_immutable(
            root, owned_ref(transition_id, "intents", "json"), intent_body
        )
        _receipt_created, recovered, _receipt_digest = _apply_from_intent(
            root, plan, plan_binding, intent_digest, payload
        )
        return _result(
            root, plan, plan_ref, plan_file_sha256, replay=False,
            recovered=recovered, mutation_performed=True,
        )


def verify_task_transition_receipt(
    root: Path, plan_ref: str, receipt_binding: dict[str, str], effect_status: str,
) -> dict[str, Any]:
    """Reopen the exact receipt and immutable historical task evidence."""

    verification = verify_task_transition_execution(root, plan_ref, phase="apply")
    expected_ref = owned_ref(
        str(verification["transition_id"]), "receipts", "json"
    )
    require(receipt_binding.get("ref") == expected_ref, "invalid_owner_result",
            "owner artifact is not the canonical task transition receipt")
    expected_status = (
        "already_applied" if effect_status == "confirmed_effect"
        else "settled_no_effect"
    )
    require(verification["status"] == expected_status,
            "stale_owner_result", "task transition receipt is not terminal")
    require(verification["effect_status"] == effect_status,
            "invalid_owner_result", "task transition receipt effect mismatch")
    require(receipt_binding == {
        "ref": verification["receipt_ref"],
        "sha256": verification["receipt_file_sha256"],
    }, "invalid_owner_result", "owner artifact is not the exact public receipt")
    return verification


__all__ = [
    "apply_task_transition_plan",
    "verify_task_transition_execution",
    "verify_task_transition_receipt",
]
