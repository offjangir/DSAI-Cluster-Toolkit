# The SSH master — one MFA tap, then N hours of silence

Skipjack (and ARCH generally) accepts exactly one authentication method:

```
$ ssh -v yjangir1@skipjack.jhu.edu
debug1: Authentications that can continue: keyboard-interactive
```

No `publickey`. The OIDC device code plus the Entra MFA tap is enforced
server-side in PAM, and it shouldn't be scripted away. What *can* be removed is
doing it more than once a day.

`local/bin/arch-login` drives that login on a pty — scraping the code as ssh
prints it, copying it to your clipboard, opening the pre-filled approval URL,
notifying you — and leaves a persistent `ControlMaster` socket behind. Every
later `ssh` / `scp` / `rsync` / editor connection multiplexes over that socket
and never authenticates at all.

> **Scope:** everything here runs on your **local machine**, not the cluster.
> `~/.local/bin`, `~/.ssh/config` and `~/.zshrc` refer to your laptop.

---

## Install

```bash
install -m 755 local/bin/arch-login ~/.local/bin/arch-login
cat local/ssh/skipjack.sshconfig >> ~/.ssh/config
sed -i '' 's/yjangir1/<your-jhu-id>/g' ~/.ssh/config     # macOS sed
```

Make sure `~/.local/bin` is on `PATH` — and that the line adding it comes
*after* any absolute `export PATH=...` earlier in your `~/.zshrc`, which
overwrites `PATH` wholesale rather than appending.

---

## Holding the login open for N hours

```bash
arch-login --hours 48 skipjack       # one tap buys 48 hours
```

`--hours` sets `ControlPersist` on the master it creates. Accepts fractions
(`--hours 0.5`), caps at 720 (30 days), and defaults to 12 — override the
default globally by exporting `ARCH_LOGIN_HOURS`.

```bash
export ARCH_LOGIN_HOURS=24           # in ~/.zshrc
```

**It's an idle timeout, not a wall clock.** The window is a *floor*: the
connection survives at least that long with nothing touching it, and the timer
resets every time you use it. With an editor attached it persists indefinitely.
It realistically only drops after N hours away from the cluster, or on a reboot
or VPN change.

`--status` reports what's left:

```
$ arch-login --status skipjack
Master running (pid=47160)
[arch-login] locked for 48h; idle until 09:12 on Wed 30 Sep (41.3h left)
```

### Re-locking a master that's already up

`ControlPersist` is fixed when the master is created — OpenSSH gives no way to
retune a running one. So `--hours` on a live master is refused rather than
silently ignored:

```
$ arch-login --hours 48 skipjack
[arch-login] master already alive for 'skipjack' - nothing to do
[arch-login] note: --hours 48 not applied to the live master. Re-lock it with:
             arch-login --reset --hours 48 skipjack
```

Re-locking costs one MFA tap, because it tears the old master down and logs in
fresh.

### Where the window is recorded

Next to the socket, as `<controlpath>.meta` — a small JSON file holding the
hours and the establishment time. It is purely informational: delete it and
everything still works, you just lose the countdown in `--status`. `--stop` and
`--reset` clean it up.

---

## Command reference

| Want | Run |
|---|---|
| Log in, default window | `arch-login skipjack` |
| Log in for 48 hours | `arch-login --hours 48 skipjack` |
| Am I logged in? How long left? | `arch-login --status skipjack` |
| Re-lock to a new window | `arch-login --reset --hours 8 skipjack` |
| Un-wedge a hung master | `arch-login --reset skipjack` |
| Log out | `arch-login --stop skipjack` |
| Re-auth over a healthy master | `arch-login --force skipjack` |
| Don't open a browser | `arch-login --no-browser skipjack` |
| Press ENTER for me after 20s | `arch-login --auto-enter 20 skipjack` |

`arch-login` is a no-op when a master is already alive, so it's safe to put in
a shell startup or run on a loop.

> **The host argument defaults to `arch`** — the *other* cluster, at
> `login.arch.jhu.edu`. Always pass `skipjack` explicitly.

---

## Picking a login node

`skipjack.jhu.edu` is a plain A record for `162.129.223.38`, which *is*
login05. No round-robin, no load balancer — that name puts you on node 5 every
time. The config snippet ships numbered aliases so you can choose:

| Alias | Node | Public name | IP |
|---|---|---|---|
| `skipjack1` | login01 | `login01.arch.jhu.edu` | 162.129.223.39 |
| `skipjack2` | login02 | `login02.arch.jhu.edu` | 162.129.223.40 |
| `skipjack3` | login03 | `login03.arch.jhu.edu` | 162.129.223.41 |
| `skipjack4` | login04 | `login04.arch.jhu.edu` | 162.129.223.42 |
| `skipjack5` | login05 | `login05.arch.jhu.edu` | 162.129.223.38 |

To move where a bare `ssh skipjack` goes, edit the one `HostName` line under
`Host skipjack`, then re-run `arch-login skipjack`. **Sockets are per-hostname**
— the `ControlPath` is keyed on the resolved name, so authenticating to
`skipjack` does nothing for `skipjack3`. Each node you use needs its own tap.

---

## Compute nodes

Reached by tunnelling through the login master; no second authentication.

| Partition | Nodes | Reach it with |
|---|---|---|
| `interactive` | `csr[048-052]` | `ssh csr050` |
| `med` | `csr[053-127]` | `ssh csr100` |
| `a100_mig` | `ga[129-130]` | `ssh ga129` |
| `a100` | `ga[131-143]` | `ssh ga131` |
| `b200` | `gb[201-216]` | `ssh gb201` |
| `b300` | `gb301` | `ssh gb301` |
| `l40s` | `gl[105-112]` | `ssh gl105` |
| `h100` | `gh[101-132]` | `ssh sj-gh101` |
| `h200` | `gh[201-206]` | `ssh sj-gh201` |
| `rtx6000` | `gr[101-103]` | `ssh sj-gr101` |

`gh*` and `gr*` are deliberately left out of the bare-wildcard block: NCSA
Delta's GH200 nodes are `gh151`/`gh152`, and `gretel.ri.cmu.edu` matches `gr*`.
First match wins in `ssh_config`, so a bare `ssh gh101` would quietly try the
wrong cluster. The `sj-` prefix is unambiguous and works for any node —
`ssh sj-csr050` is equally valid.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Hangs on connect, no prompt | `arch-login --reset skipjack` |
| `Control socket connect(...): No such file or directory` | Window elapsed — `arch-login skipjack` |
| `Permission denied (keyboard-interactive)` | No master; you declined or timed out. Log in again |
| Approved in the browser, terminal still waiting | Press ENTER. Or use `--auto-enter 20` |
| `--hours` seemed to do nothing | A master was already up — see *Re-locking* above |
| Landed on the wrong login node | Something used `skipjack.jhu.edu` instead of the alias |
| `sinfo: command not found` over `ssh host cmd` | Non-interactive shells skip `/etc/profile.d/00-slurm.sh`. Use `ssh skipjack bash -lc 'sinfo -s'` |

Check a config change without connecting:

```bash
ssh -G skipjack | grep -E '^(hostname|user|controlpath|controlpersist) '
```

---

## See also

- **[`ARCH-SSH.md`](ARCH-SSH.md)** — the same machinery pointed at
  `login.arch.jhu.edu`, plus the Cursor/VS Code remote setup (`arch-code`,
  `arch-ssh-shim`, `arch-askpass`) and how the editor shim works.
