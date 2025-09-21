# Transmission Daemon with NordVPN

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
