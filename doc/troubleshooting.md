# Ongoing and past troubleshooting

## Computer shutdowns after exactly 20 minutes

This started happenning when I replaced the Nvidia drivers from nvidia page with the ones in the ubuntu repository. I issue the command `watch uptime` and everytime after 20 minutes, the computer shut downs.

Action | Result
---|---
Vacuum the suitcase | Same
Reseat all connectors and components | Same
Remove the GPU | Same
Disable WoL | Same
Change power supply | Same
Remove cuda 11.1 and nvidia 455 | Same
Check BIOS settings | Done (1)
Check crontabs | Nothing scheduled
`shutdown -c` | Same
Replace CMOS battery | TODO
Without HDD | **It stays on**
With USB Live Ubuntu | **It stays on**
(1) Wake by LAN card was disabled. I reenabled it

That confirms to be a software issue. I remember when I installed the nvidia drivers. Something related with Xorg and gnome-shell. Let's see what I can do there. In fact now when I log in with screen and keyboard it jumps to gnome login screen. Maybe it was not shut down. Could it be that if you don't log in in 20 minutes it hybernates? I did not realise because the server is headless.

`sudo apt purge gnome-shell && sudo apt autoremove`

> **SOLVED!** Removing gnome-shell solved the issue!

## Updates cannot be automatically installed

This message appears when I log in sometimes:

```
0 updates can be installed immediately.
0 of these updates are security updates.


16 updates could not be installed automatically. For more details,
see /var/log/unattended-upgrades/unattended-upgrades.log
```

And the file `/var/log/unattended-upgrades/unattended-upgrades.log` says

```
2021-03-01 03:47:00,154 INFO Starting unattended upgrades script
2021-03-01 03:47:00,155 INFO Allowed origins are: o=Ubuntu,a=focal, o=Ubuntu,a=focal-security, o=UbuntuESMApps,a=focal-apps-security, o=UbuntuESM,a=focal-infra-security
2021-03-01 03:47:00,155 INFO Initial blacklist: 
2021-03-01 03:47:00,155 INFO Initial whitelist (not strict): 
2021-03-01 06:58:49,709 INFO Starting unattended upgrades script
2021-03-01 06:58:49,710 INFO Allowed origins are: o=Ubuntu,a=focal, o=Ubuntu,a=focal-security, o=UbuntuESMApps,a=focal-apps-security, o=UbuntuESM,a=focal-infra-security
2021-03-01 06:58:49,710 INFO Initial blacklist: 
2021-03-01 06:58:49,710 INFO Initial whitelist (not strict): 
2021-03-01 06:58:50,397 INFO No packages found that can be upgraded unattended and no pending auto-removals
2021-03-01 06:58:50,469 INFO Package libnvidia-cfg1-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,470 INFO Package libnvidia-common-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,472 INFO Package libnvidia-compute-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,473 INFO Package libnvidia-decode-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,475 INFO Package libnvidia-encode-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,476 INFO Package libnvidia-extra-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,478 INFO Package libnvidia-fbc1-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,479 INFO Package libnvidia-gl-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,481 INFO Package libnvidia-ifr1-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,516 INFO Package nvidia-compute-utils-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,518 INFO Package nvidia-dkms-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,519 INFO Package nvidia-driver-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,521 INFO Package nvidia-kernel-common-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,522 INFO Package nvidia-kernel-source-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,524 INFO Package nvidia-utils-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-01 06:58:50,559 INFO Package xserver-xorg-video-nvidia-460 is kept back because a related package is kept back or due to local apt_preferences(5).
2021-03-02 00:27:38,410 INFO Starting unattended upgrades script
...
```

Try to manually update the packages listed. If it says already the latest version it is safe to just remove the keptback file `sudo rm /var/lib/unattended-upgrades/kept-back`

## Removing wrong PPAs

sudo apt-add-repository --list

Ign:12 https://packagecloud.io/timescale/timescaledb/debian jammy InRelease
Err:15 https://packagecloud.io/timescale/timescaledb/debian jammy Release
  404  Not Found [IP: 54.183.47.114 443]
  E: The repository 'https://packagecloud.io/timescale/timescaledb/debian jammy Release' does not have a Release file.
N: Updating from such a repository can't be done securely, and is therefore disabled by default.

sudo apt-add-repository --remove ppa:https://packagecloud.io/timescale/timescaledb/debian

sudo apt-get install ppa-purge
