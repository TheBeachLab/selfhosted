# arroyo.ing NUC hosting

Live since 2026-10-22: https://arroyo.ing/ and https://www.arroyo.ing/.
The approved site was recovered from the chat "Crear web de Arroyo Bauingenieur".
Current published source: /Users/Papi/Repositories/strategy/websites/arroyo, commit 29808ffb79627e8e753415a540691df2f2fd2d4e. The original site was recovered from the chat "Crear web de Arroyo Bauingenieur".

## Runtime

Nginx serves /var/www/arroyo.ing. Only index.html, hotel-mim-sitges.html, impressum.html,
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
with cp -a. The full snapshot made immediately before the 2026-10-24 site publication is
/var/backups/arroyo.ing/20261024083832Z. It is a recoverable copy of the complete
public root as it existed immediately before deployment.

Stage the exact authorized source commit into a clean directory containing only
the six top-level allowlisted files and assets/. Copy the six files in one
rsync call, then copy the assets tree in a separate call to the explicit remote
assets/ directory. Never pass assets/ as a peer source with the top-level files:
that flattens its contents into the web root. These commands preserve existing
permissions and ownership, create no deletion set, and leave unrelated remote
files alone:

```sh
rsync -a --no-perms --no-owner --no-group --omit-dir-times \
  --rsync-path='sudo rsync' -e 'ssh -o BatchMode=yes -o ConnectTimeout=12' \
  <staging-root>/index.html <staging-root>/hotel-mim-sitges.html \
  <staging-root>/impressum.html \
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

Published 2026-10-26 from strategy commit
29808ffb79627e8e753415a540691df2f2fd2d4e. The public root has six
allowlisted top-level files and 19 files under assets/ (25 files total); every
live SHA-256 matches the staged source with no missing, extra or mismatched
files. The homepage distinguishes Bauleitung, Projektmanagement and
Machbarkeit & Projektstart, with agreed-scope task lists. Digital tools appear
in the project-management detail. The gallery links to hotel-mim-sitges.html,
which presents Fran's historical responsibilities and the documented LEED result.

The pages request styles.css?v=0853dd1a3614; the homepage
requests site.js?v=6423e8b143f7. Hash-based query URLs continue to
prevent the mixed-version Safari issue recorded in the website README.
All 25 file paths, the root homepage and both versioned resource URLs returned
200 with Cache-Control: no-cache on apex and www (56 HTTPS readbacks), with
bodies matching the source hashes. Both HTTP hostnames redirect to their matching
HTTPS host with 301. The published page and mobile service controls were also
inspected in the in-app browser without console errors or warnings.

The full predeployment snapshot is
/var/backups/arroyo.ing/20261026180621Z. Restore the complete saved tree with
`ssh pink-sudo 'sudo rsync -a --delete /var/backups/arroyo.ing/20261026180621Z/ /var/www/arroyo.ing/'`.
This restores the earlier 24-file version and removes the new case-study page.
The manifest and public readbacks are recorded in
`/Users/Papi/.codex/visualizations/2026/10/26/01a17924-05a6-7163-a658-02d5efb6713e/arroyo-services-hotel-deployment.json`.

The earlier 2026-10-23 rollback restored commit c0cc2e6 from
/var/backups/arroyo.ing/20261023114001Z before the later publications. The earlier
contact update changed the address to fran@arroyo.ing in index.html, site.js,
impressum.html and datenschutz.html; the current source retains that address.

Initial hosting verification on 2026-10-22 passed Nginx syntax, JavaScript
syntax, systemd unit validation, Certbot dry-run renewal for both hostnames
and independent Cloudflare DDNS readback.

Official API: https://developers.cloudflare.com/api/resources/dns/subresources/records/
DDNS: https://developers.cloudflare.com/dns/manage-dns-records/how-to/managing-dynamic-ip-addresses/

## Podcast URL

Since 2026-10-25, `/podcast/` is served by the dedicated
`/etc/nginx/snippets/housing-podcast.conf` include, from
`/var/www/podcast/current/`. It is separate from the main website's file
allowlist. Keep this include when updating the virtual host. See
[the podcast runtime and publishing workflow](../podcast/README.md).
