# Removing redundant offline mail exports

The owner requested cleanup of iCloud exports already retained in Msgvault
on 2026-10-12. The external volume named `1TB` is mounted at `/Volumes/1TB`
(volume UUID `597CDC85-E732-4169-B4B3-7BEFB37ABA78`); its current physical
capacity is 2 TB. It contains twelve old mbox exports under
`Downloads/iCloud-mail-migration-2026-08-02/` and eight standalone EML files.
The scattered EMLX cache copies were found in the disconnected migration
backup at `/Users/Papi/Documents/iCloud-mail-migration-2026-10-11/`, rather
than on this external volume. The owner explicitly approved cleanup of both
locations. Specialized invoice exports elsewhere in Documents/Downloads were
outside the Mac migration scope.

## External-volume result

The reviewed external-volume plan inspected **20 mail files / 2,537 message
copies**. It removed **2,134** verified copies representing **2,131** distinct
live archive IDs: two fully redundant mbox files were deleted and ten mixed
mbox files were compacted. The eight unrelated standalone EML files were
unmatched and preserved.

**403** unmatched messages remain, byte-for-byte unchanged. Reasons were:
309 identifiers absent from the live archive, 91 content/header/attachment
differences, and three malformed messages that could not be verified. Some
absence is expected after earlier owner-approved Msgvault purges; that does
not authorize removing those exports under this request's archive-presence
condition. No new mail was imported merely to make exports deletable.

The logical content reduction was **439,837,851 bytes** (about 440 MB).
This is not an assertion about immediately reclaimed APFS blocks, because
snapshots and clones can retain blocks. Verification checked every retained
file hash and every retained mbox byte-block hash/count, with **zero errors**.
The same 2,131 selected live MIME snapshots were SHA-256 checked immediately
before and after deletion. Private proof is `volume-plan.json`,
`volume-receipt.json`, `volume-result.json`, `volume-archive-preflight.json`
and `volume-archive-after.json` in the client/NUC receipt directories below.

The NUC preflight's successful encrypted snapshot was **`d40437bf`**, captured
at **00:26:57 Europe/Madrid on 2026-10-12** and completed at **00:28:26**.
This backup existed before the external-volume cleanup; no duplicate plaintext
mail export was created as a cleanup backup.

## Mac migration result

The approved migration plan inspected **2,948 files / 8,731 parsed message
copies**. It removed **7,209** verified copies: **2,241 EMLX files**, one EML
file and eight fully redundant mbox files were deleted; 27 mixed mbox files
were compacted. The message-file reduction was **1,078,550,524 bytes**.

**1,522** unmatched parsed copies and **two** unparsed EMLX cache files remain.
Of the parsed copies, 948 identifiers were absent from the active archive,
566 had content/header/attachment differences and eight had malformed MIME.
Every retained file and compacted mbox payload was hash checked after cleanup.
The same **2,511** selected active archive IDs were checked before and after,
with unchanged full-MIME SHA-256 hashes. Proof is `migration-plan.json`,
`migration-receipt.json`, `migration-result.json`,
`migration-unparsed-before.json`, `migration-archive-preflight.json` and
`migration-archive-after.json` in the private receipt directories.

Removed EMLX messages also had separate cache attachments in the sibling
`Data/.../Attachments/LOCAL_ID/PART/` folders. **344** files, totalling
**126,568,052 bytes**, matched the decoded attachment bytes of their specific
matched archive messages and were removed. **Five** different files were
preserved with unchanged hashes. The NUC checks confirmed the full-MIME hashes
and native attachment hash/size rows for **163** parent messages before and
after this additional cleanup. Proof is `migration-attachments-plan.json`,
`migration-attachments-receipt.json`, `migration-attachments-result.json` and
the matching `migration-attachments-archive-{preflight,after}.json` receipts.

## Combined result

Both locations lost **9,343 message copies** and **344 cache attachment
copies**, representing **1,644,956,427 bytes** of redundant content. All three
application receipts report **zero errors**. The two locations retain **1,925
unmatched parsed message copies**, two unparsed cache files and five unmatched
attachments associated with removed cache messages. These are occurrence
counts across exports, not counts of distinct emails.

Ten fully emptied export folders were removed after verifying they contained
no files or only an `Info.plist` with the sole key `MailboxName`. Another 525
empty cache directories were removed using `rmdir`; directories containing
remaining files or metadata were preserved. Proof is
`empty-directories-removed.json`, `empty-cache-directories-removed.json` and
`combined-result.json`. iCloud, Gmail, Msgvault's messages and the live Apple
Mail store were not modified by this cleanup.

## Verification and deletion contract

[mail-export-dedupe.py](../services/msgvault/mail-export-dedupe.py) uses native
SQLite data read-only. Its private index contains full raw-MIME SHA-256 hashes,
message identifiers and MIME-part hashes for active, retained messages.
Encryption/compression that cannot be decoded is excluded. The NUC's inspected
snapshots use zlib compression with encryption version 0. Both current accounts
remain separate sources; a match records its exact archive ID and source.

A removable message needs an exact whole-MIME SHA-256 match, or all of:

- The same RFC 822 Message-ID and correspondence headers, including recipients,
  subject, date, reply/reference headers and BCC when present.
- Equivalent complete MIME structure, filenames, content IDs and parameters.
  Text is normalized only for encoding, Unicode normalization, line endings
  and terminal transport separator newlines. Spaces and body content remain.
- Exact decoded byte hashes for attachments. Canonical comparison additionally
  requires those attachment hashes/sizes in Msgvault's attachment rows. If
  parsing or extracted attachment rows are incomplete, only an exact full-MIME
  byte match can authorize removal.

Apple `.partial.emlx` files can have zero-byte attachment placeholders. Those
are accepted only when all other content matches and the archive has the same
named/CID part with complete bytes and validated attachment rows. An empty or
truncated cache is never proof that an attachment is absent. An EMLX byte count
is checked before slicing off Apple's metadata trailer.

No sender/subject-only, approximate text or vector matches authorize deletion.
Messages already purged from Msgvault are not in the active index, even if an
older encrypted backup contains them; those local exports remain untouched.
Original Apple Mail's live `/Users/Papi/Library/Mail` data is excluded.

Plans are private and record each exact file's SHA-256, matched archive IDs,
and mbox message boundaries. Application requires `--yes`, the unchanged
index hash and each unchanged source-file hash. Symlink/redirected paths and
paths outside the approved roots are rejected. Mbox files are locked during
application. Mixed mbox containers retain
every unmatched byte block, with an fsynced temporary checked for the same
message count before atomic replacement. Stale `table_of_contents` sidecars
are removed after a successful change; import remaining mail using the
standard mbox format, which reconstructs offsets.

`scan-cache-attachments` derives an additional private plan from an applied
mail plan and its receipt. It visits only attachment folders associated with
already removed EMLX copies and requires exact byte hashes and sizes in that
specific archive message. It does not scan unrelated documents or attachments
belonging to retained messages. Apply it only after fresh active-archive and
native attachment-row checks, using the same unchanged-file/index guards;
then verify both retained local files and the NUC's full-MIME snapshots again.

Private inventory, plans and receipts are at
`/Users/Papi/.config/msgvault/export-cleanup-20261012/`; the NUC's MIME index
and live archive checks are at
`/var/lib/msgvault-backup/export-cleanup-20261012/`. Neither folder belongs in
Git. Indexing and cleanup do not change iCloud/Gmail or Msgvault's messages.

Source: inspected Apple EMLX files; current native `message_raw`/`attachments`
schemas and payloads; installed Python 3.14 `mailbox.mbox` implementation and
[Python 3.14 mbox documentation](https://docs.python.org/3.14/library/mailbox.html#mailbox.mbox).
The [safety tests](../tests/test_msgvault_export_dedupe.py) check message-ID
collisions, recipient/body/attachment differences, partial placeholders,
parameter serialization, changed files/indexes, symlinks/live stores and
byte-preserving mixed-mbox compaction. Cache attachment tests also ensure that
attachments of other messages and differing files survive, and that an EMLX
copy must already be removed before its sidecar attachments can be selected.
