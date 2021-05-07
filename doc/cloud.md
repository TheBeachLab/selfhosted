# Nextcloud server

With Nginx and PostgreSQL

## Domain and SSL certificates

Create a CNAME for `cloud` or similar to `beachlab.org` and get a certificate

`sudo certbot certonly --nginx -d cloud.beachlab.org`

## Install PHP

`sudo apt install imagemagick php-imagick php7.4-common php-fpm php7.4-pgsql php7.4-fpm php7.4-gd php7.4-json php7.4-curl  php7.4-zip php7.4-xml php7.4-mbstring php7.4-bz2 php7.4-intl php7.4-bcmath php7.4-gmp`
Check with `php -v`.
For any nginx site where you require PHP add this to the config

```

```

after that restart or reload nginx

## Download NextCloud

Check for the latest version https://nextcloud.com/install/#instructions-server

```
wget https://download.nextcloud.com/server/releases/nextcloud-21.0.1.zip
sudo unzip nextcloud-21.0.1.zip -d /var/www/
sudo chown www-data:www-data /var/www/nextcloud/ -R
```

## Edit nginx config file

`sudo nano /etc/nginx/sites-available/nextcloud`

Check the syntax `sudo nginx -t` copy to enabled sites `sudo ln -s /etc/nginx/sites-available/nextcloud /etc/nginx/sites-enabled/nextcloud` and reload nginx `sudo systemctl reload nginx`

## Postgres database

Activate PHP postgres module with `sudo phpenmod pdo_pgsql`. Modify `/etc/php/7.4/mods-available/pgsql.ini`

```
; configuration for php pgsql module
; priority=20
extension=pdo_pgsql.so
extension=pgsql.so

[PostgresSQL]
pgsql.allow_persistent = On
pgsql.auto_reset_persistent = Off
pgsql.max_persistent = -1
pgsql.max_links = -1
pgsql.ignore_notice = 0
pgsql.log_notice = 0
```

Create the user and database

```
sudo -u postgres createuser --interactive
Enter name of role to add: nextcloud
Shall the new role be a superuser? (y/n) y
```

Now create the database `sudo -u postgres createdb nextcloud`

Create a linux user with the same username `sudo adduser nextcloud`. Check the connection:

```
sudo -u nextcloud psql
psql (12.6 (Ubuntu 12.6-0ubuntu0.20.04.1))
Type "help" for help.

nextcloud=# \conninfo
You are connected to database "nextcloud" as user "nextcloud" via socket in "/var/run/postgresql" at port "5432".
nextcloud=#
```

Finally restart postgres service `sudo systemctl restart postgresql.service`

## Install

Go to cloud.beachlab.org and enter the required data

## Status 

Missconfiguration. The server throws

```
Internal Server Error

The server was unable to complete your request.

If this happens again, please send the technical details below to the server administrator.

More details can be found in the server log.
Technical details

    Remote Address: 37.135.193.89
    Request ID: 6nBf3q5CwcAromYidTcz
```

Nginx error log `/var/log/nginx/error.log` shows

```
2021/05/06 14:49:46 [error] 814#814: *62 connect() failed (111: Connection refused) while connecting to upstream, client: 37.135.193.89, server: cloud.beachlab.org, request: "GET /index.php HTTP/2.0", upstream: "fastcgi://127.0.0.1:9000", host: "cloud.beachlab.org"
```
