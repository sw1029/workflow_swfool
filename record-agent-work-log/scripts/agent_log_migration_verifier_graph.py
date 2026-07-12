"""Graph and publication orchestration for the independent verifier."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from agent_log_migration_verifier_core import (
    ALLOWED_RECOVERY,
    MIGRATION_KIND,
    SHA256_LENGTH,
    SUPPORTED_TOOL_VERSIONS,
    VerificationError,
    _canonical_json,
    _current_prefix,
    _fail,
    _hashed_ref,
    _is_int,
    _load_json,
    _migration_ref,
    _regular_file,
    _require,
    _root,
    _sha256,
    _source_rows,
    _walk_markdown,
)
from agent_log_migration_verifier_evidence import (
    _verify_committed_records,
    _verify_current_store,
    _verify_rows_and_inventory,
)


RECEIPT_KEYS = frozenset(
    "after_index_sha256 after_index_size after_row_count appendability_status before_index_sha256 before_row_count body_alias_count body_mutation_count canonicalized_count committed_at duplicate_alias_count foreign_event_count historical_claims_upgraded journal_ref kind legacy_import_count migration_id missing_body_count orphan_count plan_ref plan_sha256 post_duplicate_count post_integrity_status post_legacy_count post_orphan_count prepared_at recovery_status resolution_manifest_ref resolution_manifest_sha256 schema_version source_index_ref source_index_sha256 source_index_size source_inventory_sha256 source_snapshot_ref source_snapshot_sha256 status_map_ref status_map_sha256 tool_version transaction_status unresolved_count".split()
)
PLAN_KEYS = frozenset(
    "body_mutation_count body_resolutions classification_counts expected_after_index_sha256 expected_after_index_size expected_after_row_count historical_claims_upgraded migration_id orphans root_identity rows schema_version source_index source_inventory_sha256 source_markdown_count status_map tool_version unresolved_count".split()
)
MANIFEST_KEYS = frozenset(
    "body_mutation_count classification_counts historical_claims_upgraded kind markdown_inventory markdown_resolutions migration_id orphans schema_version source_index_sha256 source_inventory_sha256 source_rows unresolved_count".split()
)
JOURNAL_KEYS = frozenset(
    "after_index_sha256 after_index_size after_row_count committed_at kind manifest_ref manifest_sha256 migration_id phase plan_ref plan_sha256 prepared_at receipt_ref receipt_sha256 recovery_status root_identity schema_version source_index_sha256 source_index_size source_inventory_sha256 source_snapshot_ref source_snapshot_sha256 staged_index_ref status_map_ref status_map_sha256 tool_version".split()
)
JOURNAL_FORWARD_KEYS = (JOURNAL_KEYS - {"committed_at"}) | {"recovered_at"}
JOURNAL_FORWARD_AFTER_COMMIT_KEYS = JOURNAL_KEYS | {"recovered_at"}


BOUNDARY_OBSERVATION_FIELDS = (
    "schema_version",
    "kind",
    "evaluation_status",
    "status",
    "migration_id",
    "journal_phase",
    "journal_sha256",
    "plan_sha256",
    "after_index_sha256",
    "after_index_size",
    "publication_state",
    "index_switched",
    "source_index_intact",
    "marker_present",
    "receipt_present",
    "forward_recovery_required",
    "exact_replay_noop_eligible",
    "read_only",
)


def _boundary_observation_sha256(value: dict[str, Any]) -> str:
    basis = {field: value.get(field) for field in BOUNDARY_OBSERVATION_FIELDS}
    return _sha256(_canonical_json(basis))


def inspect_transaction_boundary(
    root_raw: str | Path,
    migration_id: str,
    *,
    expected_status_map_raw: str | Path | None = None,
    expected_recovery_status: str | None = None,
    recovery_observation: dict[str, Any] | None = None,
    expected_recovery_observation_sha256: str | None = None,
) -> dict[str, Any]:
    """Observe crash/publication state without invoking producer recovery code."""

    root = _root(root_raw)
    _require(
        isinstance(migration_id, str)
        and re.fullmatch(r"agent-log-migration-[A-Za-z0-9._-]+", migration_id)
        is not None,
        "transaction identity is invalid",
    )
    transaction = root / ".agent_log" / "migrations" / migration_id
    _require(transaction.exists() and transaction.is_dir() and not transaction.is_symlink(), "transaction directory is unavailable")
    journal_path = _regular_file(transaction / "journal.json", "journal")
    journal, journal_payload = _load_json(journal_path, "journal")
    _require(journal.get("migration_id") == migration_id, "journal migration identity mismatch")
    _require(
        _is_int(journal.get("schema_version")) and journal["schema_version"] == 1,
        "journal schema mismatch",
    )
    phase = journal.get("phase")
    _require(phase in {"prepared", "switched", "committed"}, "journal phase is invalid")
    index_payload = _regular_file(root / ".agent_log" / "index.jsonl", "current index").read_bytes()
    switched = False
    after_size = journal.get("after_index_size")
    after_sha = journal.get("after_index_sha256")
    if _is_int(after_size) and after_size >= 0 and isinstance(after_sha, str):
        switched = len(index_payload) >= after_size and _sha256(index_payload[:after_size]) == after_sha
    source_size = journal.get("source_index_size")
    source_sha = journal.get("source_index_sha256")
    source_intact = (
        _is_int(source_size)
        and source_size >= 0
        and isinstance(source_sha, str)
        and len(index_payload) == source_size
        and _sha256(index_payload) == source_sha
    )
    marker_path = root / ".agent_log" / "migrations" / "active.json"
    marker_present = marker_path.exists() and not marker_path.is_symlink()
    receipt_path = transaction / "receipt.json"
    receipt_present = receipt_path.exists() and not receipt_path.is_symlink()
    committed_candidate = (
        phase == "committed" and switched and marker_present and receipt_present
    )
    committed = False
    if committed_candidate:
        _require(
            expected_status_map_raw is not None,
            "committed boundary observation requires the external exact status map",
        )
        verify_migration(
            root,
            receipt_path,
            expected_status_map_raw=expected_status_map_raw,
            expected_recovery_status=expected_recovery_status,
            recovery_observation=recovery_observation,
            expected_recovery_observation_sha256=expected_recovery_observation_sha256,
        )
        committed = True
    _require(
        switched or source_intact,
        "current index matches neither the pre-switch source nor committed prefix",
    )
    _require(
        phase != "switched" or switched,
        "switched journal does not match the committed index prefix",
    )
    _require(
        phase != "committed" or committed or (switched and not marker_present),
        "committed journal lacks a complete publication boundary",
    )
    if committed:
        publication_state = "committed"
    elif switched:
        publication_state = "post_switch_incomplete"
    else:
        publication_state = "pre_switch_incomplete"
    result = {
        "schema_version": 1,
        "kind": "agent_log_migration_transaction_boundary_observation",
        "evaluation_status": "observed",
        "status": "observed",
        "migration_id": migration_id,
        "journal_phase": phase,
        "journal_sha256": _sha256(journal_payload),
        "plan_sha256": journal.get("plan_sha256"),
        "after_index_sha256": after_sha,
        "after_index_size": after_size,
        "publication_state": publication_state,
        "index_switched": switched,
        "source_index_intact": source_intact,
        "marker_present": marker_present,
        "receipt_present": receipt_present,
        "forward_recovery_required": switched and not committed,
        "exact_replay_noop_eligible": committed,
        "read_only": True,
    }
    result["observation_sha256"] = _boundary_observation_sha256(result)
    return result


def _load_verification_bundle(
    root_raw: str | Path, receipt_raw: str | Path
) -> dict[str, Any]:
    root = _root(root_raw)
    receipt_path = Path(receipt_raw)
    if not receipt_path.is_absolute():
        receipt_path = root / receipt_path
    try:
        receipt_relative = receipt_path.resolve(strict=True).relative_to(root).as_posix()
    except (OSError, ValueError) as exc:
        raise VerificationError("receipt must be a workspace-local regular file") from exc
    receipt_path = _regular_file(root / receipt_relative, "receipt")
    receipt, receipt_payload = _load_json(receipt_path, "receipt")
    _require(set(receipt) == RECEIPT_KEYS, "receipt is not the exact schema-v1 projection")
    migration_id = receipt.get("migration_id")
    _require(isinstance(migration_id, str) and migration_id, "receipt migration identity is missing")
    _require(
        _migration_ref(root, receipt_relative, migration_id, "receipt")
        == receipt_path,
        "receipt is outside its transaction",
    )
    _require(
        _is_int(receipt.get("schema_version"))
        and receipt["schema_version"] == 1
        and receipt.get("kind") == MIGRATION_KIND,
        "receipt schema or kind mismatch",
    )
    _require(
        receipt.get("transaction_status") == "committed",
        "producer success is not a committed receipt",
    )
    zero_fields = (
        "unresolved_count",
        "body_mutation_count",
        "missing_body_count",
        "post_legacy_count",
        "post_orphan_count",
        "post_duplicate_count",
    )
    for field in zero_fields:
        _require(
            _is_int(receipt.get(field)) and receipt[field] == 0,
            f"receipt {field} is not zero",
        )
    _require(
        receipt.get("historical_claims_upgraded") is False,
        "receipt upgrades historical claims",
    )
    _require(
        receipt.get("post_integrity_status") == "valid"
        and receipt.get("appendability_status") == "pass",
        "receipt publication claims are incomplete",
    )
    refs: dict[str, tuple[Path, bytes]] = {}
    for name, ref_field, sha_field in (
        ("source", "source_snapshot_ref", "source_snapshot_sha256"),
        ("plan", "plan_ref", "plan_sha256"),
        ("status", "status_map_ref", "status_map_sha256"),
        ("manifest", "resolution_manifest_ref", "resolution_manifest_sha256"),
    ):
        refs[name] = _hashed_ref(
            root,
            receipt,
            ref_field,
            sha_field,
            migration_id,
            name,
        )
    journal_path = _migration_ref(
        root, receipt.get("journal_ref"), migration_id, "journal"
    )
    staged_path = _migration_ref(
        root,
        f".agent_log/migrations/{migration_id}/staged-index.snapshot",
        migration_id,
        "staged index",
    )
    documents = {
        "plan": _load_json(refs["plan"][0], "plan")[0],
        "status": _load_json(refs["status"][0], "status map")[0],
        "manifest": _load_json(refs["manifest"][0], "resolution manifest")[0],
        "journal": _load_json(journal_path, "journal")[0],
    }
    journal_payload = journal_path.read_bytes()
    return {
        "root": root,
        "receipt_path": receipt_path,
        "receipt_relative": receipt_relative,
        "receipt": receipt,
        "receipt_payload": receipt_payload,
        "migration_id": migration_id,
        "refs": refs,
        "journal_path": journal_path,
        "journal_payload": journal_payload,
        "staged_path": staged_path,
        **documents,
    }


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


def _verify_document_headers(
    bundle: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    migration_id = bundle["migration_id"]
    plan = bundle["plan"]
    manifest = bundle["manifest"]
    journal = bundle["journal"]
    for document, label in (
        (plan, "plan"),
        (manifest, "manifest"),
        (journal, "journal"),
    ):
        _require(
            document.get("migration_id") == migration_id,
            f"{label} migration identity mismatch",
        )
        _require(
            _is_int(document.get("schema_version"))
            and document["schema_version"] == 1,
            f"{label} schema mismatch",
        )
    _require(set(plan) == PLAN_KEYS, "plan is not the exact schema-v1 projection")
    _require(
        set(manifest) == MANIFEST_KEYS,
        "manifest is not the exact schema-v1 projection",
    )
    if journal.get("recovery_status") == "forward_completed":
        journal_key_match = frozenset(journal) in {
            JOURNAL_FORWARD_KEYS,
            JOURNAL_FORWARD_AFTER_COMMIT_KEYS,
        }
    else:
        journal_key_match = set(journal) == JOURNAL_KEYS
    _require(journal_key_match, "journal is not the exact schema-v1 projection")
    _require(
        manifest.get("kind") == "agent_log_migration_resolution_manifest",
        "manifest kind mismatch",
    )
    _require(
        journal.get("kind") == "agent_log_migration_journal"
        and journal.get("phase") == "committed",
        "journal is not committed",
    )
    _require(
        _is_int(plan.get("body_mutation_count"))
        and plan["body_mutation_count"] == 0
        and _is_int(manifest.get("body_mutation_count"))
        and manifest["body_mutation_count"] == 0,
        "plan or manifest permits body mutation",
    )
    _require(
        plan.get("historical_claims_upgraded") is False
        and manifest.get("historical_claims_upgraded") is False,
        "plan or manifest upgrades historical claims",
    )
    root_identity = plan.get("root_identity")
    _require(isinstance(root_identity, dict), "plan root identity is missing")
    _require(
        set(root_identity) == {"resolved_path", "device", "inode", "sha256"},
        "plan root identity is not the exact schema-v1 projection",
    )
    root_basis = {
        field: root_identity.get(field)
        for field in ("resolved_path", "device", "inode")
    }
    _require(
        isinstance(root_basis["resolved_path"], str)
        and _is_int(root_basis["device"])
        and _is_int(root_basis["inode"]),
        "plan root identity is malformed",
    )
    _require(
        root_identity.get("sha256") == _sha256(_canonical_json(root_basis)),
        "plan root identity hash mismatch",
    )
    _require(
        journal.get("root_identity") == root_identity,
        "journal root identity binding mismatch",
    )
    plan_status = plan.get("status_map")
    plan_source = plan.get("source_index")
    _require(isinstance(plan_status, dict), "plan status-map binding is malformed")
    _require(isinstance(plan_source, dict), "plan source-index binding is malformed")
    _require(
        set(plan_status)
        == {"ref", "sha256", "schema_version", "mapping_policy_id", "version"},
        "plan status-map binding is not the exact schema-v1 projection",
    )
    _require(
        set(plan_source) == {"path", "sha256", "size", "raw_row_count"},
        "plan source-index binding is not the exact schema-v1 projection",
    )
    _require(
        _is_int(plan_status.get("schema_version"))
        and plan_status["schema_version"] == 1,
        "plan status-map schema version is malformed",
    )
    return root_identity, plan_status, plan_source


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


def _verify_marker(bundle: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    root = bundle["root"]
    receipt = bundle["receipt"]
    journal = bundle["journal"]
    plan_payload = bundle["refs"]["plan"][1]
    receipt_payload = bundle["receipt_payload"]
    journal_payload = bundle["journal_payload"]
    marker, payload = _load_json(
        root / ".agent_log" / "migrations" / "active.json",
        "publication marker",
    )
    tool_version = bundle["plan"].get("tool_version")
    _require(
        tool_version in SUPPORTED_TOOL_VERSIONS,
        "migration tool version is unsupported",
    )
    for document, label in (
        (receipt, "receipt"),
        (journal, "journal"),
        (marker, "marker"),
    ):
        _require(
            document.get("tool_version") == tool_version,
            f"{label} tool version mismatch",
        )
    expected = {
        "schema_version": 1,
        "kind": "agent_log_migration_commit_marker",
        "transaction_status": "committed",
        "migration_id": bundle["migration_id"],
        "tool_version": tool_version,
        "plan_sha256": _sha256(plan_payload),
        "receipt_ref": bundle["receipt_relative"],
        "receipt_sha256": _sha256(receipt_payload),
        "journal_ref": bundle["journal_path"].relative_to(root).as_posix(),
        "journal_sha256": _sha256(journal_payload),
        "after_index_sha256": journal.get("after_index_sha256"),
        "after_index_size": journal.get("after_index_size"),
    }
    _require(marker == expected, "publication marker is not the exact schema-v1 projection")
    _require(payload == _canonical_json(expected), "publication marker bytes are not canonical")
    return marker, payload


def _verify_publication_bindings(
    bundle: dict[str, Any],
    independent: dict[str, Any],
    marker: dict[str, Any],
) -> dict[str, Any]:
    root = bundle["root"]
    receipt = bundle["receipt"]
    journal = bundle["journal"]
    refs = bundle["refs"]
    bindings = {
        "source_index_sha256": _sha256(refs["source"][1]),
        "source_index_size": len(refs["source"][1]),
        "source_inventory_sha256": independent["inventory_sha256"],
        "source_snapshot_ref": refs["source"][0].relative_to(root).as_posix(),
        "source_snapshot_sha256": _sha256(refs["source"][1]),
        "status_map_ref": refs["status"][0].relative_to(root).as_posix(),
        "status_map_sha256": _sha256(refs["status"][1]),
        "plan_ref": refs["plan"][0].relative_to(root).as_posix(),
        "plan_sha256": _sha256(refs["plan"][1]),
        "manifest_ref": refs["manifest"][0].relative_to(root).as_posix(),
        "manifest_sha256": _sha256(refs["manifest"][1]),
        "staged_index_ref": bundle["staged_path"].relative_to(root).as_posix(),
        "after_index_sha256": bundle["plan"].get("expected_after_index_sha256"),
        "after_index_size": bundle["plan"].get("expected_after_index_size"),
        "after_row_count": bundle["plan"].get("expected_after_row_count"),
    }
    for field in ("source_index_size", "after_index_size", "after_row_count"):
        _require(_is_int(bindings[field]), f"plan/journal {field} is malformed")
    for field, expected in bindings.items():
        if _is_int(expected):
            _require(_is_int(journal.get(field)), f"journal {field} type mismatch")
        _require(journal.get(field) == expected, f"journal {field} binding mismatch")
    _require(
        journal.get("receipt_ref") == bundle["receipt_relative"]
        and journal.get("receipt_sha256") == _sha256(bundle["receipt_payload"]),
        "journal receipt binding mismatch",
    )
    _require(
        _is_int(receipt.get("after_index_size"))
        and _is_int(marker.get("after_index_size"))
        and receipt.get("after_index_sha256") == bindings["after_index_sha256"]
        and marker.get("after_index_sha256") == bindings["after_index_sha256"]
        and receipt["after_index_size"] == bindings["after_index_size"]
        and marker["after_index_size"] == bindings["after_index_size"],
        "publication after-index binding mismatch",
    )
    _require(
        _is_int(receipt.get("after_row_count"))
        and receipt["after_row_count"] == bindings["after_row_count"]
        and _is_int(receipt.get("before_row_count"))
        and receipt["before_row_count"] == len(independent["source_rows"]),
        "receipt row count mismatch",
    )
    count_bindings = {
        "canonicalized_count": "canonical_log",
        "legacy_import_count": "legacy_import_markdown",
        "duplicate_alias_count": "duplicate_alias",
        "body_alias_count": "body_alias_markdown",
        "foreign_event_count": "foreign_event",
        "orphan_count": "orphan_markdown",
        "unresolved_count": "unresolved",
    }
    for receipt_field, count_field in count_bindings.items():
        _require(
            _is_int(receipt.get(receipt_field))
            and receipt[receipt_field]
            == independent["counts"].get(count_field, 0),
            f"receipt {receipt_field} mismatch",
        )
    return bindings


def _verify_index_projection(
    bundle: dict[str, Any],
    independent: dict[str, Any],
    bindings: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    index_payload = _regular_file(
        bundle["root"] / ".agent_log" / "index.jsonl", "current index"
    ).read_bytes()
    prefix = _current_prefix(
        index_payload,
        bindings["after_index_size"],
        bindings["after_index_sha256"],
    )
    _require(
        bundle["staged_path"].read_bytes() == prefix,
        "staged index and committed prefix differ",
    )
    committed = _verify_committed_records(
        root=bundle["root"],
        migration_id=bundle["migration_id"],
        prefix=prefix,
        plan=bundle["plan"],
        source_rows=independent["source_rows"],
        inventory_by_path=independent["inventory_by_path"],
        canonical_by_line=independent["canonical_by_line"],
        orphans=independent["orphans"],
    )
    current = _verify_current_store(
        index_payload,
        independent["actual_markdown"],
        committed_row_count=len(committed),
        migration_id=bundle["migration_id"],
    )
    appended = {record["path"] for record in current[len(committed) :]}
    new_markdown = set(independent["actual_markdown"]) - set(
        independent["inventory_by_path"]
    )
    _require(
        appended == new_markdown,
        "post-migration Markdown/index accounting mismatch",
    )
    return committed, current


def verify_migration(
    root_raw: str | Path,
    receipt_raw: str | Path,
    *,
    expected_status_map_raw: str | Path,
    expected_recovery_status: str,
    recovery_observation: dict[str, Any] | None = None,
    expected_recovery_observation_sha256: str | None = None,
) -> dict[str, Any]:
    """Verify a committed migration without executing producer or recovery code."""

    bundle = _load_verification_bundle(root_raw, receipt_raw)
    root_identity, plan_status, plan_source = _verify_document_headers(bundle)
    _verify_recovery_evidence(
        bundle,
        expected_recovery_status,
        recovery_observation,
        expected_recovery_observation_sha256,
    )
    _verify_external_status_map(
        bundle, plan_status, expected_status_map_raw
    )
    independent = _verify_plan_inputs(
        bundle, root_identity, plan_status, plan_source
    )
    marker, marker_payload = _verify_marker(bundle)
    bindings = _verify_publication_bindings(bundle, independent, marker)
    committed, current = _verify_index_projection(
        bundle, independent, bindings
    )
    graph_basis = {
        "migration_id": bundle["migration_id"],
        "source_snapshot_sha256": _sha256(bundle["refs"]["source"][1]),
        "status_map_sha256": _sha256(bundle["refs"]["status"][1]),
        "plan_sha256": _sha256(bundle["refs"]["plan"][1]),
        "manifest_sha256": _sha256(bundle["refs"]["manifest"][1]),
        "journal_sha256": _sha256(bundle["journal_payload"]),
        "receipt_sha256": _sha256(bundle["receipt_payload"]),
        "marker_sha256": _sha256(marker_payload),
        "after_index_sha256": bindings["after_index_sha256"],
        "recovery_observation_sha256": expected_recovery_observation_sha256,
    }
    return {
        "schema_version": 1,
        "kind": "agent_log_migration_independent_verification",
        "status": "pass",
        "evaluation_status": "pass",
        "verifier": "agent_log_migration_plan_trust_boundary_independent_verifier",
        "source_separated": True,
        "read_only": True,
        "migration_id": bundle["migration_id"],
        "recovery_status": bundle["journal"]["recovery_status"],
        "recovery_observation_sha256": expected_recovery_observation_sha256,
        "source_row_count": len(independent["source_rows"]),
        "markdown_count": len(independent["inventory_by_path"]),
        "committed_row_count": len(committed),
        "current_row_count": len(current),
        "graph_sha256": _sha256(_canonical_json(graph_basis)),
    }
