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


sudo apt-add-repository --remove 'deb https://packagecloud.io/timescale/timescaledb/debian/ jammy main'

## Old keyring
```
Warning: apt-key is deprecated. Manage keyring files in trusted.gpg.d instead (see apt-key(8)).
/etc/apt/trusted.gpg
--------------------
pub   rsa4096 2020-03-02 [SC] [expired: 2022-03-02]
      F640 3F65 44A3 8863 DAA0  B6E0 3F01 618A 5131 2F3F
uid           [ expired] GitLab B.V. (package repository signing key) <packages@gitlab.com>

pub   rsa4096 2013-06-30 [SC]
      1637 8A33 A6EF 1676 2922  526E 561F 9B9C AC40 B2F7
uid           [ unknown] Phusion Automated Software Signing (Used by automated tools to sign software packages) <auto-software-signing@phusion.nl>
sub   rsa4096 2013-06-30 [E]

pub   rsa4096 2014-06-13 [SC]
      9FD3 B784 BC1C 6FC3 1A8A  0A1C 1655 A0AB 6857 6280
uid           [ unknown] NodeSource <gpg@nodesource.com>
sub   rsa4096 2014-06-13 [E]

pub   rsa4096 2018-08-14 [SC]
      E869 7E2E EF76 C02D 3A63  3277 8881 B2A8 2109 76F2
uid           [ unknown] Package Manager (Package Signing Key) <packages@pgadmin.org>
sub   rsa4096 2018-08-14 [E]

pub   rsa4096 2015-07-25 [SC] [expires: 2023-07-24]
      EDB7 D030 4E2F CAF6 29DF  1163 0757 21F6 A224 060A
uid           [ unknown] openHAB Bintray Repositories <owner@openhab.org>
sub   rsa4096 2015-07-25 [E] [expires: 2023-07-25]

pub   rsa4096 2022-04-14 [SC]
      EB69 3B30 35CD 5710 E231  E123 A4B4 6996 3BF8 63CC
uid           [ unknown] cudatools <cudatools@nvidia.com>

pub   rsa4096 2016-10-05 [SC]
      72EC F46A 56B4 AD39 C907  BBB7 1646 B01B 86E5 0310
uid           [ unknown] Yarn Packaging <yarn@dan.cx>
sub   rsa4096 2016-10-05 [E]

pub   rsa4096 2017-02-22 [SCEA]
      9DC8 5822 9FC7 DD38 854A  E2D8 8D81 803C 0EBF CD88
uid           [ unknown] Docker Release (CE deb) <docker@docker.com>
sub   rsa4096 2017-02-22 [S]

pub   rsa4096 2018-10-19 [SCEA]
      1005 FB68 604C E9B8 F687  9CF7 59F1 8EDF 47F2 4417
uid           [ unknown] https://packagecloud.io/timescale/timescaledb (https://packagecloud.io/docs#gpg_signing) <support@packagecloud.io>
sub   rsa4096 2018-10-19 [SEA]
```

sudo apt-key del '1637 8A33 A6EF 1676 2922  526E 561F 9B9C AC40 B2F7'


W: https://ftp.postgresql.org/pub/pgadmin/pgadmin4/apt/jammy/dists/pgadmin4/InRelease: Key is stored in legacy trusted.gpg keyring (/etc/apt/trusted.gpg), see the DEPRECATION section in apt-key(8) for details.

sudo apt-key list

pub   rsa4096 2018-08-14 [SC]
      E869 7E2E EF76 C02D 3A63  3277 8881 B2A8 2109 76F2
uid           [ unknown] Package Manager (Package Signing Key) <packages@pgadmin.org>
sub   rsa4096 2018-08-14 [E]

sudo apt-key export 210976F2 | sudo gpg --dearmour -o /etc/apt/trusted.gpg.d/pgadmin4.gpg