# Push Notifications with iGotify

**Author:** Fran

- [Overview](#overview)
- [Deployment Steps](#deployment-steps)
- [Notifier Script](#notifier-script)

## Overview

Gotify is the local push server and iGotify is the iOS push bridge. On this host both run as Docker containers behind Nginx, bound only to loopback.

## Deployment Steps

1. **Prepare Docker Compose file**

Create or edit `/srv/gotify/docker-compose.yml` with the following content:

```yaml
services:
  gotify:
    image: gotify/server:latest
    container_name: gotify
    restart: unless-stopped
    volumes:
      - ./gotify-data:/app/data
    # Expose ONLY on loopback for use behind Nginx:
    ports:
      - "127.0.0.1:8180:80"

  igotify:
    image: ghcr.io/androidseb25/igotify-notification-assist:latest
    container_name: igotify
    restart: unless-stopped
    env_file:
      - ./igotify.env
    depends_on:
      - gotify
    ports:
      - "127.0.0.1:2080:8080"
    volumes:
      - ./igotify-data:/app/data
```

2. **Store iGotify secrets outside compose**

Create `/srv/gotify/igotify.env` and keep real tokens there, not in docs or in the compose file:

```bash
sudo install -m 600 /dev/null /srv/gotify/igotify.env
sudoedit /srv/gotify/igotify.env
```

Contents:

```dotenv
GOTIFY_URLS=http://gotify
SECNTFY_TOKENS=NTFY-DEVICE-xxxxx
GOTIFY_CLIENT_TOKENS=CLe.xxxx
```

3. **Deploy or update containers**

```bash
cd /srv/gotify
sudo docker compose pull
sudo docker compose up -d --remove-orphans
sudo docker compose ps
```

Quick health check:

```bash
curl -fsS http://127.0.0.1:8180/health
curl -I http://127.0.0.1:2080/
```

Expected:

- Gotify health returns JSON with `"green"`
- iGotify may return `404` on `/` and that is fine; the container just needs to be up

4. **Configure Nginx reverse proxy**

Create or edit `/etc/nginx/sites-available/ntfy.beachlab.org` with:

```nginx
server {
  listen 443 ssl;
  listen [::]:443 ssl;
  http2 on;
  server_name ntfy.beachlab.org;

  ssl_certificate     /etc/letsencrypt/live/ntfy.beachlab.org/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/ntfy.beachlab.org/privkey.pem;

  client_max_body_size 20m;

  location / {
    proxy_pass http://127.0.0.1:8180;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;

    proxy_http_version 1.1;   # SSE/WebSocket
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";     
    proxy_buffering off;       # SSE
    proxy_read_timeout 3600s;  # SSE
  }

  location /igotify/ {
    proxy_pass http://127.0.0.1:2080/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
    proxy_read_timeout 3600s;
  }
}
```

5. **Reload and test Nginx**

```bash
sudo nginx -t
sudo systemctl reload nginx
```

6. **iOS app setup**

- Gotify Server URL: `https://ntfy.beachlab.org`
- Notification Assist URL: `https://ntfy.beachlab.org/igotify/`

7. **Get token in iOS app and test**

Obtain a token in the iOS app, then test sending a notification:

```bash
curl -s -X POST "https://ntfy.beachlab.org/message" \
  -H "X-Gotify-Key: TU_APP_TOKEN" \
  -F "title=Test Push" \
  -F "message=Hola desde APNs"
```

8. **Setup notifier script and environment variables**

Create environment variables file `/etc/notify.env` (replace tokens accordingly):

```bash
sudo tee /etc/notify.env >/dev/null <<'EOF'
GOTIFY_URL="https://ntfy.beachlab.org/message"
GOTIFY_APP_TOKEN="Ar_xxxxxx"
DEFAULT_PRIORITY="5"
EOF
```

## Notifier Script

Create the notifier script `/usr/local/bin/notify.sh`:

```bash
sudo tee /usr/local/bin/notify.sh >/dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[ -f /etc/notify.env ] && . /etc/notify.env

TITLE="${1:-Notice}"
MSG="${2:-(no message)}"
PRIO="${3:-${DEFAULT_PRIORITY:-5}}"

curl -fsS -X POST "$GOTIFY_URL" \
  -H "X-Gotify-Key: ${GOTIFY_APP_TOKEN}" \
  -F "title=${TITLE}" \
  -F "message=${MSG}" \
  -F "priority=${PRIO}" >/dev/null
EOF
sudo chmod +x /usr/local/bin/notify.sh
```

You can now send a notification with:

```bash
/usr/local/bin/notify.sh "Test ✅" "This is a test notification from the server"
```

Optionally, create an alias for convenience:

```bash
alias notify='/usr/local/bin/notify.sh'
source ~/.bashrc
```

Then use:

```bash
notify "Test 🚀" "Alias works fine"
```

To send notifications that bypass Do Not Disturb mode, use a higher priority (e.g., 10):

```bash
notify "Backup failed ❌" "Disk full" 10
```

## Operations

### Manual update

The stack does **not** auto-update just because it uses `:latest`. Pull and recreate it manually:

```bash
cd /srv/gotify
sudo docker compose pull
sudo docker compose up -d --remove-orphans
sudo docker compose ps
```

### Weekly automatic update

Install updater script:

```bash
sudo tee /usr/local/bin/update-gotify-stack.sh >/dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

cd /srv/gotify
docker compose pull
docker compose up -d --remove-orphans
EOF
sudo chmod 755 /usr/local/bin/update-gotify-stack.sh
```

Root cron:

```cron
40 4 * * 0 /usr/local/bin/update-gotify-stack.sh >> /var/log/gotify-stack-update.log 2>&1
```

This host uses that exact weekly cron as of `2026-07-02`.
