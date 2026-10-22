# arroyo.ing NUC hosting

Prepared 2026-10-22 from the approved website in
/Users/Papi/Repositories/strategy/websites/arroyo (commit 9e93daa), located
through the chat "Crear web de Arroyo Bauingenieur".

Public files copied to /var/www/arroyo.ing: index.html, impressum.html,
datenschutz.html, styles.css, site.js and assets/. Internal documentation
and design references are excluded. Nginx config is staged in sites-available;
no enabled link exists. DDNS code and units are installed but not enabled.

Pending: the Cloudflare Domains Admin token can list the active zone but DNS
reads return 403. Owner was asked for Zone > DNS > Edit for arroyo.ing.
Credentials remain outside Git.

Completion procedure:
1. Read existing records; preserve unrelated records. Set apex A to NUC IPv4
   and www CNAME to arroyo.ing, DNS-only.
2. Replace preview-only hosting text in the source privacy/imprint pages
   with the actual public setup. This Nginx config disables visitor logs.
3. Enable site, nginx -t, reload; issue a Certbot Nginx certificate for apex
   and www, with HTTPS redirect. .ing clients require HTTPS.
4. Put CLOUDFLARE_API_TOKEN in /etc/cloudflare-arroyo.env, root-only 0600;
   run cloudflare-arroyo-ddns.service and enable its timer (150s).
5. Verify public DNS, trusted HTTPS, resource parity and DDNS readback.
   Update this document and the maintained Strategy note after activation.

The updater patches only the existing apex A content, preserves other record
properties, and reads back the result. It does not create records.

Official API: https://developers.cloudflare.com/api/resources/dns/subresources/records/
