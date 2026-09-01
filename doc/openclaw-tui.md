# OpenClaw TUI Quick Access (tmux)

**Author:** Mr. Watson 🦄
**Date:** 2026-02-07

<!-- vim-markdown-toc GFM -->

- [Goal](#goal)
- [Quick usage](#quick-usage)
- [What was configured](#what-was-configured)
- [Manual fallback (no helper functions)](#manual-fallback-no-helper-functions)
- [Notes](#notes)

<!-- vim-markdown-toc -->

## Goal

Keep OpenClaw TUI running in a persistent tmux session, so reconnection is instant and safe.

## Quick usage

```bash
# start or attach TUI session
watson

# attach only (if already running)
watson_a

# kill the session
watson_k
```

## What was configured

`~/.bash_aliases` now contains:

```bash
# Personal shortcuts
# Added by Mr. Watson 🦄 on 2026-02-07

# Start/attach OpenClaw TUI in tmux session "watson"
watson() {
  tmux new-session -A -s watson 'openclaw tui --session agent:main:main --deliver'
}

# Attach to existing watson session only
watson_a() {
  tmux attach -t watson
}

# Kill watson session
watson_k() {
  tmux kill-session -t watson 2>/dev/null || true
}
```

`~/.bashrc` already sources `~/.bash_aliases`, so open a new shell (or run `source ~/.bash_aliases`) to use the commands.

## Manual fallback (no helper functions)

```bash
# direct
openclaw tui --session agent:main:main --deliver

# with tmux directly
tmux new-session -A -s watson 'openclaw tui --session agent:main:main --deliver'
```

## Updating OpenClaw

Installed via npm global. Do not replace the package while the Gateway or TUI
is running: both processes hold OpenClaw state and may keep loading modules
from the replaced installation.

```bash
systemctl --user start openclaw-maintenance-update.service
journalctl --user -u openclaw-maintenance-update.service -n 200 --no-pager
```

The `openclaw-maintenance-update.timer` checks daily at 04:15 UTC. It does
nothing when the installed version is current. For a real update it stops
`watson` and the Gateway, verifies and backs up SQLite/config/session state,
installs an exact package version, runs
`openclaw doctor --fix --non-interactive --yes`, validates the config and
databases, and requires the new Gateway version and RPC probe before recreating
the TUI. SQLite is never checked concurrently with a running Gateway; the two
integrity passes happen while all writers are stopped, before and after
`doctor`. Any failure leaves the Gateway stopped for inspection.

Check current vs latest:

```bash
openclaw --version
npm show openclaw version
```

## Notes

- If Gateway is down, start it first: `openclaw gateway start`
- Detach from tmux without stopping TUI: `Ctrl+b` then `d`

## Recovery after reboot

The gateway and the TUI session have separate lifecycles. A running gateway does
not prove that the persistent tmux session exists.

Check both before changing the gateway configuration:

```bash
openclaw gateway status
tmux ls
```

If the gateway is healthy but the tmux session is absent, recreate only the TUI
session:

```bash
tmux new-session -d -s watson 'openclaw tui --session agent:main:main --deliver'
tmux ls
```

The agent-scoped session key is required on multi-agent installations. A bare
`--session main` is ambiguous and the TUI exits immediately.
