# Skipjack Slurm shell toolkit

This file ships with the **[skipjack-slurm-toolkit](../README.md)** repository. The shell definitions live in [`shell/skipjack-slurm-toolkit.bash`](../shell/skipjack-slurm-toolkit.bash); install by sourcing that file from `~/.bashrc` (see the repo **README**).

The following describes the **Slurm shortcuts and helper functions** (historically pasted under **“SKIPJACK SLURM SHORTCUT TOOLKIT”** in `~/.bashrc`). They are tailored for the **Skipjack** login node: GPU partitions `a100`, `l40s`, `h100`, `h200`, `b200`, `b300` and the CPU partition `med`. Partition names are **not** hard-coded — see `SKIPJACK_GPU_PARTITIONS` / `SKIPJACK_CPU_PARTITION` in the [README](../README.md#environment).

## Activating and help

- **Load changes** after editing `~/.bashrc`:

  ```bash
  source ~/.bashrc
  ```

  Shortcut: `reload`

- **List all toolkit commands** with short descriptions:

  ```bash
  aliases-help
  ```

## Design ideas (read once)

1. **Interactive GPUs use `srun --pty`**  
   A normal `srun`/`sbatch` **job step** is where Slurm sets **`CUDA_VISIBLE_DEVICES`** and related cgroup behavior. Plain **`ssh` to a compute node** is a regular Linux login: you often see **all** GPUs and **all** users in `nvidia-smi`, and Slurm may not inject GPU binding for that session.

2. **`env -u SLURM_JOB_ID` on GPU `srun` aliases**  
   If an old interactive job left **`SLURM_JOB_ID`** in your login shell, a new `srun` could try to attach to that expired job. The `srun-*` aliases clear **`SLURM_JOB_ID`** for that command only so a **new** allocation starts.

3. **Memory in GiB**  
   Where helpers print **GiB**, values use **MiB / 1024** (binary gibibytes), matching Slurm’s typical **MiB** fields.

4. **`gpu_join` is for extra shells on the same job**  
   Run it **only from dsailogin** (not from **`ssh` to `l04` / `c009` / …**). From a plain compute SSH session, `srun` overlap often fails with **`Slurmd could not execve job`**; the function **refuses** when the hostname looks like a compute node unless you set **`GPU_JOIN_ANYWHERE=1`** (still may fail).  
   Command: `gpu_join <JOBID>` (id from `myjobs`). It uses **`srun --overlap`**, **`--cpu-bind=none`**, **`--pty /bin/bash`**. **`--chdir` to the job WorkDir is off by default** (can trigger **`Slurmd could not execve`** on some setups); enable with **`GPU_JOIN_CHDIR=1 gpu_join …`** if you need the job’s `/weka/...` cwd. Prefer **not** launching **`gpu_join` from inside the first `srun` shell on the node** if your site hits CPU-bind quirks.

5. **Which physical GPU is mine?**  
   In an `srun` step, **`nvidia-smi` “GPU 0”** is often **only your view**, not “socket GPU 0 on the whole node.” Run **`gpu_whereami`** in **two** shells (e.g. plain **`ssh` to the node** and again inside **`srun` / `gpu_join`** on the same node) and **match `pci.bus_id`** — the same bus id is the same physical card in both views.

6. **Plain SSH and “only my GPUs”**  
   On Skipjack, **plain `ssh` to a GPU node** often shows **all** GPUs; that is controlled by **admins** (cgroup / PAM / `pam_slurm_adopt`, etc.), not by your `~/.bashrc`.  
   User-side partial workaround: if you **`export CUDA_VISIBLE_DEVICES=…`** (e.g. copy from a step where **`mygpus`** printed it), **`smi-mine`** runs **`nvidia-smi -i …`** so the **listing** is filtered. That does **not** add kernel-level device isolation.

---

## Quick starts

| Goal | Command |
|------|---------|
| Interactive **A100**, 1 GPU, 11 cores, ~64G, 2h | `srun-a100` |
| Interactive **L40S** | `srun-l40s` |
| Same, but exit if not started in **10 min** | `srun-l40s-try` |
| Interactive **H100** / **H200** | `srun-h100` / `srun-h200` |
| **CPU** interactive (no GPU), partition `med` | `salloc-cpu` (reservation) / `srun-cpu` (shell) |
| Reserve GPU only (`salloc`), then steps | `salloc-gpu-a100` / `salloc-gpu-l40s`, then `gpu_join <JOBID>` or manual `srun --jobid=… --overlap …` |
| Submit default script | `sbatch-run` (expects `job.slurm`) |

While a GPU `srun` is **queued**, use **`myjobs-reason`** in another terminal to see **PD** reasons.

---

## Cluster overview

| Command | Purpose |
|---------|---------|
| `sinfo-gpu` | Partition-oriented `sinfo` columns (CPUs, memory, time, …). |
| `nodes` | Per node: name, partition, state, GRES string. |
| `nodes-hw` | Same nodes with **CPUs**, **MEM_MB**, GRES. |
| `node_show <nodename>` | Full `scontrol show node` (memory, GRES, features, …). |
| `cluster` | Short snapshot: `sinfo -s` plus GPU-style `sinfo` (includes GPU partitions). |
| `myjobs` | Your jobs: `squeue -u $USER`. Full queue: `squeue`. |
| `myjobs-reason` | Your jobs with **reason** column (useful while pending). |

---

## GPU capacity and memory (scheduling hints)

These commands call **`scontrol show node`** where noted; they are **hints**, not guarantees the scheduler will accept a specific `--mem`.

| Command | Purpose |
|---------|---------|
| `gpu-free` | Per partition in `$SKIPJACK_GPU_PARTITIONS`: nodes with Slurm state **`idle`** only, with **TOT_GiB**, **JOBFREE_GiB** (RealMemory−AllocMem), **OSFREE_GiB**, GRES. |
| `gpu-open` | Same layout for **`idle` or `mixed`** nodes (often where shared-node GPU jobs land). |
| `gpu-nodes-cap` | Per node: **T_GPU / U_GPU / F_GPU** from **CfgTRES / AllocTRES** `gres/gpu=`, plus **TOT_GiB** / **JOBFREE_GiB**. Skips obvious bad states (e.g. DRAIN/DOWN). |

**Column hints**

- **JOBFREE_GiB**: memory not yet booked to jobs in Slurm’s accounting (reasonable upper bound for a new `--mem`, subject to QoS/partition rules).
- **OSFREE_GiB**: OS **FreeMem** (can be lower than JOBFREE; do not ignore for memory-heavy work).
- **F_GPU**: `CfgTRES gres/gpu` minus `AllocTRES gres/gpu` (scheduler view; can disagree with `nvidia-smi` in edge cases).

---

## Queues, users, and one-shot report

| Command | Purpose |
|---------|---------|
| `gpu-queue` | **Running** then **pending** jobs on GPU partitions, **fixed-width** table; **TRES** from `squeue` is pipe-delimited so long `gres/...` strings are not truncated like narrow `%b` formats. |
| `gpu-users-gres` | Sums **`gres/gpu:N`** parsed from `squeue` `%b` per user (**running** / **pending**), plus counts of **N/A** lines not included in sums. |
| `gpu-report` | Runs **`gpu-nodes-cap`**, **`gpu-queue`**, **`gpu-users-gres`** in sequence. |
| `gpu-allocations` | `skipjack_gpu_allocations.py` on **PATH** (`~/bin`): Babel-style totals / running / pending / free (see `skipjack_gpu_allocations.py -h`). |
| `gpu-counter` | `skipjack_gpu_counter.py`: per-model GPU inventory totals. |

---

## Jobs, GPUs, and extra shells

| Command | Purpose |
|---------|---------|
| `mygpus` | Prints **`CUDA_VISIBLE_DEVICES`**, **`SLURM_STEP_GPUS`**, etc., when set; explains plain **SSH** vs **step**; suggests **`gpu_join`** / **`gpu_whereami`**. Requires a context with **`SLURM_JOB_ID`** (typical: inside allocation). |
| `gpu_whereami` | **`nvidia-smi -L`** plus **PCI `pci.bus_id`** CSV for GPUs **visible in this shell**. Run in **both** plain ssh and your **srun/gpu_join** shell and compare **`pci.bus_id`** to map logical indices to physical cards. |
| `smi-mine` | If **`CUDA_VISIBLE_DEVICES`** is set: **`nvidia-smi -i …`** (filtered view). If unset, prints guidance and runs full **`nvidia-smi`**. |
| `gpu_join [JOBID]` | Extra **`srun --overlap --pty`** shell on the **same** job; default **`JOBID`** = **`$SLURM_JOB_ID`**. Intended from **dsailogin**. |

**Correct NVIDIA variable name:** `CUDA_VISIBLE_DEVICES` (with an **`s`**).

---

## Other utilities

| Command | Purpose |
|---------|---------|
| `reload` | `source ~/.bashrc` |
| `quotas` | Runs `quotas.py` (must be on **PATH**). |
| `skipjack_gpu.py` | Optional CLI (`skipjack_gpu.py -h`): `summary`, `queue`, `by-user`, `report`, … (same partition env as above). |

---

## Troubleshooting

| Symptom | Things to try |
|---------|-----------------|
| `srun: Slurm job … has expired` / wrong job | Stale **`SLURM_JOB_ID`** on login; GPU **`srun-*`** aliases already use **`env -u SLURM_JOB_ID`**, or run `unset SLURM_JOB_ID` before manual `srun`. |
| `Slurmd could not execve job` (**gpu_join** from dsailogin) | Default **`gpu_join`** no longer uses **`--chdir`** to the job WorkDir (often **`/weka/...`**); try **`reload`** and **`gpu_join`** again. If you need that cwd: **`GPU_JOIN_CHDIR=1 gpu_join …`**. Still fails: ask admins (node prolog / image). |
| `Unable to satisfy cpu bind request` (overlap) | Run **`gpu_join` from dsailogin**; the function adds **`--cpu-bind=none`**. Avoid nesting from the compute shell if your site still errors. |
| `nvidia-smi` shows 8 GPUs after **SSH** | Expected without a Slurm step. Use **`srun-*`** / **`gpu_join`** for binding. Map your GPUs: **`gpu_whereami`** on ssh vs inside the step and match **`pci.bus_id`**. If you copied **`CUDA_VISIBLE_DEVICES`** from a step, **`smi-mine`** filters **`nvidia-smi`** (view only). For Babel-like isolation, ask **admins**. |
| **`gpu-users-gres`** undercounts | Many running rows show **`N/A`** in `%b`; those appear in **RUN_NA** / **PD_NA**; use **`gpu-queue`** for raw lines. |

---

## Editing and scope

- In this repo, edit **`shell/skipjack-slurm-toolkit.bash`** (or your copy in **`~/.bashrc`** between **`# SKIPJACK SLURM SHORTCUT TOOLKIT`** and **`# END TOOLKIT`**).
- **Partition lists** now come from **`SKIPJACK_GPU_PARTITIONS`** / **`SKIPJACK_CPU_PARTITION`**, set once at the top of the toolkit; override them in `~/.bashrc` rather than editing individual helpers.
- **Defaults** (e.g. **`--mem-per-cpu`**, **`--time=02:00:00`**, **`--gres=gpu:1`**) match common interactive use; adjust aliases to taste. Note every partition sets `DefMemPerCPU == MaxMemPerCPU`, so `--mem` inflates the **core** request instead of capping RAM — prefer `--mem-per-cpu`.

---

## License / support

Informal personal dotfile tooling; not an official cluster product. For policy, quotas, and scheduler limits, use your cluster’s documentation and support channels.
