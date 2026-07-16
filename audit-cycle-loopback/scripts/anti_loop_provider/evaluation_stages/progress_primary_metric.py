from __future__ import annotations

from ..runtime_dependencies import (
    call_adapter,
    previous_primary_metric_value,
    rel_path,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_progress_primary_metric(frame: _EvaluationFrame) -> None:
    (
        current_root_family_key, current_root_key, current_substance, decision_artifact_ref,
        domain_adapter, evidence_provenance, family_key, latest, output_delta, paths,
        quality, root, runner_validation,
    ) = frame.require(
        'current_root_family_key', 'current_root_key', 'current_substance',
        'decision_artifact_ref', 'domain_adapter', 'evidence_provenance', 'family_key',
        'latest', 'output_delta', 'paths', 'quality', 'root', 'runner_validation',
    )
    primary_metric_value, primary_metric_error = call_adapter(
        domain_adapter,
        "primary_metric",
        root=root,
        artifact_paths=[rel_path(root, path) for path in paths],
        quality_vector=quality,
        substance_metrics=current_substance,
        output_delta=output_delta,
        runner_validation=runner_validation,
        family_key=family_key,
        root_key=current_root_key,
        root_family_key=current_root_family_key,
        previous_primary_metric=previous_primary_metric_value(latest),
        evidence_provenance=evidence_provenance,
        decision_artifact_ref=decision_artifact_ref,
    )
    frame.update({
        "primary_metric_error": primary_metric_error,
        "primary_metric_value": primary_metric_value,
    })
