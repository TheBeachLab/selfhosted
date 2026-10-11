# German iCloud Mail in Msgvault

Connected on 2026-10-11 to the NUC's Msgvault 0.21.0 installation.
The Apple Account used to generate the app password is
`daswerklab@gmail.com`; the IMAP mailbox is `daswerklab@icloud.com`.

The subsequent [reviewed cleanup and English topic filing](msgvault-mail-organization.md)
records the 325-message purge and separates Beach Lab LTD from German
administration and finance. The initial import figures below are the
pre-cleanup verification.

| Setting | Applied value |
| --- | --- |
| IMAP server | `imap.mail.me.com:993`, implicit TLS |
| Username / display name | `daswerklab@icloud.com` |
| Msgvault source ID | `1` |
| Source identifier | `imaps://daswerklab@icloud.com@imap.mail.me.com:993` |
| Automatic sync | Enabled, `*/15 * * * *` (every 15 minutes) |
| Folder selection | All selectable folders; no folder filters |
| Remote deletion | Disabled |

The native `add-imap` connection test succeeded before saving the source.
The scheduler was registered through the authenticated loopback
`POST /api/v1/accounts`; `/api/v1/sources/status` confirmed its enabled
schedule. IMAP settings follow [Apple's server settings](https://support.apple.com/en-ie/102525)
and [Msgvault 0.21.0 setup](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/setup.md).

Sync copies mail into the archive and keeps previously archived messages when
the provider copy disappears. It does not request remote deletion. New folders
are included automatically because no allowlist was stored. Both migration
trees and `Revision migracion 2026-10-11` are included. Msgvault's IMAP client
combines overlapping RFC 822 Message-ID copies and retains their folder
memberships; folder-location counts can therefore exceed archived-message
counts. This is not a separate raw export of each duplicate server copy.
Sources: [IMAP sync behavior](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/imap.md)
and [IMAP identity implementation](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/imap/client.go).

## Credentials and maintenance

The user generated an [Apple app-specific password](https://support.apple.com/es-es/102654)
named `msgvault NUC`. The approved Mac handoff copy is
`/Users/Papi/.config/msgvault/icloud.env`, mode 0600 in a 0700 directory.
Its value was delivered through SSH stdin, never a command argument or Git.
The NUC credential is `/var/lib/msgvault/tokens/imap_33d47f6937259839.json`,
mode 0600, owned by `msgvault`; the encrypted NAS backup includes it.

Run daemon-backed CLI operations from the service's accessible data directory:

```bash
ssh pink-sudo "sudo -n -u msgvault sh -c 'cd /var/lib/msgvault && exec /usr/local/bin/msgvault --home /var/lib/msgvault --no-log-file sync --source-id 1'"
```

An inherited `/home/pink` working directory caused `add-imap`'s daemon
subprocess to fail with `chdir /home/pink: permission denied` before its
connection test. Changing the invocation's directory fixed that failure;
no home-directory permissions were changed.

## Verification

Verified on 2026-10-11:

| Check | Observed result |
| --- | --- |
| Initial native full sync, run 1 | Completed; 3,131 examined, 2,974 added, 157 overlapping copies skipped, zero errors |
| Independent read-only IMAP inventory | All 3,131 `(mailbox, UIDVALIDITY, UID)` locations across 29 selectable folders matched the stored memberships; no missing or extra locations |
| Archived original content | 2,974 raw-MIME rows and 2,974 body rows; no message missing its raw MIME |
| Attachments | 868 parts: 358 standalone and 510 inline; 358,036,179 bytes |
| Automatic scheduler, run 2 | Completed after the initial sync; no new messages and zero errors |
| MCP | `get_stats` and cache SQL both returned 2,974 messages; the cache reported no pending additions |
| Public HTTPS | Unauthenticated access returned 302 to the existing Authentik passkey flow |

Private live proof: `/var/lib/msgvault-backup/icloud-connection-20261011.json`.

Encrypted snapshot **35144baa** was captured after the completed full import.
The backup service passed its Sunday full Restic data check. Restoring that
exact snapshot into a new private directory passed native database-page and
attachment SHA-256 verification and the full SQLite integrity check. The
restored archive contained the same 2,974 messages, 868 attachments and 3,131
IMAP memberships. Configuration, the iCloud app credential and MCP
configuration matched the live files without exposing their values. The
temporary restore directory was removed.

Private restore proof:
`/var/lib/msgvault-backup/icloud-populated-restore-20261011.json`.
See the [main runbook](msgvault.md#storage-and-encrypted-backups) for the
backup schedule, retention and isolated restore procedure; the native restore
checks follow [0.21.0's backup contract](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/backup.md).
