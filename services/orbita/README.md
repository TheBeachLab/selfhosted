# Orbita web domain

The public site is https://orbita.arroyo.ing/. Cloudflare has a DNS-only CNAME
from `orbita.arroyo.ing` to `arroyo.ing`, so the existing Arroyo IPv4 updater
also keeps Orbita reachable. No new dynamic-IP updater is needed for this alias.

`orbita.you` and `www.orbita.you` permanently redirect HTTP and HTTPS to the new
host with status 308, preserving the path, query string and request method.
Fran will let `orbita.you` expire on 2027-03-04 rather than renew it.
Namecheap domain and privacy auto-renew checkboxes were both confirmed off.

## NUC configuration

The two `.conf` files in this directory are installed under
`/etc/nginx/sites-available/`, with links in `sites-enabled/`.
The published content remains under `/var/www/orbita.you`; the new virtual host
preserves the original API, authentication, upload and static-image locations.
Nginx rewrites the old absolute web URLs in HTML, sitemaps and robots.txt.
It also substitutes the old public Turnstile site key in JavaScript responses.
Public contact is `fran@arroyo.ing`. The footer, About pages and structured
organization metadata attribute the project to **Arroyo Ingenieurbüro**, linking
to `https://arroyo.ing`, in English, German and Spanish.

`update_contact.py` applies these approved text replacements to published HTML
with a fresh backup directory. Run it after rebuilding an older frontend that
still contains the previous contact or attribution:

```sh
sudo python3 update_contact.py --backup /var/backups/orbita-contact-NEW-UNIQUE-ID
```

The 2026-10-23 publication changed 29 HTML pages, backed up under
`/var/backups/orbita-contact-20261023/`. Public HTTPS readback verified all 29.
GitHub repository identifiers and the `maps.beachlab.org` map service remain
valid technical dependencies.

Cloudflare no longer publishes the two iCloud MX records, SPF TXT, Apple
verification TXT or `sig1._domainkey` CNAME for `orbita.you`. Its A record and
`www` CNAME continue serving the redirect. The email address/domain removal
inside iCloud is being handled by Fran. Private before/after DNS snapshots and
page readbacks are in the Mac
`~/.config/cloudflare/orbita-contact-20261023/` directory.

The new certificate is `/etc/letsencrypt/live/orbita.arroyo.ing/`, issued using
`certbot certonly --webroot -w /var/www/letsencrypt -d orbita.arroyo.ing`.
The HTTP virtual host retains that ACME challenge location for renewal.
Keep the old certificate renewing while the old domain is registered, so HTTPS
visitors can receive the redirect. The scoped `50-orbita-nginx` deploy hook
reloads Nginx after renewal of the new certificate.

The existing `/opt/orbita/api/.env` uses:

```dotenv
BASE_URL=https://orbita.arroyo.ing
ALLOWED_ORIGINS=https://orbita.arroyo.ing,http://localhost:4321
```

Its `TURNSTILE_SECRET` matches the managed Orbita widget in the existing
Cloudflare account, restricted to `orbita.arroyo.ing`. Keep this secret outside
Git. The Nginx substitution contains only the public site key. Future frontend
builds should use this widget's public site key and the new canonical site URL;
then the compatibility substitutions can be removed after readback.

The GitHub OAuth application **Orbita**, owned by TheBeachLab, retains its
existing client ID and secret. Its homepage is `https://orbita.arroyo.ing`,
with the exact callback `https://orbita.arroyo.ing/auth/oauth/github/callback`.
Wildcard URI matching is off. The existing backend's cookie remains Secure,
HttpOnly and SameSite=Lax and is issued on the new host.

Original Nginx and private environment backups are in
`/var/backups/orbita-domain-20261023/` (root-only).
After changes, run `sudo nginx -t`, restart `orbita-auth.service` if its environment
changed, reload Nginx and check both domains over public HTTPS.

## Verification

Live checks on 2026-10-23 confirmed a valid new-host HTTPS certificate, HTTP 200
on the English, German and Spanish pages, join, map, store, sitemaps and robots.txt.
Both old hostnames redirect HTTP and HTTPS directly to the new host, retaining
path and query parameters. The public authentication and PostgREST routes reach
the same backend. The OAuth initiation returns the new GitHub callback URL,
and GitHub settings confirmed it was saved. A browser OAuth login returned
to the new homepage with the existing The Beach Lab account signed in. Turnstile displayed Success on the
new join page. Invalid unauthenticated access remains HTTP 401.

Readback evidence: Mac `~/.config/cloudflare/orbita-redirect-verification.json`,
Cloudflare DNS API, saved GitHub application settings, and the live browser.
