"""Compile a small semantic operation seed into closed authority inputs.

The compiler is deliberately non-authoritative: it derives mechanical fields from
the owner manifest and current workspace bytes, but it never creates a source
approval, grant, decision, or reservation.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .canonical import (
    normalized_time,
    object_sha256,
    resolve_workspace_path,
    sha256_file,
)
from .contracts import (
    DECISION_CLASSES,
    MUTATION_CLASSES,
    REVERSIBILITY,
    RISK_TIERS,
    risk_value,
    validate_request,
)
from .evaluation_context import (
    validate_evaluation_context,
    validate_recorded_evaluation_context,
)
from .operations import default_skills_root, load_operation, validate_manifest
from .operation_request import build_request


COMPILATION_KEYS = {
    "schema_version",
    "artifact_kind",
    "compiled_at",
    "seed_fingerprint",
    "operation_manifest",
    "request",
    "request_sha256",
    "evaluation_context",
    "evaluation_context_sha256",
    "field_provenance",
    "source_and_grant_requirements",
    "compilation_fingerprint",
}
SEED_KEYS = {
    "skill_id",
    "skill_version",
    "operation_id",
    "operation_version",
    "subject",
    "scope",
    "actor_rank",
    "intent_type",
    "cardinality_requested",
    "use_budget_requested",
    "reservation_units",
    "context",
    "session_ceiling",
    "goal_autonomy_envelope",
    "classification",
    "composition_receipt",
}
SUBJECT_SEED_KEYS = {"ref", "revision", "kind"}
SCOPE_KEYS = {"cycle_id", "task_id", "pack_id"}
CONTEXT_SEED_KEYS = {
    "external_input_status",
    "goal_truth_status",
    "risk_acceptance_status",
    "design_selection_status",
    "external_input_evidence_ref",
    "risk_acceptance_evidence_ref",
    "design_selection_evidence_ref",
}
SESSION_SEED_KEYS = {"capabilities", "risk_ceiling", "mutation_classes", "evidence_id"}
ENVELOPE_SEED_KEYS = {"envelope_id", "capabilities", "risk_ceiling",
                      "decision_classes", "subjects", "operations", "source_ref"}
CLASSIFICATION_KEYS = {
    "required_capabilities",
    "effect_class",
    "data_class",
    "mutation_class",
    "reversibility",
    "risk_tier",
    "decision_class",
    "subject_kind",
}

def _closed(value: Any, allowed: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be an object.")
    extra = sorted(set(value) - allowed)
    if extra:
        raise SystemExit(f"{label} contains unknown fields: {', '.join(extra)}")
    return value


def _required(value: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(field for field in fields if field not in value)
    if missing:
        raise SystemExit(f"{label} is missing fields: {', '.join(missing)}")


def _exact_id(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 128 or "*" in normalized:
        raise SystemExit(f"{label} must be a bounded exact identifier.")
    return normalized


def _binding(root: Path, ref: Any, label: str) -> dict[str, str]:
    path = resolve_workspace_path(root, ref, label)
    return {"ref": str(ref), "sha256": sha256_file(path)}


def _select_manifest(
    seed: dict[str, Any], skills_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    skill_id = _exact_id(seed.get("skill_id"), "skill_id")
    manifest_path = resolve_workspace_path(
        skills_root,
        f"{skill_id}/authority.operations.json",
        "operation manifest",
    )
    try:
        import json

        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Operation manifest is unreadable: {exc}") from exc
    if not isinstance(raw, dict):
        raise SystemExit("Operation manifest must be an object.")
    manifest = validate_manifest(raw, manifest_path)
    if seed.get("skill_version") not in {None, manifest["skill_version"]}:
        raise SystemExit("skill_version conflicts with the current owner manifest.")
    operation_id = _exact_id(seed.get("operation_id"), "operation_id")
    candidates = [
        row
        for row in manifest["operations"]
        if row["operation_id"] == operation_id
        and seed.get("operation_version") in {None, row["operation_version"]}
    ]
    if len(candidates) != 1:
        raise SystemExit(
            "operation identity must select exactly one current manifest row."
        )
    binding = {
        "ref": manifest_path.relative_to(skills_root).as_posix(),
        "sha256": sha256_file(manifest_path),
    }
    return manifest, candidates[0], binding


def _choose(
    runtime: dict[str, Any], field: str, allowed: list[str], label: str,
) -> str:
    selected = runtime.get(field)
    if selected is None:
        if len(allowed) != 1:
            raise SystemExit(f"{label} is ambiguous; select one manifest value.")
        return allowed[0]
    selected = str(selected)
    if selected not in allowed:
        raise SystemExit(f"{label} is absent from the owner manifest.")
    return selected


def _classify(
    seed: dict[str, Any], operation: dict[str, Any], subject: dict[str, Any],
) -> dict[str, Any]:
    runtime = _closed(seed.get("classification", {}), CLASSIFICATION_KEYS,
                      "classification")
    manifest_capabilities = set(operation["required_capabilities"])
    extra_capabilities = runtime.get("required_capabilities", [])
    if not isinstance(extra_capabilities, list) or any(
        not isinstance(item, str) or not item for item in extra_capabilities
    ):
        raise SystemExit("classification.required_capabilities must be a string list.")
    capabilities = sorted(manifest_capabilities | set(extra_capabilities))

    risk = str(runtime.get("risk_tier", operation["risk_floor"]))
    if risk not in RISK_TIERS or risk_value(risk) < risk_value(operation["risk_floor"]):
        raise SystemExit("classification.risk_tier cannot lower the manifest floor.")
    mutation = str(runtime.get("mutation_class", operation["mutation_class"]))
    mutation_rank = {value: index for index, value in enumerate(MUTATION_CLASSES)}
    if mutation not in mutation_rank or mutation_rank[mutation] < mutation_rank[
        operation["mutation_class"]
    ]:
        raise SystemExit("classification.mutation_class cannot lower the manifest floor.")
    reversibility = str(runtime.get("reversibility", operation["reversibility"]))
    reversibility_rank = {value: index for index, value in enumerate(REVERSIBILITY)}
    if (
        reversibility not in reversibility_rank
        or reversibility_rank[reversibility]
        < reversibility_rank[operation["reversibility"]]
    ):
        raise SystemExit("classification.reversibility cannot overstate reversibility.")
    decision = str(runtime.get("decision_class", operation["decision_class"]))
    if decision not in DECISION_CLASSES or decision != operation["decision_class"]:
        raise SystemExit("classification.decision_class must match the owner manifest.")
    kind = _choose(runtime, "subject_kind", operation["subject_kinds"], "subject kind")
    if subject.get("kind") not in {None, kind}:
        raise SystemExit("subject.kind conflicts with the owner manifest selection.")
    return {
        "required_capabilities": capabilities,
        "effect_class": _choose(
            runtime, "effect_class", operation["effect_classes"], "effect class"
        ),
        "data_class": _choose(
            runtime, "data_class", operation["data_classes"], "data class"
        ),
        "mutation_class": mutation,
        "reversibility": reversibility,
        "risk_tier": risk,
        "decision_class": decision,
        "subject_kind": kind,
    }


def _evidence_binding(
    root: Path, context: dict[str, Any], field: str,
) -> dict[str, str] | None:
    ref = context.get(f"{field}_ref")
    return None if ref is None else _binding(root, ref, f"context.{field}_ref")


def _request_context(root: Path, raw: Any) -> dict[str, Any]:
    context = _closed(raw, CONTEXT_SEED_KEYS, "context")
    _required(
        context,
        {
            "external_input_status",
            "goal_truth_status",
            "risk_acceptance_status",
            "design_selection_status",
        },
        "context",
    )
    return {
        "external_input_status": context["external_input_status"],
        "goal_truth_status": context["goal_truth_status"],
        "risk_acceptance_status": context["risk_acceptance_status"],
        "design_selection_status": context["design_selection_status"],
        "external_input_evidence": _evidence_binding(
            root, context, "external_input_evidence"
        ),
        "risk_acceptance_evidence": _evidence_binding(
            root, context, "risk_acceptance_evidence"
        ),
        "design_selection_evidence": _evidence_binding(
            root, context, "design_selection_evidence"
        ),
    }


def _evaluation_context(
    root: Path,
    seed: dict[str, Any],
    classification: dict[str, Any],
    subject_digest: str,
    operation_identity: str,
) -> dict[str, Any]:
    session = _closed(seed.get("session_ceiling"), SESSION_SEED_KEYS,
                      "session_ceiling")
    envelope = _closed(seed.get("goal_autonomy_envelope"), ENVELOPE_SEED_KEYS,
                       "goal_autonomy_envelope")
    _required(session, SESSION_SEED_KEYS, "session_ceiling")
    _required(envelope, ENVELOPE_SEED_KEYS, "goal_autonomy_envelope")
    candidate = {
        "schema_version": 2,
        "context_kind": "authority_evaluation",
        "session_ceiling": {
            **copy.deepcopy(session),
            "evidence_id": _exact_id(
                session["evidence_id"], "session_ceiling.evidence_id"
            ),
        },
        "goal_autonomy_envelope": {
            **{key: copy.deepcopy(envelope[key]) for key in ENVELOPE_SEED_KEYS
               if key != "source_ref"},
            "envelope_id": _exact_id(
                envelope["envelope_id"], "goal_autonomy_envelope.envelope_id"
            ),
            "source_binding": _binding(
                root, envelope["source_ref"], "goal autonomy source"
            ),
        },
    }
    context = validate_recorded_evaluation_context(candidate)
    session = context["session_ceiling"]
    envelope = context["goal_autonomy_envelope"]
    request_capabilities = set(classification["required_capabilities"])
    if not request_capabilities.issubset(set(session["capabilities"])):
        raise SystemExit("session ceiling does not cover requested capabilities.")
    if not request_capabilities.issubset(set(envelope["capabilities"])):
        raise SystemExit("goal envelope does not cover requested capabilities.")
    if classification["mutation_class"] not in session["mutation_classes"]:
        raise SystemExit("session ceiling does not cover requested mutation class.")
    if risk_value(classification["risk_tier"]) > risk_value(session["risk_ceiling"]):
        raise SystemExit("session risk ceiling is below the request.")
    if risk_value(classification["risk_tier"]) > risk_value(envelope["risk_ceiling"]):
        raise SystemExit("goal risk ceiling is below the request.")
    if classification["decision_class"] not in envelope["decision_classes"]:
        raise SystemExit("goal envelope does not cover requested decision class.")
    if subject_digest not in envelope["subjects"]:
        raise SystemExit("goal envelope does not bind the exact subject digest.")
    if operation_identity not in envelope["operations"]:
        raise SystemExit("goal envelope does not bind the exact operation identity.")
    return context


def compile_operation(
    root: Path,
    seed: dict[str, Any],
    *,
    compiled_at: str,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Return one deterministic, validated, non-authoritative compilation."""

    root = root.resolve()
    seed = _closed(copy.deepcopy(seed), SEED_KEYS, "operation seed")
    _required(
        seed,
        {
            "skill_id",
            "operation_id",
            "subject",
            "scope",
            "actor_rank",
            "context",
            "session_ceiling",
            "goal_autonomy_envelope",
        },
        "operation seed",
    )
    at = normalized_time(compiled_at, "compiled_at")
    selected_skills_root = (skills_root or default_skills_root()).resolve()
    manifest, operation, manifest_binding = _select_manifest(seed, selected_skills_root)
    subject_seed = _closed(seed["subject"], SUBJECT_SEED_KEYS, "subject")
    _required(subject_seed, {"ref", "revision"}, "subject")
    subject_path = resolve_workspace_path(root, subject_seed["ref"], "subject")
    classification = _classify(seed, operation, subject_seed)
    scope = _closed(seed["scope"], SCOPE_KEYS, "scope")
    operation_identity = ":".join(
        (
            manifest["skill_id"],
            manifest["skill_version"],
            operation["operation_id"],
            operation["operation_version"],
        )
    )
    context = _evaluation_context(
        root,
        seed,
        classification,
        sha256_file(subject_path),
        operation_identity,
    )
    request_context = _request_context(root, seed["context"])
    seed_core = {
        "compiled_at": at,
        "operation_manifest": manifest_binding,
        "operation": operation,
        "subject": {
            "ref": str(subject_seed["ref"]),
            "digest": sha256_file(subject_path),
            "revision": str(subject_seed["revision"]),
            "kind": classification["subject_kind"],
        },
        "scope": {key: scope.get(key) for key in sorted(SCOPE_KEYS)},
        "actor_rank": seed["actor_rank"],
        "classification": classification,
        "request_context": request_context,
        "evaluation_context": context,
        "intent_type": seed.get("intent_type", "grant_authority"),
        "cardinality_requested": seed.get("cardinality_requested", "single_use"),
        "use_budget_requested": seed.get("use_budget_requested", 1),
        "reservation_units": seed.get("reservation_units", 1),
        "composition_receipt": seed.get("composition_receipt"),
    }
    seed_fingerprint = object_sha256(seed_core)
    request = build_request(
        manifest, operation, seed_core, classification, seed_fingerprint
    )
    context = validate_evaluation_context(root, context)
    body = {
        "schema_version": 1,
        "artifact_kind": "authority_operation_compilation",
        "compiled_at": at,
        "seed_fingerprint": seed_fingerprint,
        "operation_manifest": manifest_binding,
        "request": request,
        "request_sha256": object_sha256(request),
        "evaluation_context": context,
        "evaluation_context_sha256": object_sha256(context),
        "field_provenance": {
            "manifest_derived": [
                "skill_version",
                "operation_version",
                "required_capabilities",
                "effect_class",
                "data_class",
                "mutation_class",
                "reversibility",
                "risk_tier",
                "decision_class",
                "subject.kind",
            ],
            "workspace_derived": [
                "subject.digest",
                "request.context.*_evidence.sha256",
                "goal_autonomy_envelope.source_binding.sha256",
            ],
            "seed_bound": [
                "operation identity",
                "subject.ref",
                "subject.revision",
                "scope",
                "independent decision axes",
                "session and goal ceilings",
            ],
            "asserted_untrusted": [
                "session_ceiling",
                "goal_autonomy_envelope",
            ],
            "authority_effect": "none; evaluator must verify independent authority",
        },
        "source_and_grant_requirements": {
            "authority_applicability": operation["authority_applicability"],
            "authorization_mechanism": operation["authorization_mechanism"],
            "source_rank_floor": operation["source_rank_floor"],
            "requires_source_approval": operation["authority_applicability"] != "none",
            "requires_grant": operation["authorization_mechanism"] == "grant",
            "self_authorizing": False,
        },
    }
    return {**body, "compilation_fingerprint": object_sha256(body)}


def validate_compilation(value: Any) -> dict[str, Any]:
    compilation = _closed(value, COMPILATION_KEYS, "operation compilation")
    _required(compilation, COMPILATION_KEYS, "operation compilation")
    if (
        compilation["schema_version"] != 1
        or compilation["artifact_kind"] != "authority_operation_compilation"
    ):
        raise SystemExit("Unsupported authority operation compilation contract.")
    request = validate_request(compilation["request"])
    context = validate_recorded_evaluation_context(compilation["evaluation_context"])
    if compilation["request_sha256"] != object_sha256(request):
        raise SystemExit("Compiled request digest mismatch.")
    if compilation["evaluation_context_sha256"] != object_sha256(context):
        raise SystemExit("Compiled evaluation context digest mismatch.")
    requirements = compilation["source_and_grant_requirements"]
    if not isinstance(requirements, dict) or requirements.get("self_authorizing") is not False:
        raise SystemExit("Compilation must remain explicitly non-authoritative.")
    body = {key: copy.deepcopy(compilation[key]) for key in COMPILATION_KEYS
            if key != "compilation_fingerprint"}
    if compilation["compilation_fingerprint"] != object_sha256(body):
        raise SystemExit("Operation compilation fingerprint mismatch.")
    return {**body, "compilation_fingerprint": compilation["compilation_fingerprint"]}


def compilation_inputs(
    root: Path,
    value: Any,
    *,
    skills_root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    compilation = validate_compilation(value)
    request = compilation["request"]
    context = validate_evaluation_context(root.resolve(), compilation["evaluation_context"])
    operation, binding = load_operation(
        request["skill_id"],
        request["skill_version"],
        request["operation_id"],
        request["operation_version"],
        skills_root=(skills_root or default_skills_root()).resolve(),
    )
    if operation is None or binding != compilation["operation_manifest"]:
        raise SystemExit("Compiled operation manifest is stale; recompile required.")
    subject = resolve_workspace_path(root.resolve(), request["subject"]["ref"], "subject")
    if sha256_file(subject) != request["subject"]["digest"]:
        raise SystemExit("Compiled subject is stale; recompile required.")
    return request, context


__all__ = ["compilation_inputs", "compile_operation", "validate_compilation"]
