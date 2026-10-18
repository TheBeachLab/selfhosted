# Obsidian

Strategy syncs between the Mac and mobile Obsidian through CouchDB on the NUC.
The desktop app opens the existing Markdown vault; the NUC stores the encrypted
synchronisation database. There is no remote desktop installation of Obsidian.

[Personal knowledge: Strategy](personal-knowledge.md) explains the authoritative
notes, source catalogue, Msgvault archive and complete recovery requirements.

| Item | Location |
| --- | --- |
| Mac vault | `/Users/Papi/Repositories/project-knowledge/vaults/strategy/` |
| HTTPS endpoint | `https://api.beachlab.org/obsidian-sync` |
| Database / device account | `strategy` / `strategy-sync` |
| NUC container / local listener | `obsidian-couchdb` / `127.0.0.1:15984` |
| Deployment | `/opt/obsidian-sync/` |
| Persistent data and CouchDB configuration | `/var/lib/obsidian-sync/` |

## Mac and mobile

[Self-hosted LiveSync 1.0.38](https://github.com/vrtmrz/obsidian-livesync/releases/tag/1.0.38)
is installed in Strategy. The three release assets were checked against the
SHA-256 digests returned by GitHub's release API. LiveSync and sync on startup
are enabled, with background replication enabled on the Mac. Obsidian must be
running to exchange local file changes; reopening it scans changes made while
it was closed. Hidden File Sync and Customisation Sync are disabled.

The connection uses HTTPS and a database member account with no server
administrator role. Note content, paths and internal metadata use LiveSync's
end-to-end encryption. The encryption key is held by the devices, separately
from the NUC administrator credentials. The plugin's local data file is ignored
by Git and restricted to the Mac user.

Mobile setup files are private, outside both repositories and the vault:

```text
/Users/Papi/Library/Application Support/ProjectKnowledge/obsidian-sync/
  mobile-setup-qr.png
  mobile-setup-uri.txt
  mobile-connection-private.txt
```

The last file contains the device credentials, note-encryption key and separate
Setup URI password. The encrypted QR and URI have no expiry. Keep their password
separately when transferring them. No onboarding file is served by the web server.

1. Create an empty local vault called `Strategy` on the phone. On iPhone, leave
   **Store in iCloud** off.
2. Enable community plugins and install **Self-hosted LiveSync**.
3. From the welcome notice, choose **I am adding a device to an existing
   synchronisation setup**, then **Use a Setup URI**. Import the saved URI and
   enter its password. The system camera can also open its QR link after the
   plugin is enabled.
4. Choose **Restart and Fetch Data**. In the new empty vault choose
   **Overwrite all with remote files**, then **Keep local files even if not on
   remote**.
5. Keep Obsidian open until its progress indicators clear. Check `Fran`, create
   a mobile note, and confirm that it reaches the Mac.

Use the same configuration on iOS or Android. Mobile synchronisation cannot be
assumed to run while the operating system suspends the app. Do not enable another
sync service on the same vault. Follow the upstream
[device setup workflow](https://github.com/vrtmrz/obsidian-livesync/blob/1.0.38/docs/quick_setup.md).

## NUC deployment

[Compose](../services/obsidian-sync/compose.yaml) pins the official
[CouchDB 3.5.3](https://docs.couchdb.org/en/stable/whatsnew/3.5.html#version-3-5-3)
image by digest, runs as UID 5984 and binds only to loopback. Limits are 768 MiB,
one CPU and 256 tasks. Docker restarts the container after host reboot.

[install.py](../services/obsidian-sync/install.py) provisions a new installation
only. It refuses existing deployment paths or an unexpected API vhost. It
creates separate administrator and device credentials, restricts database
membership, backs up the vhost and validates Nginx before reloading it. The
administrator files are root-only under `/root/.config/obsidian-sync/`; the
Compose environment is `/opt/obsidian-sync/.env`.

[nginx.conf](../services/obsidian-sync/nginx.conf) is included in the existing
HTTPS `api.beachlab.org` vhost. It preserves encoded document IDs, disables
proxy buffering and permits 50 MiB requests. The existing certificate and its
renewal are reused. CouchDB handles API authentication; interactive login
redirects are unsuitable for replication. CORS is restricted to the documented
Obsidian origins in [local.ini](../services/obsidian-sync/local.ini). See the
[upstream server requirements](https://github.com/vrtmrz/obsidian-livesync/blob/1.0.38/docs/setup_own_server.md).

```bash
ssh pink-sudo
sudo docker compose -f /opt/obsidian-sync/compose.yaml ps
sudo docker logs --tail 50 obsidian-couchdb
sudo nginx -t
systemctl list-timers obsidian-sync-backup.timer
```

An unauthenticated `GET https://api.beachlab.org/obsidian-sync/strategy` must
return **401**. The device account can read and write `strategy`, but cannot
read server configuration. Keep port 15984 private.

## Backups and recovery

A complete Mac vault archive was taken before enabling LiveSync. It is retained
in the private Mac directory above as `strategy-before-livesync-*.tar.gz`.

[backup.py](../services/obsidian-sync/backup.py) stops only the CouchDB container
briefly, copies its data and configuration, and restarts it in a `finally`
block. It then writes the capture to the encrypted NAS repository:

```text
/mnt/nas-downloads/backups/obsidian-sync-restic
```

It verifies the expected Synology NFS mount and repository identity before
writing. It reuses the root-only Restic password and NAS recovery copy described
in [Backups](backups.md). The daily timer runs at 02:55 Europe/Madrid with up to
five minutes of jitter. Retention is 7 daily, 4 weekly and 6 monthly snapshots.

```bash
sudo cat /var/lib/obsidian-sync-backup/last-success.json
sudo journalctl -u obsidian-sync-backup.service -n 50 --no-pager
```

To create a new backup and test its restored files, run
`sudo python3 /opt/obsidian-sync/backup.py --verify-restore` during an agreed
maintenance window. This briefly stops CouchDB; it is not a read-only check of
the last snapshot. The scheduled run does not pass this option. Its private
local capture remains under `/var/lib/obsidian-sync-backup/payload/`.

### Restore CouchDB

Keep Obsidian clients disconnected and save their local vaults before recovering
an older sync database. In a root Bash shell on the NUC, restore an explicit
snapshot into a fresh directory:

```bash
set -euo pipefail
umask 077
export RESTIC_REPOSITORY=/mnt/nas-downloads/backups/obsidian-sync-restic
export RESTIC_PASSWORD_FILE=/root/.config/thebeachlab-backup/restic-password
restic snapshots --tag obsidian-sync
read -r -p 'CouchDB snapshot ID: ' obsidian_snapshot
test -n "$obsidian_snapshot"
obsidian_restore_dir=$(mktemp -d /var/tmp/obsidian-restore-XXXXXX)
restic restore "$obsidian_snapshot" --target "$obsidian_restore_dir"
obsidian_payload="$obsidian_restore_dir/var/lib/obsidian-sync-backup/payload"
test -d "$obsidian_payload/couchdb/data"
```

The payload contains:

- `couchdb/`: all of `/var/lib/obsidian-sync/`, including database shards and
  `etc/10-livesync.ini` and CouchDB's generated configuration.
- `deployment/`: `/opt/obsidian-sync/`, including Compose and its private `.env`.
- `administration/`: `/root/.config/obsidian-sync/`, including the matching
  administrator and device accounts.
- `nginx.conf`: the `/etc/nginx/snippets/obsidian-sync.conf` proxy snippet.

After inspecting the restored capture, activate it in a maintenance window:

1. Stop `obsidian-sync-backup.timer` and wait for any running backup service to
   finish. Stop `obsidian-couchdb`. Preserve the current data, deployment and
   administrator directories by moving them to a private recovery directory;
   do not merge a restored database into live files.
2. Copy the three payload directories back to their corresponding locations
   with `cp -a`. Restore ownership with
   `chown -R 5984:5984 /var/lib/obsidian-sync/data /var/lib/obsidian-sync/etc`.
   Preserve the root-only modes on `.env` and administrator files.
3. Restore/review the proxy snippet, keep its include in the API vhost and run
   `nginx -t` before reloading Nginx. On a replacement NUC, also recover its TLS
   configuration and the backup units from the general server backup or
   [service files](../services/obsidian-sync/).
4. Run `docker compose -f /opt/obsidian-sync/compose.yaml up -d --force-recreate couchdb`.
   Check container health, authenticated access to `strategy` and a 401 response
   without credentials. Credentials must come from the restored private files;
   never paste them into documentation or a chat.
5. Fetch into a new empty Obsidian vault using the saved device encryption key.
   Check `Fran` and representative notes, then reconcile newer edits from the
   preserved device copies before reconnecting the other clients.
6. Restore the backup script's repository identity record before restarting
   `obsidian-sync-backup.timer` on a replacement host; see
   [backup recovery state](personal-knowledge.md#the-nuc-or-a-service-database-was-lost).
   Keep the previous live directories until validation is complete.

The server backup cannot decrypt notes without the devices' separate encryption
key. It also excludes the Mac's source catalogue, Git history and linked external
documents. See [complete recovery](personal-knowledge.md#recovering-the-system) and
[CouchDB backups](https://docs.couchdb.org/en/stable/maintenance/backups.html).

## Verification on 2026-10-18

- HTTPS authenticated access returned 200; unauthenticated access and attempts
  by the device account to read administrator configuration returned 401.
- CORS accepted the three Obsidian origins and rejected an unrelated origin.
- A fresh server read reconstructed all 421 current files with no differences
  from the Mac. Concurrent authorised note changes were retained.
- Two disposable notes verified automatic upload, an encrypted server-side
  edit and automatic download. The test notes were then moved to Trash.
- Restic snapshot `e9f95aa5` was restored into a temporary directory; every
  captured file matched its SHA-256 hash. The temporary restore was removed.
- The encrypted mobile URI was decoded locally and its endpoint, credentials
  and encryption settings matched the active Mac configuration.

LiveSync needed a plugin reload after first configuration to activate file
watching. Automatic upload/download then passed. Receipts are in the private
Mac setup directory. The actual phone remains to be connected by its owner.

## Notes and graph

Strategy is the curated personal knowledge vault, entered through `Fran.md`.
Its notes can be edited directly. Hariburi is a separate local vault at
`/Users/Papi/Repositories/project-knowledge/vaults/hariburi/`; its generated
`Fuentes/` pages are read-only source views and are not part of this sync.

Markdown `[[links]]` form Obsidian's [graph](https://help.obsidian.md/plugins/graph).
[Canvas](https://help.obsidian.md/plugins/canvas) stores arranged notes and
connections in `.canvas` files. Project Knowledge's `AGENTS.md` governs source
edits and indexing.
