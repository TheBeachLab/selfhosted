# WIP. OBS ninja

Only God knows how much I hate Zoom and it's lack of support for Linux. This is day and night for streaming.

Create a CNAME in your DNS server, e.g. `webrtc.example.org`.

Clone [obsninja](https://github.com/steveseguin/obsninja) in `/var/www`

Create a file in `/etc/nginx/sites-available/webrtc.example.org` with this content

```
server {
  listen 80;
  listen [::]:80;

  server_name webrtc.example.org;
  root /var/www/obsninja;
  index index.html;

  location ~ ^/([^/]+)/([^/?]+)$ {
          root /var/www/obsninja;
          try_files /$1/$2 /$1/$2.html /$1/$2/ /$2 /$2/ /$1/index.html;
          add_header Access-Control-Allow-Origin *;
  }
  location / {
           if ($request_uri ~ ^/(.*)\.html$) {
                return 302 /$1;
            }
            try_files $uri $uri.html $uri/ /index.html;
            add_header Access-Control-Allow-Origin *;
  }

}
```

Check the syntax `sudo nginx -t`. Enable the site: 

`sudo ln -s /etc/nginx/sites-available/webrtc.example.org /etc/nginx/sites-enabled/webrtc.example.org`

Reload nginx `sudo service nginx reload`

Add SSL certificates `sudo certbot --nginx -d webrtc.example.org`

Install a turn server

`sudo apt install coturn`

Configure by editing `/etc/default/coturn` and uncommenting `#TURNSERVER_ENABLED=1` leaving it like this: `TURNSERVER_ENABLED=1`

Edit user/group to be root here `/usr/lib/systemd/system/coturn.service`

Adjust missing rules

```
sudo ufw allow 3478
sudo ufw allow 443
sudo ufw allow 49152:65535/tcp
sudo ufw allow 49152:65535/udp
```

Reload rules `sudo ufw reload`

> To be continued
