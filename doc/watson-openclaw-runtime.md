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

## Public verification commands

```bash
openclaw --version
openclaw gateway status
openclaw doctor
```

Do not paste `doctor` output into public issues without redacting paths,
usernames, account handles, tokens and provider configuration.
