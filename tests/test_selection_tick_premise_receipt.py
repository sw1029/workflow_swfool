from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from orchestrate_task_cycle.exact_subject_premise import (
    validate_exact_subject_premise,
)
from orchestrate_task_cycle.exact_subject_premise_v2 import (
    seal_artifact_verified_receipt,
)
from orchestrate_task_cycle.selection_decision_receipt import (
    render_preliminary_selection_decision,
    render_selection_decision_receipt,
)
from orchestrate_task_cycle.selection_tick import build_selection_tick
from orchestrate_task_cycle.selection_tick_premise import (
    VERIFIED_PREMISE_CONTRACT,
    validate_embedded_verified_premise_row,
)
from selection_synthesis_support import persisted_selection_synthesis


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    path.write_text(body, encoding="utf-8")


def _repo(root: Path) -> Path:
    _write(root / "task.md", "# Task\n")
    _write(root / ".agent_goal/final_goal.md", "# Goal\n")
    return root


def _canonical_sha256(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(body).hexdigest()


def _owner() -> dict[str, object]:
    return {
        "owner_id": "owner-A",
        "writable_surface_id": "surface-A",
        "authority_scope_id": "authority-A",
        "writable": True,
    }


def _receipt(
    baseline: dict[str, object],
    *,
    premise_id: str = "premise-A",
    revision: str = "revision-2",
    digest: str = "3" * 64,
) -> dict[str, object]:
    binding = {
        "binding_kind": "selection_baseline",
        "selection_baseline_id": baseline["packet_id"],
        "selection_baseline_sha256": _canonical_sha256(baseline),
    }
    context = {
        "schema_version": 1,
        "artifact_kind": "exact_subject_premise_context",
        "current_binding": binding,
        "freshness_baseline": {
            "baseline_id": "subject-baseline-A",
            "subject": {
                "subject_id": "subject-A",
                "revision_id": "revision-1",
                "content_sha256": "2" * 64,
            },
        },
        "canonical_owner": _owner(),
        "first_failing_invariant_id": "invariant-A",
    }
    submission = {
        "schema_version": 1,
        "artifact_kind": "exact_subject_premise_submission",
        "premise_id": premise_id,
        "binding": binding,
        "freshness_baseline_id": "subject-baseline-A",
        "subject": {
            "subject_id": "subject-A",
            "revision_id": revision,
            "content_sha256": digest,
        },
        "canonical_owner": _owner(),
        "first_failing_invariant": {
            "invariant_id": "invariant-A",
            "status": "failing",
            "evidence_id": "failure-A",
            "evidence_sha256": "7" * 64,
        },
        "evidence": {
            "mode": "producer_verifier_replay",
            "producer_receipt_id": "producer-A",
            "producer_receipt_sha256": "4" * 64,
            "producer_subject_sha256": digest,
            "verifier_receipt_id": "verifier-A",
            "verifier_receipt_sha256": "5" * 64,
            "verified_subject_sha256": digest,
            "replay_receipt_id": "replay-A",
            "replay_receipt_sha256": "6" * 64,
            "replayed_subject_sha256": digest,
        },
    }
    legacy = validate_exact_subject_premise(submission, context=context)["receipt"]
    if legacy["status"] != "consumed":
        return legacy
    return seal_artifact_verified_receipt(
        legacy,
        {
            "schema_version": 1,
            "artifact_kind": "exact_subject_premise_artifact_verification",
            "validator_policy": {
                "policy_id": "exact-subject-artifact-verifier",
                "policy_version": "1",
            },
            "workspace_file_validation": {
                "status": "verified",
                "workspace_local": True,
                "regular_non_symlink": True,
            },
            "current_binding_artifact": {
                "artifact_kind": "selection_baseline",
                "artifact_id": str(binding["selection_baseline_id"]),
                "digest_mode": "canonical_json_sha256",
                "binding_sha256": str(binding["selection_baseline_sha256"]),
                "raw_sha256": "1" * 64,
            },
            "current_subject": {
                "subject_id": "subject-A",
                "revision_id": revision,
                "raw_sha256": digest,
            },
            "freshness_baseline_subject": {
                "subject_id": "subject-A",
                "revision_id": "revision-1",
                "raw_sha256": "2" * 64,
            },
            "source_subject": None,
            "invariant_evidence": {
                "evidence_id": "failure-A",
                "raw_sha256": "7" * 64,
            },
            "evidence_receipts": [
                {
                    "role": "producer",
                    "receipt_id": "producer-A",
                    "raw_sha256": "4" * 64,
                },
                {
                    "role": "verifier",
                    "receipt_id": "verifier-A",
                    "raw_sha256": "5" * 64,
                },
                {
                    "role": "replay",
                    "receipt_id": "replay-A",
                    "raw_sha256": "6" * 64,
                },
            ],
            "source_body_persisted": False,
            "source_path_persisted": False,
        },
    )


def _baseline(root: Path) -> dict[str, object]:
    return build_selection_tick(
        root,
        watched_evidence_classes=["exact_subject", "authority"],
        premise_contract=VERIFIED_PREMISE_CONTRACT,
    )


def _selection_receipt(root: Path, selected: dict[str, object]) -> dict[str, str]:
    trigger_path = root / ".task/cycle/cycle-A/selection-trigger.json"
    _write(trigger_path, selected)
    _, synthesis_binding, _ = persisted_selection_synthesis(root)
    decision = render_preliminary_selection_decision(
        root,
        selected,
        synthesis_binding,
    )
    decision_path = root / ".task/cycle/cycle-A/selection-decision.json"
    _write(decision_path, decision)
    decision_binding = {
        "ref": decision_path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(decision_path.read_bytes()).hexdigest(),
    }
    trigger_binding = {
        "ref": trigger_path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(trigger_path.read_bytes()).hexdigest(),
    }
    receipt = render_selection_decision_receipt(
        root,
        selected,
        trigger_binding,
        decision_binding,
    )
    receipt_path = root / ".task/cycle/cycle-A/selection-receipt.json"
    _write(receipt_path, receipt)
    return {
        "ref": receipt_path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
    }


def test_verified_receipt_opens_selection_without_persisting_path_or_body(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    baseline = _baseline(root)
    receipt = _receipt(baseline)
    path = root / "private/premise.json"
    _write(path, receipt)

    selected = build_selection_tick(
        root,
        previous=baseline,
        premise_paths=["private/premise.json"],
        premise_ids=["premise-A"],
    )

    assert selected["status"] == "selection_required"
    row = next(
        item for item in selected["watch_entries"] if item["kind"] == "exact_premise"
    )
    assert row["sha256"] == receipt["receipt_sha256"]
    assert row["premise_receipt_id"] == receipt["receipt_id"]
    assert row["premise_receipt"] == receipt
    assert validate_embedded_verified_premise_row(row) == row
    tampered = copy.deepcopy(row)
    tampered["premise_receipt"]["receipt_id"] = "exact-premise-v2-tampered"
    with pytest.raises(ValueError, match="integrity"):
        validate_embedded_verified_premise_row(tampered)
    with_path = {**row, "path": "private/premise.json"}
    with pytest.raises(ValueError, match="non-contract"):
        validate_embedded_verified_premise_row(with_path)
    serialized = json.dumps(selected)
    assert "private/premise.json" not in serialized
    assert selected["premise_input_contract"] == VERIFIED_PREMISE_CONTRACT


def test_verified_contract_rejects_raw_file_and_contract_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    baseline = _baseline(root)
    _write(root / "raw.json", {"coverage": 0.2})

    with pytest.raises(ValueError, match="artifact-verified premise receipt"):
        build_selection_tick(
            root,
            previous=baseline,
            premise_paths=["raw.json"],
            premise_ids=["premise-A"],
        )
    with pytest.raises(ValueError, match="cannot change"):
        build_selection_tick(
            root, previous=baseline, premise_contract="raw_exact_file_v1"
        )


def test_legacy_consumed_receipt_is_never_selection_wake_eligible(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    baseline = _baseline(root)
    verified = _receipt(baseline)
    legacy_path = root / "premises/legacy-consumed.json"
    _write(legacy_path, verified["legacy_receipt"])

    with pytest.raises(ValueError, match="artifact-verified premise receipt"):
        build_selection_tick(
            root,
            previous=baseline,
            premise_paths=["premises/legacy-consumed.json"],
            premise_ids=["premise-A"],
        )


def test_acknowledged_receipt_exact_replay_is_noop_and_new_receipt_reopens(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    baseline = _baseline(root)
    first_receipt = _receipt(baseline)
    first_path = root / "premises/first.json"
    _write(first_path, first_receipt)
    selected = build_selection_tick(
        root,
        previous=baseline,
        premise_paths=["premises/first.json"],
        premise_ids=["premise-A"],
    )
    selection_receipt = _selection_receipt(root, selected)
    rebased = build_selection_tick(
        root,
        previous=selected,
        acknowledge_selection_tick_id=selected["packet_id"],
        selection_receipt_ref=selection_receipt["ref"],
        selection_receipt_sha256=selection_receipt["sha256"],
    )

    replay = build_selection_tick(
        root,
        previous=rebased,
        premise_paths=["premises/first.json"],
        premise_ids=["premise-A"],
    )
    assert replay["status"] == "no_op"
    assert replay["exact_premise_supplied"] is True
    assert replay["fresh_exact_premise_detected"] is False

    second_receipt = _receipt(
        rebased,
        premise_id="premise-B",
        revision="revision-3",
        digest="8" * 64,
    )
    _write(root / "premises/second.json", second_receipt)
    reopened = build_selection_tick(
        root,
        previous=rebased,
        premise_paths=["premises/second.json"],
        premise_ids=["premise-B"],
    )
    assert reopened["status"] == "selection_required"
    assert reopened["fresh_exact_premise_detected"] is True


@pytest.mark.parametrize(
    ("watched_classes", "expected_status", "expected_reason"),
    [
        (
            ["exact_subject"],
            "no_op",
            "changed_inputs_outside_watched_evidence_classes",
        ),
        (
            ["exact_subject", "goal_truth"],
            "selection_required",
            "material_wake_predicate_satisfied",
        ),
    ],
)
def test_identical_receipt_replay_does_not_impersonate_fresh_premise_on_drift(
    tmp_path: Path,
    watched_classes: list[str],
    expected_status: str,
    expected_reason: str,
) -> None:
    root = _repo(tmp_path)
    baseline = build_selection_tick(
        root,
        watched_evidence_classes=watched_classes,
        premise_contract=VERIFIED_PREMISE_CONTRACT,
    )
    receipt = _receipt(baseline)
    receipt_path = root / "premises/first.json"
    _write(receipt_path, receipt)
    selected = build_selection_tick(
        root,
        previous=baseline,
        premise_paths=["premises/first.json"],
        premise_ids=["premise-A"],
    )
    decision_receipt = _selection_receipt(root, selected)
    rebased = build_selection_tick(
        root,
        previous=selected,
        acknowledge_selection_tick_id=selected["packet_id"],
        selection_receipt_ref=decision_receipt["ref"],
        selection_receipt_sha256=decision_receipt["sha256"],
    )
    _write(root / ".agent_goal/final_goal.md", "# Goal changed outside premise\n")

    replay = build_selection_tick(
        root,
        previous=rebased,
        premise_paths=["premises/first.json"],
        premise_ids=["premise-A"],
    )

    assert replay["status"] == expected_status
    assert replay["reason"] == expected_reason
    assert replay["exact_premise_supplied"] is True
    assert replay["fresh_exact_premise_detected"] is False


def test_rejected_or_wrong_bound_receipt_cannot_wake_selection(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    baseline = _baseline(root)
    rejected = _receipt(baseline, digest="2" * 64)
    assert rejected["status"] == "rejected"
    _write(root / "premises/rejected.json", rejected)

    with pytest.raises(ValueError, match="artifact-verified premise receipt"):
        build_selection_tick(
            root,
            previous=baseline,
            premise_paths=["premises/rejected.json"],
            premise_ids=["premise-A"],
        )

    other_baseline = {**baseline, "packet_id": "selection-tick-" + "0" * 32}
    wrong = _receipt(other_baseline)
    _write(root / "premises/wrong.json", wrong)
    with pytest.raises(ValueError, match="another wait state"):
        build_selection_tick(
            root,
            previous=baseline,
            premise_paths=["premises/wrong.json"],
            premise_ids=["premise-A"],
        )
