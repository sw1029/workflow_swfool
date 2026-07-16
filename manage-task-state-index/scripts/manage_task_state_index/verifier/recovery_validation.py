"""Validate caller-preserved recovery observations against committed output."""

from __future__ import annotations

from typing import Any

from .core import (
    _canonical_json,
    _is_int,
    _is_sha256,
    _require,
    _sha256,
    _sha256_path,
    _workspace_ref,
)
from .recovery_contracts import (
    OBSERVATION_FIELDS,
    RECEIPT_RECOVERY_STATUSES,
    RECOVERY_JOURNAL_STATES,
    ZERO_SHA256,
)
from .recovery_documents import _journal_base_sha, _pending_journal
from .recovery_fingerprints import (
    _immutable_transaction_sha,
    _observation_sha256,
    _outside_owned_tree_sha,
    _owned_write_paths,
    _owned_write_set_sha,
    _protected_anchor_sha,
)

def _require_start_state(
    observation: dict[str, Any],
    rebuilt: dict[str, Any],
    publication: dict[str, Any],
    current: dict[str, Any],
    phase_receipt_sha: str | None,
) -> None:
    plan = rebuilt["plan"]
    boundary = b"".join(rebuilt["boundary_parts"])
    state = observation["journal_state"]
    prefix_length = len(rebuilt["prefix"])
    length = observation["index_byte_length"]
    _require(state in RECOVERY_JOURNAL_STATES, "recovery observation journal state is unsupported")
    _require(
        isinstance(observation["journal_updated_at"], str)
        and bool(observation["journal_updated_at"]),
        "recovery observation journal update time is invalid",
    )
    _require(
        observation["journal_base_sha256"]
        == _journal_base_sha(
            plan,
            publication.get("plan_sha", "") or plan.get("plan_sha256", ""),
            committed=state == "committed",
        ),
        "recovery observation journal base mismatch",
    )
    if state == "committed":
        expected_journal_sha = publication["journal_sha"]
    else:
        expected_journal_sha = _sha256(_canonical_json(_pending_journal(
            plan, publication["plan_sha"], state, observation["journal_updated_at"],
            observation["journal_owned_append_byte_length"],
            observation["journal_owned_append_sha256"], observation["receipt_sha256"],
        )))
    _require(observation["journal_sha256"] == expected_journal_sha, "recovery observation journal hash is not phase-bound")
    if state == "partial_suffix":
        _require(observation["journal_owned_append_byte_length"] > 0, "partial recovery lacks an owned append")
    else:
        _require(
            observation["journal_owned_append_byte_length"] == 0
            and observation["journal_owned_append_sha256"] == _sha256(b""),
            "non-partial recovery observation carries an append claim",
        )
    if state == "prepared":
        expected = rebuilt["prefix"]
    elif state == "partial_suffix":
        appended = observation["journal_owned_append_byte_length"]
        _require(0 < appended < len(boundary) - prefix_length, "recovery partial length is invalid")
        expected = boundary[:prefix_length + appended]
        _require(observation["journal_owned_append_sha256"] == _sha256(expected[prefix_length:]), "recovery partial tail is not journal-owned")
    elif state in {"sealed", "receipt_written"}:
        expected = boundary
    else:
        _require(current["post_anchor_event_count"] == 0, "recovered ledger has a foreign post-anchor tail")
        _require(observation["index_sha256"] == current["ledger_sha256"], "anchored recovery start ledger differs from final owned ledger")
        expected = b""
    if expected:
        _require(length == len(expected) and observation["index_sha256"] == _sha256(expected), "recovery start ledger is not an exact phase-owned state")
    expected_presence = {
        "prepared": (False, False, False, False),
        "partial_suffix": (False, False, False, False),
        "sealed": (False, False, False, False),
        "receipt_written": (False, True, False, True),
        "receipt_anchored": (True, True, False, True),
        "committed_render_pending": (True, True, False, True),
        "committed": (
            True, True,
            observation["publication_state"] == "committed_render_pending",
            True,
        ),
    }[state]
    observed_presence = (
        observation["anchor_present"], observation["receipt_present"],
        observation["completion_marker_present"], observation["rendered_snapshot_present"],
    )
    _require(observed_presence == expected_presence, "recovery observation phase surfaces are inconsistent")
    sealed_expected = state not in {"prepared", "partial_suffix"}
    expected_publication_state = (
        "pre_seal_incomplete"
        if not sealed_expected
        else "committed_render_pending"
        if state == "committed" and observation["completion_marker_present"]
        else "post_seal_incomplete"
    )
    _require(
        observation["sealed_boundary_present"] is sealed_expected
        and observation["publication_state"] == expected_publication_state,
        "recovery observation publication phase is inconsistent",
    )
    if expected_publication_state == "committed_render_pending":
        _require(
            not observation["live_projection_present"]
            or observation["live_projection_sha256"]
            != observation["rendered_snapshot_sha256"],
            "render-pending observation already has the exact live projection",
        )
    expected_anchor_sha = current["anchor_sha256"] if observation["anchor_present"] else ZERO_SHA256
    _require(observation["anchor_sha256"] == expected_anchor_sha, "recovery observation anchor hash mismatch")
    for present_field, sha_field, final_sha in (
        ("completion_marker_present", "completion_marker_sha256", publication["marker_sha"]),
        ("rendered_snapshot_present", "rendered_snapshot_sha256", publication["render_sha"]),
    ):
        expected_sha = final_sha if observation[present_field] else ZERO_SHA256
        _require(observation[sha_field] == expected_sha, f"recovery observation {sha_field} mismatch")
    if observation["receipt_present"]:
        _require(
            _is_sha256(phase_receipt_sha)
            and observation["receipt_sha256"] == phase_receipt_sha,
            "recovery observation receipt is not independently reconstructable",
        )
    else:
        _require(
            phase_receipt_sha is None and observation["receipt_sha256"] == ZERO_SHA256,
            "absent recovery receipt carries an identity",
        )

def verify_recovery_observation(
    bundle: dict[str, Any], rebuilt: dict[str, Any], publication: dict[str, Any],
    current: dict[str, Any], expected_recovery_status: str,
    observation: dict[str, Any] | None, expected_sha: str | None,
    phase_receipt_sha: str | None = None,
) -> dict[str, Any]:
    root, plan = bundle["root"], rebuilt["plan"]
    if expected_recovery_status == "not_required":
        _require(observation is None and expected_sha is None, "recovery evidence supplied for a non-recovered migration")
        _require(
            publication["recovery_status"] == "not_required",
            "non-recovery verification requires a not-required publication graph",
        )
        owned = _owned_write_paths(root, plan)
        return {"owned": owned, "outside_sha": _sha256(_canonical_json({"status": "not_applicable_no_recovery"})), "observation_sha": None}
    _require(expected_recovery_status == "forward_completed", "caller recovery expectation is invalid")
    _require(isinstance(observation, dict) and _is_sha256(expected_sha), "forward recovery requires an externally hashed observation")
    _require(set(observation) == set(OBSERVATION_FIELDS) | {"observation_sha256"}, "recovery observation has unknown or missing fields")
    _require(observation["observation_sha256"] == _observation_sha256(observation) == expected_sha, "recovery observation hash mismatch")
    for field in (
        "journal_sha256", "journal_base_sha256", "journal_owned_append_sha256",
        "plan_sha256", "index_sha256", "anchor_sha256", "receipt_sha256",
        "completion_marker_sha256", "rendered_snapshot_sha256", "live_projection_sha256",
        "recovery_owned_write_set_sha256", "immutable_transaction_sha256",
        "outside_owned_tree_sha256", "protected_anchor_aggregate_sha256",
    ):
        _require(_is_sha256(observation[field]), f"recovery observation {field} is invalid")
    for field in (
        "index_byte_length", "journal_owned_append_byte_length",
        "recovery_owned_write_path_count", "immutable_transaction_path_count",
    ):
        _require(_is_int(observation[field]) and observation[field] >= 0, f"recovery observation {field} is invalid")
    for field in (
        "source_prefix_intact", "sealed_boundary_present", "anchor_present",
        "receipt_present", "completion_marker_present", "rendered_snapshot_present",
        "live_projection_present", "forward_recovery_required",
        "exact_replay_noop_eligible", "read_only",
    ):
        _require(type(observation[field]) is bool, f"recovery observation {field} is invalid")
    scalar_contract = (
        _is_int(observation["schema_version"])
        and observation["schema_version"] == 1
        and observation["kind"] == "task_state_migration_recovery_boundary_observation"
        and observation["evaluation_status"] == observation["status"] == "observed"
        and observation["transaction_id"] == plan["migration_id"]
        and observation["source_prefix_intact"] is True
        and observation["publication_state"] in {
            "pre_seal_incomplete", "post_seal_incomplete",
            "committed_render_pending",
        }
        and observation["forward_recovery_required"] is True
        and observation["exact_replay_noop_eligible"] is False
        and observation["read_only"] is True
    )
    _require(scalar_contract, "recovery observation scalar contract is invalid")
    receipt_contract = (
        observation["receipt_recovery_status"] in RECEIPT_RECOVERY_STATUSES
        and isinstance(observation["receipt_committed_at"], str)
        and bool(observation["receipt_committed_at"])
        if observation["receipt_present"]
        else observation["receipt_recovery_status"] == "absent"
        and observation["receipt_committed_at"] == ""
    )
    _require(receipt_contract, "recovery observation receipt scalar contract is invalid")
    _require(
        observation["live_projection_present"]
        or observation["live_projection_sha256"] == ZERO_SHA256,
        "absent live projection carries a hash claim",
    )
    owned = _owned_write_paths(
        root, plan,
        journal_state=observation["journal_state"],
        publication_state=observation["publication_state"],
    )
    immutable_sha, immutable_count = _immutable_transaction_sha(root, plan)
    outside_sha = _outside_owned_tree_sha(root, set(owned))
    _require(
        observation["plan_sha256"] == bundle["plan_sha256"]
        and observation["recovery_owned_write_set_sha256"] == _owned_write_set_sha(owned)
        and observation["recovery_owned_write_path_count"] == len(owned)
        and observation["immutable_transaction_sha256"] == immutable_sha
        and observation["immutable_transaction_path_count"] == immutable_count
        and observation["outside_owned_tree_sha256"] == outside_sha
        and observation["protected_anchor_aggregate_sha256"] == _protected_anchor_sha(root, plan),
        "recovery observation ownership or immutable boundary mismatch",
    )
    _require_start_state(
        observation, rebuilt, publication, current, phase_receipt_sha,
    )
    if observation["journal_state"] in {"prepared", "partial_suffix", "sealed"}:
        _require(
            publication["recovery_status"] == "forward_completed",
            "early recovery did not publish a forward-completed graph",
        )
    elif observation["journal_state"] == "receipt_written":
        _require(
            publication["recovery_status"] == "forward_completed",
            "receipt-written recovery did not publish the exact replacement receipt",
        )
    else:
        _require(
            observation["receipt_sha256"] == publication["receipt_sha"]
            and observation["receipt_recovery_status"]
            == publication["recovery_status"],
            "anchored recovery changed the existing receipt identity or status",
        )
    _require(current["post_anchor_event_count"] == 0, "forward recovery produced a foreign ledger tail")
    live_path = _workspace_ref(root, ".task/index.md", "recovered live projection")
    _require(_sha256_path(live_path) == publication["render_sha"], "forward recovery live projection differs from the sealed rendered snapshot")
    return {"owned": owned, "outside_sha": outside_sha, "observation_sha": expected_sha}
