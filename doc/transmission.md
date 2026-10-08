# Transmission Daemon with NordVPN

The web interface and RPC use Transmission's own login over HTTPS so
Transmission Remote GUI can connect. Nginx passes the client's authentication
to the daemon. The `authentik-check.conf` and `transmission-rpc-secret.conf`
includes were removed from `location ^~ /transmission/` on 2026-09-14.

Start Transmission from the [administration panel](admin-panel.md). Downloads
and the other websites keep their passkey login. The old
`services/admin-panel/protect-transmission.py` changes this access model;
only run it when explicitly asked to change Transmission's access.

Remote GUI settings:

- Host: `beachlab.org`
- Port: `443`, SSL enabled
- RPC path: `/transmission/rpc`
- User: `transmission` and its existing RPC password

Port 9091 stays private. Missing or incorrect credentials return 401.
A valid RPC client handles the 409 session exchange before calling `session-get`.

The previous Nginx file is backed up at
`/opt/authentik/nginx-before-transmission-rpc-20260914T161905`.

## Download destination in clients

Use `/downloads` as the destination in Transmission Web and Remote GUI. Docker
mounts the server's `/home/pink/downloads` there; the host path is not available
inside the Transmission container. The container mount and `session-get`
destination were checked live on 2026-10-08.

Existing torrents can retain their own `downloadDir` even when the session
default is correct. Check each affected torrent before changing the global
setting. A completed torrent can remain in `/downloads/.incomplete` after a
failed move to an invalid destination, so it stays hidden from the
[downloads page](drop.md).

Use the client's **Set location** action with destination `/downloads` and move
existing files, or RPC `torrent-set-location` with explicit torrent IDs/hashes,
`location: "/downloads"`, and `move: true`. Transmission documents these
arguments in its [4.0.5 RPC specification, section 3.6](https://github.com/transmission/transmission/blob/4.0.5/docs/rpc-spec.md#36-moving-a-torrent).
Check the final `downloadDir`, completed-file location, and `/downloads/` listing
afterwards. If a previous move error remains, verify the affected torrent's
local data first. In 4.0.5, verification alone can leave the old error displayed;
starting the torrent clears it in
[`torrentStart`, `libtransmission/torrent.cc`](https://github.com/transmission/transmission/blob/4.0.5/libtransmission/torrent.cc#L718).
After a successful start, restore a previously paused torrent to paused and
read back its completion and error state.

## VPN health and route protection (2026-09-14)

The bundled `transmission-vpn` healthcheck
(`/etc/scripts/healthcheck.sh`) queried `google.com`; NordVPN DNS returned an A
record but NXDOMAIN for AAAA, making `nslookup` fail. Other tested domains and
HTTPS worked. This does not establish a subscription-related cause.

The deployed Compose file `/home/pink/docker/transmission-vpn/docker-compose.yml`
now adds the following to its existing service (preserve credentials and volumes):

```yaml
environment:
  # Merge with the existing environment; list syntax is also supported.
  HEALTH_CHECK_HOST: cloudflare.com
  DROP_DEFAULT_ROUTE: "true"
sysctls:
  net.ipv6.conf.all.disable_ipv6: "1"
volumes:
  # Append to existing mounts.
  - /home/pink/docker/transmission-vpn/healthcheck.sh:/etc/scripts/vpn-healthcheck.sh:ro
healthcheck:
  test: [CMD-SHELL, /etc/scripts/vpn-healthcheck.sh]
  interval: 30s
  timeout: 15s
  retries: 3
  start_period: 30s
```

Install [healthcheck.sh](../services/transmission/healthcheck.sh) at that host
path before recreating the container. Validate Compose with `config --quiet`
and use `up -d --pull never transmission-vpn` to apply without upgrading the image.
A timestamped `.before-vpn-health-*` copy of the original Compose file is retained
beside it on the host.

The image's `/etc/transmission/start.sh`
removes the Docker default route when `DROP_DEFAULT_ROUTE=true`, before starting
Transmission. The wrapper checks that no IPv4 default route exists and Internet
routes via `tun0`, then runs the image's DNS, ping and process checks. IPv6 is
disabled for this IPv4 VPN. This is route-based protection, not an enabled UFW
firewall; the explicit VPN-server and local-network routes remain available.

Removing both VPN Internet routes during the test made `ip route get 1.1.1.1` unreachable,
HTTPS fail and the healthcheck return 1. The routes were restored afterwards.
That covers loss of tunnel routes, not every VPN or tracker failure.
Docker does not restart an unhealthy container just because the healthcheck fails.

- [Transmission Daemon with NordVPN](#transmission-daemon-with-nordvpn)

For Pink

Take note of your puid/pgid numbers with `id`. Then

```bash
mkdir -p ~/downloads ~/transmission-config
mkdir -p ~/docker/transmission-vpn
cd ~/docker/transmission-vpn
printf '%s\n%s\n' 'user' 'pass' > rpc_creds
nano docker-compose.yml
```

```yml
services:
  transmission-vpn:
    image: haugene/transmission-openvpn
    container_name: transmission-vpn
    restart: unless-stopped
    cap_add:
      - NET_ADMIN
    devices:
      - /dev/net/tun
    ports:
      - "127.0.0.1:9091:9091"    
      - "51413:51413"          
      - "51413:51413/udp"
    secrets:
      - rpc_creds
    environment:
      - OPENVPN_PROVIDER=NORDVPN
      - OPENVPN_USERNAME=
      - OPENVPN_PASSWORD=
      - OPENVPN_CONFIG=es238.nordvpn.com   # server NordVPN 
      - LOCAL_NETWORK=192.168.1.0/24           
      - PUID=1000                              # your uid
      - PGID=1000                              # your gid
      - TRANSMISSION_RPC_ENABLED=true
      - TRANSMISSION_RPC_AUTHENTICATION_REQUIRED=true
      - TRANSMISSION_RPC_WHITELIST=127.0.0.1,192.168.*.*
      - TRANSMISSION_DOWNLOAD_DIR=/downloads
      - TRANSMISSION_INCOMPLETE_DIR_ENABLED=true
      - TRANSMISSION_INCOMPLETE_DIR=/downloads/.incomplete
    volumes:
      - /home/pink/downloads:/downloads
      - /home/pink/transmission-config:/config
secrets:
  rpc_creds:
    file: ./rpc_creds
```

```bash
sudo systemctl enable --now docker
cd ~/docker/transmission-vpn
docker compose up -d
```

Check

```bash
pink@thebeachlab:~/docker/transmission-vpn$ docker exec -it transmission-vpn curl -s https://ipinfo.io
{
  "ip": "185.214.97.88",
  "city": "Barcelona",
  "region": "Catalonia",
  "country": "ES",
  "loc": "41.3888,2.1590",
  "org": "AS207137 PacketHub S.A.",
  "postal": "08007",
  "timezone": "Europe/Madrid",
  "readme": "https://ipinfo.io/missingauth"
}
```

Add location in nginx

```nginx
location ^~ /transmission/ {
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_pass http://127.0.0.1:9091/transmission/;
  proxy_http_version 1.1;
  proxy_set_header Connection "";
  proxy_pass_header X-Transmission-Session-Id;
}
```

```bash
sudo nginx -t
sudo systemctl reload nginx
```

```bash
 mkdir /home/pink/downloads
sudo usermod -aG pink debian-transmission
sudo chown -R pink:pink /home/pink/downloads
sudo ufw allow 9091/tcp comment 'transmission rpc'
sudo ufw allow 51413/tcp comment 'transmission peer tcp'
sudo ufw allow 51413/udp comment 'transmission peer udp'
sudo ufw reload
```

Then go to https://beachlab.org/transmission/web/

In macOS install `brew install --cask transmission-remote-gui`
