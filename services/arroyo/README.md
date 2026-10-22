# arroyo.ing NUC hosting

Live since 2026-10-22: https://arroyo.ing/ and https://www.arroyo.ing/.
The approved site was recovered from the chat "Crear web de Arroyo Bauingenieur".
Source: /Users/Papi/Repositories/strategy/websites/arroyo, commit c0cc2e6.

## Runtime

Nginx serves /var/www/arroyo.ing. Only index.html, impressum.html,
datenschutz.html, styles.css, site.js and assets/ are public. Internal source
and design documentation are excluded. The privacy and imprint pages describe
the live hosting. Both HTTP and HTTPS visitor access/error logging are disabled.
The existing public contact email and phone are preserved.

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

## Verification

Public HTTPS returned 200 for both names, and HTTP redirected to HTTPS.
All 17 published files matched their local source hashes. README.md,
SOURCES.md, DESIGN.md, design-qa.md, design/approved.png and .git/config
were inaccessible. Nginx syntax, JavaScript syntax and systemd unit validation
passed. Certbot dry-run renewal succeeded for both hostnames. The DDNS result was independently read back from the Cloudflare API.

Official API: https://developers.cloudflare.com/api/resources/dns/subresources/records/
DDNS: https://developers.cloudflare.com/dns/manage-dns-records/how-to/managing-dynamic-ip-addresses/
