from __future__ import annotations

from . import failure_baseline
from . import failure_family
from . import failure_surface
from . import failure_diagnostics
from . import failure_metrics
from . import failure_provenance
from . import failure_consumer
from . import progress_evidence
from . import progress_reachability
from . import progress_measurement
from . import progress_blocker
from . import progress_semantics
from . import setup_adapter
from . import setup_artifact
from . import setup_budgets
from . import setup_consumer
from . import setup_external_gates
from . import setup_identity
from . import setup_quality
from . import setup_registry
from . import progress_correction
from . import progress_adapter_demand
from . import progress_chain
from . import progress_primary_metric
from . import decision_primary_metric
from . import decision_retarget
from . import decision_disposition
from . import decision_verifier
from . import decision_task_options
from . import finalize_identity
from . import finalize_consumer
from . import finalize_replay

_STAGE_MODULES = (
    failure_baseline,
    failure_family,
    failure_surface,
    failure_diagnostics,
    failure_metrics,
    failure_provenance,
    failure_consumer,
    progress_evidence,
    progress_reachability,
    progress_measurement,
    progress_blocker,
    progress_semantics,
    setup_registry,
    setup_artifact,
    setup_budgets,
    setup_adapter,
    setup_quality,
    setup_external_gates,
    setup_identity,
    setup_consumer,
    progress_correction,
    progress_adapter_demand,
    progress_chain,
    progress_primary_metric,
    decision_primary_metric,
    decision_retarget,
    decision_disposition,
    decision_verifier,
    decision_task_options,
    finalize_identity,
    finalize_consumer,
    finalize_replay,
)
