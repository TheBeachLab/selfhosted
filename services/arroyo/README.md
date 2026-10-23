# arroyo.ing NUC hosting

Live since 2026-10-22: https://arroyo.ing/ and https://www.arroyo.ing/.
The approved site was recovered from the chat "Crear web de Arroyo Bauingenieur".
Current published source: /Users/Papi/Repositories/strategy/websites/arroyo, commit f4ace99fc1af92d3aaae70054aab7746672f2c00. The original site was recovered from the chat "Crear web de Arroyo Bauingenieur".

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
The public `location /` sends `Cache-Control: no-cache` on successful and error
responses so browsers revalidate HTML, JavaScript, stylesheets and assets; it
does not disable storage (`no-store`).

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
with cp -a. The full snapshot made immediately before the 2026-10-24 cache-busting
publication is /var/backups/arroyo.ing/20261023223207Z. It is a recoverable copy
of the complete public root as it existed immediately before deployment.

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

Published 2026-10-24 from strategy commit
f4ace99fc1af92d3aaae70054aab7746672f2c00. The public root has the five
allowlisted top-level files and 17 files under assets/ (22 files total); all
live SHA-256 hashes match the staged source with no missing, extra or mismatched
files. Only index.html, impressum.html and datenschutz.html changed from the
previous published commit 1193518c988d7756983f4516bcccf0df6ba5f188. The CSS,
JavaScript and all assets retain their exact prior bytes. The Órbita section
still links to https://orbita.arroyo.ing/.

The Safari cache issue was observed after the updated HTML was live: an existing
Safari tab showed the latest page markup with stale CSS and JavaScript from
unversioned URLs; Option-Command-R fetched the current presentation. The
Cache-Control: no-cache response makes browsers revalidate but does not replace
old cached resources already stored under the same URL. The three HTML pages now
request styles.css?v=f05d9e60da49, and the homepage requests
site.js?v=b3eee4f6d407, so the browser fetches the reviewed CSS and carousel code
under new URLs. GET readbacks on apex and www returned 200 with Cache-Control:
no-cache; the versioned CSS and JS bodies matched their full source SHA-256
hashes. All 17 asset URLs returned 200 on both hosts. HTTP redirects to matching
HTTPS hosts remain 301.

The 2026-10-24 predeployment snapshot is
/var/backups/arroyo.ing/20261023223207Z. The complete live file-level manifest,
versioned URL checks and rollback command are recorded in
`arroyo-deployment-readback.md` in the Codex task artifacts.

The earlier 2026-10-23 rollback restored commit c0cc2e6 from
/var/backups/arroyo.ing/20261023114001Z before the later publications. The earlier
contact update changed the address to fran@arroyo.ing in index.html, site.js,
impressum.html and datenschutz.html; the current source retains that address.

Initial hosting verification on 2026-10-22 passed Nginx syntax, JavaScript
syntax, systemd unit validation, Certbot dry-run renewal for both hostnames
and independent Cloudflare DDNS readback.

Official API: https://developers.cloudflare.com/api/resources/dns/subresources/records/
DDNS: https://developers.cloudflare.com/dns/manage-dns-records/how-to/managing-dynamic-ip-addresses/
