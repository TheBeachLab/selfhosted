# Buchhaltung on the NUC

Requested 2026-10-12 for Q4 2026: electronic invoices, expenses, bank
reconciliation, two separate annual EÜR and combined monthly UStVA.
Address: https://buchhaltung.beachlab.org/. Source: `services/buchhaltung/`.

## Live deployment readback: 2026-10-12

Activated release `eaefe8135ac3` on the NUC; 32 packaged code/dist files matched
the release manifest. `buchhaltung.service` and Nginx were active. The process
listened only on `127.0.0.1:8098`; authenticated loopback health returned
`ok / 0.1.0`. External HTTPS requests to the UI, bootstrap API and downloads,
including a request with forged identity/proxy headers, all redirected to the
Authentik outpost without serving financial data. Internal requests with a
missing proxy credential, another username, or a foreign mutation Origin returned
403. Scoped Authentik provisioning/readback confirmed the existing passkey flow
and Fran's single-user binding; no shared-group access was added.

The certificate was issued for this host, expires 2027-01-10 and uses the existing
ACME webroot renewal. The NUC's Python 3.10 runtime passed all 13 isolated tests,
including real KoSIT validation, without a skipped test.

The issuer profile was initialized from current sevdesk metadata. Production
contained **0 records, 0 bank transactions, 0 payments and 0 documents**;
the history import remained scheduled for 20:00 Europe/Madrid. Fiscal confirmation
was false and ELSTER sending was false. The registration draft existed and was
not submitted. These are initialization facts, not a completed historical import.

The first encrypted NAS backup finished at 10:40:46 UTC. Its isolated restore
passed SQLite/audit checks and restored 0 financial records/documents, consistent
with the new empty ledger. The encrypted NAS bytes matched the independently
computed local hash. A populated one-record/one-document restore is separately
covered by the isolated test suite. Daily backup timer: 03:00 UTC plus delay.
The recovery key was saved in the Mac login Keychain without printing it.

Real human passkey login could not be tested because native Safari reported the
Mac locked. Do not infer successful Touch ID login from the internal proxy smoke.
Original runtime state is in `/opt/buchhaltung/current/release.json` and private
`/var/lib/buchhaltung/last-backup.json`; inspect current state before reusing these
dated observations. No tax returns, customer messages or real invoices were sent
during this deployment.

## Current capability and boundaries

This first release implements invoice drafts, contacts, fixed invoice numbering,
UBL XRechnung XML validated with the official KoSIT validator, a companion PDF,
receipts with originals, activity splits, professional deduction percentages,
CSV/CAMT bank imports and exact partial reconciliation. Payments can be reversed
without deleting their history. Issued and reviewed snapshots cannot be edited.

The EÜR calculation follows recorded cash payments and separates
`Ingenieur Freiberufler` from `Gewerbe Software`. It includes collected VAT,
paid input VAT, tax payments/refunds and manually configured straight-line asset
depreciation. UStVA combines the two activities and supports domestic 19/7/0%,
specified exempt turnover, EU service turnover and 19% reverse-charge service
purchases from the EU/other countries. German input VAT uses receipt date;
EU non-taxable service reporting uses performance date, including under Ist.
Domestic Soll advances are counted when paid and deducted at performance.

These are local calculations and review exports, **not submitted declarations**.
The monthly period and Ist/Soll method require the owner's verified fiscal
configuration. Foreign VAT is not automatically treated as German Vorsteuer.
Special transactions, discounts, unresolved conversions, credit notes and
imported assets without verified depreciation remain explicit review blockers.
Issued-invoice rectification and full AVEÜR/2026 ELSTER schema mapping require
further implementation. Do not replace sevdesk for filing before that validation.

**ELSTER sending is not active.** No ERiC library or certificate was found in the
locations inspected on the Mac and NUC on 2026-10-12. The official process requires
reviewed developer registration, SDK access and a Hersteller-ID; authenticated
filing also requires the taxpayer certificate. The app shows the dependency,
prepares a registration draft from the issuer profile and refuses a send request.
No JSON download is labelled as ELSTER XML and no mocked success is returned.
The SDK, year-specific schemas, native integration and test transmissions must
be completed once access is available. Official source:
https://www.elster.de/elsterweb/infoseite/entwickler (read 2026-10-12).
Registration: https://www.elster.de/elsterweb/registrierung-entwickler/form.

## Fiscal source references

- Separate EÜR for each business: ELSTER's official EÜR instructions,
  https://www.elster.de/elsterweb/helpGlobal?themaGlobal=help_euer_ufa_77_2025,
  opening instruction on separate businesses, read 2026-10-12. This is evidence
  for the separation, not proof of availability of the 2026 filing schema.
- The entrepreneur's enterprise includes all their commercial/professional
  activity: §2 UStG, https://www.gesetze-im-internet.de/ustg_1980/__2.html.
- Field mapping: official BMF USt 1 A / USt 1 E 2026, dated 2025-12-29,
  https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Umsatzsteuer/2025-12-29-vordruckmuster-USt-voranmeldung-2026.pdf?__blob=publicationFile&v=5.
  Downloaded 2026-10-12, SHA-256
  `82e7d63a0faec542bb184acb438eaf4ce90a2d7db067bb47f92ae13b4b17613d`.
  Form lines 13/14/15: 81/86/**87**; lines 30/32: 46/47 and 84/85;
  lines 34–36: 60/21/45; lines 38/41: 66/67. Field 98 is **not** domestic 0% turnover.
  Explanatory notes to lines 35/36 govern the EU performance-date rule.
- Annual cash timing needs final review, including regularly recurring payments
  near year-end: §11 EStG, https://www.gesetze-im-internet.de/estg/__11.html.
  No automatic ten-day exception is assumed. The annual close requires a note
  and a fingerprint of reviewed data; later changes invalidate that close.
- Change traceability: §146 AO,
  https://www.gesetze-im-internet.de/ao_1977/__146.html. Audit hashes and SQL
  triggers provide technical evidence; they are not a GoBD certification.

## Access and storage

FastAPI, React/Vite and SQLite; listener `127.0.0.1:8098`. Nginx protects **all**
UI/API/download paths through the existing `beachlab-passkey` Authentik flow.
The scoped application binding is for **fran only**, without a group binding or
password fallback. The backend additionally requires a private proxy credential
and the verified username. Browser mutations require the exact application Origin.
The proxy replaces incoming authentication headers. Source:
https://docs.goauthentik.io/add-secure-apps/providers/proxy/server_nginx/.

| Path | Contents |
| --- | --- |
| `/opt/buchhaltung/releases/<revision>/` | Immutable release code and compiled frontend |
| `/opt/buchhaltung/current` | Active release symlink |
| `/opt/buchhaltung/venv/` | Python runtime, pinned requirements |
| `/opt/buchhaltung/vendor/xrechnung/` | Pinned official KoSIT validator/configuration |
| `/etc/buchhaltung/private.env` | Root:buchhaltung 0640; keys outside Git/logs/argv |
| `/var/lib/buchhaltung/` | 0700, service user; SQLite, originals, import/audit state |
| `/mnt/nas-downloads/backups/buchhaltung-encrypted/` | Dedicated encrypted backups, no key |

Monetary values are integer cents. Originals are AES-256-GCM encrypted and
SHA-256 verified. The SQLite ledger itself is private filesystem data; it is
encrypted inside the off-host backup. There is no browser financial cache,
analytics, third-party font, cloud OCR or AI-provider billing in this release.

## Install / update

Build/test in the conversation's isolated worktree. Integrate the tested source
into the protected target before packaging; do not deploy unrelated tree changes.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
python3 install-validator.py
cd frontend
npm ci
npm run build
```

Transfer source and `frontend/dist/` into `/opt/buchhaltung/releases/<revision>`.
Run `install-runtime.py --release <that-directory>` as root. Configure only this
app using `configure-authentik.py`, initially without `--apply` to inspect the
scoped plan; then apply the owner-only binding. Never rerun global Authentik setup.
Obtain the domain's certificate with the existing ACME webroot. Install its own
vhost and proxy secret snippet; `nginx -t` must pass before reload.

The installation preserves the previous release symlink target. Roll back by
restoring `/opt/buchhaltung/current` to that release and restarting
`buchhaltung.service`; take a consistent backup before any schema change.
Rollback of code does not undo newly issued documents or booked cash entries.

KoSIT artifacts are checksum-pinned in `install-validator.py`:
https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/tag/v2026-08-31
and Maven `org.kosit:validator:1.6.3:standalone`. Generated test invoices are
validated against schema, EN16931 and XRechnung Schematron, not just parsed XML.

## Historical migration: 20:00 on 2026-10-12

A one-off Codex heartbeat on this chat is scheduled for **20:00 Europe/Madrid**,
automation `importar-sevdesk-2026-a-buchhaltung`. The importer refuses execution
before that time. `init-profile` reads only current issuer metadata and country
codes; it does not import the year's historical documents or transactions.

```bash
cd /opt/buchhaltung/current
sudo -u buchhaltung /opt/buchhaltung/venv/bin/python -m buchhaltung.cli \
  --env-file /etc/buchhaltung/private.env import-sevdesk --year 2026
sudo -u buchhaltung /opt/buchhaltung/venv/bin/python -m buchhaltung.cli \
  --env-file /etc/buchhaltung/private.env verify
sudo systemctl start buchhaltung-backup.service
```

The adapter permits only whitelisted **GET** endpoints with a meaningful
User-Agent; no sevdesk writes, status changes, emails, subscription changes or
tax submissions. Original identifiers, JSON versions, positions, payment logs,
PDF/XML and voucher document downloads are retained. Banking PIN/token fields
are omitted from account metadata. Invoice/voucher counts are filtered to 2026,
also including older source documents with a 2026 payment. Bank transactions
retain account, direction and original amount. Pagination duplicates/count drift
are errors. Booking-log sums must match source paidAmount before reconciliation.

Public API reference: https://api.sevdesk.de/ (read 2026-10-12).
Legacy GET `Document/{id}/download` and payment-log response shapes were observed
on the authenticated API that day; they are absent from the current OpenAPI file.
The receipt download's base64 content is used, not a document-image thumbnail.
Invoice getPdf uses `preventSendBy=true`; downloaded files and source snapshots
are evidence of what the provider returned, not independent proof of the exact
bytes present when an old invoice was originally sent.

Migration is locked and idempotent. A retry reuses original source IDs and file
hashes. A changed source snapshot is archived and reported, never silently
overwritten. Incomplete originals, ambiguous payment reversals or source drift
produce `needs_attention`/`failed`, never a false "complete". Fiscal classification
remains a separate review even after a technically complete copy.

Bank imports preserve same-day identical entries by multiplicity. Without stable
bank references, partial overlapping exports of identical rows cannot always be
distinguished. Check overlap with sevdesk before completing the bank review.
The user explicitly marks private movements, transfers and verified duplicates;
no guessed automatic classifications are made.
For a shared payment, classification applies to its unmatched remainder and
preserves the already reconciled business portion.

### Authorized corrections after migration

The sevdesk API rejects paid-voucher edits: its documented `resetToOpen` and
`resetToDraft` operations unlink payments, and only drafts may be updated.
Do not reset a source voucher implicitly when the user authorized only a read.
Before an explicitly authorized reset/rebooking, retain its raw object,
positions, originals, account/movement, signed amounts and booking dates.
Read back the complete reconstruction and compare those financial fields.
API source: https://api.sevdesk.de/, operations `updateVoucher`,
`voucherResetToOpen`, `voucherResetToDraft`, `voucherFactorySaveVoucher` and
`bookVoucher`, read and exercised against the user's authorized records 2026-10-12.

`import-sevdesk --accept-cost-centre VOUCHER_ID:CENTRE_ID` accepts only that
explicit centre and only when all other source fields/positions and the cash
payment amounts, dates and bank references match the accepted snapshot.
Provider-generated creation/update timestamps and new payment-log IDs may differ.
New log IDs become append-only aliases of the original local payment; payment
IDs, amounts and original references are retained, without a second cash entry.
Other source changes remain blocked across retries, including when their rejected
raw revision was already archived. Keep this importer version when resuming a
source rebooking: earlier versions do not interpret payment aliases.

For an independently changed source tax rule/comment,
`--accept-source-metadata VOUCHER_ID:SHA256` requires the exact inspected raw-bundle
hash. Only `taxRule`, position `comment`, generated timestamps and financially
identical replacement payment-log IDs may differ. It preserves the accepted
amounts, document dates, booking accounts, originals, centre and cash entries.
It copies the source rule identifier/comment and marks the local tax code
unclassified; copying source metadata is not verification of its legal treatment.

`classify-imported --record-id ID --classification private|tax_refund --reason TEXT`
records an explicit owner decision with before/after audit snapshots. A private
receipt stays visible with its original and payment links, contributes zero to
EÜR/UStVA, and does not mark an entire shared bank transaction as private.
The UI labels it private and excludes it from individual business filters.
Source for personal living expenses excluded from deduction: §12 EStG,
https://www.gesetze-im-internet.de/estg/__12.html, read 2026-10-12.

A confirmed VAT refund is kept as `tax_refund`, with no additional invoice VAT.
If its activity is unresolved, it stays pending and cannot be closed or silently
assigned to the first business. Official ELSTER EÜR 2025 help identifies VAT
refunds separately in line 18 and requires a separate EÜR for each business:
https://www.elster.de/elsterweb/helpGlobal?themaGlobal=help_euer_ufa_77_2025,
read 2026-10-12. This confirms the nature/separation, not a 2026 schema field or
a method for splitting a combined refund. No percentage allocation is inferred.

Synthetic tests cover unchanged cash IDs after a source rebooking, retry
idempotency, persistent rejection of financial drift, private portions of shared
payments and a VAT refund blocked until its activity allocation is verified.

## Backup / recovery

The dedicated job invokes SQLite capture/restore as **buchhaltung**, to avoid
root-owned WAL files. Root transfers only the resulting encrypted archive onto
the NAS. On 2026-10-12 the NFS server returned `EINVAL` for chown to the new
service UID; the NAS directory keeps its existing NFS ownership mapping. No
global mount/identity or other backup configuration is changed.
It verifies the existing NFS mount source before writing; it refuses fallback
to an unmounted local directory. The daily timer is 03:00 UTC with a short delay.

Each backup takes a consistent SQLite online snapshot and its referenced
encrypted originals, streams an AES-GCM encrypted archive, then decrypts and
actually restores it into a temporary private directory. SQLite integrity,
every document hash/decryption and the audit chain are verified on the restored
copy. `last-backup.json` records the result. No unrelated NAS directory or backup
is pruned. The encryption recovery key is kept separately in the Mac login
Keychain under service `buchhaltung.beachlab.org.document-encryption`, account
`fran`; `store-recovery-key.swift` never overwrites a different existing key.
The NAS copy is independently hashed before removing this job's exact local
encrypted staging duplicate. Plaintext financial files and keys are not staged
on the NAS by this job.

To restore, recover the key into a restricted environment through a private
operator channel, then use CLI `restore --archive <file> --destination <new-dir>`.
It refuses an existing directory and the active data path. Validate the restored
copy before a separate authorized cutover. Never log or paste encryption keys.

## Verification

```bash
PYTHONPATH=services/buchhaltung .venv/bin/python -m unittest discover \
  -s services/buchhaltung/tests -v
```

The isolated suite tests owner/secret/Origin enforcement, encrypted originals,
tamper detection, audit immutability, partial bank matches and reversals,
idempotent import, the 20:00 guard, cash-basis separate EÜR including VAT cash,
Ist/Soll including advances, EU reverse charge, exact cent rounding across many
payments, official XRechnung validation, fixed numbering and immutable issuance,
separate annual review jobs, refused ELSTER submission, and an actual isolated
encrypted-backup restore. Tests never use production data or sevdesk credentials.
The QA server binds only loopback and uses a disposable empty database. It is
not deployed and does not supply a production authentication bypass.
For protected-target validation, set `BUCHHALTUNG_TEST_VALIDATOR` to the verified
dependency directory in the isolated worktree (or `/opt/buchhaltung/vendor/xrechnung`
on the NUC). The required invoice-validation test fails when it is unavailable.

Design references/specification are in `services/buchhaltung/design/`.
Browser evidence is outside Git in the operator's private Codex output directory.
Production deployment and scheduled historical import are separate states; the
runtime/import records must be checked before reporting either as completed.
