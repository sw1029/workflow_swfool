"""Registry, finalized-state, and projection operations."""

from __future__ import annotations

from .registry_identity import (
    default_high_water,
    decision_input_state_fingerprint,
    content_bound_attempt_identity,
    legacy_content_bound_attempt_identity,
    logical_attempt_key,
    attempt_revision_value,
    canonical_json_sha256,
)

from .durable_projection import (
    bounded_durable_projection,
)

from .finalized_state import (
    load_verified_finalized_loopback_state,
    finalized_projection_rows,
    finalized_seal_projection,
)

from .family_registry import (
    load_registry,
    compact_registry,
    write_registry,
    normalize_hook_id,
    hook_demand_threshold_from_value,
    latest_adapter_hook_demand,
    merge_adapter_hook_demand,
)

from .root_cause_registry import (
    compact_root_cause_ledger,
    append_root_cause_ledger,
    feed_exhausted_family_seal,
    project_exhausted_family_seal,
    exhausted_family_seal_record,
)

__all__ = (
    "default_high_water",
    "decision_input_state_fingerprint",
    "content_bound_attempt_identity",
    "legacy_content_bound_attempt_identity",
    "logical_attempt_key",
    "attempt_revision_value",
    "canonical_json_sha256",
    "bounded_durable_projection",
    "load_verified_finalized_loopback_state",
    "finalized_projection_rows",
    "finalized_seal_projection",
    "load_registry",
    "compact_registry",
    "write_registry",
    "normalize_hook_id",
    "hook_demand_threshold_from_value",
    "latest_adapter_hook_demand",
    "merge_adapter_hook_demand",
    "compact_root_cause_ledger",
    "append_root_cause_ledger",
    "feed_exhausted_family_seal",
    "project_exhausted_family_seal",
    "exhausted_family_seal_record",
)
