"""External expectation, recovery, and plan-input verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import (
    ALLOWED_RECOVERY,
    SHA256_LENGTH,
    _canonical_json,
    _fail,
    _is_int,
    _regular_file,
    _require,
    _sha256,
    _source_rows,
    _walk_markdown,
)

from .boundary import _boundary_observation_sha256
from .graph_contracts import BOUNDARY_OBSERVATION_FIELDS
from .resolution_evidence import _verify_rows_and_inventory


def _verify_recovery_evidence(
    bundle: dict[str, Any],
    expected_recovery_status: str,
    observation: dict[str, Any] | None,
    expected_observation_sha256: str | None,
) -> None:
    journal = bundle["journal"]
    receipt = bundle["receipt"]
    _require(
        expected_recovery_status in ALLOWED_RECOVERY,
        "caller expected recovery status is invalid",
    )
    _require(
        receipt.get("recovery_status") == expected_recovery_status
        and journal.get("recovery_status") == expected_recovery_status,
        "receipt/journal recovery status differs from the caller expectation",
    )
    if expected_recovery_status != "forward_completed":
        _require(
            observation is None and expected_observation_sha256 is None,
            "recovery evidence supplied for a migration that did not require recovery",
        )
        return
    _require(
        isinstance(observation, dict),
        "forward recovery requires an independent pre-recovery boundary observation",
    )
    _require(
        isinstance(expected_observation_sha256, str)
        and len(expected_observation_sha256) == SHA256_LENGTH,
        "forward recovery requires an externally preserved observation hash",
    )
    _require(
        set(observation)
        == set(BOUNDARY_OBSERVATION_FIELDS) | {"observation_sha256"},
        "recovery boundary observation has unknown or missing fields",
    )
    _require(
        observation.get("observation_sha256")
        == _boundary_observation_sha256(observation)
        == expected_observation_sha256,
        "recovery boundary observation does not match the external hash anchor",
    )
    required = (
        _is_int(observation.get("schema_version"))
        and observation["schema_version"] == 1
        and observation.get("kind")
        == "agent_log_migration_transaction_boundary_observation"
        and observation.get("evaluation_status") == "observed"
        and observation.get("status") == "observed"
        and observation.get("migration_id") == bundle["migration_id"]
        and observation.get("journal_phase") in {"prepared", "switched", "committed"}
        and observation.get("publication_state") == "post_switch_incomplete"
        and observation.get("index_switched") is True
        and observation.get("source_index_intact") is False
        and observation.get("marker_present") is False
        and isinstance(observation.get("receipt_present"), bool)
        and observation.get("forward_recovery_required") is True
        and observation.get("exact_replay_noop_eligible") is False
        and observation.get("read_only") is True
    )
    _require(
        required,
        "recovery boundary observation does not prove a forward-only crash state",
    )
    _require(
        observation.get("plan_sha256") == _sha256(bundle["refs"]["plan"][1])
        and observation.get("after_index_sha256")
        == journal.get("after_index_sha256")
        and observation.get("after_index_size")
        == journal.get("after_index_size"),
        "recovery boundary observation is not bound to the committed graph",
    )

def _verify_external_status_map(
    bundle: dict[str, Any],
    plan_status: dict[str, Any],
    expected_status_map_raw: str | Path,
) -> None:
    root = bundle["root"]
    migration_id = bundle["migration_id"]
    status_path, status_payload = bundle["refs"]["status"]
    expected = Path(expected_status_map_raw).expanduser()
    if not expected.is_absolute():
        expected = root / expected
    expected = _regular_file(expected.resolve(strict=True), "external exact status map")
    plan_ref = plan_status.get("ref")
    _require(
        isinstance(plan_ref, str) and plan_ref and "\x00" not in plan_ref,
        "plan external status-map ref is invalid",
    )
    plan_path = Path(plan_ref).expanduser()
    if not plan_path.is_absolute():
        plan_path = root / plan_path
    _require(not plan_path.is_symlink(), "plan external status-map ref is a symlink")
    plan_path = _regular_file(
        plan_path.resolve(strict=True), "plan external status map"
    )
    transaction = root / ".agent_log" / "migrations" / migration_id
    try:
        plan_path.relative_to(transaction)
    except ValueError:
        pass
    else:
        _fail("plan external status map is inside the current migration transaction")
    _require(
        plan_path.read_bytes() == status_payload,
        "plan external status-map source differs from the published copy",
    )
    parts = expected.parts
    _require(
        not any(
            parts[index : index + 2] == (".agent_log", "migrations")
            for index in range(len(parts) - 1)
        ),
        "external exact status map must be caller-owned outside migration sidecars",
    )
    _require(
        not expected.samefile(status_path),
        "external exact status map must not alias the published sidecar",
    )
    _require(
        expected.stat().st_nlink == 1 and status_path.stat().st_nlink == 1,
        "status map trust anchors must not be hard-linked",
    )
    _require(
        expected.read_bytes() == status_payload,
        "published status map differs from the external exact status map",
    )

def _verify_plan_inputs(
    bundle: dict[str, Any],
    root_identity: dict[str, Any],
    plan_status: dict[str, Any],
    plan_source: dict[str, Any],
) -> dict[str, Any]:
    root = bundle["root"]
    receipt = bundle["receipt"]
    plan = bundle["plan"]
    status_map = bundle["status"]
    manifest = bundle["manifest"]
    source_payload = bundle["refs"]["source"][1]
    status_payload = bundle["refs"]["status"][1]
    _require(
        plan_status.get("sha256") == _sha256(status_payload),
        "plan does not hash-bind the exact status map",
    )
    for field in ("schema_version", "mapping_policy_id", "version"):
        _require(
            plan_status.get(field) == status_map.get(field),
            f"plan status-map {field} mismatch",
        )
    _require(
        type(plan_status.get("version")) is type(status_map.get("version"))
        and not isinstance(plan_status.get("version"), bool),
        "plan status-map version type mismatch",
    )
    _require(
        plan_source.get("path") == ".agent_log/index.jsonl",
        "plan source index path mismatch",
    )
    _require(
        plan_source.get("sha256") == _sha256(source_payload)
        and _is_int(plan_source.get("size"))
        and plan_source["size"] == len(source_payload)
        and _is_int(plan_source.get("raw_row_count"))
        and plan_source["raw_row_count"] == len(_source_rows(source_payload)),
        "plan source snapshot binding mismatch",
    )
    independent = _verify_rows_and_inventory(
        root=root,
        source_payload=source_payload,
        plan=plan,
        manifest=manifest,
        status_map=status_map,
        actual_markdown=_walk_markdown(root),
    )
    basis = {
        "tool_version": plan.get("tool_version"),
        "root_identity": root_identity["sha256"],
        "source_index_sha256": _sha256(source_payload),
        "source_inventory_sha256": independent["inventory_sha256"],
        "status_map_sha256": _sha256(status_payload),
    }
    _require(
        bundle["migration_id"]
        == "agent-log-migration-" + _sha256(_canonical_json(basis))[:24],
        "migration identity is not independently reproducible",
    )
    source_sha = _sha256(source_payload)
    _require(
        receipt.get("source_inventory_sha256") == independent["inventory_sha256"]
        and manifest.get("source_index_sha256") == source_sha
        and receipt.get("source_index_sha256") == source_sha
        and receipt.get("before_index_sha256") == source_sha
        and _is_int(receipt.get("source_index_size"))
        and receipt["source_index_size"] == len(source_payload)
        and receipt.get("source_index_ref") == ".agent_log/index.jsonl",
        "receipt or manifest source binding mismatch",
    )
    return independent
