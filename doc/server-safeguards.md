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

## 4) Postfix decommissioned

Postfix was previously adjusted to reduce lookup noise, but was later removed from exposure and disabled due to spam-risk concerns.

Applied:

```bash
sudo ufw delete allow Postfix
sudo systemctl disable --now postfix
```

Current state:

- SMTP port 25 no longer allowed in UFW
- `postfix` service disabled/inactive

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

## 6) Reverse-proxy consolidation for admin services

To reduce direct internet exposure, these admin UIs were moved behind Nginx + TLS:

- `nodered.beachlab.org` -> `https://127.0.0.1:1880`
- `openhab.beachlab.org` -> `http://127.0.0.1:8080`
- `pgadmin.beachlab.org` -> `http://127.0.0.1:5050`

Nginx files:

- `/etc/nginx/sites-available/nodered.beachlab.org`
- `/etc/nginx/sites-available/openhab.beachlab.org`
- `/etc/nginx/sites-available/pgadmin.beachlab.org`

Legacy host redirects kept for compatibility:

- `node.beachlab.org` -> `https://nodered.beachlab.org`
- `postgres.beachlab.org` -> `https://pgadmin.beachlab.org`

### Certificates

Before creating/reloading vhosts, verify cert existence:

```bash
sudo certbot certificates
```

Missing certs were requested with:

```bash
sudo certbot certonly --nginx \
  -d nodered.beachlab.org \
  -d openhab.beachlab.org \
  -d pgadmin.beachlab.org
```

API endpoint was also moved to TLS with its own certificate:

```bash
sudo certbot certonly --nginx -d api.beachlab.org
```

`api.beachlab.org` now redirects HTTP->HTTPS and serves only over 443.

Current API exposure state:

- `/air/` disabled (pending DB/API setup)
- `/data/` disabled (legacy target unknown)
- default response is `403` until explicit upstreams are defined

### Firewall hardening applied (UFW)

After reverse-proxy cutover, direct public access rules were removed for admin/data ports:

```bash
sudo ufw delete allow 1880/tcp   # Node-RED direct
sudo ufw delete allow 8080/tcp   # openHAB direct
sudo ufw delete allow 5050       # pgAdmin direct
sudo ufw delete allow 5432       # PostgreSQL direct
sudo ufw delete allow 3000       # legacy direct API port
```

Result:

- admin UIs are reachable through Nginx/TLS hostnames only
- direct PostgreSQL internet exposure removed
- external consumers should use `api.beachlab.org` endpoints, not raw DB ports

## 7) Legacy exposure cleanup (2026-02-08)

Per current usage, additional legacy/public rules were removed:

```bash
sudo ufw delete allow OpenSSH      # removes 22/tcp profile rule
sudo ufw delete allow 1935
sudo ufw delete allow 443/udp
sudo ufw delete allow 622/udp
sudo ufw delete allow 1800
sudo ufw delete allow 1803
sudo ufw delete allow 5678/tcp
sudo ufw delete allow 3478
sudo ufw delete allow 49152:65535/tcp
sudo ufw delete allow 49152:65535/udp
```

Service/vhost removals:

```bash
sudo systemctl disable --now coturn
sudo rm -f /etc/nginx/sites-enabled/<retired-webrtc-vhost>
sudo rm -f /etc/nginx/sites-enabled/n8n
sudo systemctl disable --now n8n
sudo nginx -t && sudo systemctl reload nginx
```

This retires public obsninja/coturn exposure and n8n public entrypoint for now.

## 8) Apache exposure reduced (pgAdmin backend only)

Apache is kept only as a local backend for pgAdmin web mode (`*:5050`), behind Nginx.

Public exposure removals:

```bash
sudo ufw delete allow 'Apache Full'
sudo ufw delete allow 8090
sudo ufw delete allow 10000
```

Apache vhost cleanup:

```bash
sudo a2dissite 000-default-le-ssl
sudo a2dissite tileserver_site.conf
sudo sed -i 's/^\s*Listen\s\+8090/# Listen 8090/' /etc/apache2/ports.conf
sudo rm -f /etc/apache2/sites-available/tileserver_site.conf
sudo systemctl reload apache2
```

Result:

- Apache listens on `5050` only (internal backend use)
- no public Apache SSL (`8090`) exposure
- no public tileserver Apache exposure (`10000`)

## Verification commands

```bash
# services
systemctl is-active rag-library-ingest whisper-web system-load-guard.timer egpu-watchdog.timer
systemctl is-enabled postfix && systemctl is-active postfix  # expected: disabled/inactive

# effective limits
systemctl show rag-library-ingest --property=MemoryMax,MemoryHigh,CPUQuotaPerSecUSec,OnFailure
systemctl show whisper-web --property=MemoryMax,MemoryHigh,CPUQuotaPerSecUSec,OnFailure

# timers
systemctl list-timers --all | grep -E 'system-load-guard|egpu-watchdog'

# run one eGPU check manually
sudo /usr/local/bin/egpu-watchdog.sh --verbose

# check certs
sudo certbot certificates

# verify UFW rules (1880/8080/5050 should be absent)
sudo ufw status numbered

# validate and reload nginx
sudo nginx -t && sudo systemctl reload nginx

# smoke tests
curl -I https://nodered.beachlab.org/
curl -I https://openhab.beachlab.org/
curl -I https://pgadmin.beachlab.org/

# confirm SMTP no longer listening
ss -ltnp | grep ':25 ' || echo 'OK: no smtp listener'
```

## Notes

- SSH access for `pink` must never be removed.
- SFTP access for RAG uses ACLs on folder paths (not forced via SSH group side effects).
