# Nextcloud

Nextcloud 32 running on Nginx + PHP 8.1 FPM + PostgreSQL.
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
| Version | 32.0.14 (live `occ status` and HTTPS status, 2026-10-21) |
| URL | https://cloud.beachlab.org |
| Files | `/var/www/nextcloud` (9.4 GB) |
| Data dir | `/var/www/nextcloud/data` |
| Config | `/var/www/nextcloud/config/config.php` |
| Nginx vhost | `/etc/nginx/sites-available/nextcloud` |
| PHP | 8.1 FPM (`php8.1-fpm`), Ubuntu package `8.1.2-1ubuntu2.28` |
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

### Critical PHP security maintenance

Ubuntu 22.04 requires **at least `8.1.2-1ubuntu2.28`** for
[CVE-2026-109618](https://ubuntu.com/security/CVE-2026-109618) and
[CVE-2026-109619](https://ubuntu.com/security/CVE-2026-109619), as specified in
[USN-8948-1](https://ubuntu.com/security/notices/USN-8948-1).
The fixes are backported: the upstream-looking `8.1.2` version alone does not
establish whether Ubuntu PHP is patched. The
[PHP advisory of 21 October 2026](https://www.php.net/archive/2026.php#2026-10-21-5)
includes PHP-FPM among affected web runtimes. Application updates and
upload-progress configuration are not a complete substitute for the vendor patch.

On 2026-10-21 the NUC's 15 installed packages built from source package `php8.1`
were upgraded from `.27` to `.28`, using authenticated Ubuntu APT packages and
keeping the existing PHP branch and configuration. Independently versioned APCu,
igbinary, Imagick and Redis extensions were not changed. No packages were added
or removed. The package scripts replaced all FPM workers at **22:30:32
Europe/Madrid**. Nginx routes Nextcloud to `/run/php/php8.1-fpm.sock`; Apache's
loaded modules contained WSGI and no PHP module, and PHP 7.4 had no installed
runtime packages or running workers.

Before future PHP maintenance:

1. Check `apt-cache policy php8.1-fpm`, the full installed package versions,
   active webserver/socket routes, free space and package-manager activity.
   Refresh signed indexes and simulate a PHP-only upgrade before applying it.
2. Back up PHP configuration privately. The incident's root-only configuration
   and package inventory are in
   `/var/backups/selfhosted/php-security-20261021/` on the NUC. This is not a
   Nextcloud data/database backup.
3. Upgrade all installed packages from source package `php8.1` coherently. Use
   `--only-upgrade` and `Dpkg::Options::=--force-confold`, retaining APT's locks
   and signature verification. `NEEDRESTART_MODE=l` avoids unrelated restarts;
   PHP package scripts still restart FPM. Review the package revision appropriate
   to the current advisory instead of permanently pinning the incident version.
4. Run `php-fpm8.1 -t`, `nginx -t`, `dpkg --audit`, and `dpkg -V` on the upgraded
   packages. Compare every FPM `/proc/<pid>/exe` digest with
   `/usr/sbin/php-fpm8.1` and check for deleted PHP module mappings. A CLI version
   check alone is insufficient.
5. Check `occ status --output=json`, ordinary public HTTPS status/login requests,
   and new FPM/nginx errors. Confirm `maintenance=false` and
   `needsDbUpgrade=false`. Do not use memory-exhaustion exploits on production.

Post-update verification passed configuration syntax and package audit checks.
`dpkg -V` reported only the pre-existing local customization of
`/etc/php/8.1/fpm/pool.d/www.conf`; comparison against the backup confirmed that
all PHP/APT configuration contents and symlink targets were unchanged. The master
and observed workers matched the installed FPM executable SHA-256
`402fbd505e3a03012bab01b52d427e5368b49f930e1e2d27ad34848c118f07af`, with no
deleted PHP mappings. The installed changelog explicitly lists both CVEs.
Live `occ status` and public HTTPS status confirmed Nextcloud `32.0.14`, no
maintenance mode and no pending database upgrade. Public login and OCS
capabilities GETs also passed; OCS requests require the `OCS-APIRequest: true`
header (a request without it returned HTTP 412).

The full APT index refresh warned that the unrelated Mosquitto and TimescaleDB
PPAs returned HTTP 503; Ubuntu's indexes supplied the fixed PHP packages.
The existing `daswerklab-mckenzie-maintenance.service` failure preceded this
operation and was unchanged. No exploit or retrospective compromise investigation
was performed. Do not silently roll PHP back to `.27`: that reopens both CVEs.

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
