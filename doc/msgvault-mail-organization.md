# German iCloud mail cleanup and topics

On 2026-10-11 the user authorized deleting a reviewed set of 322 messages
from the German iCloud mailbox and Msgvault, organizing the rest in English,
keeping Beach Lab LTD separate from German business correspondence, and
investigating phishing filtering. The user subsequently required protection
against all phishing or no new rule, rejecting sender-address filters.

This applies to source 1, `daswerklab@icloud.com`. It does not change the Spanish
mailbox or the ownership of the custom domain. The folder organization is a
one-time filing of existing mail; it is not an automatic classifier for new mail.

## Inbox and account identity

The organized mailbox is **`daswerklab@icloud.com`**, source 1, connected to
Apple's `imap.mail.me.com:993`. The Apple sign-in identifier is
`daswerklab@gmail.com`, which Apple Mail also uses as this Internet Account's
display name. The Gmail mailbox at that address requires its own connection;
an Apple login does not authorize Gmail access. Check the source type and
server in `GET /api/v1/sources/status`, rather than inferring the provider from
the account name in Mail.

Apple Mail's `All Inboxes` combines the inboxes of several accounts. Select
the child account `daswerklab@gmail.com` to inspect this iCloud inbox alone.
The preserved Spanish inbox and the other accounts are outside this filing.

On 2026-10-11 at 15:22 Europe/Madrid, the requested follow-up filing moved the
one pending club newsletter to `Newsletters`. Its destination MIME SHA-256,
size, Message-ID, internal date and flags matched the source before the exact
source UID was expunged. The live iCloud inbox then contained zero messages.
Native sync run 23 completed with one membership update, zero new messages
and zero errors; the archive retained 2,651 messages and 870 attachment parts.
The active semantic generation still covered all 2,651 messages.

Saved View **`iCloud Germany / Inbox`**, ID 19, uses `label:INBOX` and an
explicit source-1 filter. Its owner API and registered MCP executions both
returned zero entries after reconciliation. The 18 topic views remain scoped
to the same iCloud source. The new Inbox view does not install future-mail
classification or a phishing rule.

Private evidence: `/var/lib/msgvault-backup/gmail-connection-20261011/`,
including `icloud-inbox-before.json`, `icloud-inbox-move.json` and
`icloud-after.json`. These are live IMAP and native daemon readbacks, rather
than evidence derived from this document.
The native backup service subsequently completed successfully and verified
encrypted NAS snapshot **4efb6189** with the updated folders and Inbox view.

## Completed deletion

| Selection | Archived messages |
| --- | ---: |
| LinkedIn automatic job alerts | 154 |
| Old DLR and EPO job alerts | 23 |
| Vueling marketing | 52 |
| Old Nebenan digests and events | 39 |
| Memrise promotions | 18 |
| Headway promotions | 8 |
| Too Good To Go promotions | 14 |
| Superseded sevdesk discount offers | 8 |
| Migration verification tests | 6 |
| **Reviewed cleanup set** | **322** |
| Three phishing messages identified by the user | 3 |
| **Total purged** | **325** |

The selected messages had no attachment parts. Bills, reservations, direct
recruiter correspondence, insurance documents, current job alerts and the
latest sevdesk offer were excluded from the reviewed selection.

The live baseline contained 2,974 archived messages and 3,131 server locations.
Exactly 325 archived IDs corresponded to 337 physical iCloud locations.
Before removing anything, every selected location was checked against its
mailbox UIDVALIDITY and RFC 822 Message-ID. The provider originals were captured
privately, including 328 distinct MIME variants, and encrypted in the NAS Restic
repository. A dumped backup sample matched its captured SHA-256.

The iCloud connection advertises UIDPLUS **after authentication**. Deletion
used only `UID STORE` and `UID EXPUNGE` for the reviewed UID sets; it did not
empty Trash or expunge unrelated flagged messages. The complete native sync
then reconciled all memberships. A read-only SQLite guard checked that the
entire source-deleted ID set equalled the 325 authorized IDs before invoking
daemon-backed `msgvault gc --yes`. GC backed up SQLite automatically, purged
325 rows, compacted the archive and removed zero attachment blobs.

After GC, the retained archive contained **2,649 messages and 868 attachment
parts**. No unapproved archived ID was removed. The full analytics cache was
rebuilt, then native embedding generation 3 processed all 2,649 messages with
zero failures using the existing 2,000-character chunk configuration.

Sources: the private NUC receipts below and the pinned
[IMAP membership reconciliation](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/store/imap_memberships.go),
[UIDPLUS deletion contract](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/deletion.md#reviewing-and-executing)
and [GC implementation](https://github.com/kenn-io/msgvault/blob/v0.21.0/cmd/msgvault/cmd/gc.go).
Native query/ID staging does not support IMAP in this release; the reviewed
owner-operated IMAP batch therefore used the standard protocol directly.
Persistent remote deletion remains disabled and MCP remains read-only.

## Topic profile

The English names and descriptions are in
[mail-topics.json](../services/msgvault/mail-topics.json).

| Folder / Saved View | Original messages filed |
| --- | ---: |
| Beach Lab LTD/Administration | 31 |
| Beach Lab LTD/Apps & Development | 97 |
| Beach Lab LTD/Finance | 19 |
| Germany/Administration & Engineering | 113 |
| Germany/Finance & Taxes | 131 |
| Projects/Apps & Development | 81 |
| Projects/Cyfract & MicroBubbles | 173 |
| Projects/Liderflor & Fronda | 39 |
| Fab Academy, MIT & Panopticom | 295 |
| Employment | 109 |
| Finance & Receipts | 216 |
| Travel & Purchases | 269 |
| Health & Insurance | 119 |
| Housing & Local Life | 88 |
| Services & Security | 429 |
| Personal | 103 |
| Newsletters | 328 |
| Review | 9 |
| **Total** | **2,649** |

New mail arrived during the operation and was preserved in Inbox. The final
archive contained 2,651 messages and 870 attachment parts: the original 2,649
messages and 868 parts, plus two new messages with two parts. Current account
totals therefore exceed this fixed historical filing. The independent iCloud
inventory matched all 2,794 destination COPYUID receipts and found none of the
original UIDs in their old folders. Private proof: `remote-organization-proof.json`.

Topic assignment uses sender, subject, counterpart and relevant message
content. Beach Lab LTD assignment requires explicit company context or a known
UK company-administration counterpart. General receipts without a clear company
assignment go to `Finance & Receipts`. This filing does not determine legal
jurisdiction or tax deductibility.

Each server copy is moved with an IMAP COPYUID receipt. Its destination
Message-ID, RFC 822 size, internal date and flags are compared with the source
before exact source-UID expunge. Overlapping historical copies and MIME variants
are preserved; they are not treated as more unwanted messages. The retained
2,649 logical messages have 2,794 physical server locations.

Shared Msgvault Saved Views use exact folder-label queries, source 1 and active
mail. Definitions follow the pinned
[Saved View contract](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/store/saved_view_state.go)
and [Explore execution](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/api/saved_views_run.go).
Codex and Watson can read the same views through the existing read-only MCP
connection.

Final readback verified all 2,649 original messages against the assigned
folder labels and all 18 Saved View result counts against the profile above.
The registered Codex MCP listed all 18 views and ran the separate Beach Lab LTD
finance and Germany finance views, returning 19 and 131 messages respectively.
MCP cache SQL returned zero of the 325 purged IDs, with no pending additions.
The active vector generation covered 2,651 of 2,651 eligible messages (100%).

The native `embeddings prune` command removed 644 orphan message-generation
records from the previous generations. A read-only guard first checked that
the orphan message-ID set was exactly the 325 approved deleted IDs; the final
orphan set was empty. Source:
[native orphan pruning](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/vector/sqlitevec/backend.go).

After copying and checking the destinations, 23 empty migration folders were
removed without deleting any further messages. The final native full sync
checked 27 folders, skipped all as unchanged, and completed successfully.
The automatic 15-minute schedule, existing credentials and read-only MCP
configuration remain active. Live proof: `final-live-proof.json`.

## Phishing rule decision

No custom phishing rule remains. Two temporary sender-address rules were
removed after the user rejected that approach; the third was never created.
The German account's Rules list was verified empty in Safari's `DE iCloud`
profile. The three previously reviewed phishing messages remain purged.

The observed iCloud rule editor offers sender, recipient, Cc, subject and
List-ID conditions, with a single matching condition per rule. It does not
offer a phishing-classification condition. No comprehensive protection was
claimed and no background deletion service or broader filter was installed.
Source: the live German iCloud Mail rule editor and
[Apple's filtering-rule guide](https://support.apple.com/guide/icloud/set-up-filtering-rules-mm6b1a3f8a/icloud).
Private readback: `icloud-rules-rollback.json` below.

## Private recovery evidence

The exact IDs, UID inventories, message hashes and operation journals are
owner-only files under:

`/var/lib/msgvault-backup/mail-cleanup-20261011/`

Important files are `approval.json`, `baseline.json`, `delete-preflight.json`,
`pre-delete-encrypted-proof.json`, `purge-proof.json`, `organization-final.json`,
`organization-journal.json` and `saved-views.json`. Provider MIME captures are in
`deleted-provider-originals/`; they are recovery evidence, not part of the active
search archive. These files must not be copied into Git.

Pre-cleanup native encrypted snapshot: **4524fa3b**.
Encrypted capture of the exact provider originals and initial plan: **dd21e951**.
Post-cleanup native encrypted snapshot: **64d080e5**. Its isolated native
restore passed database-page and attachment verification plus SQLite integrity.
The restored state contained 2,651 messages and raw-MIME rows, 870 attachment
parts, 2,796 IMAP memberships and 18 Saved Views. Configuration and the IMAP
credential matched the live file hashes. The temporary restore was removed.
Private proof: `post-cleanup-restore-proof.json`.
The native GC database backup is
`/var/lib/msgvault/msgvault.db.gc-backup-20261011-114000`.
Existing encrypted backups retain older mail under their existing retention;
purging the live archive does not erase those recovery copies.

Restore only into a new private directory and compare the recorded hashes
before re-importing any message. See the
[backup runbook](msgvault.md#storage-and-encrypted-backups). Never restore a
database over the running service.

