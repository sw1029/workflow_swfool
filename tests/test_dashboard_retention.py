from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from orchestrate_task_cycle import render_cycle_dashboard
from orchestrate_task_cycle.dashboard import collections


ANCHOR = "2026-07-29T12:00:00+00:00"


def write(path: Path, body: bytes = b"{}\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def configured_event() -> dict[str, object]:
    return {
        "step": "context",
        "status": "complete",
        "created_at": ANCHOR,
        "record_retention_policy": {
            "budgets": {
                "max_cycle_files": 1,
                "max_cycle_bytes": 1,
                "max_age_days": 1,
            }
        },
    }


def test_retention_inventory_evaluates_configured_budget_and_protects_evidence(
    tmp_path: Path,
) -> None:
    payload = b'{"same":true}\n'
    digest = hashlib.sha256(payload).hexdigest()
    for cycle_id in ("cycle-a", "cycle-b"):
        cycle = tmp_path / ".task" / "cycle" / cycle_id
        write(cycle / "current_stage.json")
        write(cycle / "stage.jsonl")
        write(cycle / "packets" / f"result-run-{digest}.json", payload)
    write(tmp_path / ".task" / "cycle" / "cycle-a" / "finalization" / "receipt.json")
    write(tmp_path / ".task" / "cycle" / "cycle-a" / "authority" / "receipt.json")
    write(tmp_path / ".task" / "cycle" / "cycle-a" / "settlement" / "receipt.json")
    old = 1_753_612_800  # 2025-07-29T12:00:00Z
    for path in (tmp_path / ".task" / "cycle").rglob("*"):
        if path.is_file():
            os.utime(path, (old, old))

    result = collections.retention_inventory(
        tmp_path, [configured_event()], cycle_id="cycle-a"
    )

    assert result["policy_status"] == "configured"
    assert result["budget_status"] == "evaluated"
    assert result["retention_fail_quiet"] is False
    assert result["overage"]["files"] > 0
    assert result["overage"]["bytes"] > 0
    assert result["overage"]["age_expired_files"] == result["inventory"]["file_count"]
    assert result["duplicate_packets"]["group_count"] == 1
    assert result["duplicate_packets"]["groups"][0]["protected"] is True
    assert result["regenerable_intermediates"]["file_count"] == 2
    assert {
        "ledger",
        "compact_result_cas",
        "finalization",
        "authority",
        "settlement",
    } <= set(result["protected"]["categories"])
    assert result["archive_apply_status"] == "not_attempted"
    assert result["deletion_authority"] == "not_requested"

    write(tmp_path / ".task" / "cycle" / "cycle-a" / "dashboard.md", b"# Derived\n")
    dashboard_result = b'{"step":"dashboard"}\n'
    dashboard_digest = hashlib.sha256(dashboard_result).hexdigest()
    write(
        tmp_path
        / ".task"
        / "cycle"
        / "cycle-a"
        / "packets"
        / f"result-dashboard-{dashboard_digest}.json",
        dashboard_result,
    )
    assert (
        collections.retention_inventory(
            tmp_path, [configured_event()], cycle_id="cycle-a"
        )
        == result
    )

    summary = render_cycle_dashboard.summarize(
        [configured_event()], {}, "missing", "cycle-a", tmp_path
    )
    assert summary["retention_summary"] == result
    assert "## 보존 dry-run" in render_cycle_dashboard.render_summary(summary)


@pytest.mark.parametrize(
    ("policy", "expected_status"),
    [
        (None, "absent"),
        ({"budgets": {"max_cycle_files": 1, "max_cycle_bytes": 1}}, "malformed"),
        (
            {
                "budgets": {
                    "max_cycle_files": 1,
                    "max_cycle_bytes": True,
                    "max_age_days": 1,
                }
            },
            "malformed",
        ),
    ],
)
def test_retention_policy_absent_or_malformed_fails_quiet(
    tmp_path: Path,
    policy: dict[str, object] | None,
    expected_status: str,
) -> None:
    event: dict[str, object] = {"created_at": ANCHOR}
    if policy is not None:
        event["record_retention_policy"] = policy

    result = collections.retention_inventory(tmp_path, [event])

    assert result["policy_status"] == expected_status
    assert result["retention_fail_quiet"] is True
    assert set(result["overage"].values()) == {None}


def test_retention_inventory_skips_symlinks_and_bounds_output_and_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "outside.json"
    write(outside)
    cycle_root = tmp_path / ".task" / "cycle"
    for index in range(55):
        payload = f'{{"index":{index}}}\n'.encode()
        digest = hashlib.sha256(payload).hexdigest()
        for cycle_id in ("cycle-a", "cycle-b"):
            write(
                cycle_root
                / cycle_id
                / "packets"
                / f"result-run-{digest}.json",
                payload,
            )
    (cycle_root / "cycle-a" / "outside-link.json").symlink_to(outside)

    bounded = collections.retention_inventory(
        tmp_path, [], max_items=collections.RETENTION_OUTPUT_LIMIT + 10
    )

    assert bounded["inventory"]["skipped_symlink_count"] == 1
    assert bounded["duplicate_packets"]["group_count"] == 55
    assert len(bounded["duplicate_packets"]["groups"]) == 50
    assert bounded["duplicate_packets"]["truncated_count"] == 5

    hash_limit = collections.RETENTION_HASH_FILE_LIMIT
    monkeypatch.setattr(collections, "RETENTION_HASH_FILE_LIMIT", 2)
    hash_truncated = collections.retention_inventory(
        tmp_path, [configured_event()]
    )
    assert hash_truncated["inventory_status"] == "complete"
    assert hash_truncated["duplicate_packets"]["status"] == "partial"
    assert hash_truncated["duplicate_packets"]["hash_truncated_count"] > 0
    assert hash_truncated["retention_fail_quiet"] is False
    assert hash_truncated["overage"]["files"] > 0

    monkeypatch.setattr(collections, "RETENTION_HASH_FILE_LIMIT", hash_limit)
    monkeypatch.setattr(collections, "RETENTION_SCAN_ENTRY_LIMIT", 3)
    truncated = collections.retention_inventory(tmp_path, [configured_event()])

    assert truncated["inventory_status"] == "partial"
    assert truncated["inventory"]["truncated_count"] > 0
    assert truncated["retention_fail_quiet"] is True
    assert set(truncated["overage"].values()) == {None}
