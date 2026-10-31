# Nextcloud

Nextcloud 33 running on Nginx + PHP 8.4 FPM + PostgreSQL.
URL: `https://cloud.beachlab.org`

Nginx and PHP-FPM serve it. The [Nginx page](web.md) used to say Nextcloud was
broken for lack of Apache. This page is the current record: version 33 on
Nginx. The upgrade to Nextcloud 31 is dated 2026-03-30 in the history below.

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
| Version | 33.0.10 (live `occ status` and HTTPS status, 2026-10-26) |
| URL | https://cloud.beachlab.org |
| Files | `/var/www/nextcloud` |
| Data dir | `/var/www/nextcloud/data` |
| Config | `/var/www/nextcloud/config/config.php` |
| Nginx vhost | `/etc/nginx/sites-available/nextcloud` |
| PHP | 8.4 FPM (`php8.4-fpm`), `8.4.27-1+ubuntu22.04.1+deb.sury.org+1` |
| Database | PostgreSQL `nextcloud` DB |

History: was running NC 24.0.3, dormant for a while, resurrected and upgraded to NC 31 on 2026-03-30.

### Migration to 33

On 2026-10-22, the official updater advanced 32.0.14 → 32.0.15 → 33.0.10,
verifying each download before replacing code and migrating PostgreSQL. The
owner approved PHP 8.4 from the maintained
[Ondřej Surý PPA](https://launchpad.net/~ondrej/+archive/ubuntu/php).
[PHP 8.4.27](https://www.php.net/releases/8_4_27.php) includes the October
security release. Nextcloud 33 requires PHP 8.2 or later; see the
[33 upgrade notes](https://docs.nextcloud.com/server/33/admin_manual/release_notes/upgrade_to_33.html).

After migration, 65 applications are enabled, including all 18 additional apps.
Required compatibility updates were
Deck 1.17.7, External sites 8.0.1, Notes 6.1.0 and Office 10.3.2. Maps retains
PHP EXIF; CODE 26.4.402 remains on x86_64. The updater also installed compatible
stable releases of Analytics, Contacts, Forms, GitHub integration and Tasks.
Check future app compatibility against the
[official platform feed](https://apps.nextcloud.com/api/v1/platform/33.0.10/apps.json).

Private recovery copies are in
`/var/backups/selfhosted/services-security-20261022/`: `nextcloud.dump` and
`nextcloud-code.tgz` precede 32.0.15; `nextcloud-pre33.dump` and
`nextcloud-code-pre33.tgz` precede 33. Data is covered by the successful NAS
Restic backup. Restore code, database and data from a consistent point together.

### Forms security update, 2026-10-26

Forms 5.4.0 → [5.4.1](https://github.com/nextcloud/forms/releases/tag/v5.4.1)
corrects shared-file access and respondent checks. Nextcloud remains 33.0.10.
Maintenance mode was enabled before a PostgreSQL custom-format dump and archive
of Forms/config; `pg_restore --list` validated the dump. `occ app:update forms`
verified and installed the app. Recovery copies are
`/var/backups/selfhosted/security-20261026/nextcloud-preforms541.dump` and
`nextcloud-forms540.tgz`.

After disabling maintenance mode, `occ status` was current while the existing
FPM workers still reported `needsDbUpgrade=true` over HTTPS. `php-fpm8.4 -t`
passed; reloading FPM activated the app code and public status then confirmed
`maintenance=false` and `needsDbUpgrade=false`. Forms integrity check returned
no errors. Check both CLI and actual web workers after future app updates.

## Quick checks

```bash
# Status
sudo -u www-data php8.4 /var/www/nextcloud/occ status

# Maintenance mode
sudo -u www-data php8.4 /var/www/nextcloud/occ maintenance:mode

# Background jobs
sudo -u www-data php8.4 /var/www/nextcloud/occ background:cron

# Logs (last 20 lines)
sudo -u www-data php8.4 /var/www/nextcloud/occ log:tail --lines=20

# HTTP check
curl -sI https://cloud.beachlab.org | head -3

# PHP FPM
systemctl status php8.4-fpm
```

## Updating Nextcloud

Nextcloud can only advance one major version per update. Use the built-in updater repeatedly until the latest version is reached.

```bash
# 1. Enable maintenance mode
sudo -u www-data php8.4 /var/www/nextcloud/occ maintenance:mode --on

# 2. Run updater (repeats one major version at a time)
sudo -u www-data php8.4 /var/www/nextcloud/updater/updater.phar --no-interaction

# 3. Repeat step 2 until "No update available" or target version reached

# 4. Confirm version
sudo -u www-data php8.4 /var/www/nextcloud/occ status
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

The vhost uses PHP 8.4 FPM socket: `unix:/run/php/php8.4-fpm.sock`.

TLS certificates auto-renew through Certbot.

```bash
# Renew cert manually if needed
sudo certbot renew --nginx -d cloud.beachlab.org
```

## PHP

PHP 8.4 is the active CLI and FPM runtime. The www-data cron explicitly uses
`/usr/bin/php8.4`. Required modules include `pdo_pgsql`, `imagick`, `gd`, `curl`,
`zip`, `xml`, `mbstring`, `intl`, `bcmath`, `gmp`, `redis`, `apcu` and `exif`.
PHP 8.1 remains installed for recovery with its FPM service disabled.

The PPA source is HTTPS and scoped with
`signed-by=/usr/share/keyrings/ondrej-php.gpg`; the verified key fingerprint is
`B8DC7E53946656EFBCE4C1DD71DAEAAB4AD4CAB6`. Preference
`/etc/apt/preferences.d/nextcloud-php84` gives `php8.4*`, `php-common` and
`libgd3` priority 500, and other PPA packages priority 50. Keep this scope so a
PHP update does not replace unrelated Ubuntu packages. The `php-imagick` dummy
metapackage was removed to avoid pulling PHP 8.5; the actual 8.1 extension remains.

The existing pool settings and Nextcloud overrides were copied to `/etc/php/8.4/`:
512 MiB FPM memory, 256 MiB OPcache, 32 MiB interned strings, 128 MiB APCu,
CLI APCu enabled, and the existing pool environment. Validate `php-fpm8.4 -t`
and `nginx -t` before restarting FPM or reloading Nginx.

### PHP 8.1 security maintenance history (2026-10-21)

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

# PHP 8.4 modules (configure the scoped PPA described above first)
sudo apt install php8.4-fpm php8.4-pgsql php8.4-gd php8.4-curl php8.4-zip \
  php8.4-xml php8.4-mbstring php8.4-intl php8.4-bcmath php8.4-gmp \
  php8.4-imagick php8.4-apcu php8.4-redis imagemagick

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
