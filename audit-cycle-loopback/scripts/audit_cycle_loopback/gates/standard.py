from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import BaseGate, DispositionGate
from .. import acceptance as _acceptance
from .. import failure as _failure
from .. import quality as _quality
from .. import vectors as _vectors
from .. import verification as _verification


GateFunction = Callable[..., dict[str, Any]]


class FunctionGate(BaseGate):
    def __init__(self, name: str, function: GateFunction) -> None:
        self.name = name
        self._function = function

    def compute(self, context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return self._function(**context)


class CoverageQualityDeltaGate(DispositionGate):
    name = 'coverage_quality_delta_gate'

    def compute(self, context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return _quality.coverage_quality_delta_gate(
            context.get('quality', {}),
            context.get('previous_high_water', {}),
            int(context.get('provider_request_count') or 0),
            float(context.get('epsilon') or 1e-9),
            context.get('quality_delta_policy'),
        )


class SubstanceDeltaGate(DispositionGate):
    name = 'substance_delta_gate'

    def compute(self, context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return _vectors.vector_delta_gate(
            gate_name='G-SUBSTANCE',
            current=context.get('current', {}),
            previous=context.get('previous', {}),
            pass_field='substance_delta_pass',
            current_field='current_substance_vector',
            previous_field='previous_substance_vector',
            epsilon=float(context.get('epsilon') or 1e-9),
        )


class AcceptanceReachabilityGate(DispositionGate):
    name = 'acceptance_reachability_gate'

    def compute(self, context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return _acceptance.acceptance_reachability_gate(context.get('value'))


class OracleMetricValidityGate(DispositionGate):
    name = 'oracle_metric_validity_gate'

    def compute(self, context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return _acceptance.oracle_metric_validity_gate(context.get('value'))


class StructureMetricsGate(BaseGate):
    name = 'structure_metrics_gate'

    def compute(self, context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return _vectors.structure_metrics_gate(context.get('value'))


class FailureSurfaceStageGate(DispositionGate):
    name = 'failure_surface_stage_gate'

    def compute(self, context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return _failure.terminal_stage_resolution_gate(
            ladder_value=context.get('ladder_value'),
            classification_map_value=context.get('classification_map_value'),
            contexts=context.get('contexts') or [],
            root_family_key=str(context.get('root_family_key') or 'unknown'),
            dominant_parameter=str(context.get('dominant_parameter') or 'unknown'),
        )


class VerificationSourceSeparationGate(DispositionGate):
    name = 'verification_source_separation_gate'

    def compute(self, context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        return _verification.verification_source_separation_gate(
            provenance_value=context.get('provenance_value'),
            verified_artifact_paths=context.get('verified_artifact_paths') or [],
            independently_verified_fields=context.get('independently_verified_fields') or [],
        )
