# Getting started

<!-- vim-markdown-toc GFM -->

* [Installing Ubuntu Server](#installing-ubuntu-server)
* [Set the root password](#set-the-root-password)
* [Configure ethernet](#configure-ethernet)
* [Upgrade](#upgrade)
* [Get rid of snap](#get-rid-of-snap)
* [Install sensor monitoring tools and hwinfo](#install-sensor-monitoring-tools-and-hwinfo)
* [Configure Wake on LAN](#configure-wake-on-lan)

<!-- vim-markdown-toc -->

## Installing Ubuntu Server

First step is installing Ubuntu Server. I installed 20.04 LTS. There are plenty of tutorials on how to do this, so I won't explain it here.

## Set the root password

`sudo passwd root`. **Do not** forget the root password.

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

## Upgrade

```bash
sudo apt update
sudo apt upgrade
```

## Get rid of snap

```bash
sudo snap remove lxd
sudo snap remove core18
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

Check if the adapter supports WOL `sudo ethtool cable` and look for `Supports Wake-on: <letters>`. If `g` is among the letters, then it supports the *magic packet*. Also check if WoL is enabled `Wake-on: <letters>`. If letters contain `g` and not `d` then WoL is enabled. However, if letters contain `d` you need to enable WoL by running:

`sudo ethtool -s cable wol g`

You need to issue this command at every boot or by adding `wakeonlan: true` in netplan config file (see above).
