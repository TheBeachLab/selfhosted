# Install or update

For user sister.

## Prepare firewall
```bash
sudo ufw allow 3000 comment 'PostgREST API'
sudo ufw reload
sudo ufw status
```

## Download, decompress

```bash
wget https://github.com/PostgREST/postgrest/releases/download/v11.2.2/postgrest-v11.2.2-linux-static-x64.tar.xz -O - | tar -xJf -
```

## Create roles in the database
```sql
create role web_anon nologin;
grant usage on schema public to web_anon;
grant select on public.my_table1 to web_anon;
grant select on public.my_table2 to web_anon;
```
In your readonly user:
```sql
grant web_anon to readonly;
```
TODO: Check permissions of readonly


## Configure
`nano postgrest.conf`

```bash
db-uri = "postgres://readonly:uri_encoded_password@localhost:6432/my_database"
db-schemas = "public"
db-anon-role = "web_anon"
```

## Create service
Create a file named `postgrest.service` in the /`etc/systemd/system/` directory:

```bash
[Unit]
Description=PostgREST Service
After=network.target

[Service]
User=sister
ExecStart=/home/sister/postgrest /home/sister/postgrest.conf
Restart=always

[Install]
WantedBy=default.target
```

Activate the service
```bash
sudo systemctl daemon-reload
sudo systemctl start postgrest
sudo systemctl enable postgrest
```
