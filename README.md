# Skipjack cluster setup

Bash aliases, functions, and Python helpers for **Slurm + GPU** workflows on **Skipjack**, the JHU ARCH DSAI cluster (login node `login01`, reached as `dsailogin.arch.jhu.edu`). Defaults target partitions `med`, `a100`, `l40s`, `h100`, `h200`, `b200`, `b300`; every site-specific name is a shell variable (see [Environment](#environment)), so adjust there rather than editing functions.

Getting *onto* the cluster in the first place is a separate problem — see
**[`docs/SSH-MASTER.md`](docs/SSH-MASTER.md)** for authenticating once and holding the
login open for as many hours as you ask for, instead of doing the MFA dance on every
connection.

## Contents

| Path | Purpose |
|------|---------|
| [`shell/skipjack-slurm-toolkit.bash`](shell/skipjack-slurm-toolkit.bash) | Full toolkit block: aliases, `gpu_join`, `mygpus`, `gpu_whereami`, queue reports, etc. |
| [`scripts/skipjack_gpu.py`](scripts/skipjack_gpu.py) | CLI: `summary`, `queue`, `by-user`, `by-type`, `nodes-cap`, `report`, … |
| [`scripts/skipjack_gpu_allocations.py`](scripts/skipjack_gpu_allocations.py) | Babel-style GPU totals / running / pending / free (`--nodes`, `--json`, …). |
| [`scripts/skipjack_gpu_counter.py`](scripts/skipjack_gpu_counter.py) | Per-model GPU inventory counts. |
| [`docs/TOOLKIT.md`](docs/TOOLKIT.md) | Longer documentation (design notes, tables, troubleshooting). |
| [`local/bin/arch-login`](local/bin/arch-login) | **Local machine:** drives the OIDC device-code login and holds the SSH master open for `--hours N`. |
| [`local/ssh/skipjack.sshconfig`](local/ssh/skipjack.sshconfig) | **Local machine:** `~/.ssh/config` block — login-node aliases `skipjack1`…`skipjack5`, compute-node jumps. |
| [`docs/SSH-MASTER.md`](docs/SSH-MASTER.md) | **Local machine:** how the master works, the `--hours` lock, picking a login node, compute hops, troubleshooting. |
| [`docs/ARCH-SSH.md`](docs/ARCH-SSH.md) | **Local machine:** the same machinery aimed at `login.arch.jhu.edu`, plus the Cursor/VS Code remote setup. |

The three Python scripts expect to live in the **same directory** on `PATH` (they import each other).

## Install

1. **Clone** (or copy) this repository to the machine where you use Slurm (e.g. under your home directory).

   ```bash
   git clone https://github.com/offjangir/DSAI-Cluster-Toolkit.git ~/Skipjack-Cluster-Setup
   cd ~/Skipjack-Cluster-Setup
   ```

   > The GitHub repository is still named `DSAI-Cluster-Toolkit`; only the project
   > contents were renamed to Skipjack. If the repo is renamed later, GitHub will
   > redirect the old URL, but update your remote with
   > `git remote set-url origin <new-url>`.

2. **Put scripts on `PATH`** (pick one):

   ```bash
   cp scripts/*.py ~/bin/
   chmod +x ~/bin/skipjack_gpu.py ~/bin/skipjack_gpu_allocations.py ~/bin/skipjack_gpu_counter.py
   ```

   Ensure `~/bin` is on `PATH` (common pattern):

   ```bash
   [[ ":$PATH:" != *":$HOME/bin:"* ]] && PATH="$HOME/bin:$PATH"
   ```

3. **Load the shell toolkit.** On RHEL-family images whose stock `~/.bashrc` already sources
   `~/.bashrc.d/*`, drop a stub there and leave `~/.bashrc` untouched:

   ```bash
   mkdir -p ~/.bashrc.d
   cat > ~/.bashrc.d/skipjack-slurm-toolkit.sh <<'EOF'
   SKIPJACK_TOOLKIT_DIR="$HOME/Skipjack-Cluster-Setup"
   [[ -f "$SKIPJACK_TOOLKIT_DIR/shell/skipjack-slurm-toolkit.bash" ]] && . "$SKIPJACK_TOOLKIT_DIR/shell/skipjack-slurm-toolkit.bash"
   EOF
   ```

   Sourcing from the checkout means `git pull` updates your shell. If your `~/.bashrc` has no
   `~/.bashrc.d` loop, put that same one-liner directly in `~/.bashrc` instead.

   Alternatively, copy the contents of `shell/skipjack-slurm-toolkit.bash` between the `# SKIPJACK SLURM SHORTCUT TOOLKIT` markers in your `~/.bashrc` and keep the Python scripts on `PATH` as above.

4. **Reload** the shell:

   ```bash
   source ~/.bashrc
   ```

5. **Check**:

   ```bash
   aliases-help
   skipjack_gpu.py summary
   gpu-counter
   ```

## Environment

All three are set at the top of `shell/skipjack-slurm-toolkit.bash` and honour a pre-existing
value, so you can override them in `~/.bashrc` *before* sourcing the toolkit.

- **`SKIPJACK_GPU_PARTITIONS`** — comma-separated GPU partitions used by both the Python tools
  and the bash report functions (`gpu-free`, `gpu-open`, `gpu-nodes-cap`, `gpu-queue`,
  `gpu-users-gres`). Default: `a100,l40s,h100,h200,b200,b300`.

  ```bash
  export SKIPJACK_GPU_PARTITIONS=a100,l40s,h100,h200,b200,b300
  ```

- **`SKIPJACK_CPU_PARTITION`** — CPU-only partition for `salloc-cpu` / `srun-cpu`. Default: `med`.

- **`SKIPJACK_COMPUTE_HOST_RE`** — regex identifying compute nodes, so `gpu_join` can refuse to
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
