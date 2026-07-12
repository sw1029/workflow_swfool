"""Phase-aware, body-free recovery ownership observations and checks."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from task_state_migration_verifier_core import (
    ANCHOR_KIND,
    MIGRATION_EVENT_FIELD,
    _canonical_json,
    _is_int,
    _is_sha256,
    _load_json,
    _physical_lines,
    _regular_file,
    _require,
    _root,
    _sha256,
    _sha256_path,
    _transaction_ref,
    _workspace_ref,
)


ZERO_SHA256 = "0" * 64
OBSERVATION_FIELDS = (
    "schema_version", "kind", "evaluation_status", "status", "transaction_id",
    "journal_state", "journal_updated_at", "journal_sha256", "journal_base_sha256",
    "journal_owned_append_byte_length",
    "journal_owned_append_sha256", "plan_sha256", "index_sha256",
    "index_byte_length", "source_prefix_intact", "sealed_boundary_present",
    "anchor_present", "anchor_sha256", "receipt_present", "receipt_sha256",
    "receipt_recovery_status", "receipt_committed_at",
    "completion_marker_present", "completion_marker_sha256",
    "rendered_snapshot_present", "rendered_snapshot_sha256",
    "live_projection_present", "live_projection_sha256", "publication_state",
    "forward_recovery_required", "exact_replay_noop_eligible",
    "recovery_owned_write_set_sha256", "recovery_owned_write_path_count",
    "immutable_transaction_sha256", "immutable_transaction_path_count",
    "outside_owned_tree_sha256", "protected_anchor_aggregate_sha256", "read_only",
)

RECOVERY_JOURNAL_STATES = {
    "prepared", "partial_suffix", "sealed", "receipt_written",
    "receipt_anchored", "committed_render_pending", "committed",
}
RECEIPT_RECOVERY_STATUSES = {"not_required", "forward_completed"}


def _observation_sha256(value: dict[str, Any]) -> str:
    return _sha256(_canonical_json({field: value.get(field) for field in OBSERVATION_FIELDS}))


def _boundary_observation_sha256(value: dict[str, Any]) -> str:
    return _observation_sha256(value)


def _owned_write_paths(
    root: Path,
    plan: dict[str, Any],
    *,
    journal_state: str | None = None,
    publication_state: str | None = None,
) -> list[str]:
    values = {".task/index.lock"}
    if publication_state == "committed_render_pending":
        values.add(".task/index.md")
    elif journal_state in {"receipt_anchored", "committed_render_pending", "committed"}:
        values.update({
            ".task/index.md", plan["journal_ref"], plan["completion_marker_ref"],
        })
    elif journal_state == "receipt_written":
        values.update({
            ".task/index.jsonl", ".task/index.md", plan["journal_ref"],
            plan["receipt_ref"], plan["completion_marker_ref"],
        })
    else:
        values.update({
            ".task/index.jsonl", ".task/index.md", plan["journal_ref"],
            plan["receipt_ref"], plan["completion_marker_ref"],
            plan["render_snapshot_ref"],
        })
    for value in values:
        _workspace_ref(root, value, "recovery-owned path", must_exist=False)
    return sorted(values)


def _immutable_paths(plan: dict[str, Any]) -> list[str]:
    return sorted({
        plan["source_snapshot_ref"], plan["plan_snapshot_ref"],
        plan["mapping_manifest"]["snapshot_ref"], plan["resolution_manifest"]["ref"],
        plan["correction_suffix"]["ref"], plan["prepare_journal_ref"],
    })


def _owned_write_set_sha(paths: list[str]) -> str:
    return _sha256(_canonical_json(paths))


def _path_fingerprint(root: Path, relative: str) -> dict[str, Any]:
    path = _workspace_ref(root, relative, "recovery fingerprint path")
    return {
        "path_sha256": _sha256(relative.encode()),
        "size": path.stat().st_size,
        "sha256": _sha256_path(path),
    }


def _immutable_transaction_sha(root: Path, plan: dict[str, Any]) -> tuple[str, int]:
    paths = _immutable_paths(plan)
    return _sha256(_canonical_json([_path_fingerprint(root, path) for path in paths])), len(paths)


def _optional_sha(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, ZERO_SHA256
    _regular_file(path, "optional recovery surface")
    return True, _sha256_path(path)


def _optional_receipt(
    path: Path, transaction_id: str,
) -> tuple[bool, str, str, str]:
    if not path.exists():
        return False, ZERO_SHA256, "absent", ""
    receipt, payload = _load_json(path, "optional recovery receipt")
    _require(payload == _canonical_json(receipt), "recovery receipt is not canonical JSON")
    recovery_status = receipt.get("recovery_status")
    committed_at = receipt.get("transaction_committed_at")
    _require(
        _is_int(receipt.get("schema_version"))
        and receipt["schema_version"] == 2
        and receipt.get("kind") == "task_state_index_migration"
        and receipt.get("transaction_id") == transaction_id
        and receipt.get("status") == "committed"
        and recovery_status in RECEIPT_RECOVERY_STATUSES
        and isinstance(committed_at, str)
        and bool(committed_at)
        and receipt.get("transaction_started_at") == committed_at,
        "recovery receipt phase identity is invalid",
    )
    return True, _sha256(payload), recovery_status, committed_at


def _outside_owned_tree_sha(root: Path, owned: set[str]) -> str:
    inventory: list[dict[str, Any]] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        for item in sorted(directory.iterdir(), key=lambda value: value.name):
            relative = item.relative_to(root).as_posix()
            if item.is_symlink():
                inventory.append({"path_sha256": _sha256(relative.encode()), "kind": "symlink", "target_sha256": _sha256(str(item.readlink()).encode())})
            elif item.is_dir():
                inventory.append({"path_sha256": _sha256(relative.encode()), "kind": "directory"})
                pending.append(item)
            elif item.is_file() and relative not in owned:
                inventory.append({"path_sha256": _sha256(relative.encode()), "kind": "file", "size": item.stat().st_size, "sha256": _sha256_path(item)})
            elif not item.is_file():
                inventory.append({"path_sha256": _sha256(relative.encode()), "kind": "other"})
    inventory.sort(key=lambda entry: entry["path_sha256"])
    return _sha256(_canonical_json(inventory))


def _protected_anchor_sha(root: Path, plan: dict[str, Any]) -> str:
    values = []
    for label in ("current_task", "current_pack"):
        anchor = plan["anchors"][label]
        path = _workspace_ref(root, anchor["path"], f"protected {label} anchor")
        values.append({"label": label, "path_sha256": _sha256(anchor["path"].encode()), "content_sha256": _sha256_path(path)})
    return _sha256(_canonical_json(values))


def _load_plan(root: Path, transaction_id: str) -> tuple[dict[str, Any], bytes]:
    _require(re.fullmatch(r"tsm-[0-9a-f]{24}", transaction_id) is not None, "transaction identity is invalid")
    path = _transaction_ref(root, f".task/migrations/{transaction_id}/plan.json", transaction_id, "plan")
    plan, payload = _load_json(path, "plan")
    _require(payload == _canonical_json(plan) and plan.get("migration_id") == transaction_id, "recovery plan identity or encoding is invalid")
    for field in (
        "source_snapshot_ref", "plan_snapshot_ref", "journal_ref", "receipt_ref",
        "completion_marker_ref", "render_snapshot_ref", "prepare_journal_ref",
    ):
        _require(isinstance(plan.get(field), str) and plan[field], f"recovery plan lacks {field}")
    for field, nested in (("mapping_manifest", "snapshot_ref"), ("resolution_manifest", "ref"), ("correction_suffix", "ref")):
        _require(isinstance(plan.get(field), dict) and isinstance(plan[field].get(nested), str), f"recovery plan lacks {field}.{nested}")
    return plan, payload


def _planned_boundary(root: Path, plan: dict[str, Any]) -> bytes:
    prefix = _workspace_ref(root, plan["source_snapshot_ref"], "recovery source snapshot").read_bytes()
    correction = _workspace_ref(root, plan["correction_suffix"]["ref"], "recovery correction suffix").read_bytes()
    seal = _canonical_json(plan["seal"]["event"])
    boundary = prefix + correction + seal
    _require(
        len(boundary) == plan["expected_commit_boundary_byte_length"]
        and _sha256(boundary) == plan["expected_after_index_sha256"],
        "recovery plan boundary is not independently reproducible",
    )
    return boundary


def _journal_base(
    plan: dict[str, Any], plan_sha: str, *, committed: bool = False
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": (
            "task_state_index_migration_journal"
            if committed else "task_state_index_migration_journal_prepare"
        ),
        "transaction_id": plan["migration_id"],
        "prefix_sha256": plan["source_prefix"]["sha256"],
        "prefix_byte_length": plan["source_prefix"]["byte_length"],
        "expected_boundary_sha256": plan["expected_after_index_sha256"],
        "expected_boundary_byte_length": plan["expected_commit_boundary_byte_length"],
        "plan_ref": plan["plan_snapshot_ref"],
        "plan_sha256": plan_sha,
    }


def _journal_base_sha(
    plan: dict[str, Any], plan_sha: str, *, committed: bool = False
) -> str:
    return _sha256(_canonical_json(_journal_base(plan, plan_sha, committed=committed)))


def _pending_journal(
    plan: dict[str, Any], plan_sha: str, state: str, updated_at: str,
    append_length: int, append_sha: str, receipt_sha: str,
) -> dict[str, Any]:
    value = {
        **_journal_base(plan, plan_sha),
        "state": state,
        "journal_updated_at": updated_at,
    }
    if state == "partial_suffix":
        value.update(appended_byte_length=append_length, appended_sha256=append_sha)
    if state in {"receipt_written", "receipt_anchored", "committed_render_pending"}:
        value["receipt_sha256"] = receipt_sha
    return value


def _anchor_observation(index: bytes, boundary_length: int, transaction_id: str) -> tuple[bool, str]:
    if len(index) <= boundary_length:
        return False, ZERO_SHA256
    lines = _physical_lines(index[boundary_length:])
    if not lines:
        return False, ZERO_SHA256
    raw = lines[0]
    try:
        event = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, ZERO_SHA256
    fields = event.get("fields") if isinstance(event, dict) and isinstance(event.get("fields"), dict) else {}
    present = fields.get(MIGRATION_EVENT_FIELD) == ANCHOR_KIND and fields.get("migration_id") == transaction_id
    return present, _sha256(raw) if present else ZERO_SHA256


def inspect_transaction_boundary(
    root_raw: str | Path, transaction_id: str, *,
    expected_mapping_raw: str | Path | None = None,
    expected_recovery_status: str | None = None,
    recovery_observation: dict[str, Any] | None = None,
    expected_recovery_observation_sha256: str | None = None,
) -> dict[str, Any]:
    """Capture the exact body-free state before caller-owned forward recovery."""
    del expected_mapping_raw, expected_recovery_status, recovery_observation, expected_recovery_observation_sha256
    root = _root(root_raw)
    plan, plan_payload = _load_plan(root, transaction_id)
    journal_path = _transaction_ref(root, plan["journal_ref"], transaction_id, "journal")
    journal, journal_payload = _load_json(journal_path, "journal")
    index = _regular_file(root / ".task/index.jsonl", "current task-state index").read_bytes()
    plan_sha = _sha256(plan_payload)
    journal_state = journal.get("state")
    _require(journal_state in RECOVERY_JOURNAL_STATES, "recovery journal state is unsupported")
    committed_journal = journal_state == "committed"
    journal_base = _journal_base(plan, plan_sha, committed=committed_journal)
    _require(all(journal.get(key) == value for key, value in journal_base.items()), "recovery journal base differs from the immutable plan")
    boundary = _planned_boundary(root, plan)
    prefix_length = plan["source_prefix"]["byte_length"]
    boundary_length = len(boundary)
    prefix_intact = len(index) >= prefix_length and index[:prefix_length] == boundary[:prefix_length]
    sealed = len(index) >= boundary_length and index[:boundary_length] == boundary
    anchor_present, anchor_sha = _anchor_observation(index, boundary_length, transaction_id)
    receipt_path = _transaction_ref(
        root, plan["receipt_ref"], transaction_id, "optional recovery receipt",
        must_exist=False,
    )
    receipt_present, receipt_sha, receipt_status, receipt_committed_at = (
        _optional_receipt(receipt_path, transaction_id)
    )
    marker_present, marker_sha = _optional_sha(root / plan["completion_marker_ref"])
    render_present, render_sha = _optional_sha(root / plan["render_snapshot_ref"])
    live_present, live_sha = _optional_sha(root / ".task/index.md")
    committed_graph = (
        committed_journal and sealed and anchor_present and receipt_present
        and marker_present and render_present
    )
    live_projection_exact = live_present and live_sha == render_sha
    committed = committed_graph and live_projection_exact
    if committed:
        publication_state = "committed"
    elif committed_graph:
        publication_state = "committed_render_pending"
    elif sealed:
        publication_state = "post_seal_incomplete"
    elif prefix_intact:
        publication_state = "pre_seal_incomplete"
    else:
        publication_state = "conflicting"
    _require(publication_state != "conflicting", "current ledger matches neither source prefix nor sealed boundary")
    append_length = journal.get("appended_byte_length", 0)
    append_sha = journal.get("appended_sha256", _sha256(b""))
    _require(_is_int(append_length) and append_length >= 0 and _is_sha256(append_sha), "journal-owned append contract is invalid")
    if journal_state == "partial_suffix":
        _require(0 < append_length < boundary_length - prefix_length, "partial journal append length is invalid")
        tail = index[prefix_length:]
        _require(len(tail) == append_length and _sha256(tail) == append_sha and index == boundary[:len(index)], "partial journal does not own the exact ledger tail")
    elif journal_state == "prepared":
        _require(index == boundary[:prefix_length], "prepared recovery state contains a foreign ledger tail")
    elif journal_state in {"sealed", "receipt_written"}:
        _require(index == boundary, "pre-anchor recovery state contains a foreign ledger tail")
    journal_updated_at = journal.get("journal_updated_at")
    _require(isinstance(journal_updated_at, str) and journal_updated_at, "recovery journal update time is missing")
    if not committed_journal:
        expected_pending = _pending_journal(
            plan, plan_sha, str(journal.get("state")), journal_updated_at,
            append_length, append_sha, receipt_sha,
        )
        _require(journal_payload == _canonical_json(expected_pending), "pending recovery journal is not canonical for its phase")
    immutable_sha, immutable_count = _immutable_transaction_sha(root, plan)
    owned = _owned_write_paths(
        root, plan,
        journal_state=journal_state,
        publication_state=publication_state,
    )
    result = {
        "schema_version": 1, "kind": "task_state_migration_recovery_boundary_observation",
        "evaluation_status": "observed", "status": "observed", "transaction_id": transaction_id,
        "journal_state": journal_state, "journal_updated_at": journal_updated_at,
        "journal_sha256": _sha256(journal_payload),
        "journal_base_sha256": _journal_base_sha(plan, plan_sha, committed=committed_journal),
        "journal_owned_append_byte_length": append_length, "journal_owned_append_sha256": append_sha,
        "plan_sha256": plan_sha, "index_sha256": _sha256(index), "index_byte_length": len(index),
        "source_prefix_intact": prefix_intact, "sealed_boundary_present": sealed,
        "anchor_present": anchor_present, "anchor_sha256": anchor_sha,
        "receipt_present": receipt_present, "receipt_sha256": receipt_sha,
        "receipt_recovery_status": receipt_status,
        "receipt_committed_at": receipt_committed_at,
        "completion_marker_present": marker_present, "completion_marker_sha256": marker_sha,
        "rendered_snapshot_present": render_present, "rendered_snapshot_sha256": render_sha,
        "live_projection_present": live_present, "live_projection_sha256": live_sha,
        "publication_state": publication_state, "forward_recovery_required": not committed,
        "exact_replay_noop_eligible": committed,
        "recovery_owned_write_set_sha256": _owned_write_set_sha(owned),
        "recovery_owned_write_path_count": len(owned),
        "immutable_transaction_sha256": immutable_sha, "immutable_transaction_path_count": immutable_count,
        "outside_owned_tree_sha256": _outside_owned_tree_sha(root, set(owned)),
        "protected_anchor_aggregate_sha256": _protected_anchor_sha(root, plan), "read_only": True,
    }
    result["observation_sha256"] = _observation_sha256(result)
    return result


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
