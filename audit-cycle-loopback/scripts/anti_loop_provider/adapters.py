from __future__ import annotations

from .common import *

_QUALITY_METRICS_MODULE: Any | None = None
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

def load_quality_metrics(root: Path) -> Any:
    global _QUALITY_METRICS_MODULE
    if _QUALITY_METRICS_MODULE is not None:
        return _QUALITY_METRICS_MODULE
    candidates: list[Path] = []
    env_path = os.environ.get(LEGACY_QUALITY_ENV)
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            root / "scripts" / LEGACY_QUALITY_MODULE_NAME,
            Path.cwd() / "scripts" / LEGACY_QUALITY_MODULE_NAME,
        ]
    )
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.as_posix() in seen:
            continue
        seen.add(resolved.as_posix())
        if not resolved.is_file():
            continue
        module = load_python_module(resolved, "legacy_quality_metrics_shared")
        if module is None:
            continue
        _QUALITY_METRICS_MODULE = module
        return module
    raise RuntimeError(f"{LEGACY_QUALITY_MODULE_NAME}_not_found")

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

def candidate_work_dirs(paths: list[Path]) -> list[Path]:
    candidates: set[Path] = set()
    required_names = {"kg_nodes.jsonl", "kg_edges.jsonl", "evidence.jsonl", "quality_report.json"}
    for path in paths:
        if path.is_file() and path.name in required_names:
            candidates.add(path.parent)
        elif path.is_dir():
            if any((path / name).exists() for name in required_names):
                candidates.add(path)
            for name in required_names:
                for match in path.rglob(name):
                    candidates.add(match.parent)
    return sorted(candidates, key=lambda item: item.as_posix())

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

    work_dirs = candidate_work_dirs(paths)
    if not paths:
        return {}, [], "no_artifact_paths_supplied"
    if not work_dirs:
        return {}, [rel_path(root, path) for path in paths if path.exists()], "no_kg_work_dirs_found"

    all_nodes: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    evidence_count = 0
    missing: list[str] = []
    evidence_paths: list[str] = []
    for work_dir in work_dirs:
        nodes_path = work_dir / "kg_nodes.jsonl"
        edges_path = work_dir / "kg_edges.jsonl"
        evidence_path = work_dir / "evidence.jsonl"
        for path in (nodes_path, edges_path, evidence_path, work_dir / "quality_report.json"):
            if not path.exists():
                missing.append(rel_path(root, path))
            elif path.is_file():
                evidence_paths.append(rel_path(root, path))
        nodes = read_jsonl(nodes_path)
        edges = read_jsonl(edges_path)
        evidence = read_jsonl(evidence_path)
        all_nodes.extend(nodes)
        all_edges.extend(edges)
        evidence_count += len(evidence)

    if missing or not all_nodes or not all_edges or evidence_count == 0:
        return {}, sorted(set(evidence_paths)), "required_output_artifacts_missing_or_empty"

    try:
        quality_metrics = load_quality_metrics(root)
    except RuntimeError as exc:
        return {}, sorted(set(evidence_paths)), str(exc)
    quality = quality_metrics.summarize_quality(all_nodes, all_edges, evidence_count, root=root)
    quality["current_output_fingerprint"] = fingerprint_rows(all_nodes + all_edges)
    if quality.get("quality_signal_confidence") == "low":
        return quality, sorted(set(evidence_paths)), "quality_signal_confidence_low"
    return quality, sorted(set(evidence_paths)), None
