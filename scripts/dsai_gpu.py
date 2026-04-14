#!/usr/bin/env python3
"""
DSAI Slurm GPU cluster view (JHU dsailogin-style partitions).

Inspired by CMU Babel tir_tool/gpu.py: parse Slurm GRES/TRES, summarize
queues and capacity. Defaults to GPU partitions a100,l40s,h100,nvl.

Environment:
  DSAI_GPU_PARTITIONS   Override comma-separated partition list (default below).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import defaultdict
from typing import Any, DefaultDict, Dict, Iterable, List, Tuple

# Match babel_contrib/tir_tool/gpu.py: reasons we treat as "scheduler queue" pending.
# Some Slurm sites omit parentheses in %R; include both shapes.
PENDING_REASONS = ("(Resources)", "(Priority)", "Resources", "Priority")

DEFAULT_PARTITIONS = "a100,l40s,h100,nvl"
FLAG: Dict[str, Any] = {"verbose": False}


def partitions_csv() -> str:
    return os.environ.get("DSAI_GPU_PARTITIONS", DEFAULT_PARTITIONS).strip() or DEFAULT_PARTITIONS


def run_cmd(argv: List[str], *, shell: bool = False) -> str:
    if FLAG["verbose"]:
        print("CMD:", " ".join(argv) if not shell else argv, file=sys.stderr)
    if shell:
        p = subprocess.run(argv, shell=True, capture_output=True, text=True)
    else:
        p = subprocess.run(argv, capture_output=True, text=True)
    if p.returncode != 0 and FLAG["verbose"]:
        print(p.stderr, file=sys.stderr)
    return p.stdout or ""


def parse_nodes(nodes: str) -> List[str]:
    """Expand a Slurm nodelist string (best-effort; no external calls)."""
    # Example: babel-1-[23,27,31],babel-2-12  or  c004  or  n[05-06]
    nodelist: List[str] = []
    prefix = ""
    for s in nodes.split(","):
        s = s.strip()
        if not s:
            continue
        if "[" in s:
            pre, rest = s.split("[", 1)
            nodelist.append(pre + rest)
        elif "]" in s:
            nodelist.append(prefix + s[:-1].strip())
            prefix = ""
        else:
            nodelist.append(prefix + s)
            prefix = ""
    return [n for n in nodelist if n]


def expand_nodelist_slurm(nodelist_expr: str) -> List[str]:
    """Use scontrol for correct ranges (preferred when available)."""
    expr = (nodelist_expr or "").strip()
    if not expr:
        return []
    out = run_cmd(["scontrol", "show", "hostnames", expr], shell=False)
    hosts = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return hosts if hosts else parse_nodes(expr)


def parse_gres(gres: str) -> List[Tuple[str, int]]:
    """Parse Slurm GRES gpu fragments (legacy format like tir_tool/gpu.py)."""
    if not gres or "gpu" not in gres.lower():
        return []
    gpus: List[Tuple[str, int]] = []
    for chunk in gres.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = re.split(r"[:=]", chunk)
        if len(parts) == 3 and "gpu" in parts[0].lower():
            gpus.append((parts[1], int(parts[2])))
        elif len(parts) == 2:
            try:
                gpus.append((parts[0], int(parts[1])))
            except ValueError:
                gpus.append((parts[1], 1))
        elif len(parts) == 1 and parts[0] in ("gpu", "gres/gpu"):
            gpus.append(("gpu", 1))
        else:
            if FLAG["verbose"]:
                print("WARNING: couldn't parse", parts, file=sys.stderr)
    return gpus


def parse_tres_per_node(tres: str) -> List[Tuple[str, int]]:
    """
    Parse job TRES-per-node field (%b): comma-separated, e.g.
      billing=32,cpu=8,mem=64G,gres/gpu:a100:4
      gres/gpu:2
    """
    if not tres or tres in ("N/A", "n/a"):
        return []
    found: List[Tuple[str, int]] = []
    for part in tres.split(","):
        part = part.strip()
        if not part.lower().startswith("gres/gpu"):
            continue
        # gres/gpu:TYPE:COUNT
        m = re.match(r"gres/gpu:([A-Za-z0-9_.-]+):(\d+)$", part, re.I)
        if m:
            found.append((m.group(1).lower(), int(m.group(2))))
            continue
        # gres/gpu:COUNT
        m = re.match(r"gres/gpu:(\d+)$", part, re.I)
        if m:
            found.append(("gpu", int(m.group(1))))
            continue
        # gres/gpu=COUNT (some sites)
        m = re.match(r"gres/gpu=(\d+)$", part, re.I)
        if m:
            found.append(("gpu", int(m.group(1))))
            continue
    return found


def parse_table_rows_tsv(stdout: str, columns: List[str]) -> Iterable[Dict[str, str]]:
    rows = stdout.rstrip("\n").split("\n")
    for row in rows:
        if not row.strip():
            continue
        cells = row.split("\t")
        if len(cells) < len(columns):
            continue
        yield dict(zip(columns, [c.strip() for c in cells[: len(columns)]]))


def squeue_rows(
    states: str,
    partitions: str,
    fmt_fields: List[str],
    field_names: List[str],
) -> List[Dict[str, str]]:
    delim = "\t"
    fmt = delim.join(f"%{f}" for f in fmt_fields)
    cmd = ["squeue", "-h", "-t", states, "-p", partitions, "-o", fmt]
    out = run_cmd(cmd, shell=False)
    return list(parse_table_rows_tsv(out, field_names))


def cmd_summary(_: argparse.Namespace) -> int:
    parts = partitions_csv()
    print("Partitions:", parts)
    print(run_cmd(["sinfo", "-s", "-p", parts], shell=False))
    print("--- GPU-style lines (like sinfo-gpu) ---")
    print(
        run_cmd(
            ["sinfo", "-p", parts, "-o", "%P %.6D %.10t %.10l %.6c %.10m"],
            shell=False,
        )
    )
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    parts = partitions_csv()
    delim = "|"
    cols_run = ["u", "i", "t", "P", "b", "M", "l", "D", "N"]
    fmt_run = delim.join(f"%{c}" for c in cols_run)
    out_r = run_cmd(["squeue", "-h", "-t", "R", "-p", parts, "-o", fmt_run], shell=False)
    cols_pd = ["u", "i", "t", "P", "b", "M", "l", "D", "R"]
    fmt_pd = delim.join(f"%{c}" for c in cols_pd)
    out_p = run_cmd(["squeue", "-h", "-t", "PD", "-p", parts, "-o", fmt_pd], shell=False)

    def dump(title: str, stdout: str, reason_col: bool) -> None:
        print(f"\n=== {title} ===")
        hdr = (
            f"{'USER':<12} {'JOBID':<18} {'ST':<2} {'PARTITION':<10} "
            f"{'TRES_PER_NODE':<46} {'TIME':>14} {'TIME_LIMIT':>12} {'N':>5} "
            f"{'NODELIST/REASON':<30}"
        )
        print(hdr)
        print("-" * 136)
        for line in stdout.splitlines():
            if not line.strip():
                continue
            cells = line.split(delim)
            if len(cells) < 9:
                continue
            u, jid, st, p, b, tm, tl, nn, last = cells[:9]
            tr = b[:46] + ("..." if len(b) > 46 else "")
            if reason_col:
                tail = (last[:39] + "...") if len(last) > 42 else last
            else:
                tail = (last[:25] + "...") if len(last) > 28 else last
            print(
                f"{u[:12]:<12} {jid[:18]:<18} {st:<2} {p[:10]:<10} {tr:<46} "
                f"{tm:>14} {tl:>12} {nn:>5} {tail:<30}"
            )

    dump("RUNNING", out_r, reason_col=False)
    dump("PENDING", out_p, reason_col=True)
    print("\n(TRES truncated at 46 chars; use --verbose raw or `squeue` for full strings.)")
    return 0


def cmd_by_user(_: argparse.Namespace) -> int:
    parts = partitions_csv()
    run_sum: DefaultDict[str, int] = defaultdict(int)
    pd_sum: DefaultDict[str, int] = defaultdict(int)
    run_na: DefaultDict[str, int] = defaultdict(int)
    pd_na: DefaultDict[str, int] = defaultdict(int)

    for st, acc_sum, acc_na in (
        ("R", run_sum, run_na),
        ("PD", pd_sum, pd_na),
    ):
        rows = squeue_rows(st, parts, ["u", "b"], ["USER", "TRES"])
        for r in rows:
            u = r.get("USER", "")
            tres = r.get("TRES", "")
            parsed = parse_tres_per_node(tres)
            n = sum(c for _, c in parsed)
            if n > 0:
                acc_sum[u] += n
            else:
                acc_na[u] += 1

    users = sorted(set(run_sum) | set(pd_sum) | set(run_na) | set(pd_na))
    print(f"\n=== SUM gres/gpu (from squeue %b; partitions {parts}) ===")
    print(f"{'USER':<12} {'RUN_GRES':>10} {'PD_GRES':>10} {'RUN_NA':>10} {'PD_NA':>10}")
    for u in users:
        print(
            f"{u[:12]:<12} {run_sum[u]:>10} {pd_sum[u]:>10} {run_na[u]:>10} {pd_na[u]:>10}"
        )
    print(
        "\n(RUN_NA/PD_NA = rows with no parseable gres/gpu:N in TRES; see gpu-queue / squeue -o '%b'.)"
    )
    return 0


def cmd_by_type(_: argparse.Namespace) -> int:
    parts = partitions_csv()
    # gpu_kind -> running count, pending count
    rct: DefaultDict[str, int] = defaultdict(int)
    pct: DefaultDict[str, int] = defaultdict(int)

    for st, acc in (("R", rct), ("PD", pct)):
        rows = squeue_rows(st, parts, ["u", "P", "b"], ["USER", "PART", "TRES"])
        for r in rows:
            tres = r.get("TRES", "")
            for kind, c in parse_tres_per_node(tres):
                acc[kind] += c
            if not parse_tres_per_node(tres):
                acc["_unparsed_jobs"] += 1

    print(f"\n=== GPUs by type (from TRES; partitions {parts}) ===")
    seen = set()
    ordered = []
    for k in list(rct.keys()) + list(pct.keys()):
        if k not in seen and k != "_unparsed_jobs":
            seen.add(k)
            ordered.append(k)
    for k in ordered:
        print(f"  {k:<12}  running {rct[k]:>6}   pending {pct[k]:>6}")
    if rct["_unparsed_jobs"] or pct["_unparsed_jobs"]:
        print(
            f"  {'(unparsed job rows)':<12}  running {rct['_unparsed_jobs']:>6}   pending {pct['_unparsed_jobs']:>6}"
        )
    return 0


def cmd_pending_focus(_: argparse.Namespace) -> int:
    """Count pending jobs whose reason looks like scheduler backlog (Resources/Priority)."""
    parts = partitions_csv()
    rows = squeue_rows("PD", parts, ["u", "i", "P", "R"], ["USER", "JOBID", "PART", "REASON"])
    buckets: DefaultDict[str, int] = defaultdict(int)
    other = 0
    for r in rows:
        reason = r.get("REASON", "")
        hit = any(reason.startswith(pr) for pr in PENDING_REASONS)
        if hit:
            buckets[r.get("USER", "?")] += 1
        else:
            other += 1
    print(f"\n=== Pending jobs (partitions {parts}) ===")
    print(f"Matching reasons prefix {PENDING_REASONS} (like Babel tir_tool):")
    for u in sorted(buckets, key=lambda x: (-buckets[x], x)):
        print(f"  {u:<16} {buckets[u]:>5}")
    print(f"\nOther / dependency / limits / etc.: {other} job(s)")
    return 0


def cmd_nodes_cap(args: argparse.Namespace) -> int:
    """Lightweight gpu-nodes-cap: T_GPU/U_GPU/F_GPU from scontrol + JOBFREE GiB."""
    parts = partitions_csv()
    out = run_cmd(
        ["sinfo", "-N", "-p", parts, "-h", "-o", "%N %P %t"],
        shell=False,
    )
    print("NODE     PART     STATE    T_GPU U_GPU F_GPU  TOT_GiB JOBFREE_GiB")
    print("(F_GPU from CfgTRES/AllocTRES gres/gpu=; JOBFREE = (RealMemory-AllocMem)/1024)")
    lines = 0
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        bits = line.split()
        if len(bits) < 3:
            continue
        node, part, st = bits[0], bits[1], bits[2]
        detail = run_cmd(["scontrol", "show", "node", node, "-o"], shell=False)
        if not detail:
            continue
        st_m = re.search(r"State=([^ ]+)", detail)
        st = st_m.group(1) if st_m else st
        low = st.lower()
        if any(x in low for x in ("drain", "down", "maint", "fail", "not_resp")):
            continue
        cfg_m = re.search(r"CfgTRES=([^ ]+)", detail)
        al_m = re.search(r"AllocTRES=([^ ]+)", detail)
        cfg = cfg_m.group(1) if cfg_m else ""
        alo = al_m.group(1) if al_m else ""

        def tres_gpu_count(blob: str) -> int:
            for seg in blob.split(","):
                if seg.startswith("gres/gpu=") and seg.split("=", 1)[1].isdigit():
                    return int(seg.split("=", 1)[1])
            gm = re.search(r"Gres=gpu:[^:]+:(\d+)", detail)
            return int(gm.group(1)) if gm else 0

        tg = tres_gpu_count(cfg)
        ug = tres_gpu_count(alo)
        fg = max(tg - ug, 0)
        rm = re.search(r"RealMemory=(\d+)", detail)
        am = re.search(r"AllocMem=(\d+)", detail)
        real = int(rm.group(1)) if rm else 0
        allocm = int(am.group(1)) if am else 0
        unbook = max(real - allocm, 0)
        tot_g = real / 1024.0
        jf_g = unbook / 1024.0
        print(f"{node:<8} {part:<8} {st:<8} {tg:5d} {ug:5d} {fg:5d} {tot_g:9.1f} {jf_g:9.1f}")
        lines += 1
        max_n = getattr(args, "max_nodes", 0) or 0
        if max_n and lines >= max_n:
            break
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    cmd_summary(args)
    cmd_nodes_cap(args)
    cmd_queue(args)
    cmd_by_user(args)
    cmd_by_type(args)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="DSAI Slurm GPU reports (dsailogin-style).")
    ap.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print commands and parser warnings.",
    )
    sp = ap.add_subparsers(dest="cmd", required=True)

    p_s = sp.add_parser("summary", help="sinfo -s + wide partition table for GPU partitions.")
    p_s.set_defaults(func=cmd_summary)

    p_q = sp.add_parser("queue", help="Running/pending tables (like gpu-queue).")
    p_q.set_defaults(func=cmd_queue)

    p_u = sp.add_parser("by-user", help="Sum gres/gpu per user (running/pending).")
    p_u.set_defaults(func=cmd_by_user)

    p_t = sp.add_parser("by-type", help="Sum GPUs by model (a100, l40s, …) from TRES.")
    p_t.set_defaults(func=cmd_by_type)

    p_pf = sp.add_parser(
        "pending-focus",
        help="Pending counts by user for Resources/Priority reasons.",
    )
    p_pf.set_defaults(func=cmd_pending_focus)

    p_n = sp.add_parser(
        "nodes-cap",
        help="Per-node T_GPU/U_GPU/F_GPU + memory GiB (like gpu-nodes-cap).",
    )
    p_n.add_argument(
        "--max-nodes",
        type=int,
        default=0,
        metavar="N",
        help="Limit rows (0 = no limit).",
    )
    p_n.set_defaults(func=cmd_nodes_cap)

    p_r = sp.add_parser("report", help="Run summary, nodes-cap, queue, by-user, by-type.")
    p_r.set_defaults(func=cmd_report)

    args = ap.parse_args()
    FLAG["verbose"] = bool(args.verbose)
    fn = getattr(args, "func", None)
    if fn is None:
        ap.print_help()
        return 2
    return int(fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
