# MQTT Telemetry (alpha/stats)

This document describes how telemetry was configured on `thebeachlab` to publish server health data to MQTT for website consumption.

**Author:** Mr. Watson 🦄
**Date:** 2026-02-07

## Goal

Publish system telemetry to a simple MQTT topic for dashboards/websites, with:

- frequent live metrics
- periodic speed tests
- anonymous public read for `alpha/stats` only
- authenticated publish

## Final Topic Design

- `alpha/stats` → retained live payload (includes latest speedtest summary)
- `alpha/stats/speedtest` → full speedtest payload (also retained)

For a website, subscribing to `alpha/stats` is enough.

## What is included in `alpha/stats`

- timestamp, host
- CPU usage + temperature
- memory usage
- disk usage (`/`)
- load average
- NVIDIA GPU stats (if available)
- uptime
- `speedtest` summary block (latest known value)

## Scripts created

- `scripts/publish_telemetry.sh`
- `scripts/publish_speedtest.sh`
- `scripts/install_telemetry_cron.sh`
- `scripts/telemetry.env` (local config)
- `scripts/telemetry.env.example`
- `scripts/last_speedtest.json` (cache for latest speedtest result)

## Scheduler (cron)

Installed jobs:

```cron
* * * * * /home/pink/.openclaw/workspace/scripts/publish_telemetry.sh >/tmp/telemetry.log 2>&1
17 */6 * * * /home/pink/.openclaw/workspace/scripts/publish_speedtest.sh >/tmp/telemetry-speedtest.log 2>&1
```

- live telemetry every minute
- speedtest every 6 hours at minute 17

## Broker access model

Mosquitto configured for **public read only** on alpha stats:

- anonymous: read `alpha/stats` and `alpha/stats/#`
- authenticated publisher user: write `alpha/stats` and `alpha/stats/#`

This allows dashboards/websites to subscribe without credentials while keeping write access controlled.

## Notes on speedtest reliability

The speedtest script:

1. tries Ookla CLI (`speedtest`)
2. falls back to `speedtest-cli` if needed
3. caches last result to `scripts/last_speedtest.json`
4. injects a normalized `speedtest` summary into `alpha/stats`

If speedtest times out, summary includes an `error` field instead of values.

## Minimal frontend subscription

Subscribe to:

- `alpha/stats`

Expect a retained JSON payload, so clients receive last known value immediately upon connect.

## Security reminder

Do **not** publish credentials in repo/docs. Keep credentials in local runtime config only.
