#!/usr/bin/env python3
"""
Report total count of each GPU model on Skipjack Slurm GPU partitions.

Analog to CMU Babel gpu_counter.py: inventory from node Gres= (via
scontrol), scoped to SKIPJACK_GPU_PARTITIONS (default a100,l40s,h100,h200,b200,b300).
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import skipjack_gpu as dg  # noqa: E402
from skipjack_gpu_allocations import (  # noqa: E402
    get_cluster_data,
    parse_gres_inventory,
    pretty_model,
)


def fallback_counts_from_sinfo(partitions: str) -> Dict[str, int]:
    """
    If scontrol path yields nothing, sum GRES once per unique node from sinfo.
    """
    out = dg.run_cmd(
        ["sinfo", "-h", "-N", "-p", partitions, "-o", "%N %G"],
        shell=False,
    )
    per_node: Dict[str, Dict[str, int]] = {}
    for line in out.splitlines():
        bits = line.split(None, 1)
        if len(bits) < 2:
            continue
        node, g = bits[0], bits[1]
        if node in per_node:
            continue
        per_node[node] = parse_gres_inventory(g)
    totals: Dict[str, int] = defaultdict(int)
    for inv in per_node.values():
        for model, c in inv.items():
            totals[model] += int(c)
    return dict(totals)


def get_gpu_counts(partitions: str) -> Dict[str, int]:
    totals, _, _ = get_cluster_data(partitions)
    if totals:
        return totals
    return fallback_counts_from_sinfo(partitions)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Total GPUs per model (Skipjack GPU partitions; Babel gpu_counter.py style)."
    )
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log Slurm helper commands (via skipjack_gpu).",
    )
    args = ap.parse_args()
    dg.FLAG["verbose"] = bool(args.verbose)

    partitions = dg.partitions_csv()
    gpu_counts = get_gpu_counts(partitions)

    if not gpu_counts:
        print("No GPUs found.")
        print(f"Partitions: {partitions}")
        print("Tried: get_cluster_data() (batched scontrol show node), then sinfo -N deduped by node.")
        print("\nCheck:")
        print(f"  sinfo -N -p {partitions} -h -o '%N %G'")
        return 1

    print("GPU Model                 Count")
    print("--------------------------------")
    total = 0
    for model, count in sorted(gpu_counts.items(), key=lambda x: (-x[1], x[0])):
        label = pretty_model(model)
        print(f"{label:<25} {count:>5}")
        total += count
    print("--------------------------------")
    print(f"{'Total GPUs:':<25} {total:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
