from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_ID_RE = re.compile(r"^[^\x00-\x20/\\]{1,255}$")
DELTA_CLASSES = {"material", "cosmetic", "not_evaluated"}
RELATION_EFFECTS = {"affects_violated_relation", "does_not_affect", "not_evaluated"}
MATERIAL_DELTA_FIELDS = frozenset(
    {
        "classification",
        "delta_id",
        "rationale_id",
        "rationale_evidence_digest",
        "full_content_sha256",
        "typed_difference_ids",
        "violated_relation_effect",
        "authority_premise_changed",
        "external_state_changed",
        "toolchain_premise_changed",
        "delta_receipt_sha256",
    }
)
FindingAdder = Callable[[str, str, object], None]


def _opaque(value: object) -> bool:
    return isinstance(value, str) and bool(OPAQUE_ID_RE.fullmatch(value.strip()))


def _ids(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_opaque(item) for item in value)
        and len(value) == len(set(value))
    )


def canonical_material_delta_receipt_sha256(delta: dict[str, Any]) -> str:
    body = {key: value for key, value in delta.items() if key != "delta_receipt_sha256"}
    raw = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_input_delta(delta: object, block: FindingAdder) -> bool:
    """Return whether a supplied delta can reset stable-root recurrence."""

    if delta is None:
        return False
    if not isinstance(delta, dict):
        block(
            "recurrence_input_delta_invalid",
            "supplied_input_delta must be an object",
            None,
        )
        return False
    delta_class = str(delta.get("classification") or "")
    effect = str(delta.get("violated_relation_effect") or "")
    if delta_class not in DELTA_CLASSES or effect not in RELATION_EFFECTS:
        block(
            "recurrence_input_delta_classification_invalid",
            "input delta requires a supported classification and violated-relation effect",
            None,
        )
    if not _opaque(delta.get("delta_id")) or not _opaque(delta.get("rationale_id")):
        block(
            "recurrence_input_delta_identity_invalid",
            "input delta requires opaque delta and rationale IDs",
            None,
        )
    if delta_class == "cosmetic" and effect == "affects_violated_relation":
        block(
            "recurrence_cosmetic_delta_overclaimed",
            "a cosmetic delta cannot claim it changes the violated relation",
            None,
        )
    if delta_class != "material":
        return False
    schema_valid = set(delta) == MATERIAL_DELTA_FIELDS
    premise_flags_valid = all(
        isinstance(delta.get(field), bool)
        for field in (
            "authority_premise_changed",
            "external_state_changed",
            "toolchain_premise_changed",
        )
    )
    rationale_valid = bool(
        SHA256_RE.fullmatch(str(delta.get("rationale_evidence_digest") or ""))
    )
    receipt_valid = bool(
        SHA256_RE.fullmatch(str(delta.get("delta_receipt_sha256") or ""))
        and delta.get("delta_receipt_sha256")
        == canonical_material_delta_receipt_sha256(delta)
    )
    if (
        not schema_valid
        or not premise_flags_valid
        or not rationale_valid
        or not receipt_valid
    ):
        block(
            "recurrence_material_delta_binding_invalid",
            "material delta must use the exact bounded schema and content-bind its rationale, premise-change flags, and relation effect",
            {
                "schema_valid": schema_valid,
                "premise_flags_valid": premise_flags_valid,
                "rationale_valid": rationale_valid,
                "receipt_valid": receipt_valid,
            },
        )
    digest_valid = bool(
        SHA256_RE.fullmatch(str(delta.get("full_content_sha256") or ""))
    )
    differences_valid = _ids(delta.get("typed_difference_ids"))
    if not digest_valid or not differences_valid:
        block(
            "recurrence_material_delta_evidence_missing",
            "material input delta requires a full digest and non-empty typed-difference IDs",
            None,
        )
    if effect != "affects_violated_relation":
        block(
            "recurrence_material_delta_relation_unproven",
            "material input novelty cannot reset recurrence without affecting the violated relation",
            None,
        )
    return bool(
        schema_valid
        and premise_flags_valid
        and rationale_valid
        and receipt_valid
        and digest_valid
        and differences_valid
        and effect == "affects_violated_relation"
    )


__all__ = ("canonical_material_delta_receipt_sha256", "validate_input_delta")
