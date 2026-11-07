"""Deterministic iterative graph algorithms with no RDFLib dependency."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Hashable, Iterable, Mapping


def strongly_connected_components[N: Hashable](  # noqa: C901, PLR0912 -- iterative Tarjan uses explicit state branches.
    nodes: Iterable[N], edges: Iterable[tuple[N, N]]
) -> list[set[N]]:
    """Return Tarjan SCCs using an explicit stack, safe for deep taxonomies."""
    node_set = set(nodes)
    adjacency: dict[N, list[N]] = defaultdict(list)
    for source, target in edges:
        if source in node_set and target in node_set:
            adjacency[source].append(target)
    for neighbors in adjacency.values():
        neighbors.sort(key=repr)

    index = 0
    indices: dict[N, int] = {}
    lowlinks: dict[N, int] = {}
    component_stack: list[N] = []
    on_stack: set[N] = set()
    components: list[set[N]] = []

    for root in sorted(node_set, key=repr):
        if root in indices:
            continue
        indices[root] = lowlinks[root] = index
        index += 1
        component_stack.append(root)
        on_stack.add(root)
        frames: list[tuple[N, int]] = [(root, 0)]
        while frames:
            node, neighbor_index = frames[-1]
            neighbors = adjacency[node]
            if neighbor_index < len(neighbors):
                neighbor = neighbors[neighbor_index]
                frames[-1] = (node, neighbor_index + 1)
                if neighbor not in indices:
                    indices[neighbor] = lowlinks[neighbor] = index
                    index += 1
                    component_stack.append(neighbor)
                    on_stack.add(neighbor)
                    frames.append((neighbor, 0))
                elif neighbor in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[neighbor])
                continue

            frames.pop()
            if frames:
                parent, _ = frames[-1]
                lowlinks[parent] = min(lowlinks[parent], lowlinks[node])
            if lowlinks[node] == indices[node]:
                component: set[N] = set()
                while component_stack:
                    member = component_stack.pop()
                    on_stack.remove(member)
                    component.add(member)
                    if member == node:
                        break
                components.append(component)
    return components


def reachable[N: Hashable](
    adjacency: Mapping[N, Iterable[N]], source: N, target: N, *, ignore: tuple[N, N] | None = None
) -> bool:
    """Return whether ``target`` is reachable from ``source`` by breadth-first search."""
    seen, queue = {source}, deque([source])
    while queue:
        node = queue.popleft()
        for neighbor in adjacency.get(node, ()):
            if (node, neighbor) == ignore:
                continue
            if neighbor == target:
                return True
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return False
