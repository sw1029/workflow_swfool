from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from .derive_checks.shared import (  # noqa: F401 - legacy compatibility surface
    ADOPTION_AXIS_TASK_KINDS,
    BLOCKER_CONTRACT_REPAIR_TASK_KINDS,
    CLASSIFICATION_REPAIR_TASK_KINDS,
    COLLECTION_CONSUMPTION_TASK_KINDS,
    COMMAND_PROVENANCE_TASK_KINDS,
    CONTRACT_SATISFIABILITY_TASK_KINDS,
    CURRENT_LANE_TASK_KINDS,
    CYCLE_REACHABILITY_TASK_KINDS,
    DECISION_FRESHNESS_TASK_KINDS,
    ENVELOPE_THAW_TASK_KINDS,
    EXECUTION_SCOPE_RECOVERY_TASK_KINDS,
    EXECUTION_STARVATION_STATUSES,
    EXPECTATION_REBASELINE_TASK_KINDS,
    HANDOFF_APPLICABILITY,
    HARVEST_GATE_TASK_KINDS,
    INSTRUMENTATION_TASK_KINDS,
    METRIC_BASIS_TASK_KINDS,
    OPAQUE_ID_MAX_LENGTH,
    PACK_DISPOSITIONS,
    PACK_MUTATION_DISPOSITIONS,
    PARITY_AXIS_TASK_KINDS,
    PORTFOLIO_QUOTA_TASK_KINDS,
    PRODUCER_SUPPLY_TASK_KINDS,
    Path,
    REHARVEST_TASK_KINDS,
    REPORT_KEY_REPAIR_TASK_KINDS,
    RESOLUTION_REPAIR_TASK_KINDS,
    SCENARIO_REPAIR_TASK_KINDS,
    SCENARIO_SUPPLY_TASK_KINDS,
    STOCHASTIC_CONTRACT_TASK_KINDS,
    SURFACE_FIELD_TASK_KINDS,
    _bounded_id_items,
    _bounded_opaque_id,
    _declared_values,
    _file_digest,
    _local_packet,
    _nonnegative_int,
    _packet_scalar,
    _workspace_root,
    active_task_pack_present,
    add,
    advice_handling_rationale_present,
    allowed_task_kinds_from_basis,
    annotations,
    boolish,
    first_present,
    float_value,
    forced_task_kind,
    has_value,
    hashlib,
    json,
    list_values,
    non_empty,
    nonzero_scalar,
    number_value,
    selected_disposition,
    selected_task_kind_value,
    task_pack_in_scope,
    task_pack_queue,
    value_for,
)
from .derive_checks.shared import __all__ as __shared_exports


__all__ = (*__shared_exports, "DeriveRule")


class DeriveRule(TargetContractRule):
    """Validate next-task selection against active routing and evidence gates."""

    targets = frozenset({"derive"})

    def check(self, context: RuleContext) -> None:
        from .derive_checks import run_checks
        from .acceptance_satisfiability import validate_acceptance_satisfiability

        validate_acceptance_satisfiability(context)
        run_checks(context)
