# Transmission Daemon with NordVPN

**Author:** Fran

Actualización 2026-09-14: la web y RPC usan las credenciales propias de
Transmission sobre HTTPS, para permitir Transmission Remote GUI. Se retiraron
solo de `location ^~ /transmission/` los includes `authentik-check.conf` y
`transmission-rpc-secret.conf`: Nginx pasa la autenticación del cliente al daemon.
No volver a ejecutar `services/admin-panel/protect-transmission.py` sin una
petición explícita de cambiar este modelo de acceso. El arranque sigue disponible
[en el panel](admin-panel.md); Descargas y las demás webs conservan la passkey.

Configuración de Remote GUI: host `beachlab.org`, puerto `443`, SSL activado,
ruta RPC `/transmission/rpc`, usuario `transmission` y contraseña RPC existente.
No se abre el puerto 9091 al exterior. Verificación real: HTTPS RPC sin credenciales
y con contraseña incorrecta devuelve 401; con credenciales existentes y el
intercambio de sesión 409 devuelve 200 `success` en `session-get`. La web sin
credenciales también devuelve 401; Descargas sigue redirigiendo al login.
La VPN permaneció `healthy` y no se modificaron contenedor ni rutas.
Backup Nginx: `/opt/authentik/nginx-before-transmission-rpc-20260914T161905`.

## VPN health and route protection (2026-09-14)

Verified on the live `transmission-vpn` container: the bundled healthcheck
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

Implementation evidence: the installed image's `/etc/transmission/start.sh`
removes the Docker default route when `DROP_DEFAULT_ROUTE=true`, before starting
Transmission. The wrapper checks that no IPv4 default route exists and Internet
routes via `tun0`, then runs the image's DNS, ping and process checks. IPv6 is
disabled for this IPv4 VPN. This is route-based protection, not an enabled UFW
firewall; the explicit VPN-server and local-network routes remain available.

Live validation: VPN connected, wrapper passed, HTTPS through the tunnel worked,
and local RPC responded with its expected unauthenticated HTTP 401. Temporarily
removing both VPN Internet routes made `ip route get 1.1.1.1` report unreachable,
HTTPS fail and the healthcheck return 1. Routes were restored in a `finally`
block and the healthcheck passed again. This tests loss of tunnel routes, not
every possible VPN failure or tracker. Docker health status alone does not
restart an unhealthy container.

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
