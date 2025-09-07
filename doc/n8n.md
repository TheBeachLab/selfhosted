# n8n 

```bash
docker run -it --rm \
 --name n8n \
 -p 5678:5678 \
 -e GENERIC_TIMEZONE="Europe/Berlin" \
 -e TZ="Europe/Berlin" \
 -e N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true \
 -e N8N_RUNNERS_ENABLED=true \
 -v n8n_data:/home/node/.n8n \
 docker.n8n.io/n8nio/n8n
 ```

 Enable ports in the firewall
 
```bash
sudo ufw allow 5678/tcp
sudo ufw reload
```

For a subdomain, create a CNAME pointing to `n8n.beachlab.org`or similar and obtain a Let's Encrypt certificate.

and `sudo nano /etc/nginx/sites-available/n8n`

```nginx
server {
    server_name n8n.beachlab.org;

    listen 80;
    listen [::]:80;
    return 301 https://$host$request_uri;
}

server {
    server_name n8n.beachlab.org;

    listen 443 ssl;
    listen [::]:443 ssl;

    ssl_certificate /etc/letsencrypt/live/n8n.beachlab.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/n8n.beachlab.org/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5678;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

check and reload nginx

```bash
sudo ln -s /etc/nginx/sites-available/n8n /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

With docker compose:

WIP





