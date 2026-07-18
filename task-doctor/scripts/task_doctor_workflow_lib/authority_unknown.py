from __future__ import annotations

from pathlib import Path
from typing import Any

from manage_agent_authority.projection_receipts import validate_release_receipt
from manage_agent_authority.projection_reconciliation import (
    validate_reconciliation_receipt,
)

from .authority import (
    _authority_call,
    _current_settled_state,
    _reservation_id,
    _reservation_scope,
)
from .common import WorkflowError, read_json, require, workspace_file


def validate_unknown_settlement(
    root: Path, item: dict[str, Any], reservation: dict[str, str],
    receipt_ref: str, receipt_sha256: str,
) -> dict[str, str]:
    binding = {"ref": receipt_ref, "sha256": receipt_sha256}
    path = workspace_file(root, receipt_ref, receipt_sha256,
                          "unknown_effect_settlement")
    receipt = read_json(path, "invalid_authority_settlement")
    kind = receipt.get("artifact_kind")
    if kind == "authority_release_receipt":
        _authority_call("invalid_authority_settlement", "unknown-effect release receipt",
                        lambda: validate_release_receipt(root, receipt, path))
        require(receipt.get("effect_status") == "unknown_effect"
                and receipt.get("release_applied") is False,
                "authority_settlement_mismatch",
                "release receipt does not quarantine an unknown effect")
    elif kind == "authority_reconciliation_receipt":
        _authority_call(
            "invalid_authority_settlement", "still-unknown reconciliation receipt",
            lambda: validate_reconciliation_receipt(root, receipt, path),
        )
        require(receipt.get("outcome") == "still_unknown",
                "authority_settlement_mismatch",
                "reconciliation receipt is not still_unknown")
    else:
        raise WorkflowError(
            "invalid_authority_settlement",
            "unknown effect requires an actual release or reconciliation receipt",
        )
    require(receipt.get("reservation") == reservation,
            "authority_settlement_mismatch",
            "unknown-effect receipt binds a different reservation")
    _reservation_scope(root, item, reservation)
    _current_settled_state(root, _reservation_id(root, reservation),
                           "quarantined_unknown_effect", receipt["receipt_id"], receipt)
    return binding
