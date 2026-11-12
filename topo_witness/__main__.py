"""CLI: read {"nodes": [...], "edges": [[u, v], ...]} from a file or stdin."""

from __future__ import annotations

import argparse
import json
import sys

from .core import GraphError, parallel_layers_or_cycle, toposort_or_cycle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="topo_witness",
        description="Topologically sort JSON graph input, or print a chordless cycle.",
    )
    parser.add_argument("path", nargs="?", default="-", help="JSON file, default stdin")
    parser.add_argument("--layers", action="store_true", help="emit parallel waves instead of one order")
    args = parser.parse_args(argv)

    try:
        text = sys.stdin.read() if args.path == "-" else open(args.path, encoding="utf-8").read()
        payload = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read JSON: {exc}", file=sys.stderr)
        return 2

    if not isinstance(payload, dict) or "nodes" not in payload:
        print("error: expected an object with nodes and edges", file=sys.stderr)
        return 2
    nodes = payload["nodes"]
    edges = payload.get("edges", [])
    if not isinstance(nodes, list) or not isinstance(edges, list):
        print("error: nodes and edges must be lists", file=sys.stderr)
        return 2
    try:
        if args.layers:
            layers, cycle = parallel_layers_or_cycle(nodes, [tuple(e) for e in edges])
        else:
            layers = None
            order, cycle = toposort_or_cycle(nodes, [tuple(e) for e in edges])
    except (GraphError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if cycle is not None:
        print(json.dumps({"order": None, "layers": None, "cycle": list(cycle)}))
        print("error: cycle: " + " -> ".join(map(str, cycle + cycle[:1])), file=sys.stderr)
        return 3
    if args.layers:
        print(json.dumps({"order": None, "layers": layers, "cycle": None}))
    else:
        print(json.dumps({"order": order, "layers": None, "cycle": None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
