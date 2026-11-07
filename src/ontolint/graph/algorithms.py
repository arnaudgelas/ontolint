"""Deterministic iterative graph algorithms with no RDFLib dependency."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Hashable, Iterable, Mapping, Set


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


def hierarchy_depths[N: Hashable](nodes: Iterable[N], edges: Iterable[tuple[N, N]]) -> dict[N, int]:
    """Return the longest downward hierarchy depth of every node, iteratively.

    ``edges`` are ``(child, parent)`` pairs, the orientation of asserted
    ``rdfs:subClassOf`` triples; endpoints outside ``nodes`` are ignored. The
    depth of a node is the number of nodes on the longest chain from it down
    through its descendants, so a leaf has depth ``1``.

    The result reproduces the legacy recursive ``depth`` helper exactly:

    * Nodes in a strongly connected component of more than one node ("cyclic"
      nodes) have depth ``0`` and contribute ``0`` to their ancestors, so a
      class whose only subclasses are cyclic has depth ``1``.
    * Self-loops are ignored (a lone self-looping node is not cyclic here, it
      is a leaf of depth ``1``); CLS003 reports them separately.
    * Once cyclic nodes are removed, the remaining graph is a DAG, so depth is
      ``1 + max(child depths, default 0)`` computed bottom-up with Kahn's
      algorithm. No recursion is used, so 100k-deep chains are safe.
    """
    node_set = set(nodes)
    edge_set = {(c, p) for c, p in edges if c in node_set and p in node_set}
    cyclic = {n for comp in strongly_connected_components(node_set, edge_set) if len(comp) > 1 for n in comp}

    pending_children: dict[N, int] = {n: 0 for n in node_set if n not in cyclic}
    parents: dict[N, list[N]] = defaultdict(list)
    for child, parent in edge_set:
        if child == parent or child in cyclic or parent in cyclic:
            continue
        pending_children[parent] += 1
        parents[child].append(parent)

    depths: dict[N, int] = dict.fromkeys(cyclic, 0)
    best_child: dict[N, int] = dict.fromkeys(pending_children, 0)
    ready = deque(n for n, count in pending_children.items() if count == 0)
    while ready:
        node = ready.popleft()
        depth = depths[node] = 1 + best_child[node]
        for parent in parents[node]:
            best_child[parent] = max(best_child[parent], depth)
            pending_children[parent] -= 1
            if pending_children[parent] == 0:
                ready.append(parent)
    return depths


def transitively_redundant_edges[N: Hashable](
    edges: Iterable[tuple[N, N]], components: Iterable[Set[N]]
) -> set[tuple[N, N]]:
    """Return edges ``(c, p)`` for which ``p`` stays reachable from ``c`` without that edge.

    ``components`` must be the strongly connected components of ``edges`` in the
    order produced by :func:`strongly_connected_components` (successors first).
    Edges whose source lies on a cycle (a multi-node component or a self-loop)
    use a per-edge search; every other edge is answered from per-component
    reachability bitsets, computed only for components that can be reached from
    a node with more than one outgoing edge. Equivalent to calling
    :func:`reachable` with ``ignore=(c, p)`` on every edge.
    """
    edge_list = list(edges)
    successors: dict[N, set[N]] = defaultdict(set)
    for source, target in edge_list:
        successors[source].add(target)

    component_list = list(components)
    cyclic = {n for comp in component_list if len(comp) > 1 for n in comp}
    cyclic.update(n for n in successors if n in successors[n])

    bit, reach = _reachability_bitsets(successors, component_list, cyclic)

    redundant: set[tuple[N, N]] = set()
    for source, target in edge_list:
        if source in cyclic:
            if reachable(successors, source, target, ignore=(source, target)):
                redundant.add((source, target))
        elif any(other != target and reach[other] & bit[target] for other in successors[source]):
            redundant.add((source, target))
    return redundant


def _reachability_bitsets[N: Hashable](
    successors: Mapping[N, Set[N]], components: Iterable[Set[N]], cyclic: Set[N]
) -> tuple[dict[N, int], dict[N, int]]:
    """Return per-node bit masks and reachability masks, for nodes reachable from branching nodes only."""
    needed: set[N] = set()
    stack = [t for n, targets in successors.items() if len(targets) > 1 and n not in cyclic for t in targets]
    while stack:
        node = stack.pop()
        if node not in needed:
            needed.add(node)
            stack.extend(successors.get(node, ()))

    bit: dict[N, int] = {}
    reach: dict[N, int] = {}
    for component in components:  # successors first
        members = [n for n in component if n in needed]
        if not members:
            continue
        mask = 0
        for member in members:
            bit[member] = 1 << len(bit)
            mask |= bit[member]
        for member in members:
            mask |= _or_reach(reach, successors.get(member, ()), component)
        reach.update(dict.fromkeys(members, mask))
    return bit, reach


def _or_reach[N: Hashable](reach: Mapping[N, int], targets: Iterable[N], component: Set[N]) -> int:
    mask = 0
    for target in targets:
        if target not in component:
            mask |= reach[target]
    return mask
