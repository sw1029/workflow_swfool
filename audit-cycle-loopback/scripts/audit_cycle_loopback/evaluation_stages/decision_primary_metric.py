from __future__ import annotations

from ..runtime_dependencies import (
    normalize_gate_key,
    normalize_primary_metric_gate,
    normalize_provenance_label,
    rel_path,
    verification_source_separation_gate,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_decision_primary_metric(frame: _EvaluationFrame) -> None:
    (
        args, bind_artifact_gate, decision_artifact_ref, evidence_provenance,
        evidence_provenance_provided, evidence_provenance_value, paths, primary_metric_error,
        primary_metric_value, registry_rows, root,
    ) = frame.require(
        'args', 'bind_artifact_gate', 'decision_artifact_ref', 'evidence_provenance',
        'evidence_provenance_provided', 'evidence_provenance_value', 'paths',
        'primary_metric_error', 'primary_metric_value', 'registry_rows', 'root',
    )
    primary_metric_source = (
        primary_metric_value.get("primary_metric")
        if isinstance(primary_metric_value, dict)
        and isinstance(primary_metric_value.get("primary_metric"), dict)
        else primary_metric_value
    )
    primary_metric_id = str(
        (
            primary_metric_source.get("goal_axis_id")
            or primary_metric_source.get("axis_id")
            or primary_metric_source.get("metric_id")
            or ""
        )
        if isinstance(primary_metric_source, dict)
        else ""
    ).strip()
    primary_metric_declared_provenance = normalize_provenance_label(
        evidence_provenance.get(normalize_gate_key(primary_metric_id))
        or evidence_provenance.get(normalize_gate_key("primary_metric"))
    )
    primary_metric_source_separation_gate = verification_source_separation_gate(
        provenance_value=evidence_provenance_value,
        verified_artifact_paths=[rel_path(root, path) for path in paths],
        independently_verified_fields=(
            [primary_metric_id]
            if primary_metric_id
            and evidence_provenance_provided
            and primary_metric_declared_provenance == "independently_verified"
            else []
        ),
    )
    primary_metric_gate = normalize_primary_metric_gate(
        primary_metric_value,
        rows=registry_rows,
        cap=getattr(args, "cumulative_chain_streak_cap", None),
        epsilon=args.epsilon,
        provenance=evidence_provenance,
        provenance_hook_provided=evidence_provenance_provided,
        source_separation_gate=primary_metric_source_separation_gate,
        expected_artifact_ref=decision_artifact_ref,
    )
    primary_metric_gate = bind_artifact_gate(
        "primary_metric_gate",
        primary_metric_gate,
        pass_fields=("primary_metric_high_water_moved", "primary_metric_stalled"),
        computed_from_decision_artifact=True,
    )
    if primary_metric_error:
        primary_metric_gate["adapter_error"] = primary_metric_error
    frame.update({
        "primary_metric_gate": primary_metric_gate,
        "primary_metric_source_separation_gate": primary_metric_source_separation_gate,
    })
