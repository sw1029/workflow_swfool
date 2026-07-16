from __future__ import annotations

from ..runtime_dependencies import (
    apply_evidence_provenance_filter,
    rel_path,
    verification_source_separation_gate,
)

from ..evaluation_frame import _EvaluationFrame


def _evaluate_failure_provenance(frame: _EvaluationFrame) -> None:
    (
        coverage_gate, evidence_provenance, evidence_provenance_provided,
        evidence_provenance_value, paths, root, substance_gate,
    ) = frame.require(
        'coverage_gate', 'evidence_provenance', 'evidence_provenance_provided',
        'evidence_provenance_value', 'paths', 'root', 'substance_gate',
    )
    coverage_gate, independent_coverage_fields, attested_coverage_fields, coverage_self_grounded_fields = apply_evidence_provenance_filter(
        coverage_gate,
        improved_key="improved_fields",
        pass_key="quality_delta_pass",
        provenance=evidence_provenance,
        hook_provided=evidence_provenance_provided,
    )
    substance_gate, independent_substance_fields, attested_substance_fields, substance_self_grounded_fields = apply_evidence_provenance_filter(
        substance_gate,
        improved_key="improved_axes",
        pass_key="substance_delta_pass",
        provenance=evidence_provenance,
        hook_provided=evidence_provenance_provided,
    )
    source_separation_gate = verification_source_separation_gate(
        provenance_value=evidence_provenance_value,
        verified_artifact_paths=[rel_path(root, path) for path in paths],
        independently_verified_fields=[*independent_coverage_fields, *independent_substance_fields],
        self_grounded_fields=[*coverage_self_grounded_fields, *substance_self_grounded_fields],
    )
    downgraded_fields = set(source_separation_gate.get("independently_verified_downgraded_fields") or [])
    self_grounded_fields = set(source_separation_gate.get("self_grounded_fields") or [])
    if downgraded_fields:
        coverage_downgraded = [field for field in independent_coverage_fields if field in downgraded_fields]
        substance_downgraded = [field for field in independent_substance_fields if field in downgraded_fields]
        coverage_self_grounded = [field for field in coverage_downgraded if field in self_grounded_fields]
        substance_self_grounded = [field for field in substance_downgraded if field in self_grounded_fields]
        independent_coverage_fields = [field for field in independent_coverage_fields if field not in downgraded_fields]
        independent_substance_fields = [field for field in independent_substance_fields if field not in downgraded_fields]
        attested_coverage_fields = sorted(set(attested_coverage_fields + [field for field in coverage_downgraded if field not in self_grounded_fields]))
        attested_substance_fields = sorted(set(attested_substance_fields + [field for field in substance_downgraded if field not in self_grounded_fields]))
        if coverage_downgraded:
            coverage_gate["improved_fields"] = independent_coverage_fields
            coverage_gate["quality_delta_pass"] = bool(independent_coverage_fields)
            coverage_gate["status"] = "pass" if independent_coverage_fields else "block"
            coverage_gate["independently_verified_fields"] = independent_coverage_fields
            coverage_gate["producer_attested_fields"] = attested_coverage_fields
            coverage_gate["self_grounded_fields"] = coverage_self_grounded
            coverage_gate["attested_only_movement"] = bool(attested_coverage_fields and not independent_coverage_fields)
        if substance_downgraded:
            substance_gate["improved_axes"] = independent_substance_fields
            substance_gate["substance_delta_pass"] = bool(independent_substance_fields)
            substance_gate["status"] = "pass" if independent_substance_fields else "block"
            substance_gate["independently_verified_fields"] = independent_substance_fields
            substance_gate["producer_attested_fields"] = attested_substance_fields
            substance_gate["self_grounded_fields"] = substance_self_grounded
            substance_gate["attested_only_movement"] = bool(attested_substance_fields and not independent_substance_fields)
    frame.update({
        "attested_coverage_fields": attested_coverage_fields,
        "attested_substance_fields": attested_substance_fields,
        "coverage_gate": coverage_gate,
        "independent_coverage_fields": independent_coverage_fields,
        "independent_substance_fields": independent_substance_fields,
        "self_grounded_fields": self_grounded_fields,
        "source_separation_gate": source_separation_gate,
        "substance_gate": substance_gate,
    })
