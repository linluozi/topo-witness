# topo-witness

`topo_witness` sorts a dependency graph deterministically, and when the graph is cyclic it does not just say "cycle detected": it returns a **chordless cycle witness** — a concrete ordered list of nodes where every consecutive edge exists and no edge in the graph shortcuts across the cycle. `verify_cycle()` re-checks that witness independently.

Upstream: none

## Why this exists

Build systems, migrations and schedulers need two things from a cycle: which nodes are involved, and a proof that the report is real. A raw cycle report can contain a shortcut edge that jumps across the loop, which makes the explanation weaker. Here the witness is minimized until no chord remains, so every node in it is necessary for *that* witness.

```
graph: 0 -> 1 -> 2 -> 3 -> 4 -> 0, plus 0 -> 2
naive: 0 -> 1 -> 2 -> 3 -> 4 -> 0   (contains the 0 -> 2 shortcut)
ours:  2 -> 3 -> 4 -> 0             (no chord; node 1 is not needed)
```

## Install

```bash
python3 -m pip install .
```

Python 3.9+, zero dependencies.

## Use

```python
from topo_witness import CycleError, toposort, toposort_or_cycle, verify_cycle

order = toposort(["compile", "test", "deploy"], [("compile", "test"), ("test", "deploy")])
# ['compile', 'test', 'deploy']

order, cycle = toposort_or_cycle(
    ["a", "b", "c", "d"],
    [("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")],
)
print(order, cycle)          # None ('b', 'c', 'a')
print(verify_cycle(["a", "b", "c", "d"], [("a", "b"), ("b", "c"), ("c", "a")], cycle))
# []  -> the witness is valid and chordless

try:
    toposort(["x", "y"], [("x", "y"), ("y", "x")])
except CycleError as exc:
    print(exc.cycle)         # ('x', 'y')
```

A directed cycle has no canonical starting node, so both the diagram and the printed examples show the exact rotation this implementation returns for the given input order; any rotation describes the same cycle. Determinism: ready nodes are popped in ascending `key` order (default `(type name, repr)`), so shuffling the edge list does not change the order. Pass `key=` for domain ordering.

### CLI

```bash
echo '{"nodes":["b","a","c"],"edges":[["a","c"]]}' | python3 -m topo_witness -
# {"order": ["a", "b", "c"], "cycle": null}

echo '{"nodes":["a","b"],"edges":[["a","b"],["b","a"]]}' | python3 -m topo_witness -
# {"order": null, "cycle": ["b", "a"]}   (exit 3)
```

Exit `0` DAG, `3` cycle, `2` malformed input.

## What "witness" means here

- **Valid:** every consecutive pair, including the wrap from last to first, is a declared edge; nodes are distinct and declared.
- **Chordless:** for every `i < j` with `j >= i+2`, there is no edge `cycle[i] -> cycle[j]`. Such an edge would let the cycle be shortened, so its absence is what makes the witness locally minimal. The closing edge is `cycle[-1] -> cycle[0]` and is not a chord.
- It is **not** claimed to be the globally shortest cycle. A chordless witness can still be longer than the shortest cycle elsewhere in the graph; the README and tests say "chordless", not "shortest".

`verify_order()` and `verify_cycle()` are standalone checkers: they take the graph and the proposed answer and return a list of human-readable violations (`[]` means valid). They do not call the sorter.

## Evidence (actually run)

```bash
python3 -m unittest discover -s tests -v
```

Result on 2026-11-12, CPython 3.12.3: **20 tests, OK, 0.178 s**.

- **300 seeded random DAGs** (n=1–30, random topological permutation, p=0.18 forward edges): every output contains each node once and satisfies every edge; verified both with `verify_order` and an independent position map. Seed `20261112`.
- **200 seeded random cyclic graphs** (n=2–25, a random 2–10 node ring plus random extra edges): every witness passes `verify_cycle` **and** a separate test-side chord scan that does not call the implementation. Seed `424242`.
- Edge-order invariance: 30 shuffles of both node and edge lists produce the identical order.
- 5,000-node chain completes iteratively (no `RecursionError`) and matches the input order.
- Self-loop, 2-cycle, chorded 3-cycle, duplicate nodes/edges, unknown endpoints, empty graph, and malformed CLI JSON are covered.
- The chord-removal test starts from a 5-cycle with chord `0 -> 2` and asserts the witness is the 4-node `{0,2,3,4}` cycle with node 1 eliminated.

## Limits

- Nodes must be hashable. Default ordering uses `repr`, which is deterministic for strings/numbers but not a semantic order; pass `key=` when order matters.
- The witness is chordless, not minimum-length; computing a shortest directed cycle would need a different algorithm.
- Recursion-free by construction (iterative Kahn + predecessor walk), so very deep graphs are fine.

## License

MIT. See `LICENSE`.
