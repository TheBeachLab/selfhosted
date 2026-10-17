# Gmail in Msgvault

**`daswerklab@gmail.com` is connected as native Gmail source 2.** It is
independent of German iCloud source 1, **`daswerklab@icloud.com`**. Using the
Gmail address as an Apple sign-in identifier does not connect Google mail.

| Source | Provider | Mailbox | Schedule |
| --- | --- | --- | --- |
| 1 | iCloud IMAP | `daswerklab@icloud.com` | `*/15 * * * *` |
| 2 | Gmail API | `daswerklab@gmail.com` | `*/15 * * * *` |
| 3 | Gmail API | Personal Gmail account | `*/15 * * * *` |
| 4 | Gmail API | Fab Foundation account | `*/15 * * * *` |
| 5 | Gmail API | Hexxan account | `*/15 * * * *` |

## Additional Gmail accounts

The personal Gmail account is connected as **source 3**, with the display name
**Seacrets**. Its Google grant contains only `gmail.readonly`, and its refresh
token is stored with mode 0600. The source has an enabled 15-minute schedule.
Its address remains in the private account configuration and Strategy vault.

The initial full import completed on **2026-10-17 at 16:10:23 UTC** through
`msgvault-seacrets-initial-20261017.service`: **27,898 found, 27,898 added,
zero skipped**, with 4,047.74 MB downloaded in 3h49m29s. A later readback
showed **27,901** messages and a successful scheduled sync at 16:45 UTC.
One old message had a MIME parsing warning; its original raw message remains
archived. A separate implausible date header was replaced using a received
date. The unit finished with `Result=success`.

During the long initial CLI sync, MCP search still used the preceding cache.
Exact-message reads and read-only queries of the main SQLite archive could
already access imported messages. After completion, MCP statistics reflected
all three accounts and 30,800 messages. Do not interpret an empty search
against a stale cache as missing mail. The completion receipt is
`/var/lib/msgvault-backup/gmail-extra-20261017/seacrets-import-complete.json`.

The Fab Foundation account is connected as **source 4**, with the display name
**Fab Foundation**. Gmail's profile endpoint confirmed the mailbox, and the
saved grant contains only `gmail.readonly`, with a refresh token owned by
`msgvault` and mode 0600. Its enabled 15-minute schedule was registered before
the initial import. Both additional read-only grants were approved by the owner
on 2026-10-17.

The Fab Foundation full import completed at **18:01:13 UTC on 2026-10-17**:
native sync **1181** processed and added **5,563 messages**, with zero errors
or skipped messages. `msgvault-fabfoundation-initial-20261017.service` reported
1,892.97 MB downloaded and exited successfully. A later scheduled sync completed
at 19:00 UTC. The initial CLI unit had a 2 GiB memory limit and 200% CPU quota.
Private receipts are
`fabfoundation-authorization.json`, `fabfoundation-provider-profile.json`,
`fabfoundation-schedule.json`, `fabfoundation-import-started.json`, and
`fabfoundation-import-complete.json` in the connection receipt directory below.

The Hexxan account is connected as **source 5**, with the display name **Hexxan**.
The owner approved its read-only grant on 2026-10-17. Gmail's profile endpoint
confirmed the intended mailbox; the saved grant contains only `gmail.readonly`
and a refresh token, owned by `msgvault` with mode 0600. The native account API
confirmed an enabled 15-minute schedule before the first full import started.

Google reported **35,681 messages** before that import. Native sync **1202**
started at **19:10:57 UTC on 2026-10-17** through
`msgvault-hexxan-initial-20261017.service`, with a 2 GiB memory limit and 200%
CPU quota on the CLI unit. The disk preflight showed **134.4 GiB free**. This
records the start of the import, not its completion. Check the service result
and source 5's native sync status before treating the archive as complete.
Private authorization, provider-profile, schedule and import receipts are in
`/var/lib/msgvault-backup/hexxan-20261017/`.

For future authorization, use the user's existing Safari session signed in to
the intended account. Verify the Google account address rather than relying on
the Safari profile name, and pass `--readonly` for these additional accounts. Close the
temporary callback tab and loopback SSH tunnel after the grant is saved.

Run account commands **from `/var/lib/msgvault` as `msgvault`**, as well as
passing `--home /var/lib/msgvault`. Starting from `/home/pink` can save the
OAuth token but fail the daemon's registration subprocess with a working
directory permission error. Re-running from the correct directory reuses the
saved token; a new Google grant is unnecessary.

Register the schedule through `POST /api/v1/accounts` **before** starting the
first full sync. During this connection, schedule registration returned HTTP
503 while the CLI sync was running and succeeded after that job was stopped.
The full sync was then resumed through the same service.

The native API currently listens on `127.0.0.1:8096` on the NUC; use its configured
owner authentication locally rather than an old Tailscale listener address.

Private connection receipts, provider totals, and the configuration backup are
in `/var/lib/msgvault-backup/gmail-extra-20261017/`. The permission and schedule
statements above come from the stored token metadata, Gmail's `users/me/profile`,
and the native `/api/v1/accounts` readback. See also the
[read-only OAuth workflow](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/guides/oauth-setup.md#read-only-access).

## Google application and permissions

The dedicated Google Cloud project is **`msgvault-beachlab`**, display name
`msgvault`, number **`38818430731`**. Its Gmail API is enabled. The consent
application and Desktop OAuth client are named **`msgvault NUC`**, with
`daswerklab@gmail.com` as support/developer contact. Google showed
**In production** before the final native authorization flow was started.
The callback is `http://localhost:8089/callback`, reached through a temporary
loopback SSH tunnel; it is not exposed publicly.

The owner approved `gmail.readonly` and `gmail.modify` on 2026-10-11 to import,
search and clean mail. The stored token's exact scope set matches those two
permissions and has a refresh token. No full-mail, Calendar or Drive scope
was granted. Google includes composing and sending in `gmail.modify`; it
does not offer a scope limited to moving messages to Trash.

Msgvault 0.21.0's `delete-staged` defaults to **Gmail Trash**, recoverable for
30 days. `--permanent` needs a separate `https://mail.google.com/` grant.
No Gmail deletion batch was selected or executed during connection. The
global `[deletion].remote_enabled` remains false; an owner-approved exact
batch can use the native one-command `MSGVAULT_ENABLE_REMOTE_DELETE=1` gate.
Both MCP transports retain their read-only tool exposure. The Google provider
grant permits cleanup through the native owner workflow; it does not itself
enable MCP write tools.

Sources: [Google Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[native scope definitions](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/oauth/oauth.go),
[native deletion workflow](https://github.com/kenn-io/msgvault/blob/v0.21.0/cmd/msgvault/cmd/deletions.go),
installed `add-account`/`delete-staged` help, and live token metadata.

Google allows personal apps with fewer than 100 users without verification;
this application remains unverified and Google shows that warning. Production
removes the special seven-day refresh-token expiration of External/Testing
apps, not every possible cause of token revocation. Sources:
[personal-use exception](https://support.google.com/cloud/answer/13464323?hl=en)
and [token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).

## Credentials and public disclosures

Private NUC files are mode 0600, owned by `msgvault`:

- `/var/lib/msgvault/tokens/google-client-msgvault-nuc.json`
- `/var/lib/msgvault/tokens/daswerklab@gmail.com.json`

`[oauth].client_secrets` points to that client file. The prior configuration
is preserved at
`/var/lib/msgvault-backup/gmail-connection-20261011/config.before.toml`.
The Mac recovery client is private at
`/Users/Papi/.config/msgvault/gmail-connection-20261011/google-client.json`.
Never put secrets, tokens or OAuth callback codes in Git or command output.

Google's disabled **Publish app** action became available after the actual
homepage/privacy/use links were saved. The owner then confirmed publication
and the read/modify grant. The public disclosure URLs are:

- `https://msgvault.beachlab.org/about`
- `https://msgvault.beachlab.org/about#privacy`
- `https://msgvault.beachlab.org/about#terms`

[oauth-info.html](../services/msgvault/oauth-info.html) describes the personal
archive, the Google grant, OpenAI embeddings, private storage, encrypted NAS
backups and the separate archive deletion lifecycle. The authorized Google
domain is `beachlab.org`.

The Nginx template exposes only the exact informational `/about` route and
its `/about/` redirect. A public GET returned HTTP 200 with a byte-for-byte
match to the HTML; `/`, `/api/v1/stats` and `/about/anything` still redirected
to Authentik. The archive's existing passkey checks remain active. For
recovery, install the HTML from this repository as root-owned mode 0644 at
`/var/www/msgvault-info/index.html`, install the site template, validate Nginx
and reload it. The HTML can be reproduced from Git; the encrypted archive
backup separately preserves the native client/token/configuration. Source:
[Google OAuth Branding requirements](https://support.google.com/cloud/answer/15549049?hl=en)
and private public-route readback evidence.

## Import and semantic verification

The first full sync, native run **31**, completed on 2026-10-11 at
15:12:14 UTC: **249 found, 249 added, zero errors/skips**, 13.39 MB downloaded
in 2 minutes 28 seconds. This matched the provider's profile count of 249
before import. Scheduled run **32** at 15:15 UTC imported one new message,
bringing Gmail to **250** and demonstrating that automatic incremental sync
works. The iCloud archive remained at **2,655** messages at this readback.

The initial job `msgvault-gmail-initial-20261011.service` ran exact-source
`sync-full --source-id 2` followed by `embeddings build --yes`; it exited
successfully. The build added all 249 initial messages to active generation
**3**, with zero failures. Ten texts were reported as truncated under the
existing 2000-character input limit; their archived messages remain available
for reading and full-text search. The later scheduled message was also
indexed. The live API reported **2,905 messages, 2,905 embedded, zero missing**,
and vector status **ready**.

The semantic model remains `text-embedding-3-small`, 1536 dimensions,
fingerprint `text-embedding-3-small:1536:p1-111111:c2000:e1`. The configured
15-minute embedding schedule and post-sync trigger remain enabled.
Sources: [Msgvault vector sync triggers](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/vector-search.md)
and the native job, generation list and authenticated API readback.

Codex's registered MCP returned three semantic results for account
`daswerklab@gmail.com`, all with `source_id=2`. The same query through the
exact stdio command in Watson's current `mcp.servers.msgvault` configuration
also returned three source-2 results. That checks Watson's configured MCP
transport, not a new message sent to the Watson chat. English iCloud topic
views remain scoped to source 1.

Native live receipts are private under
`/var/lib/msgvault-backup/gmail-connection-20261011/`: `connected.json`,
`complete-readback.json` and `watson-mcp-proof.json`. Browser/protected-route
evidence is private under the Mac directory named above.

## Backup and recovery

The initial 250-message import was subsequently cleaned and filed under
English topics on 2026-10-11, with owner approval: **80** unwanted messages
(including all **34** TestFlight notifications) reached Gmail Trash and were
purged from Msgvault. The remaining **170** were filed; Inbox retained **2**
new messages and **4** items for review. Source 1 stayed at **2,655** messages.
See [Gmail organization and recovery evidence](msgvault-gmail-organization.md)
for the exact workflow, account guards, current topic profile and verification.

Encrypted NAS snapshot **`ba054dbc`**, captured at 15:16:34 UTC on 2026-10-11,
completed successfully and passed the runner's Restic data check. An isolated
Restic plus native restore reproduced sources 1/2 with **2,655 / 250**
messages and SQLite integrity **ok**. The restored Google client and Gmail
token matched the live credentials byte-for-byte, with mode 0600. The live
archive was not replaced. Proof: private `restore-proof.json` in the NUC
receipt directory. Vectors are rebuilt after restoration, following the
existing [backup procedure](msgvault.md).

To reauthorize, reuse this Cloud project/client and run the native CLI as
`msgvault`, from `/var/lib/msgvault`, with `--home /var/lib/msgvault`:
`add-account daswerklab@gmail.com`. Its normal scope set includes read/modify;
do not use `--readonly` against an existing write grant and expect it to narrow
Google permissions. After account verification, restore the exact source's
15-minute schedule, sync it and build any missing embeddings. Credential
entry, new grants and legal acceptance must follow the applicable browser
handoff/confirmation policy.

Sources: [Msgvault 0.21.0 OAuth setup](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/guides/oauth-setup.md),
[native source setup](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/setup.md),
installed CLI help and the authenticated runtime evidence above.
