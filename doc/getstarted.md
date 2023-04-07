# Getting started

<!-- vim-markdown-toc GFM -->

- [Installing Ubuntu Server](#installing-ubuntu-server)
- [Set the root password](#set-the-root-password)
- [Upgrade](#upgrade)
- [Enable beep](#enable-beep)
  - [beep on login](#beep-on-login)
- [Configure ethernet](#configure-ethernet)
- [Get rid of snap](#get-rid-of-snap)
- [Install sensor monitoring tools and hwinfo](#install-sensor-monitoring-tools-and-hwinfo)
- [Configure Wake on LAN](#configure-wake-on-lan)
- [Using screen to run a long (in time) command in a remote terminal](#using-screen-to-run-a-long-in-time-command-in-a-remote-terminal)

<!-- vim-markdown-toc -->

## Installing Ubuntu Server

First step is installing Ubuntu Server. I have currently installed 22.04 LTS. There are plenty of tutorials on how to do this, so I won't explain it here.

## Set the root password

`sudo passwd root`. **Do not** forget the root password.

## Upgrade

```bash
sudo apt update
sudo apt upgrade
```
## Enable beep

You might think that's silly, but it helps me a lot when debugging or as notification.

```bash
sudo apt install beep
sudo apt install acl
sudo modprobe pcspkr
```
If you try to beep, non root users see `beep: Error: Could not open any device` and running with sudo outputs `beep: Error: Running under sudo, which is not supported for security reasons. beep: Error: Set up permissions for the pcspkr evdev device file instead.`

You need special permissions to beep, so we will add a group `sudo addgroup --system beep` and make some rules to be able to beep. Edit `sudo nano /lib/udev/rules.d/90-pcspkr-beep.rules` and add:

```bash
# Add write access to the PC speaker for the "beep" group
ACTION=="add", SUBSYSTEM=="input", ATTRS{name}=="PC Speaker", ENV{DEVNAME}!="", RUN+="/usr/bin/setfacl -m g:beep:w '$env{DEVNAME}'"
```

Add the beeping user to the group `sudo usermod sister -a -G beep` and reboot

Test it with the `beep` command. Since we ran `sudo modprobe pcspkr` that will work for the current session. To make the beeping persistent comment the line `blacklist pcspkr` from `/etc/modprobe.d/blacklist.conf`. 

### beep on login
Create the script `/usr/local/bin/beep-on-login.sh`

```bash
#!/bin/bash
beep -f 1000 -l 100 -r 2
```

Make the script executable `sudo chmod +x /usr/local/bin/beep-on-login.sh`

Add the script to `/etc/rc.local` using `/usr/local/bin/beep-on-login.sh &`

## Configure ethernet

Check your ethernet interface name with `ip address` and run `sudo nano /etc/netplan/00-installer-config.yaml`. I have it configured with fixed IP and fixed interface name tied to the mac address.:

```bash
network:
  version: 2
  ethernets:
    lan:
      match:
        macaddress: 00:ab:cd:ef:12:34
      set-name: cable
      dhcp4: no
      wakeonlan: true
      addresses:
        - 192.168.1.50/24
      gateway4: 192.168.1.1
      nameservers:
          addresses: [1.0.0.1, 1.1.1.1]
```

Then `sudo netplan apply` you should be connected now.


## Get rid of snap

```bash
sudo snap remove lxd
sudo snap remove core20
sudo snap remove snapd
sudo apt purge snapd
rm -rf ~/snap
```

## Install sensor monitoring tools and hwinfo

```bash
sudo apt install hwinfo
sudo apt install lm-sensors
sudo sensors-detect
sudo apt install hddtemp
sudo apt install glances
```

## Configure Wake on LAN

First enable this feature in the BIOS. Check if the adapter supports WOL `sudo ethtool cable` and look for `Supports Wake-on: <letters>`. If `g` is among the letters, then it supports the *magic packet*. Also check if WoL is enabled `Wake-on: <letters>`. If letters contain `g` and not `d` then WoL is enabled. However, if letters contain `d` you need to enable WoL by running:

`sudo ethtool -s cable wol g`

You need to issue this command at every boot or by adding `wakeonlan: true` in netplan config file (see above). Finally in your computer issue the command `wol 00:ab:cd:ef:12:34` and the server should wake.

## Using screen to run a long (in time) command in a remote terminal

If you open a remote terminal and run a command, it will stop if the connection is closed. To prevent that run screen. A new terminal window will open where you can run your command. Detach the screen with control+A followed by d. To reattach the screen run screen -r. If multiple screen sessions are running, list them with screen -ls and attach the session with screen -r ID.
