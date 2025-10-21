# Auto Transfer contents to USB

- [Auto Transfer contents to USB](#auto-transfer-contents-to-usb)
  - [Install](#install)
  - [Prepare](#prepare)
- [Script](#script)
  - [systemd Service](#systemd-service)
  - [udev Rule](#udev-rule)


## Install
```bash
sudo apt update
sudo apt install -y exfatprogs rsync udisks2
```

## Prepare
Insert a USB in the left front side and check the ID_PATH:

```bash
dev=$(lsblk -dpno NAME,TRAN | awk '$2=="usb"{print $1; exit}')
udevadm info -q property -n "$dev" | grep ^ID_PATH=
```

Note the value:

`ID_PATH=pci-0000:00:14.0-usb-0:2:1.0-scsi-0:0:0:0` This is Left port  
`ID_PATH=pci-0000:00:14.0-usb-0:1:1.0-scsi-0:0:0:0` This is right port


Therefore for the left the wildcard value could be "*usb-0:2:*"


# Script
Generate a script in `/usr/local/bin/usb_left_copy.sh` and give permissions.

```bash
sudo tee /usr/local/bin/usb_left_copy.sh >/dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec >>/var/log/leftusb.log 2>&1
date +"--- %F %T leftusb start ---"

# lock para evitar concurrencia
exec 9>/run/leftusb.lock
flock -n 9 || { echo "locked"; exit 0; }

PATH=/usr/sbin:/usr/bin:/sbin:/bin
SRC="/home/pink/downloads/2usb"
MOVED="/home/pink/downloads/transferred"
MNT="/mnt/leftusb"

DEV="${1:-${DEVNAME:-}}"
[ -n "$DEV" ] || { echo "no DEV"; exit 0; }

notify(){ /usr/local/bin/notify.sh "$1" "" || true; }

mkdir -p "$MNT"
install -d -o pink -g pink "$MOVED"

notify "USB detected on $DEV"

# elegir target (partición 1 si existe)
TARGET="$DEV"; [ -b "${DEV}1" ] && TARGET="${DEV}1"

# desmontar si estaba montado
mountpoint -q "$MNT" && umount -f "$MNT" || true

# formatear exFAT
mkfs.exfat -n LEFTUSB "$TARGET" >/dev/null

# montar
mount -o uid=1000,gid=1000 "$TARGET" "$MNT"
notify "USB mounted"

# tamaños
need=$(du -sb "$SRC" 2>/dev/null | awk '{print $1+0}')
avail=$(df -B1 --output=avail "$MNT" | tail -1 | tr -d ' ')
if [ "${need:-0}" -le 0 ]; then
  sync; umount "$MNT"; udisksctl power-off -b "$DEV" >/dev/null 2>&1 || true
  notify "No data to transfer. Disk ejected"; exit 0
fi
if [ "$avail" -lt "$need" ]; then
  sync; umount "$MNT"; udisksctl power-off -b "$DEV" >/dev/null 2>&1 || true
  notify "USB too small. Disk Ejected"; exit 0
fi

notify "Copy started"
rsync -rlt --delete --inplace --no-perms --no-owner --no-group "$SRC"/ "$MNT"/

sync
umount "$MNT"
udisksctl power-off -b "$DEV" >/dev/null 2>&1 || true
notify "Copy finished. Disk ejected"

ts=$(date +%Y%m%d-%H%M%S)
mkdir -p "$MOVED"
mv "$SRC" "${MOVED}/2usb-${ts}"
chown -R pink:pink "$MOVED"
mkdir -p "$SRC"
date +"--- %F %T leftusb done ---"
EOF
```

```bash
sudo chmod +x /usr/local/bin/usb_left_copy.sh
sudo touch /var/log/leftusb.log && sudo chmod 644 /var/log/leftusb.log
```

## systemd Service
```bash
sudo tee /etc/systemd/system/leftusb@.service >/dev/null <<'EOF'
[Unit]
Description=Left-front USB workflow for %I
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/usb_left_copy.sh /dev/%I
TimeoutSec=0
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
EOF
````

And reload the daemon

`sudo systemctl daemon-reload`

## udev Rule
```bash
sudo tee /etc/udev/rules.d/99-left-front-usb.rules >/dev/null <<'EOF'
ACTION=="add", SUBSYSTEM=="block", KERNEL=="sd*", ENV{DEVTYPE}=="disk", ENV{ID_BUS}=="usb", \
  ENV{ID_PATH}=="*usb-0:2:*", TAG+="systemd", ENV{SYSTEMD_WANTS}+="leftusb@%k.service"
EOF
```

and reload

`sudo udevadm control --reload`
