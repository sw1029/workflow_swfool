"""Public facade for output-delta contract evaluation."""

from .output_delta.cli import main
from .output_delta.common import (
    DEFAULT_CONTRACT_PATHS,
    METRIC_APPLICABILITY_STATUSES,
    METRIC_POLICY_CONTRACT_ERROR_CODES,
    OPAQUE_ID_MAX_LENGTH,
    QUALITY_DELTA_KEYS,
    applicability_reason_code,
    as_list,
    boolish,
    discover_contract,
    legacy_applicability_projection,
    number_value,
    opaque_id,
    opaque_id_list_valid,
    policy_items,
    policy_items_contract,
    read_json,
)
from .output_delta.gate import (
    numeric_metric_value,
    quality_delta_gate,
    quality_metric_value,
)
from .output_delta.policy import (
    explicit_quality_delta_policy,
    normalize_metric_applicability,
    normalize_quality_delta_policy,
)
from .output_delta.provider import (
    normalize_provider_result,
    provider_entry,
    rel_path,
    run_provider,
)

__all__ = [
    "DEFAULT_CONTRACT_PATHS",
    "METRIC_APPLICABILITY_STATUSES",
    "METRIC_POLICY_CONTRACT_ERROR_CODES",
    "OPAQUE_ID_MAX_LENGTH",
    "QUALITY_DELTA_KEYS",
    "applicability_reason_code",
    "as_list",
    "boolish",
    "discover_contract",
    "explicit_quality_delta_policy",
    "legacy_applicability_projection",
    "main",
    "normalize_metric_applicability",
    "normalize_provider_result",
    "normalize_quality_delta_policy",
    "number_value",
    "numeric_metric_value",
    "opaque_id",
    "opaque_id_list_valid",
    "policy_items",
    "policy_items_contract",
    "provider_entry",
    "quality_delta_gate",
    "quality_metric_value",
    "read_json",
    "rel_path",
    "run_provider",
]


if __name__ == "__main__":
    raise SystemExit(main())
