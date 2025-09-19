# Transmission Daemon

Install `sudo apt install transmission-daemon -y`

Stop `sudo systemctl stop transmission-daemon`

Configure:

`sudo nano /etc/transmission-daemon/settings.json`

Some things you might want to change

```json
 "download-dir": "/home/pink/downloads",
 "rpc-whitelist-enabled": false,
 "rpc-username":
 "rpc-password":
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
sudo systemctl start transmission-daemon
sudo systemctl enable transmission-daemon
```

Then go to https://beachlab.org/transmission/web/

In macOS install `brew install --cask transmission-remote-gui`

Activate SSl, port 443
