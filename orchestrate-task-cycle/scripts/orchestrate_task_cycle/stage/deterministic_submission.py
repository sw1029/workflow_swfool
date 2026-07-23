"""Write-free durable-receipt gates for generic stage submission."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .deterministic_receipt import (
    validate_deterministic_commit_receipt,
)
from .builder import ResultBuilder
from .contracts import canonical_sha256
from .executor_registry import executor_spec


def _block(
    preparation: dict[str, Any],
    reason: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "status": "block",
        "stop_reason": reason,
        "preparation_id": preparation["preparation_id"],
        "reason": detail,
        "applied": False,
    }


def receipt_pair(
    preparation: dict[str, Any],
    ref: str | None,
    sha256: str | None,
) -> tuple[tuple[str, str] | None, dict[str, Any] | None]:
    """Reject absent/inapplicable receipt pairs before expensive submission work."""

    deterministic = (
        executor_spec(str(preparation["target"])).executor_kind
        == "deterministic"
    )
    if deterministic and preparation.get("schema_version") != 3:
        return None, _block(
            preparation,
            "preparation_v3_required",
            "deterministic stages require schema-v3 compiler receipts",
        )
    if bool(ref) != bool(sha256):
        return None, _block(
            preparation,
            "deterministic_commit_receipt_invalid",
            "deterministic commit ref and sha256 must be supplied together",
        )
    if deterministic and not ref:
        return None, _block(
            preparation,
            "deterministic_commit_receipt_missing",
            "deterministic stages require their compiler commit receipt",
        )
    if not deterministic and ref:
        return None, _block(
            preparation,
            "deterministic_commit_receipt_inapplicable",
            "non-deterministic stages forbid deterministic commit receipts",
        )
    return ((str(ref), str(sha256)) if ref else None), None


def validate_receipt_pair(
    root: Path,
    preparation: dict[str, Any],
    pair: tuple[str, str] | None,
    owner_result_binding: dict[str, Any],
    result_sha256: str,
    *,
    replay: bool,
    max_files: int,
    max_paths: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if pair is None:
        return None, None
    ref, digest = pair
    binding = {"ref": ref, "sha256": digest}
    try:
        exact = validate_deterministic_commit_receipt(
            root,
            preparation,
            result_sha256,
            owner_result_binding,
            binding,
            max_files=max_files,
            max_paths=max_paths,
            verify_current=not replay,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        return None, _block(
            preparation,
            "deterministic_commit_receipt_invalid",
            str(exc),
        )
    return exact, None


def build_receipted_result(
    root: Path,
    preparation: dict[str, Any],
    judgment: dict[str, Any],
    input_bindings: dict[str, Any],
    pair: tuple[str, str] | None,
    *,
    replay: bool,
    max_files: int,
    max_paths: int,
) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
    result = ResultBuilder().build(preparation, judgment)
    digest = canonical_sha256(result)
    owner = input_bindings.get("owner_result_binding") or {}
    commit_binding, block = validate_receipt_pair(
        root,
        preparation,
        pair,
        owner,
        digest,
        replay=replay,
        max_files=max_files,
        max_paths=max_paths,
    )
    if commit_binding is not None:
        input_bindings["deterministic_commit_binding"] = commit_binding
    return result, digest, block


__all__: list[str] = []
