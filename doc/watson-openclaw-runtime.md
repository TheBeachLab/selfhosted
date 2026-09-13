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
The updater version-locks the configured official WhatsApp channel plugin to
the core OpenClaw release. It intentionally does not update `llama-cpp` or any
local-model/GPU component.

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

## Model failover when primary is out of usage

Recovered August notes: historical success claims and provider behavior below
are internal notes, not independently revalidated here. On 2026-09-10, read-only
checks of `pink-sudo` confirmed `~/.openclaw/openclaw.json` still selects
`openai/gpt-5.6-sol` with fallback `openai/gpt-5.3-codex-spark`, and
`systemctl --user is-active openclaw-clear-subscription-block.timer` returned
`active`. These checks establish configuration and timer state, not successful
failover or separate quota availability.

OpenClaw can automatically switch models when the primary hits usage limits,
rate limits, billing/credit failures, auth failures, or overload timeouts —
but **only if a fallback chain is configured**. Without `fallbacks`, the
gateway cools down the failing profile and waits; it does not invent another
provider.

Sources cited by the recovered notes (not reverified during recovery): [Model failover](https://docs.openclaw.ai/concepts/model-failover),
[Models](https://docs.openclaw.ai/concepts/models).

### Two-stage failover

1. **Auth profile rotation** within the current provider (multiple keys/OAuth
   accounts for the same provider).
2. **Model fallback** to the next entry in `agents.defaults.model.fallbacks`
   (or per-agent `agents.entries.*.model.fallbacks`).

Usage-window messages such as `weekly limit reached` / `monthly limit exhausted`
are treated as rate-limit class and advance failover. Prefer a **different
provider** as the first fallback when the primary is quota-exhausted (same-
provider siblings may share the same quota).

### Watson host (thebeachlab) — automatic Sol → Spark fallback

The recovered note records configuration on 2026-08-07 and a Sol rate-limit → Spark
`candidate_succeeded` observation; the original success log was not recovered.

| Setting | Value |
| --- | --- |
| Primary | `openai/gpt-5.6-sol` |
| Fallbacks | `openai/gpt-5.3-codex-spark` |
| Runtime | both use `agentRuntime.id = "codex"` |
| Unblocker | user timer `openclaw-clear-subscription-block.timer` (every 60s) |

Config: `~/.openclaw/openclaw.json` (user `pink`).
Spark is ChatGPT/Codex OAuth-only.
Sources: [Model failover](https://docs.openclaw.ai/concepts/model-failover),
[Model providers](https://docs.openclaw.ai/concepts/model-providers).

#### How automatic fallback is done (two pieces)

**1. OpenClaw config** (native failover on usage/rate limit):

```bash
openclaw models set openai/gpt-5.6-sol
openclaw models fallbacks clear
openclaw models fallbacks add openai/gpt-5.3-codex-spark
```

```json5
// agents.defaults.model
{
  primary: "openai/gpt-5.6-sol",
  fallbacks: ["openai/gpt-5.3-codex-spark"],
}
```

**2. WHAM unblocker** (required for same-OAuth Sol→Spark)

When Sol hits the Codex subscription limit, OpenClaw can write a **profile-wide**
block (`blockedReason: subscription_limit`, `blockedSource: wham`) that lasts
until the usage reset. That poisons *all* models on the same OAuth profile, so
Spark fails with the same limit text even though it has separate quota.

Workaround installed on Watson:

| Path | Role |
| --- | --- |
| `~/.openclaw/bin/openclaw-clear-subscription-block.sh` | clears long WHAM / `subscription_limit` blocks |
| `~/.config/systemd/user/openclaw-clear-subscription-block.service` | oneshot |
| `~/.config/systemd/user/openclaw-clear-subscription-block.timer` | every 60s |

```bash
systemctl --user status openclaw-clear-subscription-block.timer
tail -20 /tmp/openclaw-clear-subscription-block.log
openclaw models status
```

With (1)+(2): each turn tries Sol; if Sol is out of usage, OpenClaw falls through
to Spark in the same turn (when the profile is not already poisoned). The timer
keeps residual WHAM blocks from sticking across messages.

#### Caveats

- Do **not** pin the session with `/model …` if you want fallbacks (user pins are
  strict). Prefer configured primary + `fallbacks`.
- Drop expired session pins: `authProfileOverride: openai:default` breaks the chain.
  Sessions file: `~/.openclaw/agents/main/sessions/sessions.json`.
- Fallback to a **different provider** (e.g. Anthropic) is more robust than
  same-OAuth siblings; add with `openclaw models fallbacks add anthropic/…` if needed.
- Pure OpenClaw alone is enough for cross-provider usage failover; the timer is
  specifically for Codex Sol→Spark on one OAuth account.

### Important caveats (Watson / main session)

| Situation | Fallback? |
| --- | --- |
| Configured default primary (`agents.defaults.model.primary`) | Yes — uses `fallbacks` |
| Per-agent `agents.entries.*.model` with its own `fallbacks` | Yes |
| Per-agent model **without** `fallbacks` | **No** (strict) |
| User `/model …` session pin (`modelOverrideSource: "user"`) | **No** — fails visibly instead of falling through |
| Manual `/model default` (clear pin) | Back to configured default + fallbacks |

If Watson was switched with `/model` and that model has no remaining usage,
OpenClaw will **not** auto-fallback until the session pin is cleared
(`/model default`) or the config default path is used.

Fallback is **turn-local**: each new turn starts from the selected primary
again; OpenClaw probes recovery and can announce return to primary. Visible
notices look like:

```text
↪️ Model Fallback: <fallback> (selected <primary>; <reason>)
↪️ Model Fallback cleared: <primary> (was <fallback>)
```

Check active vs selected model with `/status` in chat or `openclaw models status`.
