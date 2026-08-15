# ==============================
# SKIPJACK SLURM SHORTCUT TOOLKIT
# ==============================

# ---- Site configuration ----
# Legacy DSAI_* names are still honoured so existing ~/.bashrc exports keep working.
: "${SKIPJACK_GPU_PARTITIONS:=${DSAI_GPU_PARTITIONS:-a100,l40s,h100,h200,b200,b300}}"
: "${SKIPJACK_CPU_PARTITION:=${DSAI_CPU_PARTITION:-med}}"
: "${SKIPJACK_COMPUTE_HOST_RE:=${DSAI_COMPUTE_HOST_RE:-^(csr|ga|gb|gh|gl)[0-9]+$}}"
# Python helpers read the comma form; bash loops read the space form.
export SKIPJACK_GPU_PARTITIONS
SKIPJACK_GPU_PARTS_SP="${SKIPJACK_GPU_PARTITIONS//,/ }"

# ---- Cluster overview ----
alias sinfo-gpu='sinfo -o "%P %.6D %.10t %.10l %.6c %.10m"'
alias nodes='sinfo -N -o "%N %P %t %G"'
# Per-node CPUs, RAM (MB per Slurm), GRES/GPUs — see also: node_show <nodename>
alias nodes-hw='printf "%-10s %-8s %-10s %5s %12s %s\n" NODE PARTITION STATE CPUS MEM_MB GRES && sinfo -N -h -o "%10N %8P %10t %5c %12m %25G"'
alias myjobs='squeue -u $USER'
# Pending reason (Resources, Priority, QOS*, …). Use in another terminal while srun/salloc waits.
alias myjobs-reason='squeue -u $USER -o "%.18i %.9P %.2t %.10M %R"'

# Full cluster snapshot
alias cluster='echo "=== PARTITIONS ===" && sinfo -s && echo "" && echo "=== GPU STATUS ===" && sinfo -o "%P %.6D %.10t %.10l %.6c %.10m"'

# ---- Interactive sessions ----
# NOTE: every partition here sets DefMemPerCPU == MaxMemPerCPU, so RAM is welded to core
# count and --mem=64G silently inflates your core request. These aliases use explicit
# --mem-per-cpu at (or under) each partition's cap instead: ~64G, predictable core count.
#   med 4000M/cpu | a100,l40s 6000M/cpu | h100,h200,b200,b300 12000M/cpu
alias salloc-cpu='salloc --partition=${SKIPJACK_CPU_PARTITION} --cpus-per-task=8 --mem-per-cpu=4000M --time=02:00:00'
alias srun-cpu='env -u SLURM_JOB_ID srun --partition=${SKIPJACK_CPU_PARTITION} --cpus-per-task=8 --mem-per-cpu=4000M --time=02:00:00 --pty bash -l'
# GPU: srun --pty = real job step (CUDA_VISIBLE_DEVICES). First line "queued and waiting" is normal until the scheduler finds a node; see myjobs-reason in another terminal.
# Optional: fail fast if nothing starts in 10m — srun-l40s-try (below).
alias srun-a100='env -u SLURM_JOB_ID srun --partition=a100 --gres=gpu:1 --cpus-per-task=11 --mem-per-cpu=6000M --time=02:00:00 --pty bash -l'
alias srun-l40s='env -u SLURM_JOB_ID srun --partition=l40s --gres=gpu:1 --cpus-per-task=11 --mem-per-cpu=6000M --time=02:00:00 --pty bash -l'
alias srun-l40s-try='env -u SLURM_JOB_ID srun --partition=l40s --gres=gpu:1 --cpus-per-task=11 --mem-per-cpu=6000M --time=02:00:00 --immediate=600 --pty bash -l'
alias srun-h100='env -u SLURM_JOB_ID srun --partition=h100 --gres=gpu:1 --cpus-per-task=8 --mem-per-cpu=8000M --time=02:00:00 --pty bash -l'
alias srun-h200='env -u SLURM_JOB_ID srun --partition=h200 --gres=gpu:1 --cpus-per-task=8 --mem-per-cpu=8000M --time=02:00:00 --pty bash -l'
# Reservation only (no step shell); then: srun --jobid=$SLURM_JOB_ID --overlap --pty bash -l
alias salloc-gpu-a100='salloc --partition=a100 --gres=gpu:1 --cpus-per-task=11 --mem-per-cpu=6000M --time=02:00:00'
alias salloc-gpu-l40s='salloc --partition=l40s --gres=gpu:1 --cpus-per-task=11 --mem-per-cpu=6000M --time=02:00:00'

# ---- Job submission ----
alias sbatch-run='sbatch job.slurm'

# Full Slurm record for one node (CPU count, RealMemory, Gres, features, etc.)
node_show() {
	if [ -z "${1:-}" ]; then
		echo "usage: node_show <nodename>   example: node_show csr048" >&2
		return 1
	fi
	scontrol show node "$1"
}

# Which GPU indices Slurm gave this job (CUDA maps 0..N to your devices inside a real Slurm step).
mygpus() {
	local nl v val set=0
	if [ -z "${SLURM_JOB_ID:-}" ]; then
		echo "No SLURM_JOB_ID — not in an allocation. Start srun-l40s / srun-a100 / sbatch, or: srun --jobid=ID ..." >&2
		return 1
	fi
	nl="${SLURM_JOB_NODELIST:-${SLURM_NODELIST:-}}"
	if [ -z "$nl" ]; then
		nl=$(scontrol show job "$SLURM_JOB_ID" 2>/dev/null | tr ' ' '\n' | sed -n 's/^NodeList=//p' | head -1)
	fi
	echo "Slurm: SLURM_JOB_ID=${SLURM_JOB_ID}  NODELIST=${nl:-?}"
	for v in CUDA_VISIBLE_DEVICES SLURM_STEP_GPUS SLURM_JOB_GPUS SLURM_GPUS_ON_NODE HIP_VISIBLE_DEVICES ROCR_VISIBLE_DEVICES; do
		val=$(printenv "$v" 2>/dev/null) || val=
		if [ -n "$val" ]; then
			printf '  %-26s %s\n' "$v" "$val"
			set=1
		fi
	done
	if [ "$set" -eq 0 ]; then
		cat >&2 <<'EOS'
No GPU binding env vars in THIS shell. Common causes:
  • You used plain "ssh l04" — that is a normal login session; Slurm does not inject CUDA_VISIBLE_DEVICES there.
  • Raw "nvidia-smi" then shows every GPU and every job on the node — not "which one is mine" for your allocation.

To match physical GPUs: run gpu_whereami in this shell and again inside a Slurm step (below); compare the pci.bus_id column (same bus id = same card).

Use a step inside your allocation (same job id), then run mygpus again:
  srun --jobid=$SLURM_JOB_ID --nodes=1 --ntasks=1 --overlap --cpu-bind=none bash -lc 'echo CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES; nvidia-smi -L'

Interactive shell with binding (from dsailogin, not plain ssh to the node):
  srun --jobid=$SLURM_JOB_ID --nodes=1 --ntasks=1 --overlap --cpu-bind=none --pty /bin/bash

Another Mac tab: SSH to dsailogin (not to the compute node), then:  gpu_join JOBID
  (JOBID from myjobs — same allocation; gpu_join will refuse if you run it from plain ssh on csr*/ga*/gb*/gh*/gl*.)
EOS
	fi
	if [ "$set" -eq 1 ]; then
		printf '%s\n' "Tip: dsailogin → gpu_join ${SLURM_JOB_ID}  |  Match cards: gpu_whereami here vs on plain ssh (compare pci.bus_id)."
	fi
	echo "Alloc: scontrol show job ${SLURM_JOB_ID} | grep -iE 'TRES=|Gres='"
}

# Second (third, …) shell on the *same* interactive GPU job: ssh to dsailogin again, run: gpu_join 1281490
gpu_join() {
	local jid=${1:-${SLURM_JOB_ID:-}} wd wdargs=() hn
	if [[ -z "$jid" ]]; then
		echo "usage: gpu_join [JOBID]" >&2
		echo "  On dsailogin: myjobs  →  gpu_join 1281490   (your running interact/srun job id)" >&2
		echo "  If this shell already has SLURM_JOB_ID:  gpu_join   (same as gpu_join \$SLURM_JOB_ID)" >&2
		return 1
	fi
	hn=$(hostname -s 2>/dev/null || hostname)
	if [[ -z "${GPU_JOIN_ANYWHERE:-}" ]] && [[ "$hn" =~ $SKIPJACK_COMPUTE_HOST_RE ]]; then
		echo "gpu_join: run from the login node, not from plain ssh to compute node '$hn'." >&2
		echo "  Exit ssh, connect to the login node, then:  gpu_join $jid" >&2
		echo "  (Override: GPU_JOIN_ANYWHERE=1 gpu_join $jid  — may still fail with execve on some sites.)" >&2
		return 2
	fi
	wdargs=()
	# Optional: match job WorkDir (often /weka/...). Some sites break overlap with --chdir before exec → "execve" errors; default off.
	if [[ -n "${GPU_JOIN_CHDIR:-}" ]]; then
		wd=$(scontrol show job "$jid" 2>/dev/null | tr ' ' '\n' | sed -n 's/^WorkDir=//p' | head -1)
		if [[ -n "$wd" && -d "$wd" ]]; then
			wdargs=(--chdir "$wd")
		fi
	fi
	# --cpu-bind=none: overlap avoids "Unable to satisfy cpu bind request". Plain /bin/bash (no -i): fewer execve failures on slurmd.
	srun --jobid="$jid" --nodes=1 --ntasks=1 --cpus-per-task=1 --overlap --cpu-bind=none --export=ALL \
		"${wdargs[@]}" --pty /bin/bash
}

# Map "my" GPU(s) to PCI bus id (stable across ssh vs srun); in srun, only your GPU(s) are usually visible as index 0,1,...
gpu_whereami() {
	local v val
	echo "== Slurm (logical indices for CUDA; not the same as node-wide GPU 0–7) =="
	for v in CUDA_VISIBLE_DEVICES SLURM_STEP_GPUS SLURM_JOB_GPUS SLURM_GPUS_ON_NODE; do
		val=$(printenv "$v" 2>/dev/null) || val=
		[[ -n "$val" ]] && printf '%-28s %s\n' "$v" "$val"
	done
	if ! command -v nvidia-smi &>/dev/null; then
		echo "nvidia-smi not found" >&2
		return 1
	fi
	echo ""
	echo "== Visible to this shell: nvidia-smi -L =="
	nvidia-smi -L 2>/dev/null
	echo ""
	echo "== PCI bus id (run gpu_whereami in BOTH shells; same pci.bus_id = same physical GPU) =="
	nvidia-smi --query-gpu=index,name,pci.bus_id,memory.used,memory.total --format=csv,noheader 2>/dev/null \
		|| nvidia-smi --query-gpu=index,name,pci.bus_id --format=csv,noheader
	if [[ -z "${CUDA_VISIBLE_DEVICES:-}" ]]; then
		echo "" >&2
		echo "No CUDA_VISIBLE_DEVICES — usually plain SSH (all GPUs visible). Run gpu_whereami again inside srun/gpu_join and diff pci.bus_id against this output." >&2
	fi
}

# nvidia-smi filtered to CUDA_VISIBLE_DEVICES (comma indices). Does NOT secure the node — plain SSH usually has no such var; ask admins for cgroup+ssh adoption (like some other sites).
smi_mine() {
	if [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
		command nvidia-smi -i "${CUDA_VISIBLE_DEVICES}" "$@"
		return
	fi
	cat >&2 <<'EOS'
CUDA_VISIBLE_DEVICES is unset — typical on plain ssh. smi-mine cannot know your GPUs without it.

Options:
  • Use srun-l40s / srun-a100 (or gpu_join from dsailogin) so Slurm sets CUDA_VISIBLE_DEVICES, then run smi-mine.
  • Match physical GPUs across ssh vs step: run gpu_whereami in each shell and compare pci.bus_id (same id = same card).
  • From a step shell: echo $CUDA_VISIBLE_DEVICES  →  on ssh: export CUDA_VISIBLE_DEVICES=…  →  smi-mine
    (That only filters nvidia-smi; it is not full device isolation.)
  • Ask cluster admins for ssh+PAM/cgroup integration tied to your Slurm job if you need Babel-like behavior.
EOS
	command nvidia-smi "$@"
}
alias smi-mine='smi_mine'

# ---- Utilities ----
skipjack_aliases_help() {
	cat <<'EOF'
Skipjack Slurm toolkit — what each alias does
------------------------------------------
sinfo-gpu    Partition table: CPUs, memory, time limits (custom sinfo columns).
nodes        One line per node: name, partition, state, GRES (GPUs).
nodes-hw     Per-node CPUs, memory (MB), GRES/GPUs, state, partition.
node_show    Full detail for one node: node_show csr048 (uses scontrol).

myjobs       Your jobs only (squeue -u $USER). Full queue: run squeue.
myjobs-reason  Your jobs with PD reason column (Resources, Priority, …) while srun waits.
mygpus       Prints CUDA_VISIBLE_DEVICES etc. inside a Slurm **step** (srun/sbatch). Plain ssh to a node has no binding; use srun --jobid=\$SLURM_JOB_ID --overlap …
gpu_whereami  pci.bus_id CSV for GPUs visible in **this** shell. Run it on **plain ssh** and again inside **srun/gpu_join**; matching pci.bus_id = same physical GPU.
smi-mine     If CUDA_VISIBLE_DEVICES is set: nvidia-smi -i … only. Plain ssh usually has no var — use srun/gpu_join or export manually (filter only, not isolation).
gpu_join     From **dsailogin only** (refuses plain ssh csr*/ga*/gb*/gh*/gl*). --pty /bin/bash, --cpu-bind=none; no --chdir unless GPU_JOIN_CHDIR=1. Overrides: GPU_JOIN_ANYWHERE=1.

cluster      Prints partition summary (sinfo -s) then GPU-style partition lines (includes GPU partitions).

salloc-cpu   Interactive CPU allocation: partition=$SKIPJACK_CPU_PARTITION (med), 8 cores, ~31G, 2h.
srun-cpu     Same but drops you straight into a shell (srun --pty).
srun-a100    Interactive GPU shell on a100 (srun --pty); 1 GPU, 11 cores, ~64G, 2h; clears stale SLURM_JOB_ID on login.
srun-l40s    Same on l40s. srun-h100 / srun-h200 for other GPU partitions.
srun-l40s-try  Same as srun-l40s but --immediate=600 (exit if not started in 10 minutes).
salloc-gpu-a100  GPU reservation only (salloc, no step); then gpu_join \$SLURM_JOB_ID or srun --jobid=\$SLURM_JOB_ID --overlap --pty /bin/bash -i
salloc-gpu-l40s  Same for l40s.

sbatch-run   Submit job.slurm with sbatch.

quotas       Run quotas.py (cluster quota script; must be on PATH).
reload       Re-source ~/.bashrc (pick up alias changes).

gpu-free     Per partition, idle nodes: GiB totals + JOBFREE (Slurm unbooked RAM, good --mem hint) + GRES.
gpu-open     Per partition, idle or mixed: same GiB columns; on mixed nodes JOBFREE is headroom for another job's --mem. (RAM+GRES table: nodes-hw.)
gpu-nodes-cap  Per node: T_GPU/U_GPU/F_GPU from scontrol TRES + memory GiB; DRAIN/DOWN skipped; includes alloc/mixed/idle.
gpu-queue    Running + pending GPU jobs as fixed-width table (full TRES; no duplicate NODELIST column on running rows).
gpu-users-gres Sum of visible gres/gpu per user (running / pending); omits squeue N/A lines.
gpu-report   Runs gpu-nodes-cap, gpu-queue, and gpu-users-gres in one go.
gpu-allocations  Python: skipjack_gpu_allocations.py — Babel-style totals/running/pending/free + optional --nodes / --json (see skipjack_gpu_allocations.py -h).
gpu-counter    Python: skipjack_gpu_counter.py — per-model GPU inventory totals (like Babel gpu_counter.py); uses SKIPJACK_GPU_PARTITIONS.
EOF
}
alias aliases-help='skipjack_aliases_help'
alias quotas='quotas.py'
alias reload='source ~/.bashrc'

# One row: MiB from scontrol -> GiB (MiB/1024). JOBFREE = RealMemory-AllocMem (Slurm not yet booked; typical upper bound for --mem).
_gpu_mem_row_scontrol() {
	local node=$1 part=$2 state=$3 line real alloc fmem unbook tot_g jf_g os_g gres
	line=$(scontrol show node "$node" -o 2>/dev/null) || return 1
	real=0
	alloc=0
	fmem=0
	gres='?'
	[[ $line =~ RealMemory=([0-9]+) ]] && real="${BASH_REMATCH[1]}"
	[[ $line =~ AllocMem=([0-9]+) ]] && alloc="${BASH_REMATCH[1]}"
	[[ $line =~ FreeMem=([0-9]+) ]] && fmem="${BASH_REMATCH[1]}"
	[[ $line =~ Gres=([^[:space:]]+) ]] && gres="${BASH_REMATCH[1]}"
	unbook=$((real - alloc))
	((unbook < 0)) && unbook=0
	tot_g=$(awk -v m="$real" 'BEGIN { printf "%.1f", m / 1024 }')
	jf_g=$(awk -v m="$unbook" 'BEGIN { printf "%.1f", m / 1024 }')
	os_g=$(awk -v m="$fmem" 'BEGIN { printf "%.1f", m / 1024 }')
	printf '%-8s %-8s %-6s %9s %9s %9s  %s\n' "$node" "$part" "$state" "$tot_g" "$jf_g" "$os_g" "$gres"
}

_gpu_mem_gib_header() {
	printf '%s\n' 'NODE     PART     STATE   TOT_GiB  JOBFREE_GiB  OSFREE_GiB  GRES'
	printf '%s\n' 'GiB = Slurm MiB / 1024. JOBFREE = RealMemory-AllocMem (headroom for new --mem). OSFREE = OS FreeMem now (can be lower than JOBFREE).'
}

# Whole-node empty only. sinfo -t idle can list drained rows; keep $3==idle only.
gpu_free_nodes() {
	local part any
	_gpu_mem_gib_header
	for part in $SKIPJACK_GPU_PARTS_SP; do
		printf '\n=== %s (state=idle, whole node free) ===\n' "$part"
		any=0
		while read -r node p st; do
			[[ -z "${node:-}" ]] && continue
			if _gpu_mem_row_scontrol "$node" "$p" "$st"; then
				any=1
			fi
		done < <(sinfo -N -p "$part" -t idle -h -o '%N %P %10t' 2>/dev/null | awk '$3 == "idle"' | sort -u)
		if ((any == 0)); then echo '(no fully idle nodes)'; fi
	done
	# Explicit: the loop's last command is a test, so its status would otherwise leak out.
	return 0
}
alias gpu-free='gpu_free_nodes'

# Idle + mixed: where srun/salloc --gres=gpu:1 often lands; JOBFREE_GiB shows how much RAM Slurm still has for a new --mem on that node.
gpu_open_nodes() {
	local part any
	_gpu_mem_gib_header
	printf '%s\n' '(idle = empty node; mix* = partly used — Slurm may still place a GPU; not guaranteed.)'
	for part in $SKIPJACK_GPU_PARTS_SP; do
		printf '\n=== %s (idle or mixed) ===\n' "$part"
		any=0
		while read -r node p st; do
			[[ -z "${node:-}" ]] && continue
			if _gpu_mem_row_scontrol "$node" "$p" "$st"; then
				any=1
			fi
		done < <(sinfo -N -p "$part" -h -o '%N %P %10t' 2>/dev/null | awk '$3 == "idle" || $3 ~ /^mix/' | sort -u)
		if ((any == 0)); then echo '(no idle or mixed nodes)'; fi
	done
	# Explicit: the loop's last command is a test, so its status would otherwise leak out.
	return 0
}
alias gpu-open='gpu_open_nodes'

# gres/gpu= total count from CfgTRES / AllocTRES (comma-separated TRES).
_gpu_tres_gres_gpu() {
	echo "${1:-}" | tr ',' '\n' | awk -F= '$1 == "gres/gpu" && $2 ~ /^[0-9]+$/ { print $2; exit }'
}

# Per-node GPU inventory + memory (GiB). FREE = CfgTRES gres/gpu minus AllocTRES gres/gpu (Slurm accounting).
gpu_nodes_cap() {
	local node part st line cfg alloc cfg_g a_g free real am unbook totg jfg
	printf '%s\n' 'NODE     PART     STATE    T_GPU U_GPU F_GPU  TOT_GiB JOBFREE_GiB'
	printf '%s\n' 'T_GPU/U_GPU/F_GPU from scontrol CfgTRES/AllocTRES gres/gpu=. JOBFREE = (RealMemory-AllocMem)/1024 GiB.'
	while read -r node part st; do
		[[ -z "${node:-}" ]] && continue
		line=$(scontrol show node "$node" -o 2>/dev/null) || continue
		[[ $line =~ State=([^[:space:]]+) ]] && st="${BASH_REMATCH[1]}"
		case $st in
		*drain* | *DRAIN* | *drng* | *DOWN* | *NOT_RESP* | *MAINT* | *FAIL*) continue ;;
		esac
		[[ $line =~ CfgTRES=([^[:space:]]+) ]] && cfg="${BASH_REMATCH[1]}" || cfg=
		[[ $line =~ AllocTRES=([^[:space:]]+) ]] && alloc="${BASH_REMATCH[1]}" || alloc=
		cfg_g=$(_gpu_tres_gres_gpu "$cfg")
		a_g=$(_gpu_tres_gres_gpu "$alloc")
		if [ -z "$cfg_g" ] || [ "$cfg_g" -eq 0 ] 2>/dev/null; then
			[[ $line =~ Gres=gpu:[^:]+:([0-9]+) ]] && cfg_g="${BASH_REMATCH[1]}" || cfg_g=0
			a_g=0
		fi
		[ -z "$a_g" ] && a_g=0
		free=$((cfg_g - a_g))
		((free < 0)) && free=0
		[[ $line =~ RealMemory=([0-9]+) ]] && real="${BASH_REMATCH[1]}" || real=0
		[[ $line =~ AllocMem=([0-9]+) ]] && am="${BASH_REMATCH[1]}" || am=0
		unbook=$((real - am))
		((unbook < 0)) && unbook=0
		totg=$(awk -v m="$real" 'BEGIN { printf "%.1f", m / 1024 }')
		jfg=$(awk -v m="$unbook" 'BEGIN { printf "%.1f", m / 1024 }')
		printf '%-8s %-8s %-8s %5s %5s %5s %9s %9s\n' "$node" "$part" "$st" "$cfg_g" "$a_g" "$free" "$totg" "$jfg"
	done < <(sinfo -N -p "$SKIPJACK_GPU_PARTITIONS" -h -o '%N %P %t' 2>/dev/null | sort -u -k1,1 -k2,2)
}
alias gpu-nodes-cap='gpu_nodes_cap'

# squeue -o with tiny %b was truncating gres (e.g. gres/gpu:a100:10). Pipe-delimited + awk fixed widths.
_gpu_queue_fmt_run() {
	squeue -t R -p "$SKIPJACK_GPU_PARTITIONS" -h -o '%u|%i|%t|%P|%b|%M|%l|%D|%N' 2>/dev/null | awk -F'|' '
	function rule() {
		for (r = 0; r < 136; r++) printf "-"
		printf "\n"
	}
	BEGIN {
		printf "%-12s %-18s %2s %-10s %-46s %14s %12s %5s %s\n", "USER", "JOBID", "ST", "PARTITION", "TRES_PER_NODE", "ELAPSED", "TIME_LIMIT", "N", "NODELIST"
		rule()
	}
	{
		if (NF < 9) next
		u = $1; id = $2; st = $3; p = $4; tr = $5; el = $6; tl = $7; nn = $8; nd = $9
		if (length(tr) > 46) tr = substr(tr, 1, 43) "..."
		if (length(nd) > 28) nd = substr(nd, 1, 25) "..."
		printf "%-12s %-18s %2s %-10s %-46s %14s %12s %5s %s\n", substr(u, 1, 12), substr(id, 1, 18), st, substr(p, 1, 10), tr, el, tl, nn, nd
	}'
}
_gpu_queue_fmt_pd() {
	squeue -t PD -p "$SKIPJACK_GPU_PARTITIONS" -h -o '%u|%i|%t|%P|%b|%M|%l|%D|%R' 2>/dev/null | awk -F'|' '
	function rule() {
		for (r = 0; r < 136; r++) printf "-"
		printf "\n"
	}
	BEGIN {
		printf "%-12s %-18s %2s %-10s %-46s %10s %12s %5s %s\n", "USER", "JOBID", "ST", "PARTITION", "TRES_PER_NODE", "TIME", "TIME_LIMIT", "N", "REASON"
		rule()
	}
	{
		if (NF < 9) next
		u = $1; id = $2; st = $3; p = $4; tr = $5; wt = $6; tl = $7; nn = $8; rs = $9
		if (length(tr) > 46) tr = substr(tr, 1, 43) "..."
		if (length(rs) > 42) rs = substr(rs, 1, 39) "..."
		printf "%-12s %-18s %2s %-10s %-46s %10s %12s %5s %s\n", substr(u, 1, 12), substr(id, 1, 18), st, substr(p, 1, 10), tr, wt, tl, nn, rs
	}'
}

gpu_queue_report() {
	printf '\n%s\n' "=== RUNNING (GPU partitions $SKIPJACK_GPU_PARTITIONS) ==="
	_gpu_queue_fmt_run | head -350
	printf '\n%s\n' '=== PENDING (same partitions) ==='
	_gpu_queue_fmt_pd | head -500
	printf '%s\n' '(TRES wider than 46 chars is shortened. Pending TIME is squeue %M for that job.)'
}
alias gpu-queue='gpu_queue_report'

# Parse gres/gpu count from squeue %b (e.g. gres/gpu:h100:4 or gres/gpu:4).
_gpu_parse_job_gres() {
	local b=$1 n=-1
	if [[ "$b" =~ gres/gpu:[^:]+:([0-9]+) ]]; then
		n="${BASH_REMATCH[1]}"
	elif [[ "$b" =~ gres/gpu:([0-9]+) ]]; then
		n="${BASH_REMATCH[1]}"
	fi
	echo "$n"
}

gpu_users_gres_report() {
	local u b n
	declare -A rsum psum rna pna
	while read -r u b; do
		[[ -z "${u:-}" ]] && continue
		n=$(_gpu_parse_job_gres "${b:-N/A}")
		if ((n >= 0)); then
			rsum[$u]=$((${rsum[$u]:-0} + n))
		else
			rna[$u]=$((${rna[$u]:-0} + 1))
		fi
	done < <(squeue -t R -p "$SKIPJACK_GPU_PARTITIONS" -h -o '%u %b' 2>/dev/null)
	while read -r u b; do
		[[ -z "${u:-}" ]] && continue
		n=$(_gpu_parse_job_gres "${b:-N/A}")
		if ((n >= 0)); then
			psum[$u]=$((${psum[$u]:-0} + n))
		else
			pna[$u]=$((${pna[$u]:-0} + 1))
		fi
	done < <(squeue -t PD -p "$SKIPJACK_GPU_PARTITIONS" -h -o '%u %b' 2>/dev/null)
	printf '\n%s\n' '=== SUM gres/gpu (from squeue %b; N/A not counted) ==='
	printf '%-12s %10s %10s %10s %10s\n' USER RUN_GRES PD_GRES RUN_NA PD_NA
	for u in $(printf '%s\n' "${!rsum[@]}" "${!psum[@]}" "${!rna[@]}" "${!pna[@]}" | sort -u); do
		printf '%-12s %10s %10s %10s %10s\n' "$u" "${rsum[$u]:-0}" "${psum[$u]:-0}" "${rna[$u]:-0}" "${pna[$u]:-0}"
	done | sort
	printf '%s\n' '(RUN_NA/PD_NA = jobs where %b had no parseable gres/gpu:N; use gpu-queue for those.)'
}
alias gpu-users-gres='gpu_users_gres_report'

gpu_report_all() {
	gpu_nodes_cap
	gpu_queue_report
	gpu_users_gres_report
}
alias gpu-report='gpu_report_all'
alias gpu-allocations='skipjack_gpu_allocations.py'
alias gpu-counter='skipjack_gpu_counter.py'

# ==============================
# END TOOLKIT
# ==============================
