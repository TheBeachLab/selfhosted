# Backups with rsnapshot

**Author:** Fran / updated Mr. Watson 🦄 (2026-07-18)

> There’s no feeling more intense than starting over. If you've deleted your homework the day before it was due, as I have, or if you left your wallet at home and you have to go back, after spending an hour in the commute, if you won some money at the casino and then put all your winnings on red, but it came up black, if you got your best shirt dry-cleaned before a wedding and then immediately dropped food on it, if you won an argument with a friend and then later discovered that they just returned to their original view, starting over is harder than starting up.
>
> From the videogame "Getting Over It with Bennett Foddyd"

<!-- vim-markdown-toc GFM -->

- [Optional. Accessing NFS drives](#optional-accessing-nfs-drives)
- [Install and setup rsnapshot](#install-and-setup-rsnapshot)
- [Current production setup: Restic](#current-production-setup-restic)

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
- Git repositories, OpenClaw state, Minecraft, Gotify, Grafana, OpenHAB,
  Headscale, Mosquitto, and all web/Nextcloud data.

Retention is 7 daily, 4 weekly, and 6 monthly snapshots. Every run prunes old
data and checks 5% of repository data.

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
