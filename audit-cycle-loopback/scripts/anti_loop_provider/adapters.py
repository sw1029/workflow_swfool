from __future__ import annotations

from .common import *

_DOMAIN_ADAPTER_MODULE: Any | None = None

def load_python_module(path: Path, module_name: str) -> Any | None:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        return None
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def domain_adapter_candidate_paths(root: Path, explicit_path: str | None) -> list[Path]:
    candidates: list[Path] = []
    for raw in (explicit_path, os.environ.get(DOMAIN_ADAPTER_ENV), os.environ.get("DOMAIN_ADAPTER_PATH")):
        if not raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        candidates.append(candidate)
    return candidates

def load_domain_adapter(root: Path, explicit_path: str | None) -> tuple[Any | None, str | None, str | None]:
    global _DOMAIN_ADAPTER_MODULE
    if _DOMAIN_ADAPTER_MODULE is not None:
        return _DOMAIN_ADAPTER_MODULE, None, None
    candidates = domain_adapter_candidate_paths(root, explicit_path)
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.as_posix() in seen:
            continue
        seen.add(resolved.as_posix())
        try:
            module = load_python_module(resolved, "task_cycle_domain_adapter")
        except Exception as exc:  # pragma: no cover - defensive import boundary
            return None, resolved.as_posix(), f"domain_adapter_import_failed:{type(exc).__name__}"
        if module is not None:
            _DOMAIN_ADAPTER_MODULE = module
            return module, resolved.as_posix(), None
    if candidates:
        return None, None, "domain_adapter_not_found"
    return None, None, None

def call_adapter(adapter: Any | None, function_name: str, **kwargs: Any) -> tuple[Any, str | None]:
    if adapter is None or not hasattr(adapter, function_name):
        return None, None
    function = getattr(adapter, function_name)
    try:
        signature = inspect.signature(function)
        accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
        if accepts_kwargs:
            return function(**kwargs), None
        accepted = {key: value for key, value in kwargs.items() if key in signature.parameters}
        return function(**accepted), None
    except TypeError:
        try:
            return function(), None
        except Exception as exc:  # pragma: no cover - adapter-owned code
            return None, f"{function_name}_failed:{type(exc).__name__}"
    except Exception as exc:  # pragma: no cover - adapter-owned code
        return None, f"{function_name}_failed:{type(exc).__name__}"

def _load_json_argument(root: Path, value: str | None) -> Any:
    if not value:
        return None
    text = str(value).strip()
    if text.startswith(("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    source = Path(value)
    if not source.is_absolute():
        source = root / source
    try:
        if source.is_file():
            return read_json(source)
    except OSError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

def _paths_from_artifact_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [
            str(
                (item.get("artifact_path_or_store_ref") or item.get("path"))
                if isinstance(item, dict)
                else item
            )
            for item in value
        ]
    if not isinstance(value, dict):
        return []
    paths: list[str] = []
    for key in ("artifact_paths", "artifacts", "reviewed_artifacts"):
        raw = value.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            candidate = (
                item.get("artifact_path_or_store_ref") or item.get("path")
                if isinstance(item, dict)
                else item
            )
            if candidate:
                paths.append(str(candidate))
    return paths

def _artifact_ref_from_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    for key in ("decision_artifact_ref", "artifact_ref", "selected_artifact_ref"):
        if isinstance(value.get(key), dict):
            return dict(value[key])
    if any(key in value for key in ("artifact_id", "artifact_sha256", "artifact_path_or_store_ref")):
        return dict(value)
    return {}

def _normalize_artifact_path(root: Path, value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text or "://" in text or text.lower().startswith("sha256:"):
        return None
    path = Path(text)
    return path if path.is_absolute() else root / path

def _sha256_path(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_artifact_selection(
    root: Path,
    artifact_paths_json: str | None,
    artifact_paths: list[str],
    *,
    artifact_ref_json: str | None = None,
    artifact_family: str | None = None,
) -> tuple[list[Path], dict[str, Any]]:
    discovery_value = _load_json_argument(root, artifact_paths_json)
    explicit_ref_value = _load_json_argument(root, artifact_ref_json)
    supplied_ref = _artifact_ref_from_value(explicit_ref_value) or _artifact_ref_from_value(discovery_value)
    explicit_paths = [path for raw in artifact_paths if (path := _normalize_artifact_path(root, raw)) is not None]
    discovered_paths = [
        path
        for raw in _paths_from_artifact_value(discovery_value)
        if (path := _normalize_artifact_path(root, raw)) is not None
    ]
    ref_path = _normalize_artifact_path(
        root,
        supplied_ref.get("artifact_path_or_store_ref") or supplied_ref.get("path"),
    )
    raw_ref = str(supplied_ref.get("artifact_path_or_store_ref") or supplied_ref.get("path") or "").strip()
    store_ref = raw_ref if "://" in raw_ref or raw_ref.lower().startswith("sha256:") else ""
    if explicit_paths:
        paths = explicit_paths
        discovery_basis = "explicit_caller_path"
    elif ref_path is not None:
        paths = [ref_path]
        discovery_basis = str(supplied_ref.get("discovery_basis") or "explicit_artifact_ref")
    elif store_ref:
        paths = []
        discovery_basis = str(supplied_ref.get("discovery_basis") or "content_addressed_store_ref")
    else:
        paths = discovered_paths
        discovery_basis = "discovered_candidate"
    paths = list(dict.fromkeys(paths))
    selected_path = paths[0] if len(paths) == 1 else None
    computed_sha = _sha256_path(selected_path)
    declared_sha = str(supplied_ref.get("artifact_sha256") or supplied_ref.get("sha256") or "").strip().lower()
    store_hash_match = re.search(r"(?:sha256[:/])([a-f0-9]{64})(?:\b|$)", store_ref.lower())
    store_sha = store_hash_match.group(1) if store_hash_match else ""
    artifact_class = str(supplied_ref.get("artifact_class") or supplied_ref.get("class") or artifact_family or "").strip()
    lane_identity = supplied_ref.get("production_lane_identity")
    if lane_identity is None and isinstance(discovery_value, dict):
        lane_identity = discovery_value.get("production_lane_identity")
    artifact_id = str(supplied_ref.get("artifact_id") or "").strip()
    if not artifact_id and computed_sha:
        artifact_id = f"artifact-{computed_sha[:16]}"
    ref_matches_explicit = not (
        explicit_paths
        and ref_path is not None
        and ref_path.resolve() not in {path.resolve() for path in explicit_paths}
    )
    local_exact_identity = bool(
        len(paths) == 1
        and artifact_id
        and artifact_class
        and artifact_class.lower() != "unknown"
        and computed_sha
        and (not declared_sha or declared_sha == computed_sha)
        and lane_identity
        and ref_matches_explicit
    )
    store_exact_identity = bool(
        not paths
        and store_ref
        and artifact_id
        and artifact_class
        and artifact_class.lower() != "unknown"
        and declared_sha
        and declared_sha == store_sha
        and lane_identity
    )
    exact_identity = local_exact_identity or store_exact_identity
    selected_ref = {
        "artifact_id": artifact_id or None,
        "artifact_class": artifact_class or None,
        "artifact_path_or_store_ref": rel_path(root, selected_path) if selected_path is not None else (store_ref or None),
        "artifact_sha256": computed_sha or declared_sha or store_sha or None,
        "production_lane_identity": lane_identity,
        "created_or_observed_at": supplied_ref.get("created_or_observed_at"),
        "discovery_basis": discovery_basis,
        "scope_verified": exact_identity,
        "advisory_discovery": not exact_identity,
        "identity_status": (
            "verified"
            if exact_identity
            else "hash_mismatch"
            if declared_sha and computed_sha and declared_sha != computed_sha
            else "explicit_ref_path_mismatch"
            if not ref_matches_explicit
            else "store_ref_hash_unverified"
            if store_ref and not store_exact_identity
            else "not_evaluated"
        ),
        "conflicting_discovery_paths": sorted(
            {rel_path(root, path) for path in discovered_paths if path not in paths}
        ),
    }
    return paths, selected_ref

def load_artifact_paths(root: Path, artifact_paths_json: str | None, artifact_paths: list[str]) -> list[Path]:
    paths, _ = load_artifact_selection(root, artifact_paths_json, artifact_paths)
    return paths

def gate_artifact_compatibility_result(
    adapter: Any | None,
    gate_id: str,
    artifact_ref: dict[str, Any],
    gate: dict[str, Any] | None = None,
    **context: Any,
) -> dict[str, Any]:
    gate = gate or {}
    artifact_class = str(artifact_ref.get("artifact_class") or "").strip()
    base = {
        "gate_id": gate_id,
        "artifact_id": artifact_ref.get("artifact_id"),
        "artifact_sha256": artifact_ref.get("artifact_sha256"),
    }
    if not bool_value(artifact_ref.get("scope_verified")):
        return {**base, "gate_compatibility_status": "not_evaluated", "compatibility_basis": "artifact_identity_not_verified", "compatibility_evidence_ref": None}
    hook = getattr(adapter, "gate_artifact_compatibility", None) if adapter is not None else None
    hook_resolved = callable(hook)
    hook_kwargs = {
        "artifact_class": artifact_class,
        "gate_id": gate_id,
        "artifact_ref": artifact_ref,
        "gate": gate,
        **context,
    }
    hook_signature_compatible = False
    if hook_resolved:
        try:
            signature = inspect.signature(hook)
            accepts_kwargs = any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            )
            accepted = hook_kwargs if accepts_kwargs else {
                key: value for key, value in hook_kwargs.items() if key in signature.parameters
            }
            signature.bind(**accepted)
            hook_signature_compatible = accepts_kwargs or "artifact_ref" in signature.parameters
        except (TypeError, ValueError):
            hook_signature_compatible = False
    hook_value, hook_error = (
        call_adapter(adapter, "gate_artifact_compatibility", **hook_kwargs)
        if hook_signature_compatible
        else (None, "gate_artifact_compatibility_signature_incompatible" if hook_resolved else None)
    )
    if isinstance(hook_value, dict) and isinstance(hook_value.get("compatible"), bool):
        echoed_id = str(hook_value.get("artifact_id") or "")
        echoed_sha = str(hook_value.get("artifact_sha256") or "").lower()
        identity_echo_valid = bool(
            echoed_id
            and echoed_sha
            and echoed_id == str(artifact_ref.get("artifact_id") or "")
            and echoed_sha == str(artifact_ref.get("artifact_sha256") or "").lower()
        )
        receipt = {
            "consumer_context_id": f"gate_artifact_compatibility:{gate_id}",
            "adapter_loaded": adapter is not None,
            "hook_resolved": hook_resolved,
            "required_hook_callable": hook_resolved,
            "hook_signature_compatible": hook_signature_compatible,
            "invocation_completed": hook_signature_compatible and hook_error is None,
            "return_contract_valid": True,
            "artifact_identity_echo_valid": identity_echo_valid,
            "value_consumed_by_decision": identity_echo_valid,
            "status": "pass" if identity_echo_valid else "not_evaluated",
        }
        if not identity_echo_valid:
            return {
                **base,
                "gate_compatibility_status": "not_evaluated",
                "compatibility_basis": "adapter_hook_identity_echo_invalid",
                "compatibility_evidence_ref": hook_value.get("evidence_ref"),
                "consumer_invocation_receipt": receipt,
            }
        return {
            **base,
            "gate_compatibility_status": "compatible" if hook_value["compatible"] else "incompatible",
            "compatibility_basis": "adapter_hook",
            "compatibility_evidence_ref": hook_value.get("evidence_ref"),
            "unmet_precondition": hook_value.get("unmet_precondition"),
            "consumer_invocation_receipt": receipt,
        }
    if hook_resolved:
        return {
            **base,
            "gate_compatibility_status": "not_evaluated",
            "compatibility_basis": "hook_error" if hook_error else "adapter_hook_return_contract_invalid",
            "compatibility_evidence_ref": None,
            "compatibility_error": hook_error,
            "consumer_invocation_receipt": {
                "consumer_context_id": f"gate_artifact_compatibility:{gate_id}",
                "hook_id": "gate_artifact_compatibility",
                "adapter_loaded": adapter is not None,
                "hook_resolved": True,
                "required_hook_callable": True,
                "hook_signature_compatible": hook_signature_compatible,
                "invocation_completed": hook_signature_compatible and hook_error is None,
                "return_contract_valid": False,
                "artifact_identity_echo_valid": False,
                "value_consumed_by_decision": False,
                "status": "not_evaluated",
            },
        }
    supported = string_list(gate.get("supported_artifact_classes") or gate.get("artifact_classes"))
    required_class = str(gate.get("required_artifact_class") or gate.get("artifact_class") or "").strip()
    if supported or required_class:
        compatible = artifact_class in supported if supported else artifact_class == required_class
        return {
            **base,
            "gate_compatibility_status": "compatible" if compatible else "incompatible",
            "compatibility_basis": "gate_static_mapping",
            "compatibility_evidence_ref": gate.get("compatibility_evidence_ref"),
        }
    return {
        **base,
        "gate_compatibility_status": "not_evaluated",
        "compatibility_basis": "hook_error" if hook_error else "mapping_not_supplied",
        "compatibility_evidence_ref": None,
        "compatibility_error": hook_error,
        "consumer_invocation_receipt": {
            "consumer_context_id": f"gate_artifact_compatibility:{gate_id}",
            "adapter_loaded": adapter is not None,
            "hook_resolved": hook_resolved,
            "required_hook_callable": hook_resolved,
            "hook_signature_compatible": hook_signature_compatible,
            "invocation_completed": bool(hook_signature_compatible and hook_error is None),
            "return_contract_valid": False,
            "artifact_identity_echo_valid": False,
            "value_consumed_by_decision": False,
            "status": "not_evaluated",
        },
    }

def apply_gate_artifact_compatibility(
    gate: dict[str, Any],
    compatibility: dict[str, Any],
    *,
    pass_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    updated = dict(gate)
    status = str(compatibility.get("gate_compatibility_status") or "not_evaluated")
    updated["gate_compatibility"] = compatibility
    updated["gate_compatibility_status"] = status
    updated["decision_contribution_allowed"] = status == "compatible"
    if status != "compatible":
        updated["observed_evaluation_status"] = updated.get("evaluation_status") or updated.get("status")
        updated["evaluation_status"] = "not_evaluated"
        updated["constrains_disposition"] = False
        updated["hard_stop_required"] = False
        for field in pass_fields:
            if field in updated:
                updated[field] = False
    return updated

def canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): canonicalize(child) for key, child in sorted(value.items()) if str(key) not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [canonicalize(child) for child in value]
    return value

def fingerprint_rows(rows: list[dict[str, Any]]) -> str:
    canonical = [canonicalize(row) for row in rows]
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def compute_quality(
    root: Path,
    paths: list[Path],
    adapter: Any | None,
    decision_artifact_ref: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str], str | None, dict[str, bool]]:
    if adapter is not None:
        function = getattr(adapter, "quality_vector", None)
        kwargs = {
            "root": root,
            "artifact_paths": [rel_path(root, path) for path in paths],
            "absolute_artifact_paths": [path.as_posix() for path in paths],
            "decision_artifact_ref": dict(decision_artifact_ref or {}),
        }
        signature_compatible = False
        if callable(function):
            try:
                signature = inspect.signature(function)
                accepts_kwargs = any(
                    parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in signature.parameters.values()
                )
                accepted = kwargs if accepts_kwargs else {
                    key: value for key, value in kwargs.items() if key in signature.parameters
                }
                signature.bind(**accepted)
                signature_compatible = accepts_kwargs or "decision_artifact_ref" in signature.parameters
            except (TypeError, ValueError):
                signature_compatible = False
        adapter_value, adapter_error = call_adapter(
            adapter,
            "quality_vector",
            **kwargs,
        )
        receipt = {
            "hook_resolved": callable(function),
            "hook_signature_compatible": signature_compatible,
            "invocation_completed": bool(signature_compatible and adapter_error is None),
            "return_contract_valid": bool(signature_compatible and adapter_error is None and isinstance(adapter_value, dict)),
        }
        if adapter_error:
            return {}, [], adapter_error, receipt
        quality, evidence_paths, reason = normalize_adapter_quality_result(adapter_value, root)
        return quality, evidence_paths, reason, receipt

    evidence_paths = sorted({rel_path(root, path) for path in paths if path.exists()})
    return {}, evidence_paths, "domain_adapter_not_supplied", {
        "hook_resolved": False,
        "hook_signature_compatible": False,
        "invocation_completed": False,
        "return_contract_valid": False,
    }
