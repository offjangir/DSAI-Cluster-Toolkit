#!/usr/bin/env python3
"""
DSAI Slurm GPU allocation summary (CMU Babel gpu_allocations.py style).

Uses the same GPU partition list as dsai_gpu.py (DSAI_GPU_PARTITIONS / defaults).
Requires Slurm: sinfo, scontrol, squeue.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional, Set

# Reuse Slurm helpers from sibling script (same directory on PATH).
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import dsai_gpu as dg  # noqa: E402


def parse_gres_inventory(gres_blob: str) -> Dict[str, int]:
    """Parse node Gres= field, e.g. gpu:a100:8 or gpu:l40s:4."""
    out: DefaultDict[str, int] = defaultdict(int)
    if not gres_blob or gres_blob in ("(null)", "null", "N/A"):
        return {}
    for seg in gres_blob.split(","):
        seg = seg.strip()
        m = re.match(r"gpu:([a-z0-9_.-]+):(\d+)$", seg, re.I)
        if m:
            out[m.group(1).lower()] += int(m.group(2))
            continue
        m = re.match(r"gpu:(\d+)$", seg, re.I)
        if m:
            out["gpu"] += int(m.group(1))
    return dict(out)


def tres_gpu_numeric(tres: str) -> int:
    if not tres:
        return 0
    for seg in tres.split(","):
        seg = seg.strip()
        if seg.startswith("gres/gpu="):
            tail = seg.split("=", 1)[1]
            if tail.isdigit():
                return int(tail)
    return 0


def node_is_unavailable(state: str) -> bool:
    s = state.lower()
    return any(
        k in s
        for k in (
            "drain",
            "down",
            "not_resp",
            "fail",
            "maint",
            "power_down",
            "powering_down",
        )
    )


def split_node_records(blob: str) -> List[str]:
    blob = (blob or "").strip()
    if not blob:
        return []
    parts = re.split(r"\s+(?=NodeName=)", blob)
    return [p for p in parts if p.startswith("NodeName=")]


def parse_node_record(rec: str) -> Optional[Dict[str, object]]:
    m = re.search(r"\bNodeName=(\S+)", rec)
    if not m:
        return None
    name = m.group(1)
    sm = re.search(r"\bState=([A-Za-z0-9_+]+)", rec)
    state = sm.group(1) if sm else ""
    gm = re.search(r"\bGres=(\S+)", rec)
    gres = gm.group(1) if gm else ""
    cm = re.search(r"\bCfgTRES=([^ ]+)", rec)
    am = re.search(r"\bAllocTRES=([^ ]+)", rec)
    cfg = cm.group(1) if cm else ""
    alloc = am.group(1) if am else ""
    return {
        "name": name,
        "state": state,
        "gres": gres,
        "by_model": parse_gres_inventory(gres),
        "cfg_gpu": tres_gpu_numeric(cfg),
        "alloc_gpu": tres_gpu_numeric(alloc),
        "cfg_tres": cfg,
        "alloc_tres": alloc,
    }


def norm_model(s: str) -> str:
    return s.strip().lower().replace("-", "_")


def pretty_model(m: str) -> str:
    m = m.lower()
    if m == "l40s":
        return "L40S"
    if m == "h100":
        return "H100"
    if m == "a100":
        return "A100"
    if m == "nvl" or m == "nvlink":
        return m.upper()
    if m == "gpu":
        return "GPU"
    return m.upper()


def unique_gpu_nodes(partitions: str) -> List[str]:
    out = dg.run_cmd(
        ["sinfo", "-h", "-N", "-p", partitions, "-o", "%N"],
        shell=False,
    )
    nodes = sorted({ln.strip() for ln in out.splitlines() if ln.strip()})
    return nodes


def fetch_node_infos(nodes: List[str]) -> List[Dict[str, object]]:
    infos: List[Dict[str, object]] = []
    batch_size = 20
    for i in range(0, len(nodes), batch_size):
        batch = nodes[i : i + batch_size]
        arg = ",".join(batch)
        raw = dg.run_cmd(["scontrol", "show", "node", arg], shell=False)
        for rec in split_node_records(raw):
            parsed = parse_node_record(rec)
            if parsed:
                infos.append(parsed)
    return infos


def get_cluster_data(
    partitions: str,
) -> Tuple[Dict[str, int], Dict[str, int], List[Dict[str, object]]]:
    """Return totals[model], unavailable[model], parsed node records."""
    nodes = unique_gpu_nodes(partitions)
    totals: DefaultDict[str, int] = defaultdict(int)
    unavailable: DefaultDict[str, int] = defaultdict(int)
    infos = fetch_node_infos(nodes)

    for info in infos:
        state = str(info["state"])
        by_model: Dict[str, int] = dict(info["by_model"])  # type: ignore[arg-type]
        if not by_model and int(info["cfg_gpu"] or 0) > 0:
            # Typed GRES missing but CfgTRES has GPUs — count as generic.
            by_model = {"gpu": int(info["cfg_gpu"])}
        info["by_model"] = by_model
        for model, c in by_model.items():
            totals[model] += int(c)
        if node_is_unavailable(state):
            for model, c in by_model.items():
                unavailable[model] += int(c)

    return dict(totals), dict(unavailable), infos


def aggregate_job_gpus(partitions: str, state: str) -> DefaultDict[str, int]:
    rows = dg.squeue_rows(state, partitions, ["b"], ["TRES"])
    acc: DefaultDict[str, int] = defaultdict(int)
    for r in rows:
        for kind, c in dg.parse_tres_per_node(r.get("TRES", "")):
            acc[kind] += int(c)
    return acc


def get_running(partitions: str) -> DefaultDict[str, int]:
    return aggregate_job_gpus(partitions, "R")


def get_pending(partitions: str) -> DefaultDict[str, int]:
    return aggregate_job_gpus(partitions, "PD")


def primary_model(by_model: Dict[str, int]) -> str:
    if not by_model:
        return "gpu"
    return max(by_model.items(), key=lambda kv: (kv[1], kv[0]))[0]


def get_free_nodes_report(
    infos: List[Dict[str, object]],
    model_filter: Optional[Set[str]],
) -> Dict[str, List[str]]:
    """model -> list of 'nodename:free_gpus' for schedulable nodes with free GPUs."""
    free_by: DefaultDict[str, List[str]] = defaultdict(list)
    for info in infos:
        state = str(info["state"])
        if node_is_unavailable(state):
            continue
        cfg_g = int(info["cfg_gpu"] or 0)
        alloc_g = int(info["alloc_gpu"] or 0)
        free_g = max(0, cfg_g - alloc_g)
        if free_g <= 0:
            continue
        by_model = info["by_model"]  # type: ignore[assignment]
        assert isinstance(by_model, dict)
        pm = primary_model(by_model)
        if model_filter is not None and norm_model(pm) not in model_filter:
            continue
        free_by[pm].append(f"{info['name']}:{free_g}")
    return dict(free_by)


def models_in_scope(
    totals: Dict[str, int],
    running: Dict[str, int],
    pending: Dict[str, int],
    unavailable: Dict[str, int],
) -> List[str]:
    keys = set(totals) | set(running) | set(pending) | set(unavailable)
    return sorted(keys, key=lambda m: (-totals.get(m, 0), pretty_model(m)))


def print_text_report(
    totals: Dict[str, int],
    unavailable: Dict[str, int],
    running: Dict[str, int],
    pending: Dict[str, int],
    free_nodes: Dict[str, List[str]],
    free_only: bool,
    show_nodes: bool,
    model_filter: Optional[Set[str]],
) -> None:
    now = datetime.now().strftime("%Y.%m.%d at %H:%M:%S")
    print(f"executed on {now} ")
    print()

    models = models_in_scope(totals, running, pending, unavailable)
    if model_filter is not None:
        models = [m for m in models if norm_model(m) in model_filter]

    if not free_only:
        hdr = (
            f"{'GPU Model':<22} {'Total':>7} {'Running':>9} {'Free':>7} "
            f"{'Pending':>9} {'drain/dn':>12} {'Util %':>8}"
        )
        print(hdr)
        print("-" * len(hdr))
        tot_all = run_all = pend_all = un_all = 0
        free_all = 0
        for model in models:
            tot = totals.get(model, 0)
            un = unavailable.get(model, 0)
            run = running.get(model, 0)
            pend = pending.get(model, 0)
            usable = max(0, tot - un)
            free = max(0, usable - run)
            util = round((run / usable * 100) if usable > 0 else 0.0, 1)
            print(
                f"{pretty_model(model):<22} {tot:>7} {run:>9} {free:>7} "
                f"{pend:>9} {un:>12} {util:>8}"
            )
            tot_all += tot
            run_all += run
            pend_all += pend
            un_all += un
            free_all += free
        usable_all = max(0, tot_all - un_all)
        util_all = round((run_all / usable_all * 100) if usable_all > 0 else 0.0, 1)
        print("-" * len(hdr))
        print(
            f"{'Cluster total':<22} {tot_all:>7} {run_all:>9} {free_all:>7} "
            f"{pend_all:>9} {un_all:>12} {util_all:>8}"
        )
        print()

    if show_nodes or free_only:
        if not free_nodes:
            print("No nodes with free GPUs right now.")
        else:
            keys = sorted(free_nodes.keys(), key=lambda m: pretty_model(m))
            if model_filter is not None:
                keys = [k for k in keys if norm_model(k) in model_filter]
            for model in keys:
                entries = free_nodes[model]
                print(f"{pretty_model(model):<12}")
                line = "  "
                col = 0
                for entry in entries:
                    if col > 0 and col % 4 == 0:
                        print(line.rstrip())
                        line = "  "
                    line += f"{entry:<18}"
                    col += 1
                if line.strip():
                    print(line.rstrip())
                print()


def print_json(
    totals: Dict[str, int],
    unavailable: Dict[str, int],
    running: Dict[str, int],
    pending: Dict[str, int],
    free_nodes: Dict[str, List[str]],
    free_only: bool,
) -> None:
    data: Dict[str, object] = {"timestamp": datetime.now().isoformat()}
    if free_only:
        data["nodes_with_free_by_model"] = free_nodes or {}
    else:
        models_obj: Dict[str, object] = {}
        for model in sorted(set(totals) | set(running) | set(pending) | set(unavailable)):
            tot = totals.get(model, 0)
            run_cnt = running.get(model, 0)
            pend_cnt = pending.get(model, 0)
            unavail_cnt = unavailable.get(model, 0)
            usable = tot - unavail_cnt
            free = max(0, usable - run_cnt)
            util = round((run_cnt / usable * 100) if usable > 0 else 0.0, 1)
            models_obj[pretty_model(model)] = {
                "total": tot,
                "running": run_cnt,
                "free": free,
                "pending": pend_cnt,
                "unavailable": unavail_cnt,
                "utilization_percent": util,
            }
        data["models"] = models_obj
        all_m = set(totals) | set(running) | set(pending) | set(unavailable)
        data["cluster"] = {
            "total": sum(totals.values()),
            "running": sum(running.values()),
            "free": sum(
                max(0, totals.get(m, 0) - unavailable.get(m, 0) - running.get(m, 0))
                for m in all_m
            ),
            "pending": sum(pending.values()),
            "unavailable": sum(unavailable.values()),
        }
    print(json.dumps(data, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show GPU status in Slurm (DSAI-style; Babel gpu_allocations.py analog).",
        epilog="""Examples:
  dsai_gpu_allocations.py                     # Table only
  dsai_gpu_allocations.py --nodes             # Table + free nodes
  dsai_gpu_allocations.py -f                  # Free nodes only
  dsai_gpu_allocations.py -f --model h100    # Free H100-class nodes only
  dsai_gpu_allocations.py --json              # Full table as JSON
  dsai_gpu_allocations.py -f --json           # Free nodes JSON only
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--nodes",
        "-n",
        action="store_true",
        help="Include nodes with free GPUs (Slurm cfg vs alloc TRES)",
    )
    parser.add_argument(
        "--model",
        nargs="+",
        metavar="MODEL",
        help="Filter node list / table rows to these GPU model names (e.g. l40s h100)",
    )
    parser.add_argument(
        "--free-only",
        "-f",
        action="store_true",
        help="Show only the free-nodes section (skip totals table)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable JSON",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print Slurm commands to stderr",
    )
    args = parser.parse_args()
    dg.FLAG["verbose"] = bool(args.verbose)

    partitions = dg.partitions_csv()
    totals, unavailable, infos = get_cluster_data(partitions)
    running = get_running(partitions)
    pending = get_pending(partitions)
    mf: Optional[Set[str]] = None
    if args.model:
        mf = {norm_model(x) for x in args.model}

    free_nodes = get_free_nodes_report(infos, mf)

    if args.json:
        print_json(totals, unavailable, running, pending, free_nodes, args.free_only)
    else:
        show_list = args.nodes or args.free_only
        print_text_report(
            totals,
            unavailable,
            running,
            pending,
            free_nodes,
            args.free_only,
            show_list,
            mf,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
