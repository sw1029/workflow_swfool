"""Deterministic directed-graph condensation utilities."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def strongly_connected_components(
    nodes: Iterable[str], edges: Iterable[tuple[str, str]]
) -> list[list[str]]:
    ordered_nodes = sorted(set(nodes))
    adjacency: dict[str, list[str]] = {node: [] for node in ordered_nodes}
    for source, target in sorted(set(edges)):
        if source in adjacency and target in adjacency:
            adjacency[source].append(target)
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    groups: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for neighbor in adjacency[node]:
            if neighbor not in indices:
                visit(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[neighbor])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        groups.append(sorted(component))

    for node in ordered_nodes:
        if node not in indices:
            visit(node)
    return sorted(groups, key=lambda group: tuple(group))


def condensation_layers(
    components: list[list[str]], edges: Iterable[tuple[str, str]]
) -> list[list[str]]:
    component_for = {
        member: index for index, group in enumerate(components) for member in group
    }
    successors: dict[int, set[int]] = defaultdict(set)
    indegree = {index: 0 for index in range(len(components))}
    for source, target in sorted(set(edges)):
        left, right = component_for.get(source), component_for.get(target)
        if left is None or right is None or left == right or right in successors[left]:
            continue
        successors[left].add(right)
        indegree[right] += 1
    remaining = set(indegree)
    layers: list[list[str]] = []
    while remaining:
        ready = sorted(index for index in remaining if indegree[index] == 0)
        if not ready:
            ready = [min(remaining)]
        layers.append(sorted(member for index in ready for member in components[index]))
        for index in ready:
            remaining.remove(index)
            for successor in successors[index]:
                indegree[successor] -= 1
    return layers


__all__ = ("condensation_layers", "strongly_connected_components")
