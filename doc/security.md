# Setup and secure remote ssh access

## Service maintenance

Security maintenance on 2026-10-22 used complete signed APT indexes and the
vendors' application releases. Before future maintenance, refresh **all**
configured sources, simulate the selected package set, save configuration and
consistent application databases privately, then verify the running service
and ordinary public requests after activation. For a deliberately scoped APT
refresh, set `APT::Get::List-Cleanup=false` to preserve other cached indexes.

| NUC component | Activated version | Vendor security source |
| --- | --- | --- |
| Nginx | 1.31.8 | [Security advisories](https://nginx.org/en/security_advisories.html): CVE-2026-15176, 93479, 95101, 97629 and 97205 |
| Docker / containerd | 29.9.2 / 2.4.2 | [Docker 29 notes](https://docs.docker.com/engine/release-notes/29/): containerd CVE-2026-95839, Go HTTP/2 and CA revocation fixes |
| Tailscale | 1.104.2 | [Changelog](https://tailscale.com/changelog): TS-2026-013; also applied on the VPS |
| Headscale | 0.29.6 / Go 1.27.3 | [Sequential migrations and runtime rebuild](headscale.md) |
| openHAB | 5.2.3 | [Core advisories](https://github.com/openhab/openhab-core/security/advisories): SSRF, forwarded-IP authentication, OAuth redirect/PKCE and XSS fixes in 5.2.2; 5.2.3 fixes the proxy regression |
| Nextcloud / PHP | 33.0.10 / 8.4.27 | [Deployment and recovery](cloud.md) |
| Node-RED | 5.0.9 | [Runtime and custom dependency maintenance](nodejs.md) |
| Authentik | 2026.8.5 | [Deployment and recovery](authentik.md) |
| Grafana | 13.0.11 | [Deployment and recovery](grafana.md) |
| Gotify | 3.1.1 | [iGotify compatibility and recovery](igotify.md) |
| TimescaleDB / PgBouncer | 2.31.0 / 1.26.1 | [Database migration and recovery](postgres.md) |

### NUC security activation, 2026-10-26

OpenVPN `2.5.11-0ubuntu0.22.04.6` was already installed, but
`openvpn-server@server.service` still used the deleted `.5` executable. Restarting
that exact unit activated [CVE-2026-84790](https://ubuntu.com/security/CVE-2026-84790).
The new process matched the installed SHA-256 and logged initialization complete.

Headscale advanced to the verified official 0.29.6 package, including Go 1.27.3
and patched HTTP/2, gRPC and text dependencies. Both client IDs and the approved
route were retained; configuration, executable digest and public health passed.
Forms advanced 5.4.0 → 5.4.1 on Nextcloud 33.0.10; app integrity and public
status passed after reloading PHP-FPM. See [Headscale](headscale.md) and
[Nextcloud](cloud.md).

[Reviewed dependency backports](nodejs.md#dependency-security-backports-2026-10-26)
removed the affected copies from Node-RED 5.0.9 and Watson OpenClaw 2026.10.7,
including their bundled npm trees. Isolated processes reproduced the old
body-parser and multer crashes and Zod's late collection-size check; corrected
copies passed those cases and legitimate controls. Node-RED safe staging loaded
all types with no errors, then production started flows and MQTT. Watson's
maintenance completed with a ready RPC Gateway and unchanged configuration.
The updater now reapplies the backports even when the core version is unchanged.

Recovery is private under `/var/backups/selfhosted/security-20261026/` and
`~pink/.openclaw-backups/updates/20261026T092153Z-pre-2026.10.7-to-2026.10.7/`.
Headscale/Forms database backups were consistent; Node-RED code and user data and
Watson code/state were retained. Signed full-source APT refresh succeeded; no
newer Ubuntu security-pocket package or machine reboot was pending. The VPS was
not modified in this activation.

### VPS security activation, 2026-10-26

On Liderflor, restarting only unattended-upgrades activated installed zlib
`1:1.3.dfsg-3.1ubuntu2.3`; the new process has no deleted zlib mapping.
Redirection 5.8.0 → 5.10.1 passed WordPress.org checksums and database checks;
PHP-FPM reloaded and public WordPress, API, shop and admin requests passed.
Flora OpenClaw 2026.10.7 now uses the same reviewed dependency floors as Watson.
Its canonical updater reapplies them before Doctor/start after every core install.

A full private code/configuration/state archive remains on the VPS under
`/var/backups/lider-ops/security-20261026/`. All 16 SQLite checks passed and
configuration content was preserved. A restrictive-umask extraction initially
blocked Flora from reading package files; validation kept the Gateway stopped.
The helper now normalizes only public vendor files, and the regression passes
on Mac and Linux. Flora's actual user passed library controls, config validation
and independent Gateway RPC; no restart loop remained.

The final Linux source snapshot passed 784 tests. Functional health ran all 46
checks: 44 passed, with the existing disk-capacity and October 14 snapshot alerts
remaining. Global health is not green; capacity/snapshot maintenance is separate
from the applied security corrections. The disputed npm cache advisory described
in [Node maintenance](nodejs.md) is still tracked without an invented patch.

The 2026-10-22 NUC recovery directory is
`/var/backups/selfhosted/services-security-20261022/`. Stop SQLite-backed
services before archiving their data; use native PostgreSQL dumps and validate
their table of contents. The NAS Restic job completed successfully, including
its repository check, before the Nextcloud 33 migration.

On 2026-10-22 the NUC reboot at 08:59 UTC activated the updated libraries across services.
After boot, systemd reported `running` with no failed units, all ten containers
returned, the NAS mounted, Node-RED started its flows and MQTT connection, and
Watson's Gateway passed its read-only RPC check. Public Nextcloud, Authentik,
Grafana, Gotify, Node-RED, Vaultwarden, Headscale and openHAB endpoints responded.
During that verification `needrestart` listed PHP 8.4 because OPcache maps an executable
`/anon_hugepage (deleted)` segment. Inspection found only anonymous shared memory,
no deleted file-backed libraries, and the active FPM executable matched the
installed package SHA-256. Repeated restarts are not a remedy for that mapping.

openHAB's package hold remains intentional: review a specific patch release,
use `--allow-change-held-packages` for that reviewed update, and preserve the
hold afterwards. Its pre-update configuration and data are in `openhab.tgz`.
The runtime returned HTTP 200 on loopback port 8080 after activation.

Vaultwarden 1.37.4, CouchDB 3.5.3, taskchampion-sync 0.7.1 and the iGotify
1.6.0.1 bridge were already at the reviewed vendor releases. The installed
TiTiler rio-tiler 9.3.0 exceeds the patched 9.1 floor in its
[expression advisory](https://github.com/developmentseed/titiler/security/advisories/GHSA-9cfx-96xx-wmh9).
PostgreSQL 18.6 on the host and 16.15 in Authentik were current. Both hosts had
no newer installed-package revision from the Ubuntu security pockets after
the full index refresh. Ordinary `-updates` releases remain eligible for their
normal maintenance schedule.

<!-- vim-markdown-toc GFM -->

- [Setup and secure remote ssh access](#setup-and-secure-remote-ssh-access)
  - [Don't use the default port 22](#dont-use-the-default-port-22)
  - [Ban brute force attackers](#ban-brute-force-attackers)
  - [Use 2FA verification codes](#use-2fa-verification-codes)
  - [Use ssh keys instead of password to log in via ssh](#use-ssh-keys-instead-of-password-to-log-in-via-ssh)
  - [Set basic firewall rules](#set-basic-firewall-rules)

<!-- vim-markdown-toc -->

## Don't use the default port 22

Replace the standard ssh port `Port 22` with some other in `/etc/ssh/sshd_config`, say 22222. restart ssh `sudo service sshd restart`.

## Ban brute force attackers

Now ban for 10 minutes if someone makes multiple (10) attemps to log in:

```bash
sudo apt install fail2ban
cd /etc/fail2ban
sudo cp fail2ban.conf fail2ban.local
sudo nano fail2ban.local
```

And add the following

```bash
[sshd]
enabled = true
port = 22222
filter = sshd
logpath = /var/log/auth.log
maxretry = 10
bantime = 600
```

And restart fail2ban `sudo service fail2ban restart`

## Use 2FA verification codes

Now configure 2FA. Install `sudo apt install libpam-google-authenticator`, Run `google-authenticator` and scan the qr in your mobile phone app. Edit `sudo nano /etc/pam.d/sshd` and comment out `@include common-auth`. At the bottom of the file add `auth required pam_google_authenticator.so`.

## Use ssh keys instead of password to log in via ssh

We won't  use our password to login via ssh. Instead we will import our public ssh keys from github or gitlab to log in via ssh. In my case I am importing my public keys from github.

`ssh-import-id gh:thebeachlab`

Now edit `sudo nano /etc/ssh/sshd_config` and add/modify:

```bash
ChallengeResponseAuthentication yes
UsePAM yes
AuthenticationMethods publickey,password publickey,keyboard-interactive
PasswordAuthentication no
PermitRootLogin no
```

Restart the service `sudo service sshd restart`

## Set basic firewall rules

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22222/tcp comment 'SSH'
sudo ufw allow http
sudo ufw allow https
sudo ufw enable
sudo ufw reload
```

Optionally drop pings `sudo nano /etc/ufw/before.rules` and add

```bash
-A ufw-before-input -p icmp --icmp-type echo-request -j DROP
```

And again `sudo ufw reload`

