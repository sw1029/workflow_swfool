"""Recursive, revision-bound runtime closure compilation for adapter v3."""

from __future__ import annotations

import ast
import importlib.metadata
from pathlib import Path
import sys
from typing import Any

from .contracts import file_sha256, object_sha256, safe_regular_file


RUNTIME_CLOSURE_FIELDS = {
    "entry_component_ids",
    "dynamic_dependency_ids",
    "unresolved_local_import_policy",
}


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and bool(item.strip()) for item in value
    ) and len(set(value)) == len(value)


def _transitive_ids(
    starts: list[str], by_id: dict[str, dict[str, Any]]
) -> set[str]:
    seen: set[str] = set()
    pending = list(starts)
    while pending:
        component_id = pending.pop()
        if component_id in seen or component_id not in by_id:
            continue
        seen.add(component_id)
        pending.extend(by_id[component_id]["depends_on"])
    return seen


def _candidate_paths(root: Path, source: Path, module: str, level: int) -> list[Path]:
    parts = [part for part in module.split(".") if part]
    bases: list[Path] = []
    if level:
        base = source.parent
        for _ in range(max(0, level - 1)):
            base = base.parent
        bases.append(base)
    else:
        bases.extend((source.parent, root))
    candidates: list[Path] = []
    for base in bases:
        joined = base.joinpath(*parts)
        candidates.extend((joined.with_suffix(".py"), joined / "__init__.py"))
    return candidates


def _import_specs(tree: ast.Module) -> tuple[list[tuple[str, int, list[str]]], int]:
    specs: list[tuple[str, int, list[str]]] = []
    dynamic = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            specs.extend((alias.name, 0, []) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            specs.append(
                (
                    node.module or "",
                    int(node.level or 0),
                    [alias.name for alias in node.names if alias.name != "*"],
                )
            )
        elif isinstance(node, ast.Call):
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(
                node.func.value, ast.Name
            ):
                name = f"{node.func.value.id}.{node.func.attr}"
            if name in {"__import__", "importlib.import_module"}:
                dynamic += 1
    return specs, dynamic


def _resolve_import(
    root: Path,
    source: Path,
    module: str,
    level: int,
    names: list[str],
    declared_modules: dict[str, Path],
) -> tuple[Path | None, list[Path]]:
    candidates = _candidate_paths(root, source, module, level)
    base_candidates = list(candidates)
    for name in names:
        joined = ".".join(part for part in (module, name) if part)
        candidates.extend(_candidate_paths(root, source, joined, level))
    if not level:
        for name in [
            module,
            *(".".join((module, item)) for item in names if module),
        ]:
            declared = declared_modules.get(name)
            if declared is not None:
                candidates.insert(0, declared)
                base_candidates.insert(0, declared)
    existing: list[Path] = []
    for candidate in candidates:
        try:
            if candidate.is_file() and candidate.resolve(strict=True).is_relative_to(root):
                existing.append(candidate.resolve(strict=True))
        except (OSError, ValueError):
            continue
    preferred = next(
        (
            candidate.resolve(strict=True)
            for candidate in base_candidates
            if candidate.is_file()
        ),
        None,
    )
    return preferred or (existing[0] if existing else None), existing


def _declared_module_index(
    root: Path, components: list[dict[str, Any]]
) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for component in components:
        path_value = str(component.get("path") or "")
        if not path_value.endswith(".py"):
            continue
        try:
            path, relative = safe_regular_file(root, path_value)
        except (OSError, ValueError):
            continue
        parts = list(Path(relative).with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        aliases: set[str] = set()
        if parts:
            aliases.add(parts[-1])
            aliases.add(".".join(parts))
        if "scripts" in parts:
            aliases.add(".".join(parts[parts.index("scripts") + 1 :]))
        for alias in aliases:
            if alias and alias not in index:
                index[alias] = path
    return index


def _external_versions(modules: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    distribution_map = importlib.metadata.packages_distributions()
    for module in sorted(modules - set(sys.stdlib_module_names)):
        distributions = distribution_map.get(module) or []
        if not distributions:
            result[module] = "unresolved"
            continue
        versions = []
        for distribution in sorted(distributions):
            try:
                versions.append(
                    f"{distribution}=={importlib.metadata.version(distribution)}"
                )
            except importlib.metadata.PackageNotFoundError:
                versions.append(f"{distribution}==missing")
        result[module] = "|".join(versions)
    return result


def _unresolved_import_is_local(
    root: Path,
    source: Path,
    module: str,
    level: int,
    declared_modules: dict[str, Path],
) -> bool:
    if level:
        return True
    top_level = module.split(".", 1)[0]
    if not top_level:
        return False
    if any(
        alias == module
        or alias.startswith(f"{module}.")
        or module.startswith(f"{alias}.")
        for alias in declared_modules
    ):
        return True
    return any(
        candidate.exists()
        for candidate in (root / top_level, source.parent / top_level)
    )


def compile_runtime_closure(
    root: Path,
    manifest: dict[str, Any],
    components: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
    raw = manifest.get("runtime_closure")
    if not isinstance(raw, dict) or set(raw) != RUNTIME_CLOSURE_FIELDS:
        errors.append("runtime_closure_contract_invalid")
        raw = {}
    entries = raw.get("entry_component_ids")
    dynamics = raw.get("dynamic_dependency_ids")
    if not _strings(entries) or not entries:
        errors.append("runtime_entry_component_ids_invalid")
        entries = []
    if not _strings(dynamics):
        errors.append("runtime_dynamic_dependency_ids_invalid")
        dynamics = []
    if raw.get("unresolved_local_import_policy") != "block":
        errors.append("runtime_unresolved_local_import_policy_invalid")
    by_id = {row["component_id"]: row for row in components}
    unknown = sorted((set(entries) | set(dynamics)) - set(by_id))
    if unknown:
        errors.append(f"runtime_component_unknown:{','.join(unknown)}")
    closure_ids = _transitive_ids([*entries, *dynamics], by_id)
    path_to_id = {row["path"]: row["component_id"] for row in components}
    declared_modules = _declared_module_index(root, components)
    internal_edges: set[tuple[str, str]] = set()
    external_modules: set[str] = set()
    dynamic_call_count = 0
    discovered: dict[str, str] = {}
    pending = sorted(by_id[item]["path"] for item in closure_ids)
    processed: set[str] = set()
    while pending:
        path_value = pending.pop(0)
        if path_value in processed:
            continue
        processed.add(path_value)
        if len(processed) > 4096:
            errors.append("runtime_static_closure_limit_exceeded")
            break
        if not path_value.endswith(".py"):
            continue
        try:
            source, relative = safe_regular_file(root, path_value)
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=relative)
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            errors.append(
                f"runtime_component_parse_failed:{path_value}:{type(exc).__name__}"
            )
            continue
        specs, dynamic_count = _import_specs(tree)
        dynamic_call_count += dynamic_count
        for module, level, names in specs:
            resolved, existing = _resolve_import(
                root, source, module, level, names, declared_modules
            )
            if resolved is None:
                if _unresolved_import_is_local(
                    root, source, module, level, declared_modules
                ):
                    errors.append(
                        f"runtime_local_import_unresolved:{relative}:{module or '<relative>'}"
                    )
                elif module:
                    external_modules.add(module.split(".")[0])
                continue
            targets = sorted(set(existing or [resolved]))
            for candidate in targets:
                candidate_relative = candidate.relative_to(root).as_posix()
                try:
                    candidate_path, candidate_relative = safe_regular_file(
                        root, candidate_relative
                    )
                except (OSError, ValueError) as exc:
                    errors.append(
                        "runtime_local_import_unsafe:"
                        f"{candidate_relative}:{type(exc).__name__}"
                    )
                    continue
                target_id = path_to_id.get(candidate_relative)
                if target_id is not None:
                    if not by_id[target_id].get("runtime_included"):
                        errors.append(f"runtime_component_not_marked:{target_id}")
                        continue
                    added = _transitive_ids([target_id], by_id) - closure_ids
                    closure_ids.update(added)
                    for added_id in sorted(added):
                        added_path = by_id[added_id]["path"]
                        if added_path not in processed and added_path not in pending:
                            pending.append(added_path)
                else:
                    discovered[candidate_relative] = file_sha256(candidate_path)
                internal_edges.add((relative, candidate_relative))
                if (
                    candidate_relative not in processed
                    and candidate_relative not in pending
                ):
                    pending.append(candidate_relative)
            pending.sort()
    for component_id in sorted(closure_ids):
        if not by_id[component_id].get("runtime_included"):
            errors.append(f"runtime_component_not_marked:{component_id}")
    unreachable = sorted(
        component_id
        for component_id, row in by_id.items()
        if row.get("runtime_included") and component_id not in closure_ids
    )
    if unreachable:
        errors.append(f"runtime_component_unreachable:{','.join(unreachable)}")
    if dynamic_call_count and not dynamics:
        errors.append("runtime_dynamic_import_dependency_undeclared")
    closure = {
        "entry_component_ids": list(entries),
        "dynamic_dependency_ids": list(dynamics),
        "component_ids": sorted(closure_ids),
        "paths": sorted(
            {*(by_id[item]["path"] for item in closure_ids), *discovered}
        ),
        "component_sha256": {
            item: by_id[item]["sha256"] for item in sorted(closure_ids)
        },
        "discovered_transitive_sha256": dict(sorted(discovered.items())),
        "internal_import_edges": [
            {"source_path": source, "target_path": target}
            for source, target in sorted(internal_edges)
        ],
        "external_distribution_versions": _external_versions(external_modules),
        "dynamic_import_call_count": dynamic_call_count,
        "unresolved_local_import_policy": "block",
    }
    closure["runtime_closure_sha256"] = object_sha256(closure)
    return closure


__all__ = ("compile_runtime_closure",)
