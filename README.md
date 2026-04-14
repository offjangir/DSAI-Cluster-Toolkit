# DSAI Slurm toolkit

Bash aliases, functions, and Python helpers for **Slurm + GPU** workflows on **JHU-style DSAI** login nodes (partitions such as `a100`, `l40s`, `h100`, `nvl`, `cpu`). The defaults match **dsailogin**-style naming; adjust partition lists if your site differs.

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
   git clone <your-remote-url> ~/dsai-slurm-toolkit
   cd ~/dsai-slurm-toolkit
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

3. **Load the shell toolkit** from `~/.bashrc` (one line; edit the path if you cloned elsewhere):

   ```bash
   [[ -f "$HOME/dsai-slurm-toolkit/shell/dsai-slurm-toolkit.bash" ]] && . "$HOME/dsai-slurm-toolkit/shell/dsai-slurm-toolkit.bash"
   ```

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

- **`DSAI_GPU_PARTITIONS`** — comma-separated Slurm partitions for the Python tools and for mental consistency with the bash helpers (default in scripts: `a100,l40s,h100,nvl`). Example:

  ```bash
  export DSAI_GPU_PARTITIONS=a100,l40s,h100,nvl
  ```

- Bash helpers hard-code partition names in several places; if your cluster renames partitions, update **`shell/dsai-slurm-toolkit.bash`** (search for `a100`, `l40s`, etc.).

## Matching physical GPUs

Run **`gpu_whereami`** in two contexts (e.g. plain `ssh` to the node and inside `srun` / `gpu_join`) and compare the **`pci.bus_id`** column. Same bus id is the same physical card. See **`docs/TOOLKIT.md`**.

## Push to your remote

After clone, set the remote and push (replace URL and branch as needed):

```bash
cd ~/dsai-slurm-toolkit
git remote add origin https://github.com/YOU/dsai-slurm-toolkit.git
git branch -M main
git push -u origin main
```

If you created the repo locally with `git init` only, add `origin` as above, then `git push`.

## License

See [LICENSE](LICENSE).
