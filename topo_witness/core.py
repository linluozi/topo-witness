"""Deterministic topological sorting with a verifiable cycle witness.

When a graph has a cycle, "Cycle detected" is not an answer.  ``topo_witness``
returns an explicit simple cycle, then removes shortcut edges until no chord
remains, so the witness is self-contained: every listed edge exists and no
shorter edge in the graph jumps across it.
"""

from __future__ import annotations

import heapq
from typing import Callable, Hashable, Iterable, Sequence, TypeVar

T = TypeVar("T", bound=Hashable)


class GraphError(ValueError):
    """Malformed graph input."""


class UnknownNodeError(GraphError):
    """An edge references a node that was not declared."""


class CycleError(GraphError):
    """The graph is cyclic; ``cycle`` is a chordless witness."""

    def __init__(self, cycle: Sequence[T]) -> None:
        self.cycle: tuple[T, ...] = tuple(cycle)
        super().__init__("cycle: " + " -> ".join(map(str, self.cycle + self.cycle[:1])))


def _default_key(node: object) -> tuple[str, str]:
    return (type(node).__name__, repr(node))


def _normalize(
    nodes: Iterable[T], edges: Iterable[tuple[T, T]], key: Callable[[T], object] | None
) -> tuple[list[T], set[tuple[T, T]], dict[T, set[T]], dict[T, set[T]]]:
    node_list: list[T] = []
    seen: set[T] = set()
    for node in nodes:
        if node not in seen:
            seen.add(node)
            node_list.append(node)
    if not node_list:
        raise GraphError("nodes must not be empty")

    edge_set: set[tuple[T, T]] = set()
    for edge in edges:
        try:
            u, v = edge
        except (TypeError, ValueError) as exc:
            raise GraphError(f"edge must be a pair, got {edge!r}") from exc
        if u not in seen:
            raise UnknownNodeError(f"edge source {u!r} is not in nodes")
        if v not in seen:
            raise UnknownNodeError(f"edge target {v!r} is not in nodes")
        edge_set.add((u, v))

    succ: dict[T, set[T]] = {n: set() for n in node_list}
    pred: dict[T, set[T]] = {n: set() for n in node_list}
    for u, v in edge_set:
        succ[u].add(v)
        pred[v].add(u)
    return node_list, edge_set, succ, pred


def _sort_key(node: T, key: Callable[[T], object] | None) -> tuple[object, str]:
    primary = key(node) if key is not None else _default_key(node)
    return (primary, repr(node))


def toposort(
    nodes: Iterable[T],
    edges: Iterable[tuple[T, T]],
    *,
    key: Callable[[T], object] | None = None,
) -> list[T]:
    """Return a deterministic topological order or raise :class:`CycleError`.

    Ready nodes are popped in ascending ``key`` order (default: type name then
    repr), so the result does not depend on the input order of ``edges``.
    """
    order, cycle = toposort_or_cycle(nodes, edges, key=key)
    if cycle is not None:
        raise CycleError(cycle)
    assert order is not None
    return order


def toposort_or_cycle(
    nodes: Iterable[T],
    edges: Iterable[tuple[T, T]],
    *,
    key: Callable[[T], object] | None = None,
) -> tuple[list[T] | None, tuple[T, ...] | None]:
    """Return ``(order, None)`` for a DAG or ``(None, cycle)`` for a cycle."""
    node_list, edge_set, succ, pred = _normalize(nodes, edges, key)
    indegree = {n: len(pred[n]) for n in node_list}
    ready = [(_sort_key(n, key), n) for n in node_list if indegree[n] == 0]
    heapq.heapify(ready)

    order: list[T] = []
    while ready:
        _, node = heapq.heappop(ready)
        order.append(node)
        for nxt in succ[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, (_sort_key(nxt, key), nxt))

    if len(order) == len(node_list):
        return order, None
    remaining = {n for n in node_list if indegree[n] > 0}
    cycle = _find_cycle(remaining, edge_set, pred, key)
    return None, _remove_chords(cycle, edge_set)


def find_cycle(
    nodes: Iterable[T], edges: Iterable[tuple[T, T]], *, key: Callable[[T], object] | None = None
) -> tuple[T, ...] | None:
    """Return a chordless cycle witness, or ``None`` for a DAG."""
    _, cycle = toposort_or_cycle(nodes, edges, key=key)
    return cycle


def _find_cycle(
    remaining: set[T],
    edge_set: set[tuple[T, T]],
    pred: dict[T, set[T]],
    key: Callable[[T], object] | None,
) -> list[T]:
    """Walk predecessors inside the residual graph until a node repeats."""
    start = min(remaining, key=lambda n: _sort_key(n, key))
    path: list[T] = []
    position: dict[T, int] = {}
    node = start
    while node not in position:
        position[node] = len(path)
        path.append(node)
        choices = pred[node] & remaining
        if not choices:  # pragma: no cover - cannot happen after Kahn
            raise GraphError("internal invariant violated: residual node has no predecessor")
        node = min(choices, key=lambda n: _sort_key(n, key))
    cycle = list(reversed(path[position[node]:]))
    if not cycle:
        raise GraphError("internal invariant violated: empty cycle")
    return cycle


def _remove_chords(cycle: list[T], edge_set: set[tuple[T, T]]) -> tuple[T, ...]:
    """Shorten the cycle while any edge jumps across it.

    A chord ``cycle[i] -> cycle[j]`` replaces the path between them.  The
    result is chordless (no such edge remains); it is not claimed to be the
    globally shortest cycle, only a locally minimal, independently checkable
    witness.
    """
    cycle = list(cycle)
    while True:
        k = len(cycle)
        shortcut = None
        for i in range(k):
            for j in range(i + 2, k):
                # The closing edge is cycle[k-1] -> cycle[0], which never
                # appears in this i<j enumeration.  Every hit here is a chord.
                if (cycle[i], cycle[j]) in edge_set:
                    shortcut = (i, j)
                    break
            if shortcut:
                break
        if shortcut is None:
            return tuple(cycle)
        i, j = shortcut
        cycle = [cycle[i]] + cycle[j:] + cycle[:i]


def verify_order(nodes: Iterable[T], edges: Iterable[tuple[T, T]], order: Sequence[T]) -> list[str]:
    """Independently check a proposed topological order; [] means valid."""
    declared = list(dict.fromkeys(nodes))
    problems: list[str] = []
    if len(order) != len(declared):
        problems.append(f"order has {len(order)} entries, expected {len(declared)}")
    if len(set(order)) != len(order):
        problems.append("order contains duplicate nodes")
    if set(order) != set(declared):
        problems.append("order does not contain exactly the declared nodes")
    if problems:
        return problems
    index = {n: i for i, n in enumerate(order)}
    for u, v in edges:
        if u not in index or v not in index:
            problems.append(f"edge {u!r} -> {v!r} references an undeclared node")
        elif index[u] >= index[v]:
            problems.append(f"edge {u!r} -> {v!r} is violated")
    return problems


def verify_cycle(nodes: Iterable[T], edges: Iterable[tuple[T, T]], cycle: Sequence[T]) -> list[str]:
    """Independently check a cycle witness, including chordlessness."""
    declared = set(nodes)
    edge_set = set(edges)
    problems: list[str] = []
    if not cycle:
        return ["cycle is empty"]
    if len(set(cycle)) != len(cycle):
        problems.append("cycle repeats a node")
    for node in cycle:
        if node not in declared:
            problems.append(f"cycle node {node!r} is not declared")
    if problems:
        return problems
    k = len(cycle)
    for i in range(k):
        u, v = cycle[i], cycle[(i + 1) % k]
        if (u, v) not in edge_set:
            problems.append(f"missing cycle edge {u!r} -> {v!r}")
    for i in range(k):
        for j in range(i + 2, k):
            if (cycle[i], cycle[j]) in edge_set:
                problems.append(f"chord {cycle[i]!r} -> {cycle[j]!r} shortcuts the witness")
    return problems
