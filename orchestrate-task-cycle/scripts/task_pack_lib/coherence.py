"""Canonical before/after task-pack coherence validation."""

from __future__ import annotations
from pathlib import Path
from typing import Any
from .contracts import (
    PACK_COHERENCE_MUTATIONS,
    PACK_COHERENCE_VERSION,
    SHA256_PATTERN,
    normalize_action,
)
from .packet_io import load_json, non_empty
from .storage import pack_snapshot, resolve_pack_path


def _coherence_value(plan: dict[str, Any], key: str, *aliases: str) -> Any:
    nested = plan.get("pack_coherence")
    if isinstance(nested, dict):
        for candidate in (key, *aliases):
            if candidate in nested:
                return nested.get(candidate)
    for candidate in (key, *aliases):
        if candidate in plan:
            return plan.get(candidate)
    return None


def _coherence_field_declared(plan: dict[str, Any], key: str, *aliases: str) -> bool:
    nested = plan.get("pack_coherence")
    if isinstance(nested, dict) and any(
        (candidate in nested for candidate in (key, *aliases))
    ):
        return True
    return any((candidate in plan for candidate in (key, *aliases)))


def pack_coherence_contract_version(plan: dict[str, Any]) -> int | None:
    nested = plan.get("pack_coherence")
    raw = nested.get("schema_version") if isinstance(nested, dict) else None
    if raw is None:
        raw = plan.get("pack_coherence_version")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


_pack_coherence_contract_version = pack_coherence_contract_version


def _validate_current_preconditions(
    plan,
    declared,
    proposed_ids,
    proposed_order,
    mutation_kind,
    actual,
    post_mutation_receipt,
    finding,
) -> str:
    expected_hash = ""
    missing = [
        key
        for key in declared
        if not _coherence_field_declared(
            plan, key, "canonical_pack_sha256" if key == "before_pack_sha256" else key
        )
    ]
    if not mutation_kind:
        missing.append("mutation_kind")
    if not isinstance(proposed_ids, list):
        missing.append("proposed_after_item_ids")
    if not isinstance(proposed_order, list):
        missing.append("proposed_after_order")
    if missing:
        finding(
            "pack_coherence_precondition_incomplete",
            "Pack coherence before-snapshot fields are incomplete.",
            {"missing_fields": missing},
        )
    expected_hash = (
        str(declared["before_pack_sha256"] or "").removeprefix("sha256:").lower()
    )
    if mutation_kind != "create" and (not expected_hash):
        finding(
            "pack_coherence_before_hash_missing",
            "Non-create current mutations require a canonical before-pack hash.",
        )
    if expected_hash and (not SHA256_PATTERN.fullmatch(expected_hash)):
        finding(
            "pack_coherence_before_hash_invalid",
            "Pack coherence before hash must be a full lowercase SHA-256 digest.",
        )
    if (
        expected_hash
        and (not post_mutation_receipt)
        and (expected_hash != actual["canonical_pack_sha256"])
    ):
        finding(
            "stale_pack_snapshot",
            "Mutation plan was derived from a stale canonical pack snapshot.",
            {"declared": expected_hash, "actual": actual["canonical_pack_sha256"]},
        )
    for key, actual_key in (
        ("declared_before_item_ids", "item_ids"),
        ("declared_before_order", "item_order"),
    ):
        if (
            declared[key] is not None
            and (not post_mutation_receipt)
            and ([str(item) for item in declared[key] or []] != actual[actual_key])
        ):
            finding(
                f"{key}_mismatch",
                "Mutation plan does not match the canonical pack item identity/order.",
                {"declared": declared[key], "actual": actual[actual_key]},
            )
    if (
        declared["declared_current_item"] is not None
        and (not post_mutation_receipt)
        and (declared["declared_current_item"] != actual["current_item"])
    ):
        finding(
            "declared_current_item_mismatch",
            "Mutation plan current item does not match the canonical pack.",
            {
                "declared": declared["declared_current_item"],
                "actual": actual["current_item"],
            },
        )
    return expected_hash


def _validate_mutation_receipt(
    receipt_value,
    current_contract,
    expected_hash,
    actual,
    mutation_kind,
    declared,
    finding,
) -> None:
    if current_contract:
        required_receipt_fields = (
            "schema_version",
            "canonical_pack_ref",
            "before_pack_sha256",
            "after_pack_sha256",
            "actual_before_item_ids",
            "actual_before_order",
            "actual_before_current_item",
            "actual_after_item_ids",
            "actual_after_order",
            "actual_after_current_item",
            "mutation_kind",
        )
        missing_receipt = [
            field for field in required_receipt_fields if field not in receipt_value
        ]
        if missing_receipt:
            finding(
                "pack_mutation_receipt_incomplete",
                "Current pack mutation receipt is incomplete.",
                {"missing_fields": missing_receipt},
            )
        if receipt_value.get("schema_version") != PACK_COHERENCE_VERSION:
            finding(
                "pack_mutation_receipt_version_invalid",
                "Current pack mutation receipt requires schema_version=1.",
            )
    if (
        expected_hash
        and str(receipt_value.get("before_pack_sha256") or "")
        .removeprefix("sha256:")
        .lower()
        != expected_hash
    ):
        finding(
            "pack_receipt_before_hash_mismatch",
            "Mutation receipt does not preserve the declared before-pack hash.",
        )
    receipt_ref = str(receipt_value.get("canonical_pack_ref") or "")
    if current_contract and receipt_ref != actual["canonical_pack_ref"]:
        finding(
            "pack_receipt_ref_mismatch",
            "Mutation receipt references a different canonical pack.",
        )
    after_hash = (
        str(receipt_value.get("after_pack_sha256") or "")
        .removeprefix("sha256:")
        .lower()
    )
    if current_contract and (not SHA256_PATTERN.fullmatch(after_hash)):
        finding(
            "pack_receipt_after_hash_invalid",
            "Mutation receipt after hash must be a full lowercase SHA-256 digest.",
        )
    if after_hash and after_hash != actual["canonical_pack_sha256"]:
        finding(
            "pack_receipt_after_hash_mismatch",
            "Mutation receipt after hash does not match the canonical pack body.",
            {"declared": after_hash, "actual": actual["canonical_pack_sha256"]},
        )
    for key, actual_key in (
        ("actual_after_item_ids", "item_ids"),
        ("actual_after_order", "item_order"),
    ):
        value = receipt_value.get(key)
        if (
            value is not None
            and [str(item) for item in value or []] != actual[actual_key]
        ):
            finding(
                f"pack_receipt_{key}_mismatch",
                "Mutation receipt after-state does not match the canonical pack body.",
            )
    if (
        current_contract
        and receipt_value.get("actual_after_current_item") != actual["current_item"]
    ):
        finding(
            "pack_receipt_after_current_item_mismatch",
            "Mutation receipt current item does not match the canonical pack body.",
        )
    receipt_mutation_kind = normalize_action(
        str(receipt_value.get("mutation_kind") or "")
    )
    if current_contract and receipt_mutation_kind != mutation_kind:
        finding(
            "pack_receipt_mutation_kind_mismatch",
            "Mutation receipt kind does not match the declared plan mutation.",
        )
    if current_contract:
        for key, declared_key in (
            ("actual_before_item_ids", "declared_before_item_ids"),
            ("actual_before_order", "declared_before_order"),
        ):
            if [str(item) for item in receipt_value.get(key) or []] != [
                str(item) for item in declared.get(declared_key) or []
            ]:
                finding(
                    f"pack_receipt_{key}_before_mismatch",
                    "Mutation receipt before-state does not match the declared plan snapshot.",
                )
        if receipt_value.get("actual_before_current_item") != declared.get(
            "declared_current_item"
        ):
            finding(
                "pack_receipt_before_current_item_mismatch",
                "Mutation receipt before current item does not match the declared plan snapshot.",
            )


def _validate_contract_identity(
    plan, contract_version, current_contract, finding
) -> str:
    if contract_version not in {0, PACK_COHERENCE_VERSION}:
        finding(
            "pack_coherence_version_missing_or_invalid",
            "Pack coherence requires schema/version 1; legacy normalization requires explicit version 0.",
        )
    mutation_kind = normalize_action(
        str(_coherence_value(plan, "mutation_kind", "action", "pack_disposition") or "")
    )
    if mutation_kind and mutation_kind not in PACK_COHERENCE_MUTATIONS:
        finding(
            "pack_mutation_kind_invalid",
            "Pack coherence names an unsupported mutation kind.",
            {"mutation_kind": mutation_kind},
        )
    outer_mutation_kind = normalize_action(
        str(plan.get("action") or plan.get("pack_disposition") or "")
    )
    if (
        current_contract
        and outer_mutation_kind
        and (mutation_kind != outer_mutation_kind)
    ):
        finding(
            "pack_mutation_kind_mismatch",
            "Pack coherence mutation kind does not match the requested mutation action.",
            {"declared": mutation_kind or None, "requested": outer_mutation_kind},
        )
    return mutation_kind


def _validate_proposed_items(
    actual, proposed_ids, proposed_order, mutation_kind, finding
) -> None:
    before_ids = set(actual["item_ids"])
    if isinstance(proposed_ids, list) and mutation_kind not in {"create", "insert"}:
        unknown = sorted({str(item) for item in proposed_ids} - before_ids)
        if unknown:
            finding(
                "pack_coherence_unknown_item",
                "Proposed pack state contains item IDs absent from the canonical snapshot.",
                {"item_ids": unknown},
            )
    if isinstance(proposed_order, list) and mutation_kind not in {"create", "insert"}:
        unknown = sorted({str(item) for item in proposed_order} - before_ids)
        if unknown:
            finding(
                "pack_coherence_unknown_order_item",
                "Proposed pack order contains item IDs absent from the canonical snapshot.",
                {"item_ids": unknown},
            )


def _normalized_coherence(
    contract_version,
    actual,
    expected_hash,
    current_contract,
    contract_declared,
    receipt_value,
    post_mutation_receipt,
    declared,
    proposed_ids,
    proposed_order,
    mutation_kind,
    explicit_legacy,
) -> dict[str, Any]:
    normalized = {
        "schema_version": PACK_COHERENCE_VERSION,
        "contract_version": contract_version,
        "canonical_pack_ref": actual["canonical_pack_ref"],
        "before_pack_sha256": (
            expected_hash if current_contract else actual["canonical_pack_sha256"]
        ),
        "declared_before_item_ids": (
            declared["declared_before_item_ids"]
            if contract_declared
            else actual["item_ids"]
        ),
        "actual_before_item_ids": (
            receipt_value.get("actual_before_item_ids")
            if post_mutation_receipt
            else actual["item_ids"]
        ),
        "declared_before_order": (
            declared["declared_before_order"]
            if contract_declared
            else actual["item_order"]
        ),
        "actual_before_order": (
            receipt_value.get("actual_before_order")
            if post_mutation_receipt
            else actual["item_order"]
        ),
        "declared_current_item": (
            declared["declared_current_item"]
            if contract_declared
            else actual["current_item"]
        ),
        "actual_current_item": (
            receipt_value.get("actual_before_current_item")
            if post_mutation_receipt
            else actual["current_item"]
        ),
        "proposed_after_item_ids": proposed_ids,
        "proposed_after_order": proposed_order,
        "mutation_kind": mutation_kind,
        "legacy_normalized": explicit_legacy,
    }
    return normalized


def validate_pack_coherence_contract(
    root: Path,
    plan: dict[str, Any],
    *,
    receipt: dict[str, Any] | None = None,
    require_declared: bool = False,
    require_receipt: bool = False,
) -> dict[str, Any]:
    """Validate a derive plan/receipt against the canonical pack body.

    This is the single deterministic owner used both by mutation execution and
    the derive result contract. Legacy plans may be normalized at execution
    time, but a caller that declares the current contract must provide every
    before-snapshot precondition.
    """
    findings: list[dict[str, Any]] = []

    def finding(code: str, message: str, evidence: Any = None) -> None:
        item: dict[str, Any] = {"severity": "block", "code": code, "message": message}
        if evidence is not None:
            item["evidence"] = evidence
        findings.append(item)

    pack_ref = _coherence_value(plan, "canonical_pack_ref", "pack_path")
    if not non_empty(pack_ref):
        finding(
            "canonical_pack_ref_missing",
            "Pack coherence requires `canonical_pack_ref` or legacy `pack_path`.",
        )
        return {"status": "block", "findings": findings, "pack_coherence": None}
    try:
        path = resolve_pack_path(root, str(pack_ref))
        data = load_json(path)
    except SystemExit as exc:
        finding("canonical_pack_unreadable", str(exc))
        return {"status": "block", "findings": findings, "pack_coherence": None}
    actual = pack_snapshot(root, path, data)
    receipt_value = receipt or plan.get("pack_mutation_receipt")
    post_mutation_receipt = isinstance(receipt_value, dict)
    contract_version = _pack_coherence_contract_version(plan)
    current_contract = contract_version == PACK_COHERENCE_VERSION
    explicit_legacy = contract_version == 0
    mutation_kind = _validate_contract_identity(
        plan, contract_version, current_contract, finding
    )
    declared = {
        "before_pack_sha256": _coherence_value(
            plan, "before_pack_sha256", "canonical_pack_sha256"
        ),
        "declared_before_item_ids": _coherence_value(plan, "declared_before_item_ids"),
        "declared_before_order": _coherence_value(plan, "declared_before_order"),
        "declared_current_item": _coherence_value(plan, "declared_current_item"),
    }
    contract_declared = current_contract
    expected_hash = ""
    if require_declared and (not (current_contract or explicit_legacy)):
        finding(
            "pack_coherence_precondition_missing",
            "Pack mutation contracts require an explicit current or legacy discriminator.",
        )
    proposed_ids = _coherence_value(plan, "proposed_after_item_ids")
    proposed_order = _coherence_value(plan, "proposed_after_order", "item_order")
    if current_contract:
        expected_hash = _validate_current_preconditions(
            plan,
            declared,
            proposed_ids,
            proposed_order,
            mutation_kind,
            actual,
            post_mutation_receipt,
            finding,
        )
    _validate_proposed_items(
        actual, proposed_ids, proposed_order, mutation_kind, finding
    )
    if require_receipt and current_contract and (not isinstance(receipt_value, dict)):
        finding(
            "pack_mutation_receipt_missing",
            "Current post-mutation validation requires a complete pack mutation receipt.",
        )
    if isinstance(receipt_value, dict):
        _validate_mutation_receipt(
            receipt_value,
            current_contract,
            expected_hash,
            actual,
            mutation_kind,
            declared,
            finding,
        )
    normalized = _normalized_coherence(
        contract_version,
        actual,
        expected_hash,
        current_contract,
        contract_declared,
        receipt_value,
        post_mutation_receipt,
        declared,
        proposed_ids,
        proposed_order,
        mutation_kind,
        explicit_legacy,
    )
    return {
        "status": "block" if findings else "ok",
        "findings": findings,
        "pack_coherence": normalized,
        "path": path,
        "data": data,
    }
