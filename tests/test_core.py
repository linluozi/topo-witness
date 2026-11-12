from __future__ import annotations

import json
import random
import subprocess
import sys
import unittest

from topo_witness import (
    CycleError,
    GraphError,
    UnknownNodeError,
    find_cycle,
    toposort,
    toposort_or_cycle,
    verify_cycle,
    verify_order,
)


def random_dag(rng: random.Random, n: int) -> tuple[list[int], list[tuple[int, int]]]:
    perm = list(range(n))
    rng.shuffle(perm)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            if rng.random() < 0.18:
                edges.append((perm[i], perm[j]))
    return perm, edges


def assert_chordless(test: unittest.TestCase, edges: list[tuple[int, int]], cycle) -> None:
    """Test-side chord check, deliberately not calling verify_cycle."""
    edge_set = set(edges)
    k = len(cycle)
    for i in range(k):
        test.assertIn((cycle[i], cycle[(i + 1) % k]), edge_set)
    for i in range(k):
        for j in range(i + 2, k):
            if i == 0 and j == k - 1:
                continue
            test.assertNotIn((cycle[i], cycle[j]), edge_set, msg=f"chord {cycle} at {i},{j}")


class DAGs(unittest.TestCase):
    def test_300_random_dags(self) -> None:
        rng = random.Random(20261112)
        checked = 0
        for _ in range(300):
            n = rng.randint(1, 30)
            nodes, edges = random_dag(rng, n)
            order = toposort(nodes, edges)
            self.assertEqual(len(order), n)
            self.assertEqual(verify_order(nodes, edges, order), [])
            # Independent positional check, not relying on verify_order.
            index = {node: i for i, node in enumerate(order)}
            for u, v in edges:
                self.assertLess(index[u], index[v])
            checked += 1
        self.assertEqual(checked, 300)

    def test_edge_order_does_not_change_output(self) -> None:
        nodes = ["build", "lint", "test", "docs", "deploy"]
        edges = [("build", "test"), ("build", "lint"), ("test", "deploy"), ("docs", "deploy")]
        baseline = toposort(nodes, edges)
        rng = random.Random(7)
        for _ in range(30):
            shuffled_edges = list(edges)
            shuffled_nodes = list(nodes)
            rng.shuffle(shuffled_edges)
            rng.shuffle(shuffled_nodes)
            self.assertEqual(toposort(shuffled_nodes, shuffled_edges), baseline)

    def test_default_key_is_stable_for_mixed_types(self) -> None:
        self.assertEqual(toposort([3, "3", 1], [(1, 3)]), [1, 3, "3"])

    def test_custom_key(self) -> None:
        order = toposort(["b", "a", "c"], [("a", "c")], key=lambda s: s)
        self.assertEqual(order, ["a", "b", "c"])

    def test_duplicate_nodes_and_edges_are_ignored(self) -> None:
        self.assertEqual(toposort(["a", "a", "b"], [("a", "b"), ("a", "b")]), ["a", "b"])

    def test_empty_graph_rejected(self) -> None:
        with self.assertRaises(GraphError):
            toposort([], [])

    def test_unknown_endpoint(self) -> None:
        with self.assertRaises(UnknownNodeError):
            toposort(["a"], [("a", "b")])
        with self.assertRaises(UnknownNodeError):
            toposort(["a"], [("z", "a")])

    def test_5000_node_chain_is_iterative(self) -> None:
        n = 5000
        nodes = list(range(n))
        edges = [(i, i + 1) for i in range(n - 1)]
        order = toposort(nodes, edges)
        self.assertEqual(order, nodes)
        self.assertEqual(verify_order(nodes, edges, order), [])


class Cycles(unittest.TestCase):
    def test_finds_known_cycle(self) -> None:
        nodes = ["a", "b", "c", "d"]
        edges = [("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")]
        order, cycle = toposort_or_cycle(nodes, edges)
        self.assertIsNone(order)
        self.assertIsNotNone(cycle)
        assert cycle is not None
        self.assertEqual(verify_cycle(nodes, edges, cycle), [])
        self.assertEqual(set(cycle), {"a", "b", "c"})

    def test_toposort_raises_with_witness(self) -> None:
        with self.assertRaises(CycleError) as ctx:
            toposort(["x", "y"], [("x", "y"), ("y", "x")])
        self.assertEqual(set(ctx.exception.cycle), {"x", "y"})

    def test_self_loop(self) -> None:
        order, cycle = toposort_or_cycle(["solo"], [("solo", "solo")])
        self.assertIsNone(order)
        self.assertEqual(cycle, ("solo",))
        self.assertEqual(verify_cycle(["solo"], [("solo", "solo")], cycle), [])

    def test_two_cycle(self) -> None:
        edges = [("a", "b"), ("b", "a")]
        cycle = find_cycle(["a", "b"], edges)
        self.assertEqual(set(cycle), {"a", "b"})
        self.assertEqual(verify_cycle(["a", "b"], edges, cycle), [])

    def test_200_random_cyclic_graphs_have_valid_chordless_witness(self) -> None:
        rng = random.Random(424242)
        checked = 0
        for _ in range(200):
            n = rng.randint(2, 25)
            nodes = list(range(n))
            k = rng.randint(2, min(n, 10))
            ring = rng.sample(nodes, k)
            edges = [(ring[i], ring[(i + 1) % k]) for i in range(k)]
            for _ in range(rng.randint(0, n)):
                u, v = rng.choice(nodes), rng.choice(nodes)
                edges.append((u, v))
            order, cycle = toposort_or_cycle(nodes, edges)
            self.assertIsNone(order)
            self.assertIsNotNone(cycle)
            assert cycle is not None
            self.assertEqual(verify_cycle(nodes, edges, cycle), [])
            self.assertEqual(len(set(cycle)), len(cycle))
            assert_chordless(self, edges, cycle)
            checked += 1
        self.assertEqual(checked, 200)

    def test_chord_removal_shortens_obvious_shortcut(self) -> None:
        # 0->1->2->3->4->0 plus 0->2: witness must drop the 0->1->2 detour.
        nodes = list(range(5))
        edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0), (0, 2)]
        cycle = find_cycle(nodes, edges)
        self.assertEqual(len(cycle), 4)
        self.assertEqual(set(cycle), {0, 2, 3, 4})
        self.assertNotIn(1, cycle)
        assert_chordless(self, edges, cycle)
        self.assertEqual(verify_cycle(nodes, edges, cycle), [])

    def test_verify_cycle_catches_bad_witness(self) -> None:
        nodes = ["a", "b", "c"]
        edges = [("a", "b"), ("b", "c"), ("c", "a")]
        self.assertTrue(verify_cycle(nodes, edges, ["a", "b"]))          # missing edge
        self.assertTrue(verify_cycle(nodes, edges, ["a", "b", "a"]))    # repeat
        self.assertTrue(verify_cycle(nodes, edges, ["a", "b", "z"]))    # unknown
        # Add a chord a->c; the 3-cycle now has a chord and must be rejected.
        self.assertTrue(verify_cycle(nodes, edges + [("a", "c")], ["a", "b", "c"]))

    def test_verify_order_rejects_bad_orders(self) -> None:
        nodes = ["a", "b"]
        edges = [("a", "b")]
        self.assertTrue(verify_order(nodes, edges, ["b", "a"]))
        self.assertTrue(verify_order(nodes, edges, ["a"]))
        self.assertTrue(verify_order(nodes, edges, ["a", "b", "b"]))
        self.assertTrue(verify_order(nodes, [("a", "z")], ["a", "b"]))
        self.assertEqual(verify_order(nodes, edges, ["a", "b"]), [])

    def test_acyclic_returns_none_cycle(self) -> None:
        self.assertIsNone(find_cycle(["a", "b"], [("a", "b")]))


class CLI(unittest.TestCase):
    def run_cli(self, payload: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "topo_witness", "-"],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_dag_exit_zero(self) -> None:
        proc = self.run_cli(json.dumps({"nodes": ["b", "a", "c"], "edges": [["a", "c"]]}))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["order"], ["a", "b", "c"])

    def test_cycle_exit_three(self) -> None:
        proc = self.run_cli(json.dumps({"nodes": ["a", "b"], "edges": [["a", "b"], ["b", "a"]]}))
        self.assertEqual(proc.returncode, 3)
        payload = json.loads(proc.stdout)
        self.assertIsNone(payload["order"])
        self.assertEqual(set(payload["cycle"]), {"a", "b"})

    def test_bad_json_exit_two(self) -> None:
        self.assertEqual(self.run_cli("{oops").returncode, 2)
        self.assertEqual(self.run_cli(json.dumps({"nodes": ["a"], "edges": [["a", "z"]]})).returncode, 2)


if __name__ == "__main__":
    unittest.main()
