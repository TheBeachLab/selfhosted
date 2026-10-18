# Msgvault

Open [msgvault.beachlab.org](https://msgvault.beachlab.org/) and sign in with
the existing [Authentik passkey](authentik.md). Access is assigned only to
`fran`. Nginx protects the UI, API, health endpoint and embedded assets; the
backend listens only on `127.0.0.1:8096`.

The NUC runs **0.21.0**, from the official Linux amd64
[release](https://github.com/kenn-io/msgvault/releases/tag/v0.21.0).
The downloaded archive's SHA-256 matched
`56b2438eab14f3cadd15b6edecc4ea30454b6584c1039c2d5593a0afa77d7497`.
The binary includes the browser application; no separate Node process is needed
([0.21.0 Web UI](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/web-ui.md)).

On 2026-10-12 the NUC returned from the local email/discovery builds to this
unmodified official executable. The existing archive, profiles and summaries
were retained. See [the current runtime and return checkpoint](#official-runtime-and-preserved-data).
The three local extension sections below are historical recovery information;
their patches and activation commands are not part of the active installation.

Installation on 2026-10-10 initialized an empty archive. On 2026-10-11,
the [German iCloud account](msgvault-icloud.md) was connected and its first
full sync completed: **2,974 messages and 868 attachments**, with automatic
sync every 15 minutes. Source: NUC daemon-backed sync and source status,
the independent read-only IMAP UID inventory, and MCP `get_stats` / `query_sql`.

The [subsequent English topic filing](msgvault-mail-organization.md) organizes
the iCloud history and provides a source-specific Inbox view. The separate
[`daswerklab@gmail.com` Gmail connection](msgvault-gmail.md) is now active as
source 2, with 250 messages imported and semantically indexed at the verified
2026-10-11 readback. Both accounts sync every 15 minutes. The Google grant
includes the owner's requested ability to move approved junk to Gmail Trash;
the MCP transports retain read-only tools.

## Files

```text
/opt/msgvault/0.21.0/msgvault
/usr/local/bin/msgvault -> /opt/msgvault/0.21.0/msgvault
/opt/msgvault/deployment/
/opt/msgvault/backups/
/var/lib/msgvault/config.toml
/var/lib/msgvault/mcp.toml
/var/lib/msgvault/msgvault.db
/var/lib/msgvault/attachments/
/var/lib/msgvault/analytics/
/var/www/msgvault-info/index.html
/etc/systemd/system/msgvault.service
/etc/systemd/system/msgvault-mcp.service
/etc/systemd/system/msgvault-backup.service
/etc/systemd/system/msgvault-backup.timer
/etc/nginx/sites-available/msgvault.beachlab.org
/etc/nginx/snippets/msgvault-api-key.conf
/etc/letsencrypt/live/msgvault.beachlab.org/
/etc/letsencrypt/renewal-hooks/deploy/50-msgvault-nginx
/usr/local/bin/msgvault-mcp-client
/opt/msgvault/mcp-venv/
/usr/local/sbin/msgvault-backup
/var/lib/msgvault-backup/
/var/lib/msgvault/backup-staging/
/mnt/nas-downloads/backups/msgvault-restic/
```

The service runs as `msgvault`, with a private data directory (0700) and
configuration/database files (0600). Systemd restarts it after failure and
starts it at boot. Limits are 2 GiB RAM and two CPU.

Nginx adds the backend API key only after Authentik authorizes the request.
The include containing that key is root-only (0600), and the key remains out
of Git. This avoids a second login in msgvault. Only localhost is listed in
`server.trusted_proxies`, so the daemon recognizes the forwarded HTTPS scheme.
Configuration reference:
[0.21.0 server settings](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/configuration.md#server).

API-key authentication skips msgvault's browser-session CSRF checks, as shown in
[0.21.0 csrf.go](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/api/csrf.go).
The Nginx configuration therefore rejects mutations with a foreign Origin or
cross-origin Fetch Metadata before adding the key. It replaces forwarded host
and scheme headers and clears client Authorization and Forwarded headers.

## API and MCP

The REST API is active on `127.0.0.1:8096`. Its OpenAPI document is at
`/openapi.json`; the installed 0.21.0 daemon reports API schema **3.0.0**.
`GET /api/v1/settings` reads configuration and `PATCH /api/v1/settings` changes
editable settings. The public HTTPS routes still require the Authentik session,
including requests with an API key. Local scripts use the daemon's owner key
over loopback or SSH. See the
[0.21.0 API reference](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/api-server.md).

`msgvault-mcp.service` exposes a separate, private MCP endpoint at
`http://127.0.0.1:8097/mcp`. It runs without `--http-allow-writes`, so deletion
staging, attachment export, Saved View changes and profile writes are absent.
The inbound MCP key differs from the owner REST key. Its private `mcp.toml`
uses `[remote]` to authenticate to the existing daemon; the MCP key itself
cannot authenticate to the owner REST API (verified 401).
Source: [0.21.0 MCP transport and write controls](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/chat.md).

The stdio bridge reads its credential on the NUC. Neither client configuration
contains a key:

| Client | Registration | Connection |
| --- | --- | --- |
| Mac Codex | `~/.codex/config.toml`, server `msgvault` | SSH `pink-sudo`, then `sudo -n -u msgvault /usr/local/bin/msgvault-mcp-client` |
| Watson | `/home/pink/.openclaw/openclaw.json`, `mcp.servers.msgvault` | Same local stdio client, with `codex.agents = ["main"]` |

The OpenClaw agent scope applies to native Codex projection; it is not a policy
for other runtime adapters. Mckenzie's existing `group:plugins` denial was
preserved; configured MCP tools are owned by the `bundle-mcp` plugin
([tool policy](https://docs.openclaw.ai/gateway/config-tools/tool-policy)).
Existing model, channel and other agent settings were preserved. Templates are
[codex-mcp.toml](../services/msgvault/codex-mcp.toml) and
[openclaw-mcp.json](../services/msgvault/openclaw-mcp.json).
Sources: [Codex MCP configuration](https://developers.openai.com/codex/mcp/) and
[OpenClaw registry and agent scope](https://docs.openclaw.ai/cli/mcp/registry).

The bridge uses `mcp-proxy` **0.13.0** and MCP Python SDK **1.30.0** in its
private virtual environment. All resolved versions are pinned in
[mcp-requirements.txt](../services/msgvault/mcp-requirements.txt).
[install-mcp.py](../services/msgvault/install-mcp.py) installs the endpoint and
bridge on an existing Msgvault host; it refuses existing MCP installation files.

OpenClaw 2026.9.9 initially rejected the entire tool list because `query_sql`
declares `oneOf` two object output schemas without an explicit root `type`.
[mcp-proxy-compat.py](../services/msgvault/mcp-proxy-compat.py) adds the redundant
`type: object` only for that schema, preserving both branches and all results.
The adapter leaves installed Msgvault/OpenClaw packages unchanged. The original
diagnostic and successful probe are retained privately in Watson's
`~/.openclaw/backups/msgvault-mcp-20261010T193147Z/`. Check for later changes
before recovery.

Check the endpoint and bridge on the NUC:

```bash
sudo systemctl status msgvault-mcp
sudo journalctl -u msgvault-mcp -n 30 --no-pager
sudo /opt/msgvault/mcp-venv/bin/python /opt/msgvault/deployment/probe-mcp.py
```

The probe checks authentication separation, absence of write tools,
`get_stats`, the corrected schema and a read-only `SELECT 1` through stdio.
On 2026-10-10, the Mac's exact registered SSH command also initialized MCP,
listed 36 tools and called `get_stats`. OpenClaw's native probe succeeded with
38 tools (including its generated resource utilities), with no diagnostics.
These checks exercise the MCP transports and clients, not an AI conversation.

OpenClaw's saved-server mutations and live CLI probes require its gateway to
be stopped for exclusive state ownership. Use its supported CLI with the
managed Node runtime, then start the gateway again. Read-only `mcp status` and
`mcp doctor` without `--probe` can run while it is active. Client configuration
backups stay private under each client's backup directory; restore only this
server's entry after checking later changes. Compare parsed Codex configuration
before and after registration: this run's readback showed `node_repl.args`
missing. It was restored from the baseline, then all prior settings matched.

## AI providers

On 2026-10-11, **message semantic search, semantic people search and automatic
people inference are active**. Both systemd services are running; authenticated
`/health` reports `ok`, vector `ready` and DuckDB. The settings endpoints report
no pending restart, and the configured and running people-policy fingerprints
match. The initial vector generation was created against an empty archive,
and a synthetic MCP hybrid query completed successfully with zero results.
The subsequent iCloud import completed with 2,974 messages. The populated
index checks are recorded under [Embedding input limits and recovery](#embedding-input-limits-and-recovery).
Email profile inference is evaluated separately under Automatic profiles from
email below.

The personal OpenAI key is `msgvault-restricted`, owned by Francisco Sanchez
in `Default project`, with **Restricted** permissions and expiration on
**2027-01-01** (confirmed by the OpenAI Administration API on 2026-10-11).
Its creation form and saved key table were read back. Only model
listing, chat completions and embeddings were allowed. With that key,
`GET /v1/models` returned HTTP 200 and listed both configured models;
`GET /v1/files` returned HTTP 401 with explicit missing `api.files.read`
scope. The fixed synthetic embedding test subsequently returned HTTP 200,
1536 finite dimensions and six input tokens. The native people check returned
HTTP 200 for `gpt-6-luna`, with 60 input and 12 output tokens. No archive text
was needed for either capability check.

The approved Mac recovery copy is `/Users/Papi/.config/msgvault/openai.env`,
mode 0600 inside a 0700 directory. The daemon holds the same key in two native,
owner-only stores:

| Feature | Active configuration | Credential file on the NUC |
| --- | --- | --- |
| Message and people embeddings | `text-embedding-3-small`, 1536 dimensions, `https://api.openai.com/v1` | `/var/lib/msgvault/tokens/provider-credentials.json` |
| Historical people inference; automation disabled | Profile `openai`, model `gpt-6-luna`, `openai_chat`, `json_object` | `/var/lib/msgvault/tokens/people-providers/openai.json` |

Both NUC files were compared with the approved local copy without displaying
the secret and checked as mode 0600, owned by `msgvault`. The former service
account key was replaced in both live stores; its private Mac recovery copy
is `/Users/Papi/.config/msgvault/openai-service-account-20261011.env`.
The old cloud key has not been revoked. Provider keys are outside `config.toml`,
Git and command arguments. Embedding credentials are bound to the configured
endpoint origin; the people profile uses the native OpenAI preset. Sources:
[0.21.0 stored provider credentials](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/configuration.md#stored-provider-credentials)
and [people provider lifecycle](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/people-automation.md#configure-a-provider).

[ai-settings.json](../services/msgvault/ai-settings.json) is the applied,
active settings profile. Message embeddings run every 15 minutes and after
supported scheduled source syncs. The daemon timezone is `Europe/Madrid`;
the native people sweep default is `15 2 * * *` (02:15), but the sweep and brief
automation are now disabled after the return to official. Native inference
budgets remain at their release defaults: up to 100 requests, one million
input tokens and 160,000 output tokens per run; up to 500 requests, five
million input tokens and 800,000 output tokens per day. No provider prices or
monetary caps were added. Review these limits before the first real run;
a local cost estimate is not an OpenAI billing cap. Sources:
[recommended scheduling and budgets](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/recommended-configuration.md),
[sweep defaults](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/peoplesweep/config.go).

[people-openai.json](../services/msgvault/people-openai.json) is the policy body
used to create the retained, inactive people provider. Its sources are conversation and
meeting text from 2023-01-01 onward. This includes all archived correspondence
currently linked to the eight selected profiles. `allow_sensitive` records the operator's
choice to permit private archive text; this release uses the same flag for
sensitive profile fields. Its saved check and consent belong to the historical
email-evidence program; reverify and consent to the official program before any
future activation for supported sources. The separate curated-person semantic
embedding consent and vector indexing remain active.
`provider-declared` is a posture assertion, not verification of zero retention.
Profile automation requires choosing people to track; conversation briefs
require their own enrollment. Eight profiles are selected for maintenance.
See the [0.21.0 policy boundary](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/people-automation.md#understand-and-correct-automatic-facts).

### Identity scoring with Jev

The native 0.21.0 identity scorer uses TypeSafe Jev at the fixed HTTPS endpoint
`https://api.typesafe.ai/v1/systemone` and the pinned model `jev-1.13.0`.
Its configuration is separate from the existing OpenAI profile provider.
Source: [identity scoring configuration](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/configuration.md#people-identity-scoring)
and [native review workflow](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/people.md#optional-identity-scoring).

The provider receives a bounded pair of observed participants: names, email
addresses, phones, up to eight typed identifiers each, and identity evidence
classes, values and source counts. Message bodies and private Notes are outside
this packet. The native worker applies local blockers before a provider request.
Scoring records suggestions and judgments; accepting a participant link remains
a separate operation with a current review token. This upstream scorer evaluates
already seeded candidates when invoked. The
historical mailbox discovery extension below handled names and phones in email
signatures. That extension is retired; the native candidate scorer remains
configured and neither path accepts participant merges automatically.

[identity-jev.toml](../services/msgvault/identity-jev.toml) sets a batch limit of
20 and the native threshold of 0.80. Its exact retention declaration references
the TypeSafe [hosted terms](https://typesafe.ai/legal/mca) and
[privacy policy](https://typesafe.ai/legal/privacy-policy), reviewed 2026-10-12.
The provider states it does not train models on inputs and retains personal data
as reasonably necessary for its stated purposes; this setup does not assert
zero retention.

Local credential entry uses `/Users/Papi/.config/typesafe/jev.env`, mode 0600,
with one `TYPESAFE_API_KEY=` assignment. The deployment copy is
`/var/lib/msgvault/tokens/identity-jev.env`, owned by `msgvault`, mode 0600.
[identity-jev.conf](../services/msgvault/identity-jev.conf) supplies it only to
the serving daemon as an EnvironmentFile. The existing encrypted NAS backup
captures both this token file and the daemon drop-in. Credentials never enter Git.
The upstream [extras selection](https://github.com/kenn-io/msgvault/blob/v0.21.0/cmd/msgvault/cmd/backup.go)
includes the complete `tokens` directory when `--include-tokens` is set.

After securely installing the private env file on the NUC, place these three
deployment files together in a private directory and run:

```bash
sudo python3 install-identity-jev.py
```

[install-identity-jev.py](../services/msgvault/install-identity-jev.py) rejects
conflicting configuration or drop-ins, verifies the pinned model and a synthetic
Noul response, completes an encrypted NAS backup, preserves a private checkpoint,
activates the configuration and records native consent to its exact disclosure.
It checks live readiness and unchanged existing provider credential hashes;
activation failure restores its own configuration changes and service drop-in.
It neither changes the binary nor runs archive scoring by itself.

For diagnosis of the upstream candidate scorer, use the `msgvault_cli` wrapper
under Maintain (the unattended discovery worker does not need these commands):

```bash
msgvault_cli person scoring status --json
msgvault_cli person scoring run --limit 20 --json
msgvault_cli person scoring history --limit 20 --json
msgvault_cli identity matches list --json
```

No scored candidate can replace missing identity evidence or overcome local
blockers for a shared contact point. The Geier professional address and the
GMX mailbox with a joint `Edwin Geier & Thomas Happel` signature were observed
as separate participants on 2026-10-12 (MCP `search_people`, and messages 2378
and 2707). Activating the scorer alone does not establish an exclusive-person
binding for that shared mailbox.

At initial Jev activation on 2026-10-12, the native scorer reported `enabled`,
`credential_available`, `consent_active` and `ready` as true, using
`jev-1.13.0`, threshold 0.80 and batch limit 20. Both Msgvault services are
active and the then-current `0.21.0-email-2` binary was unchanged. The synthetic
provider request returned the exact pinned model and a valid Noul answer;
the model-list endpoint exposed only `jev-latest` and `jev-preview`, so the
installer verifies the exact-version request instead of substituting an alias.
The first native batch completed without errors with `processed = 0`; the
participant-link count stayed at one, and Geier's profile then contained only
his professional address. That first activation enabled scoring with no current
candidate to evaluate; it did not discover the other mailbox. Primary private
receipts: `/var/lib/msgvault-backup/identity-jev-20261012T080947Z/activation.json`
and `first-batch-summary.json`; registered MCP status, judgment history and
profile reads confirmed the saved state.
The final encrypted NAS snapshot is `ca9e56bc`; restoring the Jev service
drop-in matched its live SHA-256, and the NAS staging payload was removed.
Receipt: `nas-final-proof.json` in the same private checkpoint directory.

### Historical: automatic mailbox discovery with Jev

Retired on 2026-10-12. The discovery timer, service, runner and opt-in were
removed from their active locations. The already recorded contacts, labels and
auxiliary evidence tables remain in the archive; the official daemon does not
run this extension.

The local native build `v0.21.0-discovery-3` retains the email extraction patch
and adds [mailbox-discovery-v0.21.0.patch](../services/msgvault/patches/mailbox-discovery-v0.21.0.patch)
on pinned upstream commit `598ca5cc89042ded95e484b5315cc29b9342fa42`.
The implementation lives in the Msgvault daemon (`internal/mailboxdiscovery`,
Store operations and `/api/v1/identity/discovery/*`); it is not a Codex task.

The native worker finds another sender's own footer containing a tracked
person's complete name and phone digits that match the person's known sender
signature. It examines Gmail/IMAP only, excludes owner-sent/deleted/forwarded
messages, strips quoted replies (including decorated GMX *Gesendet:*/*Von:* headers)
and requires a signature name line, not a name
mentioned in prose. Body hydration is by message primary key; list queries do
not join `message_bodies`. A maximum of 5,000 metadata rows are read per run;
a persistent cursor rotates larger archives and holds a page when the provider
request limit is reached. Anchors use the last 16 own messages per bound sender.
The initial scope is the existing tracked profiles (at most 1,000 per scan).
A missing own signature, complete name or matching phone is left unresolved.

Jev `jev-1.13.0` receives a separate `mailbox-signature-packet-v2`: tracked name,
known/candidate sender emails, one own signature each (768 characters maximum),
matching phone digits and evidence message IDs. Private message prose and quoted
threads do not enter this packet. This broader signature disclosure has its own
native consent fingerprint, independently revocable at
`POST /api/v1/identity/discovery/revoke`; it keeps the existing TypeSafe retention
declaration. The consent gate runs again immediately before the provider request
and before publishing a contact point. API calls reject redirects and validate
the exact returned model and both probabilities.

An ordinary related contact requires probability >= 0.95. A possible shared
contact instead requires related probability >= 0.50, shared probability >= 0.80
and an independently matching mobile number in both own signatures, in addition
to the complete-name match. This is a possible contact point, not an exclusive
identity judgment. The native transaction saves `source=extraction`, the actual
related confidence and an audit reference; it labels shared contacts
**posiblemente compartido**. It does not bind the
candidate participant, merge identities, replace the preferred address or assign
all messages from a household mailbox to one person's profile. Existing curated
values and superseded addresses win; changed/deleted evidence, untracking or a
profile revision during scoring prevents publication. A shared address is a
possible contact for this person, not proof of who authored a particular email.

[msgvault-mailbox-discovery.timer](../services/msgvault/msgvault-mailbox-discovery.timer)
runs on the NUC shortly after activation/boot and every 15 minutes, with up to
30 seconds of jitter.
[mailbox-discovery.py](../services/msgvault/mailbox-discovery.py) only calls the
native daemon over loopback and logs counts. It does not read email or call Jev.
It supports the NUC system Python 3.10 without extra dependencies.
Each run permits eight provider requests, with a durable ceiling of 40 per UTC
day across all profiles. Successful and inconclusive judgments are cached by
person/evidence/disclosure fingerprint. Provider errors retry after 24 hours;
an interrupted pending claim becomes eligible after five minutes. More evidence
or a policy change can produce a new fingerprint. No manual batches are needed.

The setup requires the already configured private Jev key and a tested native
build. [build-mailbox-discovery.sh](../services/msgvault/build-mailbox-discovery.sh)
verifies upstream, Go and Bun archive hashes, applies both patches without fuzz,
runs `go fmt`, `go vet`, native regression tests (including the serving adapter)
and builds on Linux amd64.
[install-mailbox-discovery.py](../services/msgvault/install-mailbox-discovery.py)
requires the verified previous daemon and backup hashes, performs an encrypted
NAS backup first, preserves a private activation checkpoint, switches the binary,
records the separately authorized signature consent and enables the timer. It
preserves the existing config and credential files and rolls back its own runtime
files if activation fails. [backup.py](../services/msgvault/backup.py) also captures
the runner, timer/service, drop-in and complete recovery sources on the NAS, then
removes its temporary staging only after a verified encrypted snapshot.

Verified on 2026-10-12: `v0.21.0-discovery-3` is serving on the NUC;
its SHA-256 is `f4b5b18271d014b2310a6b297206b0c77d858c4d84c2ce23ecb23e1426daab95`.
The timer triggered the native worker at 09:40:16 UTC and finished successfully:
2,825 scanned messages, one candidate, one Jev request and one shared contact
saved. MCP `get_person_profile(person_id=8)` returned both mailboxes; the new
point has `source=extraction` and `type_label=posiblemente compartido`, while
the professional address remains preferred. The native journal retained actual
related/shared probabilities 0.76/0.91 and evidence IDs 2232/2707. Confidence is
not upgraded to a confirmed identity. Participant 9 remains separate; person 8
is still bound only to participant 54, and the existing participant-link count
stays one. All 2,837 original archived message/body hashes were unchanged.
The v2 packet contains only the own footer, with the GMX quoted reply removed.
Primary private receipts are `activation.json`, `verified-history.json` and
`runtime-proof.json` under
`/var/lib/msgvault-backup/mailbox-discovery-20261012T094014Z/`.
The previous v1 discovery consent was revoked after v2 activation; its audit
was retained. These observations are deployment evidence, not guarantees about
unseen signatures or who authored mail from a shared address.

### Historical: automatic briefs from signed messages in a related mailbox

Retired on 2026-10-12. Existing brief versions and their citations remain
readable through the official API/MCP. New shared-mail messages no longer
trigger this specialized summary worker.

The native `v0.21.0-signed-brief-1` extension uses the existing Jev-discovered
contact as a candidate mailbox. It requires a personal closing in each message's
own text, naming the tracked person alone or together with another signer. A
joint address footer by itself, another person's closing, quoted/forwarded
replies, owner mail and unsigned messages do not qualify. A first name qualifies
only at a personal closing in this already related mailbox. This is signing
text evidence, not cryptographic authentication.

[The native patch](../services/msgvault/patches/signed-mail-brief-v0.21.0.patch)
indexes eligible message IDs, their body hashes and individual/joint authorship.
The daemon rechecks current text, tracking, brief enrollment, the active contact
and its consented Jev judgment before hydration and citation alignment. Body
edits, removals and membership changes wake the native brief journal. An edit
fails closed before the next index pass. This read scope exists only during
brief assembly: shared-mail evidence cannot become extraction claims or a
participant binding. The primary address and shared label retain their existing
meaning. Joint authorship is supplied to the brief model explicitly.

The existing NUC discovery timer also wakes this native brief worker every
15 minutes, after archive ingestion. Changed signed mail publishes work for
tracked and enrolled people. The watched scope uses a one-minute minimum brief
interval; other people's configured cadence stays in place. Unchanged evidence
makes no new model call. Existing provider consent, leases, retry backoff and
usage caps still apply. Jev handles mailbox relations; the configured OpenAI
profile provider continues generating prose. Python only sends the loopback
wake-up and logs counts; Codex and the Mac are not required for ongoing work.

[build-signed-mail-brief.sh](../services/msgvault/build-signed-mail-brief.sh)
applies the email, discovery and signed-brief patches to the pinned upstream
source and runs native checks on Linux amd64.
[install-signed-mail-brief.py](../services/msgvault/install-signed-mail-brief.py)
requires the verified discovery-3 binary and previous runner, takes an encrypted
NAS backup, preserves configuration/credentials and a rollback checkpoint,
then enables the same timer. Recovery sources stay under the already backed-up
`/opt/msgvault/deployment/mailbox-discovery` tree.

Verified on 2026-10-12: the NUC is serving `v0.21.0-signed-brief-1`, binary SHA-256
`1624c33470cfc51d2b845b344b58d9da5b596ce1cd649236618225c5779cf3f0`.
The timer fired at 18:35:20 UTC and the native worker generated Geier's brief
version 2 at 18:35:38 UTC using `openai_chat`, `gpt-6-luna`, program
`v1-signed-mail-1`. The input held 34 messages: 16 from the professional sender
and 18 signed GMX messages (15 individual, three joint), 55,827 input bytes.
The new brief cites GMX message 2695 for the September 20 meeting and professional
message 2707 for the Phase 2 discussion. Unsigned GMX message 2829 is excluded.
The first timer response reported 18 signed changes and one brief, with zero
new Jev requests because the mailbox judgment was cached. A separate validation
wake-up with unchanged mail reported zero signed changes, zero Jev requests and
zero briefs; the next calendar trigger was observed at 18:45:13 UTC.

All 2,840 pre-upgrade message/header/body/raw-content hashes matched after the
native update. Person 8 still has only participant 54, participant 9 remains
unbound, and the global participant-link count remains one. MCP readback kept
the preferred professional address and the GMX `posiblemente compartido` label.
Primary private receipts: `/var/lib/msgvault-backup/signed-brief-20261012T183418Z/`
(`activation.json`, `archive-before.json`, `runtime-proof.json`). These are
runtime observations, not conclusions from a Codex-written profile.
The final encrypted NAS snapshot is `777aaeb7`, completed at 18:38:48 UTC.
Eight restored runtime/recovery files matched their live SHA-256, including the
new builder, installer, native patch and build manifest. Temporary NAS staging
was removed. Receipt: `nas-final-proof.json` in that checkpoint.

### Historical: automatic profiles from email

Retired on 2026-10-12. Existing facts and summaries are preserved. The active
official daemon has `people.sweep.enabled=false` and
`people.sweep.brief.enabled=false`; its Gmail/IMAP evidence policy is unchanged
from the official release.

The stock 0.21.0 extractor excludes Gmail and IMAP as subject-authored evidence.
Enabling the provider alone therefore produces no email-derived profile facts.
This restriction is implemented in
[sender attribution](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/store/person_sweep_evidence.go)
and the [exact-subject gate](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/peoplesweep/assembler.go).

The local native build `v0.21.0-email-2` adds explicit email support through
[people-email-evidence-v0.21.0.patch](../services/msgvault/patches/people-email-evidence-v0.21.0.patch).
The systemd drop-in
[people-email-evidence.conf](../services/msgvault/people-email-evidence.conf) sets
`MSGVAULT_PEOPLE_EMAIL_EVIDENCE=1`. Only tracked, sender-bound Gmail/IMAP messages
become seeds. The archived sender/profile binding is a declared identity, not
cryptographic authentication of the From header. Recipient-only and group
participation cannot assert that the person authored the text. Attachment
authorship keeps the upstream authentication requirement.

The email path removes quoted replies and common English, German, Spanish and
French forwarding separators, retaining the sender's own signature. Extraction
uses the native provider, typed catalog, evidence alignment, claim resolver,
audit history and user-value protection. It accepts explicit facts and leaves
unstated or ambiguous details empty. An organization address in a signature
does not establish the person's residence. Briefs summarize the person's own
messages; they cannot reconstruct owner replies or prove an old request is
still pending. The extraction and brief programs have new fingerprints, so
the configured provider must be checked and consented again after deployment.

The configured OpenAI profile uses `json_object`. OpenAI rejected the stock
extraction schema's untyped `claims.items.value` during the live check. JSON
object mode is supported by the
[native driver](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/peoplesweep/openai_chat.go);
the local parser still validates the closed output schema, typed values and
evidence. The patch also accepts an organization name supplied as a string,
normalizing it to the existing organization object before the same validation.
It preserves the original model output in the claim audit. Empty names,
wrong field types, duplicate fields and unknown fields remain rejected.

Build on Linux x86_64 with
[build-email-profiles.sh](../services/msgvault/build-email-profiles.sh), passing
a new output directory. It verifies the pinned upstream, Go and Bun archives,
runs formatting, vet and the native evidence, sweep, brief and resolver tests,
and compiles the embedded browser UI. Temporary build dependencies are removed
on exit. It does not modify the live installation.

Deploy with [activate-email-profiles.py](../services/msgvault/activate-email-profiles.py)
beside the drop-in. It requires the verified stock or previous local binary, validates the built
checksums, completes the existing encrypted NAS backup, records a private
checkpoint, sets only the provider's date bound and JSON object mode while the
daemon is stopped, switches the binary symlink and starts both services. Failed health
or credential checks restore the original binary and remove only its own
drop-in and its configuration changes. It preserves an already installed,
matching drop-in when upgrading the local build. The original release remains
at `/opt/msgvault/0.21.0/msgvault`.

After activation, use the native CLI wrapper described under Maintain:

```bash
msgvault_cli person provider reverify openai --yes --json
sudo systemctl restart msgvault.service msgvault-mcp.service
msgvault_cli person brief enroll PERSON_ID --track --json
msgvault_cli person sweep run --backstop --limit 8 --json
msgvault_cli person sweep status --json
```

Enroll profiles with sender-authored evidence separately. Keep recipient-only
profiles tracked without brief enrollment: this release's manual idle-brief
path can otherwise leave a retry for a profile with nothing to summarize.
The daily 02:15 Europe/Madrid sweep maintains tracked facts and eligible briefs
with the existing request/token budgets. Briefs retain the configured minimum
interval of 168 hours. A run marked successful can still have no facts: check native request
counts, evidence, claim decisions and the saved profile. A contact present only
as a recipient has no self-authored evidence and retains its existing fields.
Upstream upgrades require reviewing and rebasing the patch; a stock replacement
does not inherit this email support from the drop-in alone.

Verified on 2026-10-12: eight profiles remain tracked, seven have generated
briefs, and the native model has projected six employment records across three
profiles with `source = extraction`. The recipient-only profile stays tracked
without a brief. The incremental run completed with zero provider requests;
the queue has no dirty, leased or retrying work. The original 2,827 message
content hashes matched after inference. Later imports continued normally,
and live semantic coverage reached 2,831/2,831 messages, generation 3, ready.
Private primary evidence is retained under
`/var/lib/msgvault-backup/email-profiles-first-run-20261011T220915Z/` and
`/var/lib/msgvault-backup/email-profiles-reprocess-20261011T222857Z/`;
activation checkpoints record the binary and credential hashes. The four
native test packages and embedded UI asset validation passed on the deployed
build. Registered MCP reads confirmed the saved briefs and employment records.
Encrypted backups also capture the daemon's regular systemd drop-ins, including
the email evidence opt-in, so restoring host configuration preserves it.

MCP discovers the daemon's vector capabilities at startup; its separate
client-facing configuration does not need a copy of the vector settings.
Restart both services after changing those capabilities. After activation,
the HTTP and stdio probes each listed **37 read-only tools**, preserved owner
REST/MCP authentication separation and called `get_stats` successfully. Codex's
registered `semantic_search_messages` tool also completed a hybrid query against
active generation 1 (`text-embedding-3-small`, 1536 dimensions). Sources:
[pinned MCP capability wiring](https://github.com/kenn-io/msgvault/blob/v0.21.0/cmd/msgvault/cmd/mcp.go)
and the live probe and connector responses.

The first generation required `embeddings build --full-rebuild --yes`; the
incremental command reported that no active generation existed. It scanned
zero messages and activated generation 1 without inserting synthetic archive
data. Later manual imports require an incremental build; supported scheduled
syncs and the 15-minute cron trigger embedding automatically. Use the CLI
wrapper under [Maintain](#maintain), which sets a working directory accessible
to the service user. Sources:
[vector build and sync triggers](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/vector-search.md).

### Embedding input limits and recovery

The applied profile sets `vector.embeddings.max_input_chars = 2000`.
This is a limit per overlapping chunk, not a cutoff for the whole message;
long messages produce multiple embedding inputs. The document prefix remains
empty. OpenAI limits `text-embedding-3-small` inputs to **8192 tokens**;
characters and tokens are different units, so the previous 32768-character
default could produce an oversized request. Sources:
[OpenAI embedding model limits](https://developers.openai.com/api/docs/guides/embeddings#embedding-models)
and [Msgvault chunk sizing](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/vector-search.md#matching-max_input_chars-to-your-embedders-context-window).

Changing this limit changes the generation fingerprint. Save it through
`PATCH /api/v1/settings` with the current `ETag`, restart the daemon, then use
the [Maintain](#maintain) wrapper:

```bash
msgvault_cli embeddings build --full-rebuild --yes
```

The native rebuild creates a new generation and activates it on completion;
the previous generation is retained. Vector and hybrid search report
`index_stale` while the configured fingerprint differs from the serving
generation. Full-text search remains available. Source:
[Msgvault generation rotation](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/vector-search.md#model-rotation).

Check both authenticated `GET /api/v1/stats` and
`POST /api/v1/search/coverage` with `{"filters":[]}` after the build.
`missing_embeddings_total = 0` alone is insufficient: the worker also stamps
message-specific permanent HTTP 4xx failures so subsequent scheduled passes
skip them. A populated index is complete only when the eligible and embedded
counts agree. Sources: the installed OpenAPI `getSearchCoverage` contract and
[Msgvault permanent-failure handling](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/vector/embed/worker.go).

Verified on 2026-10-11: generation 1 had 2,922 of 2,974 messages indexed
(98.3%). The daemon journal identified exactly 52 distinct messages rejected
with HTTP 400 `input too long`. After reducing the chunk limit from 32768
to 2000 and running the native full rebuild, generation 2 activated in
162.2 seconds with **2,974 succeeded and zero failed**. Authenticated coverage
reported **2,974 eligible / 2,974 embedded (100%, ready)**. All 52 previously
rejected message IDs have embeddings in generation 2. Its 6,583 chunks are
at most 2,000 characters each, and no message reached the 64-chunk ceiling
(maximum 35). The native `truncated: 223` counter includes hard chunk boundaries
covered by overlap; it is not a count of dropped messages. Source:
[Msgvault chunk accounting](https://github.com/kenn-io/msgvault/blob/v0.21.0/internal/vector/embed/worker.go).

The logical hash of all message bodies, subjects and source identities matched
before and after the rebuild. The two provider credential files were unchanged,
both services reported active, and no restart was pending. A registered Codex
MCP vector search returned a result from generation 2. Live proof and the
private pre-change configuration are under
`/opt/msgvault/backups/fragmentation-20261011T112151Z/`; `receipt.json` records
the coverage, recovered IDs, content hashes and backup snapshots.

Settings were saved through the daemon API with the current strong config
ETag; the separate provider-store ETag and people credential's opaque revision
were used for credential writes. Immediately after these API writes, parsed
TOML comparison showed only the six intended changes: vector enablement, semantic people
enablement, embedding cron, post-sync embedding, people sweep enablement and
selected people provider. Unrelated settings were preserved. The subsequent
source import's configuration and data changes were also preserved; final
readback still showed the checked, consented people policy running without a
pending restart. The private pre-activation copy is `/opt/msgvault/backups/ai-activation-20261011T094614Z/`;
its `synthetic-check.json` records the successful native provider check.

The encrypted backup service succeeded after activation. Snapshot `5aa04599`
was restored into an isolated private directory and passed the native integrity
check. At that point, recovered configuration and both credential files
matched the live files byte for byte; both active consent records were present
in the restored archive database. This snapshot predates the concurrent source
import and validates the initial AI setup, not populated-archive recovery.
The temporary restore was removed. The private receipt is
`/var/lib/msgvault-backup/ai-active-restore-20261011T095118Z.json`.
Earlier credential-only receipts remain under `/var/lib/msgvault-backup/`.

The service-account alternative was abandoned after assigning the saved
`Msgvault AI` role failed twice with `Organization ... not found`. The account
retained `Member`, and its former key could read `/v1/files`; the cause of that
assignment failure remains unverified. The operator approved the restricted
personal replacement. Before credit was added, a synthetic embedding request
returned HTTP 429, `insufficient_quota` and `credit_balance_exhausted`, while
Billing showed zero API credit. The same configured key now passes both
provider checks. No credit purchase was performed by this setup.

## Storage and encrypted backups

[storage-settings.json](../services/msgvault/storage-settings.json) is the
applied NUC profile. The settings API readback and authenticated `/health`
confirmed these values after restarting the daemon; DuckDB is active and
`pending_restart` is false.

| Setting | Value |
| --- | --- |
| Cache builder memory / threads | 512 MB / 1 |
| Cache builder temporary storage | 2 GB |
| Minimum automatic cache rebuild interval | 15 minutes |
| Beeper, Slack and Teams attachment size | 100 MiB per attachment |
| Discord attachment size | 50 MiB per attachment |
| Chat media participant threshold | 20 |

The media limits apply to future downloads from those four chat providers.
They do not impose a Gmail/IMAP attachment cap or remove existing files.
The daemon's systemd limit remains 2 GiB; a DuckDB buffer limit is not a total
process memory limit. Sources: [0.21.0 analytics settings](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/configuration.md#analytics)
and [media policy](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/configuration.md#media-policy).

`msgvault-backup.timer` runs daily at **02:30 Europe/Madrid**, with up to five
minutes of random delay and catch-up after downtime. Its separate encrypted
Restic repository is `/mnt/nas-downloads/backups/msgvault-restic`; the existing
server backup's script, timer, repository and retention were left intact.
Daily snapshots tagged `msgvault` keep **7 daily, 4 weekly and 6 monthly** copies.
The job checks 5% of repository data nightly and all data on Sundays. Sources:
[service](../services/msgvault/msgvault-backup.service),
[timer](../services/msgvault/msgvault-backup.timer),
[runner](../services/msgvault/backup.py), and
[Restic 0.12.1 retention](https://restic.readthedocs.io/en/v0.12.1/060_forget.html).

Each run first uses `msgvault backup create` to capture a coherent database,
attachments, deletion audit, configuration and OAuth tokens while the daemon
continues serving. The temporary capture is now created directly on the NAS at
`/mnt/nas-downloads/backups/msgvault-staging/payload`, mode 0700. It adds
`mcp.toml`, service units and Nginx access files, then encrypts the capture into
the separate `msgvault-restic` repository on the same NAS.
Msgvault 0.21.0's native repository has no encryption or retention; its temporary
repository contains private plaintext, including the selected credentials. The
explicit plaintext-secrets flag applies only to this private NAS capture. The
stage is removed after the encrypted snapshot, checks and retention succeed.
Source: [0.21.0 capture and restore contract](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/usage/backup.md).

The runner estimates space without assuming compression: the NAS must have room
for both the temporary capture and its encrypted backup, plus **10 GiB free**;
the NUC retains a **10 GiB** reserve for the live service and its caches. This is
a backup preflight, not a total archive quota. It refuses a missing/wrong NFS mount
or a changed repository identity. An upload failure retains the completed NAS
capture for retry; an incomplete capture is preserved for operator inspection
rather than deleted automatically.
An uploaded capture whose cleanup fails is retried before any new capture.
The guards and recovery-before-deletion tests are in
[test_msgvault_backup.py](../tests/test_msgvault_backup.py).

Native `msgvault gc` fixes its pre-delete database backup beside the live DB;
there is no destination flag in [v0.21.0 gc.go](https://github.com/kenn-io/msgvault/blob/v0.21.0/cmd/msgvault/cmd/gc.go).
Each daily backup collects exact `msgvault.db.gc-backup-YYYYMMDD-HHMMSS` recovery
files into the NAS stage and preserves them in a separate encrypted snapshot
tagged `msgvault-gc-recovery`. This tag is excluded from daily-current-state
retention so a later run on the same day cannot erase the sole pre-GC database.
These recovery snapshots remain until explicitly retired. Before deleting a
local GC file, the runner recovers every byte from that exact NAS snapshot and
compares size and SHA-256, then checks that the original file has not changed.
The temporary NAS stage is deleted after verification; a failed check preserves
the local original and the stage. Proof and per-file cleanup results are in
`/var/lib/msgvault-backup/last-success.json`. Source: [runner](../services/msgvault/backup.py).

The daemon can write only the staging directory on the NAS; the root backup
service also writes the encrypted repository. The staging parent is created
before restarting these units, and service-account write access is checked.
Upgrades must preserve any existing `pending.json` or old local payload:
the runner refuses an unexplained legacy capture instead of deleting it.

Verified on 2026-10-11 after moving staging to the NAS: daily snapshot
**03827d7c** and separate GC recovery snapshot **39dc8ca5** both exist.
The two local GC files (602,353,664 and 570,032,128 bytes) were removed only
after full recovery from the encrypted snapshot matched their SHA-256 and size.
A NAS-only restore using `dump`/`tar --no-same-owner`, full native repository
verification and native restore recovered **2 accounts, 2,825 messages/raw-MIME
rows and 898 attachment parts**. SQLite integrity was `ok`; configuration and
both OpenAI credential files matched the live SHA-256 hashes. The temporary
capture and both restore attempts were removed. Primary private receipt:
`/var/lib/msgvault-backup/nas-staging-restore-proof-20261011.json`.
Deployment and unchanged-configuration evidence:
`/var/lib/msgvault-backup/nas-staging-deployment-20261011.json`.

The job reuses the existing root-only Restic password file. Its private NAS
recovery copy was compared successfully before installation; locations and
access are in [Backups](backups.md). No key values enter Git or command arguments.
The repository identity, last successful run and restore receipt are private
files under `/var/lib/msgvault-backup/`. Command failure diagnostics also stay
there, mode 0600. Original pre-profile configuration is retained under
`/opt/msgvault/backups/storage-<UTC timestamp>/`.

First installation on this existing NUC layout:

```bash
sudo python3 services/msgvault/install-backup.py
```

The installer refuses existing backup paths and uses the settings API's current
strong `ETag` in `If-Match` so concurrent edits are rejected. It changes only
the profile's named settings. Contract: the installed OpenAPI `patchSettings`
operation and [API reference](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/api-server.md).

Run and inspect:

```bash
sudo systemctl start msgvault-backup.service
systemctl list-timers msgvault-backup.timer
systemctl show msgvault-backup.service -p Result -p ExecMainStatus
sudo journalctl -u msgvault-backup.service -n 30 --no-pager
```

### Restore the mail archive

For a restore test, run in a root Bash shell and restore into a new private NAS
directory. This Synology export rejects Restic's `Lchown` with `operation not
permitted`; use `dump` and extract with NAS ownership, then verify every native
pack before restoring the database. This does not change export permissions.

```bash
set -euo pipefail
umask 077
restic -r /mnt/nas-downloads/backups/msgvault-restic \
  --password-file /root/.config/thebeachlab-backup/restic-password \
  snapshots --tag msgvault
read -r -p 'Msgvault snapshot ID: ' msgvault_snapshot
test -n "$msgvault_snapshot"
backup_restore_dir=$(mktemp -d /mnt/nas-downloads/backups/msgvault-staging/restore-XXXXXX)
mkdir -m 700 "$backup_restore_dir/restic"
restic -r /mnt/nas-downloads/backups/msgvault-restic \
  --password-file /root/.config/thebeachlab-backup/restic-password \
  --cache-dir /var/lib/msgvault-backup/restic-cache \
  dump "$msgvault_snapshot" /mnt/nas-downloads/backups/msgvault-staging/payload \
  | tar --extract --file - --directory "$backup_restore_dir/restic" \
      --no-same-owner --no-same-permissions
msgvault --home /var/lib/msgvault --no-log-file backup verify \
  --repo "$backup_restore_dir/restic/mnt/nas-downloads/backups/msgvault-staging/payload/archive" \
  --all --jobs 1
msgvault --home /var/lib/msgvault --no-log-file backup restore \
  --repo "$backup_restore_dir/restic/mnt/nas-downloads/backups/msgvault-staging/payload/archive" \
  --target "$backup_restore_dir/archive" --jobs 1 --integrity-check
```

Review machine-specific paths in the restored `config.toml` before starting
any daemon from it. The live archive is not overwritten by these commands.
The separate `host-files` tree contains MCP and Nginx configuration for recovery.
Keep test directories private and remove only the test directory after review.
Snapshots from the previous staging layout require dumping their old
`/var/lib/msgvault/backup-staging/payload` path and contain the native repository
under `restic/var/lib/msgvault/backup-staging/payload/archive` instead.
See [Restic restore](https://restic.readthedocs.io/en/v0.12.1/050_restore.html)
and the native restore contract above.

For a real recovery, check capacity for both the preserved live archive and the
restored copy before starting. The database, attachments and native metadata must
be restored together. To activate the validated copy:

1. Stop `msgvault-backup.timer`, wait for any running backup to finish, then stop
   `msgvault-mcp.service` and `msgvault.service`. Preserve `/var/lib/msgvault/`
   in a separate private directory on the same filesystem.
2. Copy the restored native archive into a fresh `/var/lib/msgvault/`, preserving
   its contents and modes. Set its ownership to `msgvault:msgvault`. Inspect
   `config.toml` for machine-specific `database_url`, `data_dir` and `remote.url`
   before use; an old remote URL must not send checks to the wrong host.
3. Restore needed `host-files` entries selectively, including MCP configuration,
   service units/drop-ins and Nginx settings. Keep keys and tokens private.
   Restore compatible binaries, run `systemctl daemon-reload`, and validate Nginx
   before reloading it. Start `msgvault.service` before `msgvault-mcp.service`.
4. Check SQLite integrity and source/message/attachment counts against the native
   manifest, open a known attachment and verify authenticated API and MCP reads.
   Read the real SQLite database as user `msgvault` in read-only mode; analytics
   caches may lag and are not the authoritative archive.
5. Restore the backup script's repository identity record on a replacement host
   as described in [backup recovery state](personal-knowledge.md#the-nuc-or-a-service-database-was-lost).
   Resume the backup timer and incremental account sync once paths and accounts
   are correct. Keep the preserved live copy until the recovered service passes
   these checks. Updates after the capture may need to be fetched from the mail
   providers, if they still exist there.

Msgvault is a source archive for [Strategy](personal-knowledge.md), not its
maintained profile. Recovering the mail does not restore the Markdown vault or
the source catalogue on the Mac.

Verified on 2026-10-10: encrypted snapshot **e26ba98c**, full Restic data check,
native repository verification, temporary restore and SQLite `integrity_check`
all passed. Restored configuration and MCP access configuration matched the
originals by SHA-256; a wrong repository password was rejected. Restored
`sources`, `messages` and `attachments` each contained zero rows. This checks
the initial empty archive. A [populated iCloud restore](msgvault-icloud.md#verification)
passed on 2026-10-11 from encrypted snapshot **35144baa**, including all
2,974 messages and 868 attachments. Both test and capture directories
were removed. Live proof: `/var/lib/msgvault-backup/restore-proof.json`, service
readback, authenticated `/health`, the MCP `get_stats` call and public HTTPS
302 into Authentik from the Mac.

## Official runtime and preserved data

Verified on 2026-10-12 at 19:40 UTC: `/usr/local/bin/msgvault` selects
`/opt/msgvault/0.21.0/msgvault`, SHA-256
`2e00619b03f9914aaece4f6458299dc66bc9f6386856098ea9329c889d0a5a1e`.
This matches the executable in the checksummed official release archive.

The guarded [return-to-official.py](../services/msgvault/return-to-official.py)
required a fresh encrypted NAS backup and a full official pack verification and
restore before changing the executable. The current `msgvault.db`, attachments,
`vectors.db`, configuration and credentials stayed in place; no old database
was restored over the live archive. All 40 protected tables and official
profile/brief API responses matched before/after. The archive retained **2,841
messages, 901 attachment records, eight people, seven current briefs and eight
total brief versions**. Geier retained both emails, the GMX shared label, brief
version 2 and its citations.

Only the two people automation booleans changed in `config.toml`. The two patch
opt-in drop-ins and the discovery timer/service/runner were retired to the private
checkpoint. The native Jev credential drop-in, both account schedules, all vector
settings, the MCP bridge and encrypted NAS backup service/timer were retained.
The five auxiliary extension tables were left intact for evidence and recovery.

A real MCP vector query returned results from active generation **3** using
`text-embedding-3-small`, 1536 dimensions and the exact accelerator. Native
`embeddings list` reported **2,841 / 2,841 embedded, zero missing**, with the
unchanged 2,000-character chunk policy.

The pre-return snapshot was created and fully restored as `bd350a01`. It was
then retagged to protected snapshot **`ddeff6ac`**, preserving exactly the same
Restic tree, under `msgvault-official-return-before-20261012T193944Z`. This tag
is outside the daily job's `--tag msgvault` retention filter, so a later backup
on the same day cannot prune the return checkpoint. The temporary restore was
removed. The original patched executable remains available for rollback.

The supervised backup was then run again with the official executable. It
completed at **19:44:25 UTC**, encrypted snapshot **`c744b924`**, with
`Result=success` and `ExecMainStatus=0`. Its `capture.json`, read back from the
encrypted snapshot, identifies
`msgvault v0.21.0`. NAS staging and the pending-capture marker were removed;
the protected pre-return snapshot still exists after normal retention/pruning.
The existing daily 02:30 Europe/Madrid timer (up to five minutes of jitter)
remains enabled and active. Native Jev candidate scoring also remains ready,
with its existing consent and credential; the automatic signature scanner is
retired.

Primary private proofs on the NUC:

```text
/var/lib/msgvault-backup/official-pre-restore-proof-ddeff6ac.json
/var/lib/msgvault-backup/official-return-20261012T193944Z/activation.json
/var/lib/msgvault-backup/official-return-20261012T193944Z/protected-before.json
/var/lib/msgvault-backup/official-return-20261012T193944Z/nas-checkpoints.json
/var/lib/msgvault-backup/official-return-20261012T193944Z/live-readback.json
```

The checkpoint also retains the previous configuration, extension files and
their ownership/modes. The encrypted pre-return snapshot contains the previous
configuration and credentials. Do not run the historical patch installers as
part of official updates. This one-off return helper only accepts the two
audited executables; it is not a generic upgrade tool. Ordinary future updates
should use official release checksums and a fresh verified NAS backup while
preserving the current archive home.

Sources: official release artifact comparison, full NAS restore, frozen SQLite
row hashes, before/after profile API hashes and live native/MCP readback. Tests:
seven official-return guards (including startup-failure rollback and concurrent
file preservation), plus ten existing NAS-backup guards.

## Maintain

On the NUC (`ssh pink-sudo`):

```bash
msgvault_cli() {
  sudo -n -u msgvault sh -c \
    'cd /var/lib/msgvault && exec /usr/local/bin/msgvault --home /var/lib/msgvault --no-log-file "$@"' msgvault "$@"
}

sudo systemctl status msgvault
sudo journalctl -u msgvault -n 50 --no-pager
sudo systemctl restart msgvault
msgvault_cli list-accounts
msgvault_cli stats
curl http://127.0.0.1:8096/health
```

Always use `MSGVAULT_HOME=/var/lib/msgvault` and the service user for archive
commands. The serving process owns database writes; `daemon_auto_start=false`
and `daemon_auto_restart="never"` leave lifecycle management to systemd.
`serve` initializes the database itself. `init-db` cannot bootstrap this
configuration while its supervised daemon is stopped.
The CLI proxy preserves the caller's working directory: invoking it from
`/home/pink` failed with `chdir /home/pink: permission denied`. The wrapper
above was verified from the SSH login directory. This host's sudo policy
rejects `--chdir` for the executable, so the service user's shell changes
directory before executing the native CLI.
Sources: installation readback and the
[0.21.0 configuration reference](https://github.com/kenn-io/msgvault/blob/v0.21.0/docs/configuration.md#server).

Before updating or restoring, complete and verify the existing encrypted NAS
backup, including the database, attachments, configuration and tokens. Keep the
live archive home and its vector database in place when switching executables.
Run the supervised backup while the daemon is healthy:

```bash
sudo systemctl start msgvault-backup.service
systemctl show msgvault-backup.service -p Result -p ExecMainStatus
systemctl list-timers msgvault-backup.timer
```

The supervised capture requires a healthy daemon. Recovery tests use new private
NAS directories as documented under Backups; they never replace the live
archive. Temporary capture and restore payloads are removed after verification.

Read the selected release's migration notes before opening this archive with
a newer binary. No automatic binary updates are configured.

## Install

The source package is [services/msgvault](../services/msgvault/).
[install.sh](../services/msgvault/install.sh) installs the pinned native release,
verifies its archive checksum, creates the service user and random API key,
and starts systemd. It refuses existing installation paths or an occupied port.
It is for a first installation, not an upgrade.

```bash
sudo bash services/msgvault/install.sh
sudo python3 services/msgvault/configure-authentik.py --apply
```

The Authentik script defaults to a read-only plan. It requires Fran's enrolled
passkey and the existing `beachlab-passkey` flow, creates only the `msgvault`
provider/application and its Fran binding, and adds that provider to the
embedded outpost while preserving other providers and its configuration.
The NUC's Authentik 2026.8.2 API schema was checked before provisioning.
Do not rerun the global Authentik `configure.py` for this service.
Sources: [forward auth](https://docs.goauthentik.io/add-secure-apps/providers/proxy/forward_auth/)
and [application access](https://docs.goauthentik.io/add-secure-apps/applications/manage_apps/).

For the HTTPS host:

1. Install `http-bootstrap.conf` as
   `/etc/nginx/sites-available/msgvault.beachlab.org`, enable its symlink, and
   run `nginx -t` before reloading. This serves only ACME challenges.
2. Issue the certificate with the existing Certbot account:
   `sudo certbot certonly --webroot -w /var/www/letsencrypt --cert-name msgvault.beachlab.org -d msgvault.beachlab.org --non-interactive`.
3. Create `/etc/nginx/snippets/msgvault-api-key.conf` as root, mode 0600,
   containing `proxy_set_header X-API-Key "<server.api_key>";` with the current
   key from the data configuration. Do not paste the key into shell history.
4. Install `msgvault.beachlab.org.conf` over the bootstrap, validate and reload
   Nginx. Keep a private copy of the previous file for rollback.
5. Install `50-msgvault-nginx` as the executable Certbot deploy hook. The
   existing `certbot.timer` renews the certificate; this hook validates and
   reloads Nginx only for msgvault's renewed lineage.

The first deployment's private backups are under `/opt/msgvault/backups/`:
the Authentik inventory, initial backend configuration and HTTP bootstrap.
Check current ownership/state before restoring them. A backend rollback to
the first configuration would reopen the initial Tailscale listener.

## Checks

Verified on 2026-10-10: systemd enabled/running, loopback listener, SQLite
`PRAGMA quick_check` returned `ok`, DuckDB cache initialized, and the public
certificate matched `msgvault.beachlab.org`. Unauthenticated requests to the
UI, API, health, OpenAPI and assets returned a redirect into Authentik, including
requests presenting the backend key or forged identity/forwarding headers.
Foreign-origin mutations returned 403. Direct Tailscale access to port 8096
failed after moving the listener to localhost.

The provider uses the existing WebAuthn-only flow with required user
verification, and its application has only Fran's access binding. Backend
requests carrying Nginx's key and HTTPS headers reported `auth_mode=api_key`,
`https=true`, no plain-HTTP warning, and zero archived messages/accounts.
Native Safari requested Touch ID for Fran's existing passkey, then loaded the
authenticated msgvault Settings page without a second API-key login.
Source: live Authentik API readback, NUC systemd/socket/SQLite checks, and HTTPS
requests from the Mac.
