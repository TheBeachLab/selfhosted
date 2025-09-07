# Push Notifications with iGotify

Gosh, this shit took me a while. I started with [ntfy](https://ntfy.sh) at the beginning, but push notifications never went through with a self hosted solution. Apparently for that to work you need to recompile the iOS app with your Apple Developer.

Gotify is a self-hosted server for sending and receiving push notifications, offering a simple web interface and apps for real-time message delivery.

iGotify (Docker on Ubuntu) is a containerized notification bridge that works alongside a Gotify server. Deployed via Docker (often using Docker Compose on Ubuntu), iGotify decrypts Gotify messages and forwards them as push notifications through Apple’s APNs to iOS devices—filling the gap since Gotify lacks native support for iOS push alerts.

`sudo nano /srv/gotify/docker-compose.yml`

```yaml
version: "3.8"

services:
  gotify:
    image: gotify/server
    container_name: gotify
    restart: unless-stopped
    volumes:
      - ./gotify-data:/app/data
    # Lo exponemos SOLO en loopback para usarlo detrás de Nginx:
    ports:
      - "127.0.0.1:8180:80"

  igotify:
    image: ghcr.io/androidseb25/igotify-notification-assist:latest
    container_name: igotify
    restart: unless-stopped
    environment:
      - GOTIFY_URLS=http://gotify
      - SECNTFY_TOKENS=NTFY-DEVICE-xxxxx
      - GOTIFY_CLIENT_TOKENS=CLe.xxxx
    depends_on:
      - gotify
    ports:
      - "127.0.0.1:2080:8080"
    volumes:
      - ./igotify-data:/app/data
```


```bash
cd /srv/gotify
docker compose down --remove-orphans (optional)
sudo docker compose pull
sudo docker compose up -d
```

Check

`curl -sS -D- https://ntfy.beachlab.org/igotify/Version`

nginx reverse proxy `sudo nano /etc/nginx/sites-available/ntfy.beachlab.org`

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

and test/reload

```bash
sudo nginx -t
sudo systemctl reload nginx
```

iOS App

Gotify Server URL: https://ntfy.beachlab.org 

Notification Assist URL: https://ntfy.beachlab.org/igotify/

Get a token in the iOS app. And test with the token:

```bash
curl -s -X POST "https://ntfy.beachlab.org/message" \
  -H "X-Gotify-Key: TU_APP_TOKEN" \
  -F "title=Test Push" \
  -F "message=Hola desde APNs"
```

Create a notifier

```bash
# 1) Variables globales (edita TU token)
sudo tee /etc/notify.env >/dev/null <<'EOF'
GOTIFY_URL="https://ntfy.beachlab.org/message"
GOTIFY_APP_TOKEN="Ar_xxxxxx"
DEFAULT_PRIORITY="5"
EOF

# 2) Script notificador
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

Then you can just `/usr/local/bin/notify.sh "Test ✅" "This is a test notification from the server"`

You might create an alias

`alias notify='/usr/local/bin/notify.sh'`

and `source ~/.bashrc`

then would be as easy as `notify "Test 🚀" "Alias works fine"`

If you want the notification to go through even with no disturb mode use:

`notify "Backup failed ❌" "Disk full" 10`


