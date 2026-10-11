# Gmail cleanup and English topics

This procedure is scoped to native Gmail source **2**,
**`daswerklab@gmail.com`**. German iCloud is independent source 1,
`daswerklab@icloud.com`. Its profile and existing Saved Views remain separate.

## Verified cleanup on 2026-10-11

The owner approved the previously reviewed **69** messages and all remaining
TestFlight notifications. The exact final batch contained **80 messages**:
46 reviewed unwanted messages and **34 TestFlight** notifications, including
11 beyond the original selection. No selected message had attachments.

| Readback | Result |
| --- | ---: |
| Gmail messages reviewed | 250 |
| Moved to Gmail Trash and hard-purged from Msgvault | 80 |
| Retained and filed under English topics | 170 |
| Reviewed retained Inbox memberships removed | 145 |
| Inbox: new / review pending | 2 / 4 |
| Existing iCloud messages preserved | 2,655 |
| Entire archive after purge | 2,825 |
| Attachments / packed files preserved | 898 / 11 |
| Gmail Saved Views created | 18 |
| Existing iCloud Saved Views preserved | 19 |

The six Inbox messages are two new account alerts (Apple HomePod and the
Google Msgvault permission grant) and four items held for review: the latest
bicycle-insurance support reply, two Google Play notices whose resolution
was not established by this mail filing operation, and `TBL iCoud Notes`,
whose company attribution is uncertain. The last four also carry
`Action Required`. This does not verify the current status of the underlying
insurance or developer-console issues.

Thirteen populated topic views cover all 170 retained messages. The three
Beach Lab LTD topics are reserved and empty: this Gmail review did not
establish UK company attribution for any message. The native full sync after
GC found **170**, added **0** and skipped **170**; the 80 Trash messages were
not reimported. All 2,825 retained message content hashes, all 898 attachment
references and all 11 pack-file hashes matched the pre-change baseline.
Gmail metadata, unrelated labels and read states were also unchanged.
SQLite integrity was `ok`, with no foreign-key errors.

Analytics readback through Codex MCP returned **2,655 / 170** for sources
1/2 and **zero** selected deletion IDs. All 18 Gmail Saved Views returned
their expected counts with source-2 results. The Inbox view returned the
same exact six IDs through Codex MCP and Watson's configured read-only stdio
transport. Semantic retrieval under `Germany/Developer Accounts` returned
three retained source-2 messages. Active vector generation **3** contains
**2,825 messages / 5,259 chunks**, with no orphaned embeddings or references
to the purged IDs in message embeddings or document membership.

The native batch is
`20261011-175923-staged-from-CLI-mess-fbd67557d9a46b9c`, verified completed for
exact source 2 and 80 approved provider IDs. GC retained its automatic SQLite
backup, `msgvault.db.gc-backup-20261011-160627`. Encrypted pre-change NAS
snapshot **`2c758704`** captured at **15:53:40 UTC** passed native verification
and the Restic data check before execution.

Encrypted post-change snapshot **`03827d7c`** captured at **16:09:13 UTC**
completed at **16:14:40 UTC**. It passed native backup verification and the
runner's full Restic data check. Recovery copies intentionally retain the
previous state; the live archive and search contain no selected deletion IDs.

Private current-run evidence is under
`/var/lib/msgvault-backup/gmail-cleanup-20261011/`: the owner-reviewed plan,
native manifest and command receipts, provider-before/after metadata,
archive content and attachment-file baselines, GC preflight, post-purge
archive/vector results, `mcp-after.json` and `watson-mcp-after.json`.
`backup-before.json` and `backup-after.json` identify both verified snapshots.
The Mac also retains the private plan and Codex MCP proof at
`/Users/Papi/.config/msgvault/gmail-cleanup-20261011/`.

### Owner review completed at 16:42 UTC

The owner confirmed that the insurance issue was resolved by the new contract,
that the apps were registered, and that the production-testing notice was
acknowledged. Archive IDs **3005, 3061 and 3105** were therefore archived in
Gmail and removed from `Action Required`; their topic labels, message metadata
and read states were preserved. Acknowledging the testing email does not
establish production approval.

The owner explicitly retained **3126**, `TBL iCoud Notes`, in `Action Required`.
Exact-source Gmail sync completed with **3 changes, 0 added**. Codex MCP then
returned **1** item in `Gmail / Action Required` (3126) and **3** in
`Gmail / Inbox` (3126 plus the two new alerts, 2981 and 3230). The archive still
contains all 170 retained Gmail messages. Provider before/after receipts are
private at `/var/lib/msgvault-backup/gmail-pending-20261011/`.

## Filing policy

[gmail-topics.json](../services/msgvault/gmail-topics.json) records the English
topic names and account boundary. Business attribution needs explicit message
content. An address or app identifier containing `beachlab.org` alone does not
establish ownership by Beach Lab LTD. Uncertain ownership goes to
`Review/Company Attribution`; the UK company has separate administration,
finance and development topics from `Germany/*`.

Resolved, reviewed history receives a topic label and loses only `INBOX`.
Existing user labels, message contents, attachments and read state are
preserved. Reviewed new messages and unresolved items stay in Inbox; pending
items also receive `Action Required`. Unreviewed arrivals are untouched.
This is a one-time filing operation, not an automatic classifier.

Gmail label names and IDs are reconciled into Msgvault with exact-source
incremental sync. Msgvault Saved Views use an explicit source-2 filter and an
active-deletion filter; naming them `Gmail / <topic>` distinguishes them from
the iCloud views. Both read-only MCP transports can query these views.

## Owner workflow and safeguards

Use [gmail-file.py](../services/msgvault/gmail-file.py) on the NUC with an
owner-reviewed private JSON plan. Run it with access to the native credential
files; this NUC's OAuth client is `tokens/google-client-msgvault-nuc.json`.
The token filename is derived from the approved account and its Google
profile must match the archive source. Credentials are never printed or
rewritten by this helper.

1. Capture and verify a complete encrypted backup. Keep the plan and receipts
   in a private 0700 directory with files mode 0600, outside Git.
2. Run the helper without flags. This reads the exact reviewed IDs, rejects
   account/source mismatches and drafts, and stores the initial provider
   metadata and labels. Record archive content/attachment hashes separately.
3. Native `stage-delete --ids <approved archive IDs> --dry-run` must match the
   reviewed count. Stage that same set and verify the manifest's source,
   mailbox and provider IDs before executing it.
4. Run native `delete-staged <exact batch> --source-id 2 --yes` with
   **one-command** `MSGVAULT_ENABLE_REMOTE_DELETE=1`. Keep the global remote
   deletion setting disabled. Native deletion moves Gmail mail to Trash and
   marks archive rows source-deleted; it does not purge the local archive.
5. Run the helper with `--apply` only after the selected messages reach Trash.
   It creates/reuses labels and files only reviewed retained messages.
   `--verify-only` verifies the applied plan without any provider mutations.
   Final checks include exact topic/Inbox/pending state, original metadata
   and unrelated label preservation.
6. Sync **source 2**. Immediately before `gc --yes`, verify that the entire
   archive's source-deleted set is exactly the approved set, with no unrelated
   rows. Native GC is global and has no account filter. Keep its automatic
   SQLite backup enabled as well as the full encrypted backup.
7. Check hard deletion and retained content/attachments. Run native
   `embeddings prune`, incremental embedding build and a full analytics-cache
   rebuild. Confirm that no selected IDs or orphaned message embeddings
   remain. Sync source 2 again and check that Trash is not reimported.
8. Create/reuse source-scoped topic, Inbox and Action Required Saved Views;
   read their results through MCP. Verify the existing iCloud Saved Views and
   archive content, then capture and verify a post-change encrypted backup.

The helper paces provider requests and retries only idempotent reads or label
batch updates for documented rate-limit/server errors. Label creation is not
retried automatically after an ambiguous error. An observed HTTP 403
`rateLimitExceeded` during final metadata reads motivated this pacing; it did
not indicate a missing Gmail modify grant.

Provider contracts: [Gmail batch label changes](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/batchModify),
[label creation](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels/create),
[error reasons and backoff](https://developers.google.com/workspace/gmail/api/guides/handle-errors).
Native lifecycle: [Msgvault 0.21.0 deletion and GC](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/deletion.md)
and the installed `embeddings prune` / `embeddings build` help. The native
documentation recommends full cache rebuilding; on this NUC, deletion from
vectors is verified directly after native prune and the incremental build.
