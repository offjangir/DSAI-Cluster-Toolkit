# DSAI Slurm toolkit

Bash aliases, functions, and Python helpers for **Slurm + GPU** workflows on **JHU-style DSAI** login nodes. Defaults target partitions `med`, `a100`, `l40s`, `h100`, `h200`, `b200`, `b300`; every site-specific name is a shell variable (see [Environment](#environment)), so adjust there rather than editing functions.

## Contents

| Path | Purpose |
|------|---------|
| [`shell/dsai-slurm-toolkit.bash`](shell/dsai-slurm-toolkit.bash) | Full toolkit block: aliases, `gpu_join`, `mygpus`, `gpu_whereami`, queue reports, etc. |
| [`scripts/dsai_gpu.py`](scripts/dsai_gpu.py) | CLI: `summary`, `queue`, `by-user`, `by-type`, `nodes-cap`, `report`, … |
| [`scripts/dsai_gpu_allocations.py`](scripts/dsai_gpu_allocations.py) | Babel-style GPU totals / running / pending / free (`--nodes`, `--json`, …). |
| [`scripts/dsai_gpu_counter.py`](scripts/dsai_gpu_counter.py) | Per-model GPU inventory counts. |
| [`docs/TOOLKIT.md`](docs/TOOLKIT.md) | Longer documentation (design notes, tables, troubleshooting). |

The three Python scripts expect to live in the **same directory** on `PATH` (they import each other).

## Install

1. **Clone** (or copy) this repository to the machine where you use Slurm (e.g. under your home directory).

   ```bash
   git clone https://github.com/offjangir/DSAI-Cluster-Toolkit.git ~/DSAI-Cluster-Toolkit
   cd ~/DSAI-Cluster-Toolkit
   ```

2. **Put scripts on `PATH`** (pick one):

   ```bash
   cp scripts/*.py ~/bin/
   chmod +x ~/bin/dsai_gpu.py ~/bin/dsai_gpu_allocations.py ~/bin/dsai_gpu_counter.py
   ```

   Ensure `~/bin` is on `PATH` (common pattern):

   ```bash
   [[ ":$PATH:" != *":$HOME/bin:"* ]] && PATH="$HOME/bin:$PATH"
   ```

3. **Load the shell toolkit.** On RHEL-family images whose stock `~/.bashrc` already sources
   `~/.bashrc.d/*`, drop a stub there and leave `~/.bashrc` untouched:

   ```bash
   mkdir -p ~/.bashrc.d
   cat > ~/.bashrc.d/dsai-slurm-toolkit.sh <<'EOF'
   DSAI_TOOLKIT_DIR="$HOME/DSAI-Cluster-Toolkit"
   [[ -f "$DSAI_TOOLKIT_DIR/shell/dsai-slurm-toolkit.bash" ]] && . "$DSAI_TOOLKIT_DIR/shell/dsai-slurm-toolkit.bash"
   EOF
   ```

   Sourcing from the checkout means `git pull` updates your shell. If your `~/.bashrc` has no
   `~/.bashrc.d` loop, put that same one-liner directly in `~/.bashrc` instead.

   Alternatively, copy the contents of `shell/dsai-slurm-toolkit.bash` between the `# DSAI SLURM SHORTCUT TOOLKIT` markers in your `~/.bashrc` and keep the Python scripts on `PATH` as above.

4. **Reload** the shell:

   ```bash
   source ~/.bashrc
   ```

5. **Check**:

   ```bash
   aliases-help
   dsai_gpu.py summary
   gpu-counter
   ```

## Environment

All three are set at the top of `shell/dsai-slurm-toolkit.bash` and honour a pre-existing
value, so you can override them in `~/.bashrc` *before* sourcing the toolkit.

- **`DSAI_GPU_PARTITIONS`** — comma-separated GPU partitions used by both the Python tools
  and the bash report functions (`gpu-free`, `gpu-open`, `gpu-nodes-cap`, `gpu-queue`,
  `gpu-users-gres`). Default: `a100,l40s,h100,h200,b200,b300`.

  ```bash
  export DSAI_GPU_PARTITIONS=a100,l40s,h100,h200,b200,b300
  ```

- **`DSAI_CPU_PARTITION`** — CPU-only partition for `salloc-cpu` / `srun-cpu`. Default: `med`.

- **`DSAI_COMPUTE_HOST_RE`** — regex identifying compute nodes, so `gpu_join` can refuse to
  run from a plain `ssh` session. Default: `^(csr|ga|gb|gh|gl)[0-9]+$`.

### Memory is welded to core count

Every partition on this cluster sets `DefMemPerCPU == MaxMemPerCPU`, so `--mem=64G` does not
cap memory — it silently inflates your **core** request until the ratio fits. The interactive
aliases therefore use explicit `--mem-per-cpu` at or under each cap:

| Partition | Max MB/core | Node shape |
|---|---|---|
| `med` | 4000 | 112 cores (108 usable), ~515 GB, no GPUs |
| `a100`, `l40s` | 6000 | 96 / 128 cores, 8 GPUs |
| `h100`, `h200`, `b200`, `b300` | 12000 | 128 cores, 8 GPUs |

## Matching physical GPUs

Run **`gpu_whereami`** in two contexts (e.g. plain `ssh` to the node and inside `srun` / `gpu_join`) and compare the **`pci.bus_id`** column. Same bus id is the same physical card. See **`docs/TOOLKIT.md`**.



## License

See [LICENSE](LICENSE).
