# Gmail in Msgvault

The requested Gmail mailbox is **`daswerklab@gmail.com`**. It is independent
of the already connected German iCloud mailbox **`daswerklab@icloud.com`**;
using the Gmail address to sign in to Apple does not connect Google mail.

## Current authorization checkpoint

As of 2026-10-11, the NUC's native `/api/v1/accounts` and
`/api/v1/sources/status` still list only iCloud source 1. Gmail is not yet
registered, imported or semantically indexed. The native `[oauth]` section
has an empty `client_secrets` path: no Google OAuth client is configured for
Msgvault yet.

The Google Cloud credentials page is open in Safari's regular `DE iCloud`
profile. Preparing it was interrupted by foreground Safari window changes;
the user has been asked to leave that tab active. No existing Cloud project,
Google credential or Gmail permission was changed. Resume from this point
rather than registering an unverified account or claiming Gmail is connected.

## Connection procedure

Use the native Gmail API source and request **read-only Gmail access**:

1. In Google Cloud, prepare a desktop OAuth client for Msgvault with the
   Gmail API enabled. Verify the selected project and account before changes.
   Any credential creation, legal agreement or final permission grant must
   follow the applicable browser-control handoff/confirmation policy.
2. Store the downloaded client JSON outside Git with owner-only permissions.
   Configure the NUC's `[oauth].client_secrets` to that actual private file,
   preserving all existing settings and taking a recoverable configuration
   copy. The service user must be able to read the file.
3. Run the installed 0.21.0 CLI from `/var/lib/msgvault` as the `msgvault`
   user: `msgvault --home /var/lib/msgvault --no-log-file add-account
   daswerklab@gmail.com --readonly`. On the NUC, use a loopback SSH tunnel for
   the browser callback at `http://localhost:8089/callback`; do not expose the
   callback listener publicly. `--headless` only prints setup instructions.
4. Verify that the Google profile returned by authorization is exactly
   `daswerklab@gmail.com`, and that the stored grant has `gmail.readonly`.
   Check the newly assigned native source ID instead of assuming it is 2.
5. Register a 15-minute source schedule and start a native full sync of this
   exact Gmail source. Keep it separate from source 1 and the iCloud topic
   views. Do not change Gmail messages, labels or folders as part of import.
6. After the first manual import, run native `embeddings build --yes` to add
   the new messages to the existing active semantic generation. Verify the
   Gmail source counts, eligible/embedded coverage and a source-scoped semantic
   query through the registered MCP. Scheduled later syncs use the already
   enabled post-sync embedding trigger.
7. Take an encrypted NAS backup including the new source, OAuth client and
   token, and verify native backup completion. Record actual connection and
   index results here only after live readback.

The existing semantic model is `text-embedding-3-small`, 1536 dimensions with
2000-character chunks. It was verified ready for all 2,651 current iCloud
messages, with zero missing embeddings, after the follow-up Inbox filing.
It does not yet provide evidence of Gmail indexing.

Sources: [Msgvault 0.21.0 OAuth setup](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/guides/oauth-setup.md),
[native source setup](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/setup.md),
[vector sync triggers](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/vector-search.md),
the installed CLI's `add-account`, `sync-full` and `export-token` help, and
the authenticated native source/settings readback on 2026-10-11.
