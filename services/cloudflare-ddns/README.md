# NUC Cloudflare DNS

Cloudflare is authoritative for `beachlab.org`, `hexxan.com` and `orbita.you`.
The Free zones use `jakub.ns.cloudflare.com` and `keira.ns.cloudflare.com`.
The migration retained all 48 records (34 + 7 + 7) as DNS-only, with the
original values and MX priorities. TTL is 1800 seconds. Beach Lab mail routes
to iCloud and Hexxan to Google. Orbita's five iCloud mail records were later
removed at Fran's request; its zone now contains the two web records for the
redirect to `orbita.arroyo.ing`.

The NUC runs `cloudflare-nuc-ddns.timer` every 150 seconds. It updates only
`beachlab.org`, `hs.beachlab.org`, `hexxan.com` and `orbita.you` to the public
IPv4 returned by ipify. `liderflorapi.beachlab.org` remains a fixed A record.
The existing `cloudflare-arroyo-ddns.timer` continues to manage Arroyo separately.

## Registrations

The Cloudflare Registrar API confirmed both transfers completed on 2026-10-23:

| Domain | Registrar | Expiry |
| --- | --- | --- |
| beachlab.org | Cloudflare | 2027-12-28 |
| hexxan.com | Cloudflare | 2027-11-26 |
| orbita.you | Namecheap | 2027-03-04 |

Both transferred domains are active, transfer-locked and use contact redaction.
Each retained its remaining term and gained one year. Automatic renewal remains
off, matching the prior setting. Orbita remains locked at Namecheap because
Cloudflare Registrar does not support `.you`.
The site now uses [orbita.arroyo.ing](../orbita/README.md); the old domain
redirects there and its automatic renewal is off.

## Installed configuration

- `/usr/local/lib/cloudflare-ddns/ddns.py`: this updater.
- `/etc/cloudflare-nuc-ddns.json`: `records.json`, containing exact zone and record IDs.
- `/etc/cloudflare-arroyo.env`: existing root-only Cloudflare token; never commit it.
- `/etc/systemd/system/cloudflare-nuc-ddns.{service,timer}`: installed units.

The updater validates every record's identity and DNS-only state before any
writes, changes only `content`, and verifies the address and preserved fields
afterward. An unchanged address causes no DNS write. Failed requests leave the
next timer run to retry. Check service failures and recent runs with:

```sh
sudo systemctl status cloudflare-nuc-ddns.timer
sudo journalctl -u cloudflare-nuc-ddns.service -n 30 --no-pager
sudo systemctl start cloudflare-nuc-ddns.service
```

## Namecheap transition

The parent registries switched delegation on 2026-10-23. The longest observed
parent NS TTL was 172800 seconds. The old Namecheap updater remains in place
alongside Cloudflare during that cache window, including the previously inactive
Orbita block. The unrelated `susabogados.es` configuration remains with ddclient.

`cloudflare-namecheap-retirement.timer` runs once on **2026-10-25 at 18:30 UTC**,
over 48 hours after delegation changed. Its service first verifies all Cloudflare
zones are active, runs the new updater successfully and checks that both old
configuration files have their recorded SHA-256 hashes. It then removes only the
three migrated domain sections and restarts ddclient. Changed configurations
stop the operation for review. A restart failure restores both original files.

The root-only retirement manifest is `/etc/cloudflare-namecheap-retirement.json`.
Original backups are under `/var/backups/cloudflare-migration-20261023/`, and the
retirement operation takes another backup in its `retirement/` subdirectory.
Completion creates `/var/lib/cloudflare-namecheap-retired`. Check the result with:

```sh
sudo systemctl status cloudflare-namecheap-retirement.service
sudo journalctl -u cloudflare-namecheap-retirement.service --no-pager
sudo test -f /var/lib/cloudflare-namecheap-retired
```

If configuration changed intentionally, review and update the manifest hashes
before manually starting the retirement service. Do not restore old nameservers
without reconciling current DNS records at the old provider first. NUC SSH access
through Tailscale is independent of this public DNS delegation.

> **Open question.** This page schedules the Namecheap retirement and says how
> to check `/var/lib/cloudflare-namecheap-retired`. It does not record whether
> that file was created.

## Validation and provenance

On 2026-10-23 both Cloudflare authoritative nameservers returned every imported
record with the expected name, type, value and priority. No real AAAA records
existed at the original authority; resolver-generated NAT64 answers were excluded.
The Cloudflare API confirmed all three zones active. Parent-registry queries
confirmed the new delegation. The new systemd updater completed successfully
and verified all four dynamic records at the NUC's public address.

Before and after checks matched for the three website homepages, Headscale health,
Authentik, Nextcloud status, openHAB and the authenticated Obsidian endpoint.
Seven unit tests cover address-only writes, idempotency, preflight failures,
failed readback, private IP rejection and preservation of unrelated DDNS blocks:

```sh
python3 -m unittest discover -s services/cloudflare-ddns -p 'test_*.py'
```

Private API snapshots, original record inventory and HTTP checks are in
`~/.config/cloudflare/migration-20261023/` on the Mac. Transfer authorization
material is private and must stay out of this repository and the vault.

Official references: [DNS record API](https://developers.cloudflare.com/api/resources/dns/subresources/records/),
[Registrar transfer process](https://developers.cloudflare.com/registrar/get-started/transfer-domain-to-cloudflare/).
Cloudflare's transfer eligibility API returned `extension_not_supported` for
`.you`: Orbita's registration stays at Namecheap while its DNS uses Cloudflare.
