# Server Safeguards (Resource Limits + Alerts)

This page documents safeguards added after an instability incident during RAG deployment.

**Author:** Mr. Watson 🦄
**Date:** 2026-02-08

## Goals

- Prevent heavy services from starving the host
- Alert on service failures
- Alert on sustained high load / low memory
- Reduce noisy postfix error flood

## 1) Resource limits for AI services

### RAG ingest limits

Drop-in:

- `/etc/systemd/system/rag-library-ingest.service.d/safeguards.conf`

```ini
[Unit]
OnFailure=service-failure-notify@%n.service

[Service]
MemoryHigh=2500M
MemoryMax=3G
CPUQuota=200%
TasksMax=256
Nice=10
```

### Whisper service limits

Drop-in:

- `/etc/systemd/system/whisper-web.service.d/safeguards.conf`

```ini
[Unit]
OnFailure=service-failure-notify@%n.service

[Service]
MemoryHigh=3G
MemoryMax=4G
CPUQuota=250%
TasksMax=256
Nice=5
```

## 2) Service failure notifications (iGotify)

Files:

- `/usr/local/bin/service-failure-notify.sh`
- `/etc/systemd/system/service-failure-notify@.service`

Template service runs on failure and sends iGotify notification.

## 3) High-load watchdog notification

Files:

- `/usr/local/bin/system-load-guard.sh`
- `/etc/systemd/system/system-load-guard.service`
- `/etc/systemd/system/system-load-guard.timer`

Timer cadence:

- every 5 minutes

Alert conditions (with cooldown):

- load average above threshold (`cores * 2.0`)
- available RAM below threshold (default `700MB`)

Cooldown default: 30 minutes to avoid notification spam.

## 4) Postfix lookup error flood fix

Observed repeated errors from missing/invalid virtual map DB lookups.

Applied:

```bash
sudo postmap /etc/postfix/virtual
sudo systemctl reload postfix
```

This removed `virtual.db` lookup noise from logs.

## 5) eGPU watchdog (Thunderbolt)

Added automated eGPU monitoring + auto-recovery attempts + iGotify alerts.

Files:

- `/usr/local/bin/egpu-watchdog.sh`
- `/etc/systemd/system/egpu-watchdog.service`
- `/etc/systemd/system/egpu-watchdog.timer`
- `/etc/egpu-watchdog.env`

Behavior:

- checks if expected Thunderbolt enclosure is connected (`boltctl`)
- checks if NVIDIA device exists in PCI (`lspci`)
- if missing, attempts auto-recovery:
  - restart `bolt`
  - `echo 1 > /sys/bus/pci/rescan`
  - try `modprobe nvidia*`
- if still missing, sends iGotify alert (with cooldown)
- sends recovery notification when NVIDIA reappears

Current env:

```bash
EGPU_NAME=Razer Core X
COOLDOWN_S=1800
```

## Verification commands

```bash
# services
systemctl is-active rag-library-ingest whisper-web postfix system-load-guard.timer egpu-watchdog.timer

# effective limits
systemctl show rag-library-ingest --property=MemoryMax,MemoryHigh,CPUQuotaPerSecUSec,OnFailure
systemctl show whisper-web --property=MemoryMax,MemoryHigh,CPUQuotaPerSecUSec,OnFailure

# timers
systemctl list-timers --all | grep -E 'system-load-guard|egpu-watchdog'

# run one eGPU check manually
sudo /usr/local/bin/egpu-watchdog.sh --verbose

# recent postfix map errors (should be empty)
journalctl --since '5 minutes ago' -u postfix | grep -Ei 'virtual.db|lookup error|map lookup problem'
```

## Notes

- SSH access for `pink` must never be removed.
- SFTP access for RAG uses ACLs on folder paths (not forced via SSH group side effects).
