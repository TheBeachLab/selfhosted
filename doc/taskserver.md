# Taskwarrior, TaskChampion and Nextcloud Tasks

## Active setup

The NUC (`ssh pink-sudo`, host `thebeachlab`) and Mac use **Taskwarrior 3.5.0**.
The NUC hosts **TaskChampion Sync Server 0.7.1** and the **syncall 1.8.8**
CalDAV adapter. These were the latest stable Taskwarrior/server releases checked
on 2026-09-13: [Taskwarrior release](https://github.com/GothenburgBitFactory/taskwarrior/releases/tag/v3.5.0),
[TaskChampion server release](https://github.com/GothenburgBitFactory/taskchampion-sync-server/releases/tag/v0.7.1).

```text
Mac Taskwarrior <-> TaskChampion (via SSH) <-> NUC Taskwarrior <-> syncall <-> Nextcloud Tasks <-> Apple Reminders
```

TaskChampion syncs encrypted Taskwarrior replicas; it does **not** replace the
CalDAV bridge. Its [sync configuration](https://taskwarrior.org/docs/man/task-sync.5/)
uses a server URL, client ID and encryption secret. Nextcloud and Apple Reminders
use CalDAV, so syncall remains necessary for this workflow.

Apple Reminders must use the Nextcloud account's lists. This does not bridge
separate iCloud lists. See [Apple's CalDAV account guide](https://support.apple.com/en-ie/guide/iphone/iph8739025dd/ios)
and [Nextcloud's compatible clients](https://github.com/nextcloud/tasks/blob/main/README.md).
Apple-device UI behavior and notifications have not been tested in this setup.

## Daily use

On the Mac:

```sh
task next
task projects
task add "My task"                 # defaults to NC.Quick_Reminder
task 123 done
task sync
```

On the NUC use `task-nc` instead of `task`; it selects the bridge replica and
runs as `taskmaster`. Each list has a mapped `NC.*` project. The mapping records
exact collection URLs, so duplicate display names remain distinct.

The Mac sync LaunchAgent runs every 120 seconds while logged in. The NUC timer
runs two minutes after the previous bridge invocation finishes. The bridge
pulls from TaskChampion, reconciles CalDAV, then pushes to TaskChampion, all
under an exclusive lock. Propagation across the whole chain can take several
minutes. Local Taskwarrior commands work offline against the last synced data.
For an immediate round trip:

```sh
task sync
ssh pink-sudo 'sudo systemctl start nextcloud-taskwarrior.service'
task sync
```

If both Nextcloud and the NUC replica changed since bridge synchronization,
**Nextcloud wins**. Missing collections and failed reads fail the run rather
than being interpreted as empty lists. Collection URLs are fixed; new lists
must be deliberately added to the mapping.

## Versions and installation

The Mac binary is managed by Homebrew (`brew install task`), available at
`/opt/homebrew/bin/task`. `~/.local/bin/task` points to it too, avoiding ambiguity
with the earlier private 2.6.2 build. The Mac configuration is `~/.taskrc`.
LaunchAgents live under `~/Library/LaunchAgents`:

- `com.beachlab.taskwarrior-tunnel`: SSH forwarding
  `127.0.0.1:53590` to NUC `127.0.0.1:53590` through `pink-sudo`.
- `com.beachlab.taskwarrior-sync`: Homebrew Taskwarrior sync every 120 seconds.

Logs live under `~/Library/Logs/Taskwarrior`. The versioned
[agent installer](../scripts/taskwarrior/install_macos_agents.py) requires
`--replace-existing` when upgrading an existing definition and saves the old
plist before replacement. Binary and credentials must already be provisioned.

Ubuntu's repository only provided Taskwarrior 2.6.1, so the NUC's 3.5.0 binary
was built from official tag `v3.5.0`, commit
`3419d5ba1e6a780fbbb0a8d68d8fd31e675c1bf8`, with its pinned submodules, into
`/opt/taskwarrior-3.5.0`. Build commands use two jobs and nice priority to limit
impact. The actual taskchampion-lib submodule requires Rust 1.91.1, despite the
root INSTALL file mentioning 1.88.0. `/usr/local/bin/task` selects this build. CMake 3.24+ is required; 3.31.10 was used.
Rust's `rust-src` component must be installed before starting parallel builds.

```sh
# As taskmaster, after installing Rust 1.91.1 + rust-src and CMake 3.31.10:
git clone --branch v3.5.0 --depth 1 --recurse-submodules --shallow-submodules \
  https://github.com/GothenburgBitFactory/taskwarrior.git ~/taskwarrior-3.5.0
cmake -S ~/taskwarrior-3.5.0 -B ~/taskwarrior-3.5.0/build-stable \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/taskwarrior-3.5.0 \
  -DRust_TOOLCHAIN=1.91.1-x86_64-unknown-linux-gnu \
  -DCORROSION_TOOLS_RUST_TOOLCHAIN=1.91.1-x86_64-unknown-linux-gnu
CARGO_BUILD_JOBS=2 nice -n 10 cmake --build ~/taskwarrior-3.5.0/build-stable -j2
sudo cmake --install /home/taskmaster/taskwarrior-3.5.0/build-stable
```

TaskChampion runs as container `taskchampion-nextcloud` using the official image
pinned to 0.7.1 and digest
`sha256:7903477ff4857cc7c702377d1c93a3f6703eed2f89e1733400b8599a4d0bb1bc`.
The [Compose definition](../scripts/taskwarrior/taskchampion-compose.yaml)
is installed at `/home/taskmaster/taskchampion/compose.yaml`. It runs directly
as UID/GID 1001 (taskmaster) against a pre-owned directory; the image's default
root chown entrypoint is unnecessary. The listener is published only on
127.0.0.1:53590. SSH supplies transport protection; Taskwarrior also encrypts
payloads. One allowed client ID is configured in the private server.env.
No public firewall port was opened.

```sh
ssh pink-sudo 'sudo docker compose -f /home/taskmaster/taskchampion/compose.yaml ps'
ssh pink-sudo 'sudo systemctl status nextcloud-taskwarrior.timer'
ssh pink-sudo 'sudo journalctl -u nextcloud-taskwarrior.service -n 30 --no-pager'
launchctl print gui/$(id -u)/com.beachlab.taskwarrior-tunnel
launchctl print gui/$(id -u)/com.beachlab.taskwarrior-sync
```

## Bridge compatibility and limits

The [adapter](../scripts/taskwarrior/sync_nextcloud.py) explicitly scopes bubop's
preferences factory because bubop 0.1.12 ignores XDG_CONFIG_HOME. Existing
`~/.config/syncall` mappings were moved into the replica backup boundary. A
mapped UUID missing from the local replica stops the run before reconciliation;
an empty or incorrectly selected database must not become mass deletion.
The adapter uses syncall's identity
mapping/change-detection engine, with typed VTODO serialization and URI-based
collection selection. Unmodified syncall 1.8.8 wrote an invalid empty PRIORITY
when editing an unprioritized task, causing the next read to fail. Its taskw-ng
library also retained removed tags. The adapter corrects those tested problems;
do not invoke plain `tw_caldav_sync` against the managed replica.

Supported fields include title, completion, notes/annotations, priority, tags,
and deadlines. Date-only deadlines remain dates. Remote alarms, Apple properties
and other unsupported metadata are preserved on edits. Priority maps to H/M/L:
CalDAV 1-4 -> H, 5 -> M, 6-9 -> L; Taskwarrior writes those as 1/5/9.

Recurrence, waiting/scheduling semantics, dependencies and subtask hierarchy are
not bridged. New recurring items stop that collection's sync for review. The
one pre-existing completed task in `NC.Lista_Con_Fran` had its expired recurrence
removed at the user's request on 2026-09-13; no tasks remain excluded. Renaming
mapped projects, moving tasks between projects, and deleting whole lists are
not validated workflows.

## Data and recovery

| Path | Purpose |
|---|---|
| `/home/taskmaster/nextcloud-sync/data` | NUC Taskwarrior 3 replica |
| `/home/taskmaster/nextcloud-sync/config` | Syncall identity mappings and previous-state cache |
| `/home/taskmaster/nextcloud-sync/settings.json` | Collection mapping and TaskChampion sync switch |
| `/home/taskmaster/nextcloud-sync/taskrc` | NUC config, including private sync credentials |
| `/home/taskmaster/nextcloud-sync/app-password` | Nextcloud credential, mode 0600 |
| `/home/taskmaster/taskchampion/data` | TaskChampion server SQLite data |
| `/home/taskmaster/taskchampion/client.json` | Private client ID/encryption secret provisioning record |
| `/home/taskmaster/nextcloud-sync/initial-caldav-backup` | Initial 1,462 VTODOs before installation |
| `/home/taskmaster/nextcloud-sync/before-recurrence-removal.ics` | Original completed recurring task |
| `/var/backups/taskwarrior-nextcloud/before-sync-20260913.sql` | Original calendar table dump, root-only |
| `/home/taskmaster/nextcloud-sync/backups` | Daily pre-sync replica/config snapshots, latest 14 days with runs |

Keep Taskwarrior data and syncall state together. Removing mappings can duplicate
or mis-reconcile tasks. The daily snapshot uses SQLite's online backup API for the v3 database.
Local snapshots are not off-host backups. Stop sync
schedules and wait for active runs before restoring. Taskwarrior 3 SQLite files
must not be synchronized through file-copy tools; use TaskChampion. For a manual
snapshot, stop writers first or use SQLite's backup facilities. Keep the
TaskChampion client ID and encryption secret in a secure backup too.

The original legacy `taskd.service` and its historical data remain untouched.
The Ubuntu 2.6 package was removed after preserving its binary in
`migration-v3/task-2.6.1`. The short-lived `taskd-nextcloud.service` is disabled.
The 2.6 setup was superseded by
TaskChampion; old data/configuration are retained only as migration backups.
The server migration imports v2 data once; the Mac starts as an empty v3 replica
and downloads via TaskChampion to avoid creating competing imported histories.
The existing task UUIDs and syncall mappings are retained.
The one-time [migration script](../scripts/taskwarrior/migrate_server_v3.py)
retains `migration-v3/` and `data-v2-20260913/` on the NUC. The Mac retains
`~/.task-migration-3.5.0/` and `~/.task-v2-20260913/`. Source fields and UUIDs
were compared before/after import. During cutover, a shell command incorrectly
continued after the migration script failed its state-path check. The brief
run against an empty v3 replica soft-deleted 115 tasks. All 115 were matched
by original Taskwarrior and CalDAV UUIDs, restored using Nextcloud's own
CalDAV restore backend, and restored in Taskwarrior with their original
contents/statuses and mappings. Content hashes alone do not detect soft
deletions: final checks also cover live/deleted state and all 1,462 tasks.
The adapter now explicitly scopes its state, blocks a missing mapped replica,
and has an integration test proving that this case cannot delete remote tasks.
Recovery evidence is retained under `migration-v3/recovery-plan.json`. Run migration/deployment commands with fail-fast error handling; never activate
a new adapter after a failed migration. Back up and coordinate both replicas
before any future migration.

## Verified result (2026-09-13)

Taskwarrior 3.5.0 on both hosts and TaskChampion Sync Server 0.7.1 are active.
Post-recovery checks verified all **1,462 non-deleted tasks**, including **214
pending** and **1,248 completed**, with original UUIDs and source fields
(except modification timestamps changed by recovery). Every live Nextcloud UID
matches its mapped Taskwarrior UUID. A full subsequent reconciliation succeeded.

The [round-trip integration test](../scripts/taskwarrior/test_roundtrip.py)
passed on 3.5 for creation, editing, completion/reopening, deletion, priority,
date-only deadlines, and clearing tags/deadlines. It also proves an empty
replica cannot delete mapped Nextcloud tasks. Mac creation reached Nextcloud
through TaskChampion, and Nextcloud completion returned to the Mac; the test
task was then deleted. A production SQLite backup passed integrity_check and
contained the scoped syncall state. No Apple-device UI test is claimed.

## Historical taskd installation reference

The following is the original setup, retained for the already-running service.
It is not the Nextcloud bridge installation procedure. Taskwarrior 3 uses a
different sync implementation and cannot use taskd; see the
[official upgrade guide](https://taskwarrior.org/docs/upgrade-3/).




It is a bit tedious but worth it

## Prerrequisites

```bash
sudo apt install g++
sudo apt install libgnutls28-dev
sudo apt install uuid-dev
sudo apt install cmake
sudo apt install gnutls-bin
```

## Install the server

```bash
sudo adduser taskmaster
usermod -aG sudo taskmaster
su taskmaster
git clone --recurse-submodules=yes https://github.com/GothenburgBitFactory/taskserver.git taskserver.git
cmake -DCMAKE_BUILD_TYPE=release .
make
cd test
make
./run_all
cd ..
sudo make install
```

## Configure the server

```bash
export TASKDDATA=~/taskd
mkdir -p $TASKDDATA
cd taskserver.git
cp -R pki ~/taskd
taskd init
nano ~/taskd/pki/vars
```

In `vars` we have information about the server

```bash
BITS=4096
EXPIRATION_DAYS=3650
ORGANIZATION="The Beach Lab"
CN=beachlab.org
COUNTRY=ES
STATE="Barcelona"
LOCALITY="Sitges"
```

Generate and install the server certificates

```bash
./generate
cp client* $TASKDDATA
cp server* $TASKDDATA
cp ca.cert.pem  $TASKDDATA
taskd config --force client.cert $TASKDDATA/client.cert.pem
taskd config --force client.key  $TASKDDATA/client.key.pem
taskd config --force server.cert $TASKDDATA/server.cert.pem
taskd config --force server.key  $TASKDDATA/server.key.pem
taskd config --force server.crl  $TASKDDATA/server.crl.pem
taskd config --force ca.cert  $TASKDDATA/ca.cert.pem
```

Configure the server settings

```bash
taskd config --force log $PWD/taskd.log
taskd config --force pid.file $PWD/taskd.pid
taskd config --force server localhost:53589
cd /home/taskmaster/taskserver.git/scripts/systemd/
cp /home/taskmaster/taskserver.git/scripts/systemd/taskd.service ~
```

Edit the service daemon `nano taskd.service`

```bash
[Unit]
Description=Secure server providing multi-user, multi-client access to task data
Requires=network.target
After=network.target
Documentation=http://taskwarrior.org/docs/

[Service]
ExecStart=/usr/local/bin/taskd server --data /home/taskmaster/taskd
Restart=on-abort
Type=simple
User=taskmaster
Group=taskmaster
WorkingDirectory=/home/taskmaster/taskd
PrivateTmp=true

[Install]
WantedBy=multi-user.target
cp taskd.service /etc/systemd/system
systemctl daemon-reload
systemctl start taskd.service
systemctl status taskd.service
systemctl enable taskd.service
systemctl enable taskd.service
```

## Generate certificate files for each client

Add org and users

```bash
taskd add org TBL --data ~/taskd
taskd add user 'TBL' 'Fran Sanchez' --data ~/taskd
cd taskd/pki
./generate.client fran_sanchez
```

This will generate a certificate and a private key for the user fran_sanchez

## Copy the certificates to the client machine/device (taskwarrior)

Remember taskmaster user must have keys in .ssh folder and 2FA enabled

```bash
scp -P 622 taskmaster@beachlab.org:/home/taskmaster/taskd/pki/fran_sanchez.cert.pem ~/.task
scp -P 622 taskmaster@beachlab.org:/home/taskmaster/taskd/pki/fran_sanchez.key.pem ~/.task
scp -P 622 taskmaster@beachlab.org:/home/taskmaster/taskd/pki/ca.cert.pem ~/.task
```

Add the certificates to taskwarrior

```bash
task config taskd.certificate -- ~/.task/fran_sanchez.cert.pem
task config taskd.key -- ~/.task/fran_sanchez.key.pem
task config taskd.ca -- ~/.task/ca.cert.pem
```

Set the server parameters

```bash
task config taskd.server      -- beachlab.org:53589
task config taskd.credentials -- TBL/Fran Sanchez/YOUR-CREDENTIALS-HERE
```
Credentials where shown when creating the user.

## Sync

`task sync`

