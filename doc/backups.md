# Backups with rsnapshot

**Author:** Fran / updated Mr. Watson 🦄 (2026-07-18)

> There’s no feeling more intense than starting over. If you've deleted your homework the day before it was due, as I have, or if you left your wallet at home and you have to go back, after spending an hour in the commute, if you won some money at the casino and then put all your winnings on red, but it came up black, if you got your best shirt dry-cleaned before a wedding and then immediately dropped food on it, if you won an argument with a friend and then later discovered that they just returned to their original view, starting over is harder than starting up.
>
> From the videogame "Getting Over It with Bennett Foddyd"

<!-- vim-markdown-toc GFM -->

- [Optional. Accessing NFS drives](#optional-accessing-nfs-drives)
- [Install and setup rsnapshot](#install-and-setup-rsnapshot)
- [Current production setup: Restic](#current-production-setup-restic)
- [Minecraft USB backups](#minecraft-usb-backups)

<!-- vim-markdown-toc -->

## Optional. Accessing NFS drives

Assuming here you have a NAS or similar with NFS and appropiate user/permissions set. In ubuntu server install the nfs tools:

```bash
sudo apt update
sudo apt install nfs-common
```

Create the local mountpoint `sudo mkdir -p /mnt/backups`

Mount the NFS shared folder `sudo mount 192.168.1.100:/volume1/backups/ubuntu-server /mnt/backups` (your NFS IP and shared volume will differ). Confirm that the drive is mounted `df –h`

```bash
Filesystem                                    Size  Used Avail Use% Mounted on
udev                                          3.8G     0  3.8G   0% /dev
tmpfs                                         786M  1.2M  785M   1% /run
/dev/sda2                                     469G   12G  434G   3% /
tmpfs                                         3.9G     0  3.9G   0% /dev/shm
tmpfs                                         5.0M     0  5.0M   0% /run/lock
tmpfs                                         3.9G     0  3.9G   0% /sys/fs/cgroup
192.168.1.100:/volume1/backups/ubuntu-server  2.7T  1.7T  1.1T  61% /mnt/backups
tmpfs                                         786M     0  786M   0% /run/user/1000
```

Test your write permissions

```bash
cd /mnt/backups
touch test
```

Check on the NFS server that the file is actually there. Now you can automate this to mount at boot time. Add this entry in `/etc/fstab`

`192.168.1.100:/volume1/backups/ubuntu-server /mnt/backups nfs defaults 0 0`

Next time you start your machine the NFS share will be automatically mounted at the specified mount point.

## Install and setup rsnapshot

rsnapshot is a **backup tool based on rsync**. It's fast and can do incremental backups. Install rsnapshot `sudo apt install rsnapshot` and configure it `sudo nano /etc/rsnapshot.conf`. The most important thing to remember is **use tabs instead of spaces to separate keys and values**. Set your intervals and folders to backup. I have created 7 `beta` which I will use for the daily backups and 4 `gamma` that I will use for the weekly backups. At the moment I do not need to create any hourly backup. Also specify what to backup. rsnapshot can backup from anything to anything. In my case I hace rsnapshot locally installed and I am pushing the backups to a NFS. But I could also use a remote server with rsnapshot to pull my files via ssh.

After saving the configuration file check for errors `rsnapshot configtest`. It is advisable also to dry-run test the backup levels/intervals specified in the config file `rsnapshot -t beta`.

Automate your backups in ` crontab -e` **as the root user**

```bash
@daily /usr/bin/rsnapshot beta &> /dev/null
@weekly /usr/bin/rsnapshot gamma &> /dev/null
```

> Make sure that root will have read/write **and admin (change permissions, take ownership)** permissions on the NFS drive. Otherwise you will get errors like:
> `/bin/cp: failed to preserve ownership for '/mnt/backups/alpha.1/localhost/var': Operation not permitted`

## Current production setup: Restic

The active server backup uses Restic against the Synology NFS mount at
`/mnt/nas-downloads`. It replaces the old disabled rsnapshot cron entries.

Main files:

```bash
/usr/local/sbin/thebeachlab-backup
/etc/systemd/system/thebeachlab-backup.service
/etc/systemd/system/thebeachlab-backup.timer
```

The repository is encrypted and stored at:

```bash
/mnt/nas-downloads/backups/thebeachlab-restic
```

The host password copy is root-only. A recovery copy is stored beside the
repository on the NAS and is protected by the NAS share permissions:

```bash
/root/.config/thebeachlab-backup/restic-password
/mnt/nas-downloads/backups/thebeachlab-restic-password
```

The backup runs every day around `03:10 UTC` with a randomized delay of up to
10 minutes. It includes:

- all PostgreSQL databases plus global roles;
- `/etc`, `/usr/local/bin`, and `/usr/local/etc`;
- Git repositories, OpenClaw state, Minecraft server files and its consistent
  world archives, Gotify, Grafana, OpenHAB, Headscale, Mosquitto, and all
  web/Nextcloud data;
- custom administration scripts in both `/usr/local/bin` and
  `/usr/local/sbin`.

Retention is 7 daily, 4 weekly, and 6 monthly snapshots. Every run prunes old
data and checks 5% of repository data. Transient caches, logs, crash reports,
and Nextcloud's obsolete updater copies are excluded.

On 2026-07-18, 15 GB of obsolete Nextcloud updater backups (versions 23 to 30)
were removed from the live filesystem. The updater workspace was preserved and
Nextcloud 31.0.14 remained healthy. The first Restic snapshot still contains
those files until normal retention removes that snapshot.

Run and inspect:

```bash
sudo systemctl start thebeachlab-backup.service
systemctl status thebeachlab-backup.service
sudo journalctl -u thebeachlab-backup.service -n 100 --no-pager
systemctl list-timers thebeachlab-backup.timer
```

List snapshots:

```bash
sudo env \
  RESTIC_REPOSITORY=/mnt/nas-downloads/backups/thebeachlab-restic \
  RESTIC_PASSWORD_FILE=/root/.config/thebeachlab-backup/restic-password \
  restic snapshots
```

Test a restore into a temporary directory:

```bash
sudo mkdir -p /var/tmp/restic-restore-test
sudo env \
  RESTIC_REPOSITORY=/mnt/nas-downloads/backups/thebeachlab-restic \
  RESTIC_PASSWORD_FILE=/root/.config/thebeachlab-backup/restic-password \
  restic restore latest --target /var/tmp/restic-restore-test \
  --include /etc/ssh/sshd_config
sudo test -s /var/tmp/restic-restore-test/etc/ssh/sshd_config
sudo rm -rf /var/tmp/restic-restore-test
```

The script refuses to run if `/mnt/nas-downloads` is not an NFS mount, so a
NAS outage cannot silently fill the local root filesystem.

## Minecraft USB backups

The Minecraft Java world also has a fast restore copy on a dedicated Kingston
DataTraveler. This complements Restic; it does not replace the NAS history.

Drive and mount:

```text
UUID:        FEF9-F572
Filesystem:  exFAT
Mount:       /mnt/minecraft-backups
```

`/etc/fstab` uses `x-systemd.automount`, a 60-second idle timeout, and `nofail`,
so the server still boots when the drive is absent. Keep the drive in the safe
USB port. The udev rule in `services/99-left-front-usb.rules` explicitly excludes
this drive's serial number from the destructive left-front `2usb` formatter.

Production files:

```text
/usr/local/sbin/mc-usb-backup
/etc/systemd/system/mc-usb-backup.service
/etc/systemd/system/mc-usb-backup.timer
/etc/udev/rules.d/99-left-front-usb.rules
```

Repository sources:

```text
services/mc-usb-backup
services/mc-usb-backup.service
services/mc-usb-backup.timer
services/99-left-front-usb.rules
```

The timer runs daily at `02:45 UTC` with up to five minutes of jitter, before
the Restic timer at `03:10 UTC`. It only creates a backup when `Fran90908` has
joined since the previous check. Activity is read from the systemd journal and
confirmed with the premium player-data modification time. A skipped run advances
the activity checkpoint; a failed run does not, so it retries later.

Discord notifications use the dedicated world server channels:

```text
Status:   1536372549653635192
Backups:  1536373187259011134
```

The backup channel receives completed and failed runs, not no-activity skips.
The existing one-minute Minecraft watchdog reports actual service state changes
to the status channel.

Backup sequence:

1. Verify that the expected USB UUID is mounted, never the root filesystem.
2. Run `save-off` and `save-all flush` over local RCON.
3. Create and test a Zstandard tar archive, then immediately run `save-on`.
4. Hash the local archive, copy it to the USB, and hash the USB copy again.
5. Keep two archives on the USB and one local archive in
   `/opt/minecraft/backups/daily`.

The local archive is included by the regular Restic job, which provides the
longer 7-daily/4-weekly/6-monthly history. The USB remains intentionally short:
two known-good, directly restorable copies.

Inspect or trigger:

```bash
systemctl list-timers mc-usb-backup.timer
sudo systemctl start mc-usb-backup.service
sudo journalctl -u mc-usb-backup.service -n 100 --no-pager

# Ignore the activity check and create a backup now
sudo /usr/local/sbin/mc-usb-backup --force
```

Validate an archive without restoring it:

```bash
sha256sum -c world-YYYY-MM-DD_HHMMSSZ.tar.zst.sha256
tar --zstd -tf world-YYYY-MM-DD_HHMMSSZ.tar.zst >/dev/null
```

Restore only while Minecraft is stopped:

```bash
sudo systemctl stop minecraft-java.service
sudo tar --zstd -xf world-YYYY-MM-DD_HHMMSSZ.tar.zst -C /opt/minecraft/server
sudo chown -R minecraft:minecraft /opt/minecraft/server/Hariburi-World
sudo systemctl start minecraft-java.service
```
