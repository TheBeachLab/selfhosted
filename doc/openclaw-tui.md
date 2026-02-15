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
  tmux new-session -A -s watson 'openclaw tui --session main --deliver'
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
openclaw tui --session main --deliver

# with tmux directly
tmux new-session -A -s watson 'openclaw tui --session main --deliver'
```

## Notes

- If Gateway is down, start it first: `openclaw gateway start`
- Detach from tmux without stopping TUI: `Ctrl+b` then `d`
