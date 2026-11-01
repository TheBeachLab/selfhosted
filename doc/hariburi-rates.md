# Hariburi currency rates

Hourly job on the NUC. It publishes
`https://beachlab.org/apps/hariburi/rates.json`.

Checked on the NUC (`pink`) on 2026-11-01. The script and the systemd units
are installed on the host. They are not in this repository. This page records
that check.

This job is separate from the Minecraft world `Hariburi-World`
([Minecraft](minecraft.md)) and from the Mac Hariburi vault
([personal knowledge](personal-knowledge.md)).

The last run at 2026-11-01 00:04 UTC succeeded.

## Timer and service

`hariburi-currency-rates.timer` runs hourly:

- `OnCalendar=hourly`
- `RandomizedDelaySec=10m`
- `Persistent=true`

It starts the oneshot `hariburi-currency-rates.service`.

The service runs:

```text
/usr/bin/python3 /opt/hariburi-currency-rates/hariburi_currency_rates.py
```

Configuration is read from `/etc/default/hariburi-currency-rates` and
`/etc/notify.env`. Settings are environment variables prefixed
`HARBURI_CURRENCY_RATES_`. The unit and directory names use `hariburi`; the
prefix on the host is `HARBURI`.

The unit sets `StateDirectory=hariburi-currency-rates` and `ReadWritePaths`
for `/var/www/beachlab.org/apps/hariburi` and
`/var/lib/hariburi-currency-rates`. It also sets `NoNewPrivileges` and
`PrivateTmp`.

The Open Exchange Rates app id and the Gotify material stay in those env
files. Keep them out of Git and out of this page.

## What a run does

The script fetches Open Exchange Rates `latest.json` and validates it. It
writes `/var/www/beachlab.org/apps/hariburi/rates.json` atomically. It inserts
a snapshot into `public.currency_rates` in the `misc_data` PostgreSQL
database via `psql`. See [PostgreSQL](postgres.md).

Alert state is `/var/lib/hariburi-currency-rates/state.json`. The default
alert age is 12 hours: when `rates.json` is older than that, the script sends
a Gotify alert. See [iGotify](igotify.md).

## Previous method

Node-RED at `nodered.beachlab.org` has an Exchange Rates tab. That tab used
to fetch hourly, save `rates.json` and add rows to the database. Its hourly
inject is disabled and labelled `rates handled by systemd`.

## Checks

```sh
systemctl status hariburi-currency-rates.timer
systemctl status hariburi-currency-rates.service
journalctl -u hariburi-currency-rates.service -n 30 --no-pager
```
