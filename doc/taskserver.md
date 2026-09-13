# Taskwarrior and Nextcloud Tasks

**Author:** Fran

## Active Nextcloud bridge (2026-09-13)

The NUC (`ssh pink-sudo`, host `thebeachlab`) runs Taskwarrior **2.6.1** and
**syncall 1.8.8** in an isolated Python 3.10 environment under
`/home/taskmaster/nextcloud-sync`. The existing `taskd.service` remains running
with its historical data and configuration. This new replica is separate from
that legacy taskd dataset; it synchronizes directly with Nextcloud CalDAV.

```text
server Taskwarrior <-> syncall adapter <-> Nextcloud Tasks <-> Apple Reminders
```

Apple Reminders must use the **Nextcloud account's lists**. This does not bridge
iCloud lists. Apple lists CalDAV account support in its
[Reminders guide](https://support.apple.com/en-ie/guide/iphone/iph8739025dd/ios),
and [Nextcloud Tasks lists Apple Reminders as compatible](https://github.com/nextcloud/tasks/blob/main/README.md).
Apple-device round trips were not tested during this server installation.

### Use

SSH to the NUC, then:

```sh
task-nc next
task-nc projects
task-nc add "My new task"
task-nc 123 done
sudo systemctl start nextcloud-taskwarrior.service
sudo systemctl status nextcloud-taskwarrior.timer
sudo journalctl -u nextcloud-taskwarrior.service -n 30 --no-pager
```

`task-nc` runs the replica as `taskmaster` with the right configuration. New tasks
default to `NC.Quick_Reminder`. Each configured list maps to a separate `NC.*`
project; `settings.json` records its display name, immutable collection URL, and
project. Duplicate display names get distinct project names. No new network port
or taskd client registration is required for this bridge.

The system timer runs two minutes after each completed invocation. One process
holds an exclusive file lock. A failed collection read or conversion fails the
service; it is not treated as an empty task list. When both copies have changed,
**Nextcloud wins**. Changes flow both ways otherwise.

### Compatibility adapter and boundaries

[Upstream syncall CalDAV documentation](https://github.com/bergercookie/syncall/blob/master/docs/readme-tw-caldav.md)
describes bidirectional synchronization and excludes recurrence. Live testing of
unmodified 1.8.8 reproduced an invalid `PRIORITY:` on a task without a priority:
a subsequent read failed with `ValueError: Expected int, got:`. Do not use its
plain `tw_caldav_sync` command against this replica.

The versioned [adapter](../scripts/taskwarrior/sync_nextcloud.py) uses syncall's
matching/state engine with URI-based collection selection and valid typed VTODO
serialization. It preserves unsupported remote metadata (including alarms and
Apple properties), keeps date-only deadlines, detects priority/tag changes (including explicit removal of old tags, which
taskw-ng otherwise retains), and
maps completion timestamps. Priority maps to Taskwarrior H/M/L; CalDAV values
1-4 map to H, 5 to M, and 6-9 to L. A subsequent Taskwarrior edit normalizes these
to 1/5/9. Nextcloud notes map to Taskwarrior annotations.

- The initial inventory contains 1,462 tasks in 35 task-capable calendars.
  Initially, one completed recurring UID in `NC.Lista_Con_Fran` was excluded.
  On 2026-09-13 its expired daily recurrence was removed at the user's request,
  preserving its title and completed status, and the exclusion was removed.
  All 1,462 tasks are now in scope: 214 pending and 1,248 completed.
  Its original VTODO is saved as `before-recurrence-removal.ics` in the bridge directory.
  Initial import and a repeat sync succeeded; all 1,462 remote VTODO contents
  matched the pre-import backup (zero modifications or new resources).
- New recurrence in a configured collection stops that collection's sync for
  review. Taskwarrior recurrence, waiting/scheduling semantics, dependency and
  subtask hierarchy are not bridged.
- Collection creation/deletion and task moves between projects are not validated
  workflows. Add lists explicitly to the mapping after testing; do not rename
  mapped projects to move tasks. Missing collections are not recreated.
- Server-side tests establish CalDAV behavior, not notifications or UI behavior
  on a particular Apple device.

### Files, backup, and recovery

| Path | Purpose |
|---|---|
| `/home/taskmaster/nextcloud-sync/venv` | Isolated, pinned dependencies |
| `/home/taskmaster/nextcloud-sync/data` | Taskwarrior replica |
| `/home/taskmaster/nextcloud-sync/config` | Syncall identity mapping and previous-state cache |
| `/home/taskmaster/nextcloud-sync/settings.json` | Fixed list URLs, projects, recurrence exclusion |
| `/home/taskmaster/nextcloud-sync/app-password` | Dedicated Nextcloud app credential, mode 0600 |
| `/home/taskmaster/nextcloud-sync/initial-caldav-backup` | Original VTODO files before initial import |
| `/var/backups/taskwarrior-nextcloud/before-sync-20260913.sql` | Pre-install calendar table dump, root-only |
| `/home/taskmaster/nextcloud-sync/backups` | Once-daily pre-sync replica/config snapshots; latest 14 days with runs |

Keep the data directory **and syncall state together**. Removing the state can
cause duplicates or incorrect reconciliation. Snapshots are local recovery
copies, not off-host backups. Stop the timer and wait for the service to finish
before any restore. Restore only the intended records/resources after comparing
current data; do not overwrite the entire live Nextcloud database with the
partial table dump.

```sh
sudo systemctl disable --now nextcloud-taskwarrior.timer
# Inspect any active service before repairing/restoring state.
sudo systemctl status nextcloud-taskwarrior.service
```

### Reproduce and validate

Source templates live in [scripts/taskwarrior](../scripts/taskwarrior/).
The environment needed `typing_extensions` explicitly; old PyYAML requires
Cython <3 for a source build, and wheel <0.46 avoids a packaging dependency conflict.
The complete installed version set is in `requirements.lock`.

```sh
sudo apt-get install taskwarrior python3-venv
sudo -u taskmaster python3 -m venv /home/taskmaster/nextcloud-sync/venv
sudo -u taskmaster /home/taskmaster/nextcloud-sync/venv/bin/pip install 'Cython<3' 'wheel<0.46'
# Copy requirements.lock from this repository first.
sudo -u taskmaster /home/taskmaster/nextcloud-sync/venv/bin/pip install --no-build-isolation -r requirements.lock
```

Provision credentials with Nextcloud's `occ user:auth-tokens:add`, redirecting
output to a protected file and retaining only the generated token line. Never
commit or print the token. Inventory exact CalDAV URLs before writing settings;
list names alone are ambiguous on this server. A temporary collection could not
be created because Nextcloud returned `Calendar limit reached`; verification
used temporary, subsequently deleted tasks in the otherwise empty `Work FF` list.

`test_adapter.py` checks typed serialization, date conversion, and metadata
preservation. `test_roundtrip.py` requires a separately prepared test replica
and an otherwise empty test collection; it creates/edits/deletes test tasks.
It must never be pointed at the production mapping.

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

