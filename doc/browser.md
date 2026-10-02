# Remote browser

Chromium runs on the NUC and opens at:

```text
https://beachlab.org/browser/
```

Sign in with an [Authentik passkey](authentik.md). The old HTTP Basic files
are kept for recovery. The container's HTTP port is on `127.0.0.1`; Nginx
handles HTTPS and WebSocket.

## Files

```text
/srv/remote-browser/docker-compose.yml
/srv/remote-browser/config/
/usr/local/sbin/remote-browser-firewall
/etc/systemd/system/remote-browser.service
/etc/systemd/system/remote-browser-firewall.service
/etc/nginx/snippets/remote-browser.conf
/etc/nginx/.htpasswd-browser
```

The profile and cookies persist in `/srv/remote-browser/config/`. Downloads
go to `/home/pink/downloads`, mounted as `/config/Downloads`. Open
[Downloads](https://beachlab.org/downloads/) to manage them. The browser's
**Archivos** side panel can upload and download files too.

Systemd gives `Downloads` mode 0755 and `/config` mode 0711, so the internal
Nginx can serve downloads without listing the profile.

This is one shared browser session. Avoid simultaneous use by different people;
signed-in sessions and cookies remain on the server.

## Usage

Status and logs:

```bash
sudo systemctl status remote-browser remote-browser-firewall
sudo docker logs --tail 100 remote-browser
```

Update:

```bash
cd /srv/remote-browser
sudo docker compose pull
sudo systemctl restart remote-browser
```

Restart:

```bash
sudo systemctl restart remote-browser
```

## Isolation

The container mounts its config and downloads, with no Docker socket.
Terminals, sudo, external application tools, session sharing, microphone and
gamepads are disabled. Limits are 3 GiB RAM, two CPU and 1024 processes.

`HARDEN_DESKTOP` is not used because this image removes the file manager when
it is enabled, even with `SELKIES_FILE_TRANSFERS` enabled.

The `172.31.250.0/28` network cannot initiate connections to private ranges,
localhost, link-local or other Docker networks. The systemd service starts
after the firewall; Docker does not start the container independently.

The legacy Basic password is stored as bcrypt in
`/etc/nginx/.htpasswd-browser`, separately from Drop.

Check the filter:

```bash
sudo iptables -S REMOTE-BROWSER
sudo docker exec remote-browser curl -I --max-time 5 http://192.168.1.1
sudo docker exec remote-browser curl -I --max-time 10 https://example.com
```

The first curl should fail. The second should return an HTTP response.
