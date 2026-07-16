"""Independent agent-log migration verification orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .boundary import (
    _boundary_observation_sha256 as _boundary_observation_sha256,
    inspect_transaction_boundary as inspect_transaction_boundary,
)
from .bundle import _load_verification_bundle, _verify_document_headers
from .core import _canonical_json, _sha256
from .input_verification import (
    _verify_external_status_map,
    _verify_plan_inputs,
    _verify_recovery_evidence,
)
from .publication_verification import (
    _verify_index_projection,
    _verify_marker,
    _verify_publication_bindings,
)


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
