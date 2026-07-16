from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


POLICY_PATH = (
    Path(__file__).resolve().parents[3] / "references" / "model-effort-profiles.json"
)
MODEL_REF_PREFIX = "model_ref:"
EVIDENCE_ID_FIELDS = ("event_id", "run_id", "artifact_id", "ledger_event_id")


def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    models = policy.get("models")
    tiers = policy.get("tiers")
    binding_contract = policy.get("model_binding_contract")
    if not isinstance(models, dict) or not models:
        raise ValueError("routing policy models must be a non-empty object")
    model_refs = {str(value) for value in models.values()}
    if any(not value.startswith(MODEL_REF_PREFIX) for value in model_refs):
        raise ValueError(
            "global routing policy models must use abstract model_ref values"
        )
    if not isinstance(tiers, dict) or not tiers:
        raise ValueError("routing policy tiers must be a non-empty object")
    for tier_id, tier in tiers.items():
        if not isinstance(tier, dict) or str(tier.get("model") or "") not in model_refs:
            raise ValueError(f"routing tier {tier_id} must reference policy models")
    if not isinstance(binding_contract, dict):
        raise ValueError("routing policy model_binding_contract is required")
    if binding_contract.get("request_field") != "model_bindings":
        raise ValueError("routing policy model binding request field is unsupported")
    max_policy = policy.get("max_escalation")
    if (
        not isinstance(max_policy, dict)
        or str(max_policy.get("model") or "") not in model_refs
    ):
        raise ValueError("max escalation must use a policy model_ref")
    return policy


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("routing policy must be a JSON object")
    return validate_policy(value)


def load_json_arg(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    if value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    stripped = value.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    path = Path(stripped)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(stripped)


def normalized_signals(
    value: Any, allowed: set[str]
) -> tuple[dict[str, bool], list[str]]:
    if isinstance(value, list):
        raw = {str(item): True for item in value}
    elif isinstance(value, dict):
        raw = {str(key): bool(item) for key, item in value.items()}
    else:
        raw = {}
    unknown = sorted(key for key in raw if key not in allowed)
    return {key: raw.get(key, False) for key in allowed}, unknown


def evidence_present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return any(evidence_present(item) for item in value)
    if isinstance(value, dict):
        return any(evidence_present(item) for item in value.values())
    return value is not None and value is not False


def valid_evidence_reference(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value) and all(valid_evidence_reference(item) for item in value)
    if not isinstance(value, dict):
        return False
    return any(evidence_present(value.get(field)) for field in EVIDENCE_ID_FIELDS)


def sanitized_evidence_reference(value: Any) -> Any:
    if isinstance(value, list):
        return [
            sanitized_evidence_reference(item)
            for item in value
            if valid_evidence_reference(item)
        ]
    if not isinstance(value, dict):
        return None
    return {
        field: value[field]
        for field in EVIDENCE_ID_FIELDS
        if evidence_present(value.get(field))
    }


def sanitized_prior_tier5_evidence(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    allowed = {
        *EVIDENCE_ID_FIELDS,
        "profile_id",
        "routing_tier",
        "requested_model_ref",
        "requested_model",
        "model_configuration_status",
        "requested_reasoning_effort",
        "unresolved_finding_id",
    }
    return {key: item for key, item in value.items() if key in allowed}


def receipt_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_model_binding(
    model_ref: str,
    request: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[str, str, dict[str, str] | None, list[dict[str, Any]]]:
    contract = policy["model_binding_contract"]
    raw_bindings = request.get(str(contract["request_field"]))
    if raw_bindings is None:
        return model_ref, "reference_only", None, []
    if not isinstance(raw_bindings, dict):
        return model_ref, "invalid", None, [{"code": "model_bindings_invalid"}]

    known_refs = {str(value) for value in policy["models"].values()}
    unknown_refs = sorted(
        str(key) for key in raw_bindings if str(key) not in known_refs
    )
    violations: list[dict[str, Any]] = []
    if unknown_refs:
        violations.append(
            {"code": "unknown_model_binding_refs", "model_refs": unknown_refs}
        )

    binding = raw_bindings.get(model_ref)
    if not isinstance(binding, dict):
        violations.append({"code": "model_binding_missing", "model_ref": model_ref})
        return model_ref, "invalid", None, violations

    model = binding.get("model")
    binding_id = binding.get("binding_id")
    source = binding.get("source")
    source_values = {str(item) for item in contract.get("binding_source_values", [])}
    if (
        not isinstance(model, str)
        or not model.strip()
        or model.strip().startswith(MODEL_REF_PREFIX)
    ):
        violations.append(
            {"code": "model_binding_model_invalid", "model_ref": model_ref}
        )
    if not isinstance(binding_id, str) or not binding_id.strip():
        violations.append({"code": "model_binding_id_missing", "model_ref": model_ref})
    if str(source or "") not in source_values:
        violations.append(
            {
                "code": "model_binding_source_invalid",
                "model_ref": model_ref,
                "source": source,
            }
        )
    if violations:
        return model_ref, "invalid", None, violations
    receipt_body = {
        "model_ref": model_ref,
        "model_sha256": hashlib.sha256(model.strip().encode("utf-8")).hexdigest(),
        "binding_id": binding_id.strip(),
        "source": str(source),
    }
    receipt = {**receipt_body, "receipt_sha256": receipt_hash(receipt_body)}
    return model.strip(), "resolved", receipt, []


def valid_prior_tier5_evidence(value: Any, policy: dict[str, Any]) -> bool:
    if not isinstance(value, dict) or not valid_evidence_reference(value):
        return False
    max_policy = policy["max_escalation"]
    return (
        str(value.get("profile_id") or "")
        == str(max_policy["required_evidence_profile"])
        and value.get("routing_tier") == int(max_policy["tier"])
        and str(value.get("requested_model_ref") or value.get("requested_model") or "")
        == str(max_policy["model"])
        and str(value.get("requested_reasoning_effort") or "")
        == str(policy["tiers"][str(max_policy["tier"])]["effort"])
        and evidence_present(value.get("unresolved_finding_id"))
    )


def rule_matches(rule: dict[str, Any], signals: dict[str, bool]) -> bool:
    when_all = [str(item) for item in rule.get("when_all", [])]
    when_any = [str(item) for item in rule.get("when_any", [])]
    return (not when_all or all(signals.get(item, False) for item in when_all)) and (
        not when_any or any(signals.get(item, False) for item in when_any)
    )
