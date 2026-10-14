# Mebuko launch page on the NUC

Source: `services/mebuko/`. Public target: `https://mebuko.de/`, with `www`
redirecting to the apex. A separate service listens on `127.0.0.1:8099`.
It has no dependency on the private Buchhaltung database, Authentik application,
ERiC runtime, certificates or tax-transmission controls. Those remain separate.

The page announces **1 January 2027 as the planned launch**, offers DE/ES/EN/FR/IT/PT,
shows a labelled example interface on three devices, and collects consent for
**one launch email**. Email confirmation, expiry, withdrawal and rate limits are
implemented. No launch message is sent automatically by installing this service.

## Domain and DNS

On 14 October 2026, the authenticated Hetzner Cloud API created the primary
zone `mebuko.de`, ID `1644108`, in the existing project. Its assigned servers are
`hydrogen.ns.hetzner.com`, `oxygen.ns.hetzner.com`, `helium.ns.hetzner.de`.
The apex A record uses the NUC's verified public IPv4 (60s TTL); `www` is a
CNAME to `mebuko.de.`. Domain registration is separate from creating a zone.
Do not infer ownership from a successful DNS API request.

Registration was subsequently completed in Robot on 2026-10-14. DENIC's live
RDAP endpoint returned HTTP 200, `active`, and the three assigned nameservers:
https://rdap.denic.de/domain/mebuko.de . Public recursive resolvers also returned
the verified NUC IPv4. This is a dated registration/delegation observation.

Contact verification follows Hetzner's process: new .de email addresses must
follow the verification link within 14 days; already verified addresses may be
verified automatically. The official sender/link domain is
`your-emailverification.de`. Check for a pending verification after changing a
registrar contact; do not infer its state from a DNS record or order receipt.
Source, checked 2026-10-14:
https://docs.hetzner.com/robot/domain-registration-robot/contact-information-verification/

The registrar's Robot form quoted €3.90/year plus €2 setup, including 19% VAT.
This is a dated quote; verify the checkout before any future purchase. Hetzner's
DNS API manages records; its documented registration API is a PGP-signed email
interface. No new signing key or alternative registrar is configured here.
Sources, checked 2026-10-14:

- https://docs.hetzner.com/robot/domain-registration-robot/faq/
- https://docs.hetzner.com/robot/domain-registration-robot/getting-started/
- https://docs.hetzner.com/robot/domain-registration-robot/email-interface/
- https://www.hetzner.com/dns/
- https://docs.hetzner.cloud/reference/cloud

`mebuko-ddns.timer` runs the scoped updater every five minutes using the existing
root-only `/etc/hetzner-ddns.env`. It changes only Mebuko's apex A record with
`set_records` and verifies the result. It neither changes the other zones nor
passes that credential to the public web service. No unverified AAAA record.

## Runtime and private state

| Path | Use |
| --- | --- |
| `/opt/mebuko/releases/<revision>/` | Immutable integrated code and assets |
| `/opt/mebuko/current` | Active release symlink |
| `/etc/mebuko/private.env` | root:mebuko 0640, private token/SMTP configuration |
| `/var/lib/mebuko/subscribers.sqlite3` | mebuko 0600, directory 0700 |
| `/var/lib/mebuko-backup/` | Root-only consistent staging and restore proofs |
| `/mnt/nas-downloads/backups/mebuko-encrypted/` | Dedicated encrypted repository |
| `/root/.config/mebuko-backup/restic-password` | Root-only backup key |

The database stores email, language, request/confirmation timestamps, consent
version and random token nonce. URLs use purpose-bound HMAC signatures. A GET
does not confirm or cancel a signup: an explicit button POST is required, so
link scanners cannot subscribe people. Unconfirmed rows expire after 48h and
are removed by daily pruning; confirmed rows are removed after the one launch
message, with an enforced final expiry at 2027-04-01 UTC. A future launch send
must be explicitly authorized and followed by list deletion.

Raw IPs and message bodies are not stored in application logs. Transient keyed
fingerprints limit mail to one/address/hour, three/IP/hour and 100 globally/day;
they are pruned after 24h plus the daily interval. The scoped Nginx access log
contains IP, timestamp, method, URI path and status only; logrotate retains at
most seven days. It excludes query strings, tokens, emails, referrers and agents.

SMTP uses the existing iCloud Mail account with verified STARTTLS on
`smtp.mail.me.com:587`, sender/reply-to `fran@daswerklab.de`. Credentials stay in
the private environment, never argv, Git or frontend. Apple official settings
explicitly allow the same app-specific password as the incoming client:
https://support.apple.com/en-gb/102525 (checked 2026-10-14). SMTP failures return
a failure state and do not silently record a new pending signup.

## Legal pages and evidence

The public owner/contact/address and VAT-ID were checked against the current
owner profile and the existing professional footer on 2026-10-14. No private
Steuernummer, bank details, personal tax ID or certificate is published.

`impressum.html` and `datenschutz.html` provide German and Spanish information.
The pages describe the actual processing, consent, recipients, third-country
mail processing, retention, withdrawal, rights and supervisory authority.
No tracking, external fonts or client storage; the language stays in the URL.
They do not claim independent legal certification.

Primary sources checked 2026-10-14:

- Provider identity: https://www.gesetze-im-internet.de/ddg/__5.html
- Email consent: https://www.gesetze-im-internet.de/uwg_2004/__7.html
- GDPR Articles 6, 7, 13, 15–22, 32: https://eur-lex.europa.eu/eli/reg/2016/679/oj/spa
- End-device storage: https://www.gesetze-im-internet.de/ttdsg/__25.html
- Apple recipient/transfer information (EEA controller in Ireland; standard
  contractual clauses): https://www.apple.com/legal/privacy/de-ww/
- Supervisory contact: https://www.lda.bayern.de/de/kontakt.html

## Verify and deploy

From an isolated conversation worktree:

```bash
python3 -m unittest discover -s services/mebuko/tests -v
python3 -m compileall -q services/mebuko
node --check services/mebuko/public/app.js
```

Integrate into `master` and rerun these checks before packaging the committed
service directory. Verify a scoped pre-deployment backup and restoration.
The 2026-10-14 encrypted Nginx pre-deployment snapshot `100207a0` passed matching
restored SHA-256 checks for nginx.conf and the existing public vhost.

Transfer to a new release directory, run `install-runtime.py --release ...`,
and supply the private environment through SSH stdin. Required configuration:
`MEBUKO_TOKEN_SECRET` (at least 48 chars, random), `MEBUKO_SMTP_USER`,
`MEBUKO_SMTP_PASSWORD`; canonical origin defaults to HTTPS mebuko.de.
Initialize the database as the service user, prepare the dedicated encrypted
Restic repository/key, run `backup.py --verify-restore`, then start the service.
Do not expose a signup form with a fake mail-success response.

Deployment readback, checked directly on 2026-10-14:

- Integrated release `f08ce0f35011` is linked at `/opt/mebuko/current`;
  all 28 packaged files matched the integrated Git archive before activation.
- `mebuko.service` is running, bound only to `127.0.0.1:8099`;
  `/_health` returned `{"ok": true}`. It and the DDNS, pruning and backup timers
  are enabled. Each scoped maintenance service completed with exit status 0.
- Public HTTPS returned the exact integrated HTML, JS, CSS, device image and
  legal pages, with the expected security headers and no Set-Cookie header.
  `www` redirects to the apex. Private source/env/database paths returned 404;
  a cross-origin signup POST returned 403 without sending mail.
- The certificate covers both names and expires on 2027-01-12. The existing
  `certbot.timer` is active/enabled; the installed Mebuko deploy hook tests and
  reloads Nginx only for this certificate lineage. Its live invocation passed.
- An owner-controlled public browser test received the Spanish confirmation
  email from `fran@daswerklab.de`. Opening the link left one pending row;
  pressing confirmation created one confirmed row; the withdrawal button
  removed it. The subscriber database is now empty. Temporary test links were
  removed. No launch notification was sent.
- The private environment and database have the permissions listed above.
  Dedicated encrypted snapshot `a42fef04` passed restoration and integrity/hash
  checks. A restricted recovery-key copy is under
  `/mnt/nas-downloads/backups/mebuko-recovery/` (0700; key 0600).
- The scoped updater read the existing apex A record successfully and verified
  the NUC IPv4 without changing it. Hetzner expects the literal `@` in the
  RRSet endpoint; percent-encoding it as `%40` returned 404 in the live API.

This dated readback is not a replacement for checking the current host state.

Only after registration and delegation are verified, install this host's HTTP
ACME vhost and obtain its certificate using the existing `/var/www/letsencrypt`
webroot. Install the scoped HTTPS vhost, run `nginx -t`, reload, and check public
HTTPS, redirects, assets, legal pages, security headers and the actual opt-in /
confirmation / withdrawal loop using only an owner-controlled test address.
Enable `mebuko`, DDNS, daily pruning and daily encrypted backups.

Every dedicated backup uses SQLite's consistent backup API, restores the exact
snapshot into a root-only temporary directory, checks DB integrity/hash and the
private configuration, then applies a 30-day retention to **this repository**.
The host's general backup does not include these new `/var/lib/mebuko*` paths;
its longer-lived `/etc` copies contain configuration, not the subscriber list.

Rollback: remove only this new vhost link and reload after a passing Nginx check;
stop only `mebuko.service`. For later upgrades, restore the prior `current`
symlink and restart that service. Preserve private subscriber state and keys.
Never disable the other vhosts, authentication services or backup schedules.

Confirmed-only export is a local administrative command, never a public route:

```bash
sudo -u mebuko python3 /opt/mebuko/current/server.py export \
  --env-file /etc/mebuko/private.env --output /var/lib/mebuko/launch-export.csv
```

It creates a new file at mode 0600 and does not send mail. Delete the reviewed
export after its authorized use; do not commit it or upload it to the website.
