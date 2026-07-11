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
    default_candidate = root / DEFAULT_DOMAIN_ADAPTER_REL_PATH
    if default_candidate.is_file():
        candidates.append(default_candidate)
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

def load_artifact_paths(root: Path, artifact_paths_json: str | None, artifact_paths: list[str]) -> list[Path]:
    values = list(artifact_paths)
    if artifact_paths_json:
        source = Path(artifact_paths_json)
        loaded: Any = None
        if not source.is_absolute():
            source = root / source
        if source.is_file():
            loaded = read_json(source)
        else:
            try:
                loaded = json.loads(artifact_paths_json)
            except json.JSONDecodeError:
                loaded = None
        if isinstance(loaded, list):
            values.extend(str(item) for item in loaded)
        elif isinstance(loaded, dict):
            for key in ("artifact_paths", "artifacts", "evidence_paths", "changed_files", "reviewed_artifacts"):
                raw = loaded.get(key)
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict) and item.get("path"):
                            values.append(str(item["path"]))
                        else:
                            values.append(str(item))
    paths: list[Path] = []
    for value in values:
        if not value or "://" in value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        if path not in paths:
            paths.append(path)
    return paths

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

def compute_quality(root: Path, paths: list[Path], adapter: Any | None) -> tuple[dict[str, Any], list[str], str | None]:
    if adapter is not None:
        adapter_value, adapter_error = call_adapter(
            adapter,
            "quality_vector",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            absolute_artifact_paths=[path.as_posix() for path in paths],
        )
        if adapter_error:
            return {}, [], adapter_error
        return normalize_adapter_quality_result(adapter_value, root)

    evidence_paths = sorted({rel_path(root, path) for path in paths if path.exists()})
    return {}, evidence_paths, "domain_adapter_not_supplied"
