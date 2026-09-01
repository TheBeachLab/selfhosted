# OpenClaw runtime maintenance

The self-hosted OpenClaw agent is a separate deployment from other agents. Do
not copy configuration, credentials, state or repair operations between hosts
without verifying the target first.

This public runbook intentionally omits SSH aliases, hostnames, messaging
handles, local ports, exact state paths, backup filenames, account identifiers
and runtime credentials.

## Upgrade and migration procedure

1. Record the installed CLI and gateway versions privately.
2. Back up configuration, the current state database and any legacy state
   sources outside the repository.
3. Stop the user service before changing persistent state.
4. Use OpenClaw's supported migration or storage APIs instead of editing the
   state database directly.
5. Preserve legacy sources until record counts and identifiers have been
   compared with the migrated store.
6. Restart the gateway and verify service health, restart count and configured
   messaging transports.
7. Archive verified legacy sources; retain the recoverable backups according to
   the private backup policy.

## Automated maintenance

The host uses these versioned files:

| File | Installed location | Purpose |
| --- | --- | --- |
| `services/openclaw-maintenance-update` | `~/.local/bin/openclaw-maintenance-update` | transactional update/migration |
| `services/openclaw-maintenance-update.service` | `~/.config/systemd/user/` | user oneshot with the real HOME |
| `services/openclaw-maintenance-update.timer` | `~/.config/systemd/user/` | daily update check |
| `services/openclaw-gateway-restart-policy.conf` | Gateway user-unit drop-in | bounded `Restart=on-failure` policy |

The installer removes only the old cron line that performed an in-place global
npm replacement followed by an unchecked restart. It does not touch unrelated
cron jobs or services. It also replaces the obsolete, ambiguous
`openclaw tui --session main --deliver` command in `~/.bash_aliases` with the
agent-scoped session key required by the migrated multi-agent configuration.

Run and inspect maintenance manually:

```bash
systemctl --user start openclaw-maintenance-update.service
systemctl --user status openclaw-maintenance-update.service
journalctl --user -u openclaw-maintenance-update.service -n 200 --no-pager
```

Never start the Gateway after a failed migration. Keep its protected backup,
inspect the exact error, and verify every SQLite database with
`PRAGMA quick_check` before any retry.

### OpenClaw 2026.8.1 migration notes

OpenClaw's official issue tracker records two relevant 2026.8.1 regressions:
non-TTY `doctor --fix` can skip Doctor-owned migrations
([openclaw/openclaw#134036](https://github.com/openclaw/openclaw/issues/134036)),
and a legacy multi-agent roster can fail migration without explicit ownership
([openclaw/openclaw#126571](https://github.com/openclaw/openclaw/issues/126571)).
Do not work around these by deleting state. Preserve backups, establish explicit
agent ownership and channel bindings, then use OpenClaw's migration routines and
validate the canonical config before importing legacy approval state.

The TUI session must use an agent-scoped key on this multi-agent deployment:

```bash
tmux new-session -d -s watson \
  'openclaw tui --session agent:main:main --deliver'
```

## Public verification commands

```bash
openclaw --version
openclaw gateway status
openclaw doctor
```

Do not paste `doctor` output into public issues without redacting paths,
usernames, account handles, tokens and provider configuration.
