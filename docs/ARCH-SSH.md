# ARCH (JHU) SSH — one login, then everything is free

Tooling to make `login.arch.jhu.edu` usable without doing the OIDC device-code
+ Entra MFA dance on every single connection.

> **Scope:** everything in this document runs on your **local machine** (macOS),
> not on the cluster. It is the counterpart to the rest of this repo, which runs
> on the login node. Paths like `~/.local/bin` and `~/.zshrc` refer to your Mac.

> **Skipjack users:** see **[`SSH-MASTER.md`](SSH-MASTER.md)** instead. Same
> tooling, aimed at the Skipjack login nodes, and it documents the `--hours`
> flag that sets how long one MFA tap lasts. This page stays focused on
> `login.arch.jhu.edu` and the Cursor shim.

**TL;DR — the whole workflow is one command:**

```bash
arch-code            # opens Cursor on ARCH, logging in first only if needed
```

or, if you just want a shell:

```bash
arch-login && ssh arch
```

---

## Why this exists

ARCH's login node accepts exactly one authentication method:

```
$ ssh -v yjangir1@login.arch.jhu.edu
debug1: Authentications that can continue: keyboard-interactive
```

No `publickey`. So the usual "upload an SSH key and forget about it" escape
hatch does not exist here — the device flow is enforced server-side in PAM,
and the Entra approval tap can't (and shouldn't) be scripted away.

What *can* be removed is everything around it:

1. **Authenticate once, reuse forever.** An SSH `ControlMaster` socket is
   established on first login; every later `ssh` / `scp` / `rsync` / Cursor
   connection multiplexes over it and never authenticates at all.
2. **No copy-pasting.** The device URL comes pre-filled with your code and
   opens in your browser automatically; the code also lands on your clipboard.

---

## Daily use

| Want | Run |
|---|---|
| Open Cursor on ARCH | `arch-code` |
| Open a specific remote dir | `arch-code /scratch4/yjangir1/proj` |
| Open a compute node | `arch-code --host arch-c001 /scratch4/yjangir1` |
| Just a shell | `ssh arch` |
| Log in / refresh the master | `arch-login` |
| Log in for 48 hours | `arch-login --hours 48` |
| Am I logged in? | `arch-login --status` |
| Log out | `arch-login --stop` |

`arch-login` is a no-op when a master is already alive, and `arch-code` calls
it for you — so `arch-code` alone is a complete workflow.

**Expiry:** `ControlPersist` is an *idle* timeout, not a hard clock. It resets
whenever anything uses the connection, so with Cursor connected it persists
indefinitely. It realistically only drops after the full window away from ARCH,
or on reboot / VPN change.

The window defaults to 12h and is set per-login with `arch-login --hours N`
(or globally with `ARCH_LOGIN_HOURS`). Because `ControlPersist` is fixed when
the master is created, changing it on a live master means re-locking it:
`arch-login --reset --hours 48`. See
**[`SSH-MASTER.md`](SSH-MASTER.md#holding-the-login-open-for-n-hours)**.

Copying files needs no extra login:

```bash
rsync -avP ./data arch:/scratch4/yjangir1/
scp arch:/home/jhu/yjangir1/results.csv .
```

> ARCH's docs note that pushing large transfers through the *same* multiplexed
> connection as an interactive session can cause lag. For very large syncs,
> either accept it or `ssh -O stop arch` afterwards.

---

## What's installed

### Scripts — `~/.local/bin/`

| File | Role |
|---|---|
| `arch-login` | Drives the device-code login on a pty: detects the URL + code, opens the pre-filled approval page, copies the code, notifies you, and leaves a persistent master behind. |
| `arch-code` | Ensures the master is live (calling `arch-login` if not), resolves your remote `$HOME`, and launches Cursor/VS Code into it. |
| `arch-ssh-shim` | A drop-in `ssh` replacement used **only by Cursor**, so the device flow works when the *editor* initiates a login. See below. |
| `arch-askpass` | `SSH_ASKPASS` helper invoked by the shim; answers the "Press ENTER after approving" prompt via a native dialog. |

### `~/.ssh/config`

```
Host arch
  HostName login.arch.jhu.edu
  User yjangir1
  ControlMaster auto
  ControlPath ~/.ssh/sockets/%r@%h-%p
  ControlPersist 12h
  ServerAliveInterval 60
  ServerAliveCountMax 3
  TCPKeepAlive yes
  ForwardAgent yes

Host arch-*
  User yjangir1
  ProxyCommand sh -c 'exec ssh arch -W "${1#arch-}:$2"' -- %h %p
  ...
```

`arch-*` reaches compute nodes (`ssh arch-c001`) through the same authenticated
master — no second login.

### `~/.zshrc`

Added `export PATH="$HOME/.local/bin:$PATH"` at the end. This *must* stay after
the two absolute `export PATH=...` lines earlier in the file, which overwrite
`PATH` wholesale instead of appending — that's why the scripts were initially
"command not found".

### Cursor — `~/Library/Application Support/Cursor/User/settings.json`

```json
"remote.SSH.path": "/Users/yash/.local/bin/arch-ssh-shim",
"remote.SSH.useLocalServer": true,
"remote.SSH.connectTimeout": 120,
"remote.SSH.lockfilesInTmp": true,
"remote.SSH.remotePlatform": { "arch": "linux", ... }
```

`lockfilesInTmp` matters because ARCH home is a network filesystem (WekaFS)
where the remote server's lockfiles misbehave.

**Backups** were written next to each original:
`~/.ssh/config.bak.*` and `…/Cursor/User/settings.json.bak.*`.

---

## How the Cursor shim works

The editor is a bad place to do an interactive login: it fires several SSH
connections at once and buries prompts in an output channel, where the device
URL appears as **unclickable text**. Normally you avoid this entirely by having
the master up first (`arch-code` does this). The shim is the safety net for
when Cursor initiates a login anyway.

`remote.SSH.path` points Cursor at `arch-ssh-shim`, which branches:

- **Not an ARCH host** → `os.execv()` to `/usr/bin/ssh` as its first action.
  Babel, Delta, DSAI, rtx2 are byte-for-byte unaffected and never see
  `SSH_ASKPASS`. The env var is set only on ARCH child processes — never
  exported globally.
- **An ARCH host** → runs real ssh with its **stderr piped through the shim**.
  This is the only place the code is observable: OpenSSH routes the
  keyboard-interactive *instruction* field (the block with the URL and code)
  to stderr via `logit()`, and passes only the short *prompt* field to
  `SSH_ASKPASS`. The shim tees every byte through unchanged while scraping the
  code, opening the browser, and stashing the code for `arch-askpass` — which
  then shows a dialog and answers with ENTER once you confirm.

`stdin`/`stdout` are inherited untouched, so the editor's protocol is unaffected.

### Safety properties

- `arch-askpass` **refuses** any prompt matching `passw|passphrase|secret|token|pin`
  and tells you to use a terminal. It exists to click through a device
  approval, not to collect secrets via a dialog box.
- Any unexpected exception in the shim falls back to `exec`ing real ssh, so a
  bug degrades to stock behaviour rather than breaking the editor.
- The device-code state file is written `0600` under `$TMPDIR` and ignored
  after 300s.

---

## Verified vs. not

Confirmed working:

- Terminal login, master establishment, `ssh arch`, remote command execution.
- Shim pass-through is byte-identical to stock ssh (`-V` output, exit codes),
  and a real `babel-login` connection through it succeeds.
- Host detection across 18 cases including every alias in your config. One real
  bug was caught here: `login.arch.jhu.edu` is a substring of your existing
  `dsailogin.arch.jhu.edu`, which was wrongly matching — fixed with a lookbehind.
- The exact ARCH banner replayed through the stderr watcher yields the right
  code and pre-filled URL; stdout and exit codes survive intact.

Not yet exercised live:

- The `arch-askpass` path — it only triggers if Cursor starts a login while no
  master exists. In normal use the master is already up, so ssh never prompts.
  If it does fire and misbehaves, `arch-code` remains the path that doesn't
  depend on it.

---

## Troubleshooting

**`zsh: command not found: arch-login`**
`source ~/.zshrc`, or check that the `PATH` line is still last in the file.

**Cursor prompts for a device code / shows an unclickable link**
The master expired. Run `arch-login` in any terminal (Cursor's integrated
terminal works fine — it's a real pty) and reconnect.

**Cursor ignores the shim**
Cursor's `anysphere.remote-ssh` is a fork and may not honour `remote.SSH.path`.
Doesn't matter in practice: keep using `arch-code`, which authenticates before
the editor ever launches.

**Browser didn't open during login**
The raw ssh output passes through untouched, so finish the login manually. Then
the code-detection regexes in `arch-login` / `arch-ssh-shim` need adjusting to
match whatever ARCH actually printed.

**Everything is broken, undo it**
Restore `~/.ssh/config.bak.*` and `settings.json.bak.*`, delete
`~/.local/bin/arch-*`, and remove the `PATH` line from `~/.zshrc`.

---

## Reference

- Account: `yjangir1` · Home: `/home/jhu/yjangir1` · Login node: `login01`
- [Logging in to Rockfish — ARCH docs](https://docs.arch.jhu.edu/en/latest/1_Clusters/Rockfish/2_Navigating/Connecting_to_Rockfish.html)
- [ARCH Access](https://www.arch.jhu.edu/access/)
