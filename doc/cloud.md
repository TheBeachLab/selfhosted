# Nextcloud

**Author:** Mr. Watson 🦄 (updated 2026-03-30, originally Fran)

Nextcloud 31 running on Nginx + PHP 8.1 FPM + PostgreSQL.
URL: `https://cloud.beachlab.org`

<!-- vim-markdown-toc GFM -->

- [Current state](#current-state)
- [Quick checks](#quick-checks)
- [Updating Nextcloud](#updating-nextcloud)
- [Nginx vhost](#nginx-vhost)
- [PHP](#php)
- [PostgreSQL](#postgresql)
- [Fresh install (reference)](#fresh-install-reference)

<!-- vim-markdown-toc -->

## Current state

| Item | Value |
|---|---|
| Version | 31.0.14 |
| URL | https://cloud.beachlab.org |
| Files | `/var/www/nextcloud` (9.4 GB) |
| Data dir | `/var/www/nextcloud/data` |
| Config | `/var/www/nextcloud/config/config.php` |
| Nginx vhost | `/etc/nginx/sites-available/nextcloud` |
| PHP | 8.1 FPM (`php8.1-fpm`) |
| Database | PostgreSQL `nextcloud` DB |

History: was running NC 24.0.3, dormant for a while, resurrected and upgraded to NC 31 on 2026-03-30.

## Quick checks

```bash
# Status
sudo -u www-data php /var/www/nextcloud/occ status

# Maintenance mode
sudo -u www-data php /var/www/nextcloud/occ maintenance:mode

# Background jobs
sudo -u www-data php /var/www/nextcloud/occ background:cron

# Logs (last 20 lines)
sudo -u www-data php /var/www/nextcloud/occ log:tail --lines=20

# HTTP check
curl -sI https://cloud.beachlab.org | head -3

# PHP FPM
systemctl status php8.1-fpm
```

## Updating Nextcloud

Nextcloud can only advance one major version per update. Use the built-in updater repeatedly until the latest version is reached.

```bash
# 1. Enable maintenance mode
sudo -u www-data php /var/www/nextcloud/occ maintenance:mode --on

# 2. Run updater (repeats one major version at a time)
sudo -u www-data php /var/www/nextcloud/updater/updater.phar --no-interaction

# 3. Repeat step 2 until "No update available" or target version reached

# 4. Confirm version
sudo -u www-data php /var/www/nextcloud/occ status
```

The updater runs `occ upgrade` and disables maintenance mode automatically when using `--no-interaction`.

**Gotcha:** Any unexpected files in the Nextcloud root will block the updater with "Check for expected files failed". Remove or move them first.

## Nginx vhost

Config: `/etc/nginx/sites-available/nextcloud`
Enabled: `/etc/nginx/sites-enabled/nextcloud` (symlink)

```bash
# Enable vhost
sudo ln -s /etc/nginx/sites-available/nextcloud /etc/nginx/sites-enabled/nextcloud

# Test and reload
sudo nginx -t && sudo systemctl reload nginx
```

The vhost uses PHP 8.1 FPM socket: `unix:/run/php/php8.1-fpm.sock`

SSL cert: Let's Encrypt, valid until 2026-05-18 (auto-renews via certbot).

```bash
# Renew cert manually if needed
sudo certbot renew --nginx -d cloud.beachlab.org
```

## PHP

PHP 8.1 installed. Required modules already active: `pdo_pgsql`, `imagick`, `gd`, `curl`, `zip`, `xml`, `mbstring`, `intl`, `bcmath`, `gmp`.

```bash
php --version
php -m | grep -E "pdo_pgsql|imagick|gd|curl"
systemctl status php8.1-fpm
sudo systemctl restart php8.1-fpm
```

## PostgreSQL

Database: `nextcloud`, owner: `nextcloud` user.

```bash
# Check DB exists
sudo -u postgres psql -l | grep nextcloud

# Connect
sudo -u postgres psql -d nextcloud

# Row counts (sanity check)
sudo -u postgres psql -d nextcloud -c "SELECT count(*) FROM oc_filecache;"
```

## Fresh install (reference)

Only needed if starting from scratch — skip if Nextcloud is already installed.

```bash
# SSL cert
sudo certbot certonly --nginx -d cloud.beachlab.org

# PHP 8.1 modules
sudo apt install php8.1-fpm php8.1-pgsql php8.1-gd php8.1-curl php8.1-zip \
  php8.1-xml php8.1-mbstring php8.1-intl php8.1-bcmath php8.1-gmp \
  php8.1-imagick imagemagick

# Download Nextcloud
wget https://download.nextcloud.com/server/releases/latest.zip
sudo unzip latest.zip -d /var/www/
sudo chown -R www-data:www-data /var/www/nextcloud/

# PostgreSQL
sudo -u postgres psql << 'SQL'
CREATE USER nextcloud WITH PASSWORD 'yourpassword';
CREATE DATABASE nextcloud TEMPLATE template0 ENCODING 'UNICODE';
ALTER DATABASE nextcloud OWNER TO nextcloud;
GRANT ALL PRIVILEGES ON DATABASE nextcloud TO nextcloud;
SQL

# Enable vhost and visit https://cloud.beachlab.org to finish setup
sudo ln -s /etc/nginx/sites-available/nextcloud /etc/nginx/sites-enabled/nextcloud
sudo nginx -t && sudo systemctl reload nginx
```
