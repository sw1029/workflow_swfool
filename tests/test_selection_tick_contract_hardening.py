from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from orchestrate_task_cycle.selection_tick import build_selection_tick
from orchestrate_task_cycle.selection_tick_contract import (
    canonical_bytes,
    validate_selection_tick_v2,
)
from orchestrate_task_cycle.selection_tick_publication_contract import (
    validate_selection_publication,
)
from orchestrate_task_cycle.selection_tick_policy import selection_policy
from orchestrate_task_cycle.selection_tick_premise import VERIFIED_PREMISE_CONTRACT


def _repo(root: Path) -> Path:
    (root / ".agent_goal").mkdir(parents=True, exist_ok=True)
    (root / "task.md").write_text("# Task\n", encoding="utf-8")
    (root / ".agent_goal/final_goal.md").write_text("# Goal\n", encoding="utf-8")
    return root


def _reseal(packet: dict[str, object]) -> None:
    rows = packet["watch_entries"]
    assert isinstance(rows, list)
    packet["observed_input_manifest_sha256"] = hashlib.sha256(
        canonical_bytes(rows)
    ).hexdigest()
    body = {key: value for key, value in packet.items() if key != "packet_id"}
    packet["packet_id"] = (
        "selection-tick-" + hashlib.sha256(canonical_bytes(body)).hexdigest()[:32]
    )


def test_exact_subject_cannot_bypass_exact_premise_kind(tmp_path: Path) -> None:
    packet = build_selection_tick(_repo(tmp_path))
    packet["watch_entries"][0]["evidence_class"] = "exact_subject"

    with pytest.raises(ValueError, match="requires exact-premise kind"):
        validate_selection_tick_v2(packet)


def test_new_baseline_defaults_verified_while_raw_requires_explicit_compat(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    baseline = build_selection_tick(root)
    assert baseline["premise_input_contract"] == VERIFIED_PREMISE_CONTRACT

    raw = build_selection_tick(root, premise_contract="raw_exact_file_v1")
    assert raw["premise_input_contract"] == "raw_exact_file_v1"
    assert build_selection_tick(root, previous=raw)["premise_input_contract"] == (
        "raw_exact_file_v1"
    )


def test_authority_cannot_bypass_effective_authority_kind(tmp_path: Path) -> None:
    packet = build_selection_tick(_repo(tmp_path))
    packet["watch_entries"][0]["evidence_class"] = "authority"

    with pytest.raises(ValueError, match="requires effective-authority kind"):
        validate_selection_tick_v2(packet)


def test_raw_exact_input_is_compatibility_only_and_cannot_wake(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    premise = root / "premise.json"
    premise.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot open selection re-entry"):
        build_selection_tick(
            root,
            premise_paths=[premise.name],
            premise_ids=["premise-A"],
            premise_contract="raw_exact_file_v1",
        )

    historical = build_selection_tick(root, premise_contract="raw_exact_file_v1")
    historical["watch_entries"].append(
        {
            "watch_id": "watch-" + "f" * 24,
            "exists": True,
            "kind": "exact_premise",
            "evidence_class": "exact_subject",
            "premise_id": "premise-historical",
            "path_redacted": True,
            "sha256": "a" * 64,
            "size_bytes": 2,
        }
    )
    historical["watch_entries"].sort(
        key=lambda row: (str(row["kind"]), str(row["watch_id"]))
    )
    _reseal(historical)
    assert validate_selection_tick_v2(historical) == historical


@pytest.mark.parametrize("evidence_class", ["exact_subject", "authority"])
def test_sticky_evidence_cannot_be_removed(tmp_path: Path, evidence_class: str) -> None:
    packet = build_selection_tick(_repo(tmp_path))
    packet["changed_watch_entries"] = [
        {
            "watch_id": "watch-" + "f" * 24,
            "evidence_class": evidence_class,
            "change_kind": "removed",
        }
    ]

    with pytest.raises(ValueError, match="cannot remove sticky evidence"):
        validate_selection_tick_v2(packet)


@pytest.mark.parametrize("value", [7, "unsupported_class"])
@pytest.mark.parametrize("surface", ["watch", "change"])
def test_evidence_classes_require_supported_string_values(
    tmp_path: Path, value: object, surface: str
) -> None:
    packet = build_selection_tick(_repo(tmp_path))
    if surface == "watch":
        packet["watch_entries"][0]["evidence_class"] = value
    else:
        packet["changed_watch_entries"] = [
            {
                "watch_id": "watch-" + "f" * 24,
                "evidence_class": value,
                "change_kind": "added",
            }
        ]

    with pytest.raises(ValueError, match="evidence_class|row is invalid"):
        validate_selection_tick_v2(packet)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("premise_input_contract", True, "premise contract"),
        ("previous_input_manifest_sha256", 7, "previous manifest"),
        ("minimum_material_delta", True, "wake policy"),
        ("reason", True, "status and selection_required"),
    ],
)
def test_closed_scalar_fields_do_not_coerce_non_strings(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    packet = build_selection_tick(_repo(tmp_path))
    packet[field] = value

    with pytest.raises(ValueError, match=message):
        validate_selection_tick_v2(packet)


def test_programmatic_api_rejects_non_string_minimum_delta(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a string"):
        build_selection_tick(
            _repo(tmp_path),
            minimum_material_delta=True,  # type: ignore[arg-type]
        )


def test_programmatic_api_rejects_non_string_policy_and_premise_inputs(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    with pytest.raises(ValueError, match="must contain strings"):
        build_selection_tick(root, wake_predicates=[True])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="must contain strings"):
        build_selection_tick(
            root,
            watched_evidence_classes=[True],  # type: ignore[list-item]
        )
    with pytest.raises(ValueError, match="paths and IDs must be strings"):
        build_selection_tick(
            root,
            premise_paths=[True],  # type: ignore[list-item]
            premise_ids=["premise-A"],
        )
    with pytest.raises(ValueError, match="contract must be a string"):
        build_selection_tick(root, premise_contract=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="manifest must be a string"):
        selection_policy(
            {"observed_input_manifest_sha256": True},
            (),
            (),
            "one-watched-class-digest-change",
        )


def test_watch_and_authority_scope_ids_require_actual_strings(tmp_path: Path) -> None:
    packet = build_selection_tick(_repo(tmp_path))
    packet["watch_entries"][0]["watch_id"] = 7
    with pytest.raises(ValueError, match="watch IDs"):
        validate_selection_tick_v2(packet)

    packet = build_selection_tick(_repo(tmp_path))
    row = packet["watch_entries"][0]
    row["kind"] = "effective_authority"
    row["evidence_class"] = "authority"
    row["authority_scope_id"] = 7
    with pytest.raises(ValueError, match="authority scope ID"):
        validate_selection_tick_v2(packet)


def test_exact_delta_requires_explicit_premise_supply(tmp_path: Path) -> None:
    packet = build_selection_tick(_repo(tmp_path), premise_contract="raw_exact_file_v1")
    exact_row = {
        "watch_id": "watch-" + "f" * 24,
        "exists": True,
        "kind": "exact_premise",
        "evidence_class": "exact_subject",
        "premise_id": "premise-historical",
        "path_redacted": True,
        "sha256": "a" * 64,
        "size_bytes": 2,
    }
    change = {
        "watch_id": exact_row["watch_id"],
        "evidence_class": "exact_subject",
        "change_kind": "added",
    }
    packet["watch_entries"].append(exact_row)
    packet["watch_entries"].sort(
        key=lambda row: (str(row["kind"]), str(row["watch_id"]))
    )
    packet["previous_input_manifest_sha256"] = "b" * 64
    packet["changed_watch_entries"] = [change]
    packet["material_changed_watch_entries"] = [change]
    packet["changed_evidence_classes"] = ["exact_subject"]
    _reseal(packet)

    with pytest.raises(ValueError, match="fresh exact-premise state"):
        validate_selection_tick_v2(packet)


def test_changed_watch_cannot_also_be_carried_forward(tmp_path: Path) -> None:
    packet = build_selection_tick(_repo(tmp_path))
    row = next(
        item
        for item in packet["watch_entries"]
        if item["evidence_class"] == "task_state"
    )
    change = {
        "watch_id": row["watch_id"],
        "evidence_class": "task_state",
        "change_kind": "content_changed",
    }
    packet["previous_input_manifest_sha256"] = "b" * 64
    packet["changed_watch_entries"] = [change]
    packet["material_changed_watch_entries"] = [change]
    packet["changed_evidence_classes"] = ["task_state"]
    packet["carried_forward_watch_ids"] = [row["watch_id"]]
    _reseal(packet)

    with pytest.raises(ValueError, match="cannot be carried forward"):
        validate_selection_tick_v2(packet)


def _publication(
    head: dict[str, object], pending: list[str] | None = None
) -> dict[str, object]:
    pending = pending or []
    initialized = head["status"] != "not_initialized"
    status = (
        "recovery_required"
        if pending
        else "drift_blocked"
        if head["status"] in {"drifted", "ambiguous"}
        else "clear"
    )
    allowed = status == "clear" and initialized
    return {
        "status": status,
        "pending_transaction_ids": pending,
        "selection_journal_initialized": initialized,
        "selection_consumption_allowed": allowed,
        "selection_consumption_reason": (
            "committed_unique_current_head"
            if allowed
            else "no_committed_selection"
            if not initialized
            else "publication_recovery_or_drift_repair_required"
        ),
        "current_head": head,
        "mutation_performed": False,
    }


def _current_head(status: str = "current") -> dict[str, object]:
    expected = "b" * 64
    return {
        "status": status,
        "head_transaction_id": "selection-" + "a" * 64,
        "head_count": 1,
        "expected_task_sha256": expected,
        "current_task_sha256": expected if status == "current" else "c" * 64,
        "lineage_mode": "explicit",
    }


def test_publication_current_head_accepts_each_closed_status_shape() -> None:
    heads = [
        {
            "status": "not_initialized",
            "head_transaction_id": None,
            "head_count": 0,
            "lineage_mode": "uninitialized",
        },
        _current_head(),
        _current_head("drifted"),
        {
            "status": "ambiguous",
            "head_transaction_id": None,
            "head_count": 2,
            "head_transaction_ids": [
                "selection-" + "a" * 64,
                "selection-" + "b" * 64,
            ],
            "current_task_sha256": "c" * 64,
            "lineage_mode": "explicit",
            "lineage_errors": [],
        },
    ]
    for head in heads:
        publication = _publication(head)
        validate_selection_publication(publication, [])


@pytest.mark.parametrize(
    "mutation",
    [
        {"extra": True},
        {"head_count": True},
        {"current_task_sha256": "c" * 64},
        {"lineage_mode": 7},
    ],
)
def test_current_head_rejects_extra_fields_wrong_types_and_status_drift(
    mutation: dict[str, object],
) -> None:
    head = {**_current_head(), **mutation}
    with pytest.raises(ValueError, match="current head schema"):
        validate_selection_publication(_publication(head), [])


@pytest.mark.parametrize(
    "mutation",
    [
        {"head_count": 1},
        {"lineage_errors": ["untyped-error"]},
        {
            "head_count": 1,
            "head_transaction_ids": ["selection-" + "a" * 64],
        },
    ],
)
def test_ambiguous_head_rejects_inconsistent_count_or_lineage(
    mutation: dict[str, object],
) -> None:
    head = {
        "status": "ambiguous",
        "head_transaction_id": None,
        "head_count": 2,
        "head_transaction_ids": [
            "selection-" + "a" * 64,
            "selection-" + "b" * 64,
        ],
        "current_task_sha256": "c" * 64,
        "lineage_mode": "explicit",
        "lineage_errors": [],
        **mutation,
    }
    with pytest.raises(ValueError, match="current head schema"):
        validate_selection_publication(_publication(head), [])


def test_packet_status_must_match_publication_blocker(tmp_path: Path) -> None:
    packet = build_selection_tick(_repo(tmp_path))
    packet["selection_publication_status"] = _publication(_current_head("drifted"))

    with pytest.raises(ValueError, match="disagrees with publication blocker"):
        validate_selection_tick_v2(packet)

    packet = build_selection_tick(_repo(tmp_path))
    packet.update(
        {
            "status": "drift_blocked",
            "reason": "selection_publication_head_drift",
            "next_action": "repair_selection_publication_drift",
        }
    )
    with pytest.raises(ValueError, match="disagrees with publication blocker"):
        validate_selection_tick_v2(packet)


def test_packet_disposition_is_recomputed_from_material_delta(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    baseline = build_selection_tick(root)
    (root / ".agent_goal/final_goal.md").write_text("# Changed\n", encoding="utf-8")
    selected = build_selection_tick(root, previous=baseline)
    selected.update(
        {
            "status": "no_op",
            "reason": "changed_inputs_outside_watched_evidence_classes",
            "selection_required": False,
            "agent_fanout_allowed": False,
            "satisfied_wake_predicates": [],
            "next_action": "preserve_terminal_wait",
        }
    )

    with pytest.raises(ValueError, match="not causally derived"):
        validate_selection_tick_v2(selected)


def test_packet_reason_is_canonical_for_its_cause(tmp_path: Path) -> None:
    packet = build_selection_tick(_repo(tmp_path))
    packet["reason"] = "plausible_but_unbound_reason"

    with pytest.raises(ValueError, match="not causally derived"):
        validate_selection_tick_v2(packet)
