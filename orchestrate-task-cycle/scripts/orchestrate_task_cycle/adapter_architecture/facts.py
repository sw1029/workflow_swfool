"""Compile privacy-safe, deterministic adapter architecture facts."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .contracts import (
    ANALYZER_REVISION,
    load_bound_json,
    object_sha256,
    safe_regular_file,
)
from .graph import condensation_layers, strongly_connected_components
from .python_source import analyze_python_source


def _load_convention(
    root: Path, row: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    path = row.get("code_convention_contract_path")
    digest = row.get("code_convention_contract_sha256")
    if not path or not digest:
        return None, None
    value, _relative = load_bound_json(
        root, path, digest, "code convention contract"
    )
    return (value if isinstance(value, dict) else None), str(digest)


def _component_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("components")
    if not isinstance(raw, list):
        return []
    rows = [dict(item) for item in raw if isinstance(item, dict)]
    known_paths = {str(item.get("path")) for item in rows}
    closure = row.get("runtime_closure")
    discovered = (
        closure.get("discovered_transitive_sha256")
        if isinstance(closure, dict)
        else None
    )
    for path, digest in (
        discovered.items() if isinstance(discovered, dict) else []
    ):
        if str(path) in known_paths:
            continue
        rows.append(
            {
                "component_id": "transitive-" + object_sha256(path)[:16],
                "path": str(path),
                "sha256": digest,
                "kind": "discovered_python_module",
                "role": "runtime_transitive",
                "required": True,
                "revision_included": True,
                "runtime_included": True,
                "architecture_audit_scope": str(path).endswith(".py"),
                "depends_on": [],
            }
        )
    return sorted(rows, key=lambda item: str(item.get("component_id", "")))


def _thresholds(convention: dict[str, Any] | None) -> dict[str, int]:
    defaults = {
        "module_logical_loc": 500,
        "function_logical_loc": 140,
        "class_logical_loc": 420,
    }
    raw = convention.get("thresholds") if isinstance(convention, dict) else None
    if not isinstance(raw, dict):
        return defaults
    result = dict(defaults)
    aliases = {
        "module_logical_loc": "module_logical_loc",
        "max_module_logical_loc": "module_logical_loc",
        "max_file_logical_loc": "module_logical_loc",
        "function_logical_loc": "function_logical_loc",
        "max_function_logical_loc": "function_logical_loc",
        "class_logical_loc": "class_logical_loc",
        "max_class_logical_loc": "class_logical_loc",
    }
    for raw_key, key in aliases.items():
        value = raw.get(raw_key)
        if isinstance(value, int) and value > 0:
            result[key] = value
    return result


def _inheritance_facts(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    classes = {
        str(symbol["qualified_name"]): symbol
        for symbol in symbols
        if symbol.get("kind") == "class"
    }
    by_local: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for symbol in classes.values():
        by_local[str(symbol.get("local_name"))].append(symbol)
    facts: list[dict[str, Any]] = []
    for child in classes.values():
        for raw_base in child.get("bases", []):
            candidates = by_local.get(str(raw_base).split(".")[-1], [])
            for base in candidates:
                if base is child:
                    continue
                overrides = sorted(
                    set(child.get("methods", [])) & set(base.get("methods", []))
                )
                facts.append(
                    {
                        "base": base["qualified_name"],
                        "child": child["qualified_name"],
                        "override_methods": overrides,
                        "base_is_protocol": bool(base.get("is_protocol")),
                        "base_is_abstract": bool(base.get("is_abstract")),
                    }
                )
    return sorted(facts, key=lambda item: (item["base"], item["child"]))


def _clone_groups(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for symbol in symbols:
        digest = symbol.get("normalized_ast_sha256")
        if digest:
            groups[str(digest)].append(str(symbol["qualified_name"]))
    return [
        {"normalized_ast_sha256": digest, "symbols": sorted(names)}
        for digest, names in sorted(groups.items())
        if len(names) > 1
    ]


def _component_module_name(component: dict[str, Any]) -> str | None:
    path = Path(str(component.get("path") or ""))
    if path.suffix != ".py":
        return None
    parts = list(path.with_suffix("").parts)
    if "scripts" in parts:
        parts = parts[parts.index("scripts") + 1 :]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or None


def _owner_symbol_qualified_name(
    component_id: str,
    symbol: str,
    component: dict[str, Any],
) -> str:
    relative = symbol.strip()
    aliases = sorted(
        {
            alias
            for alias in (component_id, _component_module_name(component))
            if alias
        },
        key=len,
        reverse=True,
    )
    for alias in aliases:
        if relative.startswith(f"{alias}."):
            relative = relative[len(alias) + 1 :]
            break
    return f"{component_id}.{relative}" if relative else component_id


def _hook_mapping(
    row: dict[str, Any],
    symbols: list[dict[str, Any]],
    component_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    symbols_by_component: dict[str, set[str]] = defaultdict(set)
    for item in symbols:
        component_id = str(item.get("component_id") or "")
        qualified_name = str(item.get("qualified_name") or "")
        if component_id and qualified_name:
            symbols_by_component[component_id].add(qualified_name)
    contracts = row.get("hook_contracts")
    if not isinstance(contracts, list):
        return []
    result: list[dict[str, Any]] = []
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        owner = contract.get("owner")
        component_id: str | None = None
        symbol: str | None = None
        if isinstance(owner, dict):
            component_id = str(owner.get("component_id") or "") or None
            symbol = str(owner.get("symbol") or "") or None
        elif isinstance(owner, str):
            component_id, separator, symbol = owner.partition(":")
            if not separator:
                symbol, component_id = component_id, None
        tests = contract.get("test_component_ids")
        test_ids = (
            sorted(str(item) for item in tests) if isinstance(tests, list) else []
        )
        owner_component = component_by_id.get(component_id or "")
        owner_exists = bool(
            component_id
            and symbol
            and owner_component
            and _owner_symbol_qualified_name(
                component_id, symbol, owner_component
            )
            in symbols_by_component.get(component_id, set())
        )
        result.append(
            {
                "hook_id": str(contract.get("hook_id") or ""),
                "owner_component_id": component_id,
                "owner_symbol": symbol,
                "owner_component_exists": component_id in component_by_id
                if component_id
                else True,
                "owner_symbol_exists": owner_exists,
                "test_component_ids": test_ids,
                "tests_exist": all(test_id in component_by_id for test_id in test_ids),
            }
        )
    return sorted(result, key=lambda item: item["hook_id"])


def _dag_violations(
    components: list[dict[str, Any]],
    edges: list[tuple[str, str]],
    convention: dict[str, Any] | None,
) -> list[dict[str, str]]:
    raw = (
        convention.get("module_dependency_dag")
        if isinstance(convention, dict)
        else None
    )
    if not isinstance(raw, dict):
        return []
    roles = {
        str(item.get("path")): str(item.get("role") or "")
        for item in components
    }
    allowed = {
        str(role): {str(item) for item in dependencies}
        for role, dependencies in raw.items()
        if isinstance(dependencies, list)
    }
    violations: list[dict[str, str]] = []
    for source, target in edges:
        source_role, target_role = roles.get(source, ""), roles.get(target, "")
        if (
            source_role in allowed
            and target_role not in allowed[source_role] | {source_role}
        ):
            violations.append(
                {
                    "source": source,
                    "source_role": source_role,
                    "target": target,
                    "target_role": target_role,
                }
            )
    return violations


def _analyze_components(
    root: Path,
    components: list[dict[str, Any]],
    changed: set[str],
    thresholds: dict[str, int],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    modules: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    pressures: list[dict[str, Any]] = []
    for component in components:
        if not component.get("architecture_audit_scope"):
            continue
        path_value = str(component.get("path") or "")
        if not path_value.endswith(".py"):
            continue
        try:
            path, relative = safe_regular_file(root, path_value)
            source = path.read_text(encoding="utf-8")
            analysis = analyze_python_source(
                source,
                filename=relative,
                module_id=str(component.get("component_id") or relative),
            )
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            blockers.append(
                {
                    "code": "adapter_architecture_source_unreadable",
                    "component_id": component.get("component_id"),
                    "error_class": type(exc).__name__,
                }
            )
            continue
        logical_loc = sum(
            1
            for line in source.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        module = {
            "component_id": component.get("component_id"),
            "path": relative,
            "role": component.get("role"),
            "logical_loc": logical_loc,
            "changed": relative in changed,
            "top_level_effect_kinds": analysis["top_level_effect_kinds"],
            "dynamic_import_count": analysis["dynamic_import_count"],
            "symbol_count": len(analysis["symbols"]),
        }
        modules.append(module)
        component_symbols = [
            {**symbol, "component_id": component.get("component_id")}
            for symbol in analysis["symbols"]
        ]
        symbols.extend(component_symbols)
        calls.extend(analysis["calls"])
        if logical_loc > thresholds["module_logical_loc"]:
            pressures.append(
                {
                    "fact_id": f"module-size:{relative}",
                    "axis": "module_size",
                    "subject": relative,
                    "changed": relative in changed,
                }
            )
        for symbol in component_symbols:
            limit = (
                thresholds["class_logical_loc"]
                if symbol.get("kind") == "class"
                else thresholds["function_logical_loc"]
            )
            if int(symbol.get("line_span", 0)) > limit:
                pressures.append(
                    {
                        "fact_id": "symbol-size:"
                        + object_sha256(symbol["qualified_name"])[:16],
                        "axis": "symbol_size",
                        "subject": symbol["qualified_name"],
                        "changed": relative in changed,
                    }
                )
    return modules, symbols, calls, blockers, pressures


def compile_architecture_facts(
    root: str | Path,
    adapter_row: dict[str, Any],
    *,
    changed_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a content-bound packet containing no raw source or literal bodies."""

    repo_root = Path(root).expanduser().resolve(strict=True)
    components = _component_rows(adapter_row)
    component_by_id = {str(item.get("component_id")): item for item in components}
    changed = set(changed_paths)
    convention, convention_digest = _load_convention(repo_root, adapter_row)
    modules, symbols, calls, blockers, pressures = _analyze_components(
        repo_root, components, changed, _thresholds(convention)
    )
    closure = adapter_row.get("runtime_closure")
    edge_rows = (
        closure.get("internal_import_edges") if isinstance(closure, dict) else None
    )
    edges = sorted(
        {
            (str(item.get("source_path")), str(item.get("target_path")))
            for item in edge_rows or []
            if isinstance(item, dict)
            and item.get("source_path")
            and item.get("target_path")
        }
    )
    nodes = sorted(
        str(item.get("path")) for item in components if item.get("path")
    )
    sccs = strongly_connected_components(nodes, edges)
    cyclic = [group for group in sccs if len(group) > 1]
    for group in cyclic:
        pressures.append(
            {
                "fact_id": f"import-cycle:{object_sha256(group)[:16]}",
                "axis": "import_cycle",
                "subjects": group,
                "changed": any(path in changed for path in group),
            }
        )
    clones = _clone_groups(symbols)
    for group in clones:
        pressures.append(
            {
                "fact_id": f"ast-clone:{group['normalized_ast_sha256'][:16]}",
                "axis": "normalized_ast_clone",
                "subjects": group["symbols"],
                "changed": False,
            }
        )
    hooks = _hook_mapping(adapter_row, symbols, component_by_id)
    for hook in hooks:
        if (
            not hook["owner_component_exists"]
            or not hook["owner_symbol_exists"]
            or not hook["tests_exist"]
        ):
            pressures.append(
                {
                    "fact_id": f"hook-map:{hook['hook_id']}",
                    "axis": "hook_owner_test_mapping",
                    "subject": hook["hook_id"],
                    "changed": False,
                }
            )
    dag_violations = _dag_violations(components, edges, convention)
    for violation in dag_violations:
        pressures.append(
            {
                "fact_id": f"dependency-dag:{object_sha256(violation)[:16]}",
                "axis": "dependency_dag",
                "subject": violation["source"],
                "changed": violation["source"] in changed,
            }
        )
    packet: dict[str, Any] = {
        "schema_version": 1,
        "artifact_kind": "adapter_architecture_fact_packet",
        "analyzer_revision": ANALYZER_REVISION,
        "adapter_id": adapter_row.get("adapter_id"),
        "adapter_revision_sha256": adapter_row.get("adapter_revision_sha256"),
        "manifest_sha256": adapter_row.get("manifest_sha256"),
        "convention_sha256": convention_digest,
        "coverage": {
            "component_count": len(components),
            "audited_python_component_count": len(modules),
            "hook_contract_count": len(hooks),
            "changed_path_count": len(changed),
        },
        "modules": sorted(modules, key=lambda item: str(item["path"])),
        "symbols": sorted(symbols, key=lambda item: str(item["qualified_name"])),
        "import_graph": {
            "edges": [
                {"source_path": source, "target_path": target}
                for source, target in edges
            ],
            "strongly_connected_components": sccs,
            "cyclic_components": cyclic,
            "layers": condensation_layers(sccs, edges),
        },
        "call_graph": sorted(
            calls, key=lambda item: (item["caller"], item["callee"])
        ),
        "normalized_ast_clone_groups": clones,
        "inheritance": _inheritance_facts(symbols),
        "hook_owner_test_mapping": hooks,
        "dependency_dag_violations": dag_violations,
        "structural_pressures": sorted(
            pressures, key=lambda item: str(item["fact_id"])
        ),
        "blockers": blockers,
        "raw_source_persisted": False,
        "forbidden_raw_source_persisted": True,
    }
    packet["fact_packet_sha256"] = object_sha256(packet)
    return packet


__all__ = ("compile_architecture_facts",)
