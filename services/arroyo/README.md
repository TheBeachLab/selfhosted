# arroyo.ing NUC hosting

Live since 2026-10-22: https://arroyo.ing/ and https://www.arroyo.ing/.
The approved site was recovered from the chat "Crear web de Arroyo Bauingenieur".
Current published source: /Users/Papi/Repositories/strategy/websites/arroyo, commit 49b1832792d1757acb7752be08751da8745190ef. The original site was recovered from the chat "Crear web de Arroyo Bauingenieur".

## Runtime

Nginx serves /var/www/arroyo.ing. Only index.html, impressum.html,
datenschutz.html, styles.css, site.js and assets/ are public. Internal source
and design documentation are excluded. The privacy and imprint pages describe
the live hosting. Both HTTP and HTTPS visitor access/error logging are disabled.
The public contact address is fran@arroyo.ing (iCloud Mail); the existing
public phone is preserved.

Cloudflare zone arroyo.ing (acc70087bb85ea5da695e277bf0f2d1d) uses an apex
A record for the NUC public IPv4 and a www CNAME to arroyo.ing. Both are
DNS-only with TTL 60 seconds. The Cloudflare web proxy is disabled.

Nginx configuration: /etc/nginx/sites-available/arroyo.ing, enabled by symlink.
nginx.conf here is the live configuration; nginx-http.conf is the bootstrap
configuration used before issuing the first certificate.

Let's Encrypt certificate covers both names. Initial expiry: 2027-01-20.
HTTP redirects to HTTPS; the existing Certbot Nginx renewal service manages
renewal. Certificate and key stay under /etc/letsencrypt/live/arroyo.ing/.

## Dynamic IP

/usr/local/lib/arroyo/ddns.py reads /etc/cloudflare-arroyo.env, root-only 0600,
containing CLOUDFLARE_API_TOKEN. Credentials are outside Git. The token needs
DNS edit permission for this zone; the earlier Domains Admin token alone
could list zones but returned 403 for DNS access.

cloudflare-arroyo-ddns.timer is enabled and checks every 150 seconds. It calls
the oneshot service, which validates the public IPv4, patches only the existing
apex A content when changed, preserves proxy status and TTL, and verifies the
Cloudflare result. www follows the apex without a second DDNS update.

Inspect with systemctl status cloudflare-arroyo-ddns.timer and
journalctl -u cloudflare-arroyo-ddns.service. Restarting the service performs an
immediate check. Initial and subsequent scheduled service runs succeeded.

## Publishing updates

Keep website changes local by default; publish only after explicit user
authorization. Before each authorized content deployment, make a new
UTC-stamped full copy of /var/www/arroyo.ing under /var/backups/arroyo.ing/
with cp -a. The full snapshot made before the 2026-10-23 publication is
/var/backups/arroyo.ing/20261023175318Z. It is a recoverable copy of the complete
public root as it existed immediately before that deployment.

Stage the exact authorized source commit into a clean directory containing only
the five top-level allowlisted files and assets/. Copy the five files in one
rsync call, then copy the assets tree in a separate call to the explicit remote
assets/ directory. Never pass assets/ as a peer source with the top-level files:
that flattens its contents into the web root. These commands preserve existing
permissions and ownership, create no deletion set, and leave unrelated remote
files alone:

```sh
rsync -a --no-perms --no-owner --no-group --omit-dir-times \
  --rsync-path='sudo rsync' -e 'ssh -o BatchMode=yes -o ConnectTimeout=12' \
  <staging-root>/index.html <staging-root>/impressum.html \
  <staging-root>/datenschutz.html <staging-root>/styles.css \
  <staging-root>/site.js pink-sudo:/var/www/arroyo.ing/

rsync -a --no-perms --no-owner --no-group --omit-dir-times \
  --rsync-path='sudo rsync' -e 'ssh -o BatchMode=yes -o ConnectTimeout=12' \
  <staging-root>/assets/ pink-sudo:/var/www/arroyo.ing/assets/
```

Compare the complete live file list and SHA-256 hashes with the source allowlist,
then read back both HTTPS hostnames, the HTTP redirect, homepage content and
every asset URL. To restore the full saved tree, run
`ssh pink-sudo 'sudo rsync -a --delete /var/backups/arroyo.ing/<snapshot>/ /var/www/arroyo.ing/'`
with the selected snapshot directory. This removes files that are absent from
that full snapshot.

## Current published version and verification

Published 2026-10-23 from strategy commit
49b1832792d1757acb7752be08751da8745190ef. The public root contains the five
allowlisted top-level files and 17 files under assets/ (22 files total). The
complete live file list and SHA-256 manifest matched the staged source with no
missing, extra, or mismatched files. The five project entries are Hotel MiM
Sitges, Passeig de la Ribera 46, Passeig Marítim 59, Mirador de Can Pei, and
Josep Carbonell. The public contact is fran@arroyo.ing.

Apex and www HTTPS returned 200; both HTTP hostnames returned 301 to their
matching HTTPS hostname. All 17 asset URLs returned 200. The served stylesheet
contains the 32 × 8 px gallery indicator, 28–32 px responsive slide gap,
project-specific image aspect ratios, and automatic image height sizing. The
full file-level readback and rollback command are recorded in
`arroyo-deployment-readback.md` in the Codex task artifacts.

The earlier 2026-10-23 rollback restored commit c0cc2e6 from
/var/backups/arroyo.ing/20261023114001Z before this publication. It verified the
original two-scene hero and 17-file state at that time. The earlier contact
update had changed the address to fran@arroyo.ing in index.html, site.js,
impressum.html and datenschutz.html; the current source retains that address.

Initial hosting verification on 2026-10-22 passed Nginx syntax, JavaScript
syntax, systemd unit validation, Certbot dry-run renewal for both hostnames
and independent Cloudflare DDNS readback.

Official API: https://developers.cloudflare.com/api/resources/dns/subresources/records/
DDNS: https://developers.cloudflare.com/dns/manage-dns-records/how-to/managing-dynamic-ip-addresses/
