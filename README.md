# Selfhosted

> To become independent, you don't have to  ask for independence. To become independent you have *to be* independent. 
>
> Fran Sanchez

This is the story of how I am slowly becoming independent.

![](img/suitcase.jpg)

<!-- vim-markdown-toc GFM -->

* [Why am I doing that](#why-am-i-doing-that)
* [Hardware](#hardware)
* [Installing Ubuntu Server](#installing-ubuntu-server)
* [Configure ethernet](#configure-ethernet)
* [Upgrade](#upgrade)
* [Get rid of snap](#get-rid-of-snap)
* [Install sensor monitoring tools](#install-sensor-monitoring-tools)
* [Setup and secure remote ssh access](#setup-and-secure-remote-ssh-access)
* [Set firewall rules](#set-firewall-rules)
* [Nginx web server](#nginx-web-server)
* [Mail servers: Postfix, Dovecot and OpenDKIM](#mail-servers-postfix-dovecot-and-opendkim)
	* [Postfix](#postfix)
* [Backups via NFS](#backups-via-nfs)

<!-- vim-markdown-toc -->

## Why am I doing that

My name is Francisco, in french it means "free person" . Some people in life want performance, some other want reliability. The only thing I care about is freedom. To do what I want, when I want and how I want to.

## Hardware

My server is an oldie i3-3220 (4 cores?) @ 3.300GHz with 8GB RAM and 500GB SSD running Ubuntu Server 20.04 LTS. It has a UPS power supply. The Internet line is a 600Mbps symmetric FTTH with dynamic IP address.

- TODO: Convert a powerbank to 12V UPS for the router using a [Pololu Adjustable Boost Regulator 4-25V](https://www.pololu.com/product/799/specs)

## Installing Ubuntu Server

First step is installing Ubuntu Server. I installed 20.04 LTS. There are plenty of tutorials on how to do this, so I won't explain it here.

## Configure ethernet

Check your ethernet interface name with `ip address` and run `sudo nano /etc/netplan/00-installer-config.yaml`. I have it configured with fixed IP:

```bash
network:
  ethernets:
    enp4s0:
      dhcp4: no
      addresses:
        - 192.168.1.50/24
      gateway4: 192.168.1.1
      nameservers:
          addresses: [8.8.8.8, 1.1.1.1]
  version: 2
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

## Install sensor monitoring tools

```bash
sudo apt install lm-sensors
sudo sensors-detect
sudo apt install hddtemp
sudo apt install glances
```

## Setup and secure remote ssh access

Replace the standard ssh port `Port 22` with some other in `/etc/ssh/sshd_config`, say 22222. restart ssh `sudo service sshd restart`. 

Now ban multiple attemps to log in:

```bash
sudo apt install fail2ban
cd /etc/fail2ban
sudo cp fail2ban.conf fail2ban.local
sudo nano fail2ban.local
```

And add the following

```bash
[sshd]
enabled = true
port = 22222
filter = sshd
logpath = /var/log/auth.log
maxretry = 10
bantime = 600
```

And restart fail2ban `sudo service fail2ban restart`

Now configure 2FA. Install `sudo apt install libpam-google-authenticator`, Run `google-authenticator` and scan the qr in your mobile phone app. Edit `sudo nano /etc/pam.d/sshd` and comment out `@include common-auth`. At the bottom of the file add `auth required pam_google_authenticator.so`. 

We won't  use our password to login via ssh. Instead we will import our public ssh keys from github or gitlab to log in via ssh. In my case I am importing my public keys from github.

`ssh-import-id gh:thebeachlab`

Now edit `sudo nano /etc/ssh/sshd_config` and add/modify:

```bash
ChallengeResponseAuthentication yes
UsePAM yes
AuthenticationMethods publickey,password publickey,keyboard-interactive
PasswordAuthentication no
PermitRootLogin no
```

Restart the service `sudo service sshd restart`

## Set firewall rules

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22222/tcp comment 'SSH'
sudo ufw allow http
sudo ufw allow https
sudo ufw enable
sudo ufw reload
```

Optionally drop pings `sudo nano /etc/ufw/before.rules`

```bash
-A ufw-before-input -p icmp --icmp-type echo-request -j DROP
```

And again `sudo ufw reload`

## Nginx web server

```bash
sudo apt install nginx
sudo ufw allow 'Nginx Full'
```

Create your website(s) `sudo mkdir -p /var/www/yourdomain.com` and edit `sudo nano /etc/nginx/sites-available/yourdomain.com` with this content

```bash
server {
listen 80;
listen [::]:80;
root /var/www/mydomain.com;
index index.html;
server_name mydomain.com www.mydomain.com;
location / {
try_files $uri $uri/ =404;
}
}
```

Check for mistakes in the syntax `sudo nginx -t -c /etc/nginx/nginx.conf` anc create a link to enable the site: `sudo ln -s /etc/nginx/sites-available/mydomain.com /etc/nginx/sites-enabled/mydomain.com`. Finally reload nginx `sudo systemctl reload nginx`

Point your local IP address to your machine. Get your local machine name `cat /etc/hostname` and point it to the fixed ip address that you set at the beginning `sudo nano /etc/host`. I have `192.168.1.50 thebeachlab` in my case.

> Warning: Still not sure why but 127.0.0.1 will not work. You have to use the network ip.

The following step is to create SSL certificates. For that you will need to create A records for @ and www pointing to your IP. In my case since I don't have a fixed public IP address I have created a dynamic A record in namecheap (where my domains are registered). Then I use a daemon that uses namecheap API to update the IP address. Look for a solution that works for you.

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d mydomain.com -d www.mydomain.com
```

If you want to query auto the renewal timer `sudo systemctl status certbot.timer` or you can test the auto renewal process `sudo certbot renew --dry-run`

My proud website hosted in my suitcase:

![screenshot](img/tbl.png)

## Mail servers: Postfix, Dovecot and OpenDKIM

### Postfix


## Backups via NFS

Assuming here you have a NAS or similar with NFS and appropiate user/permissions set. In ubuntu server install the nfs tools:

```bash
sudo apt update
sudo apt install nfs-common
```

Create the local mountpoint `sudo mkdir -p /mnt/backups`

Mount the NFS shared folder `sudo mount 192.168.1.100:/volume1/backups /mnt/backups` (your NFS IP and shared volume will differ). Confirm that the drive is mounted `df –h`

```bash
Filesystem                      Size  Used Avail Use% Mounted on
udev                            3.8G     0  3.8G   0% /dev
tmpfs                           786M  1.2M  785M   1% /run
/dev/sda2                       469G   12G  434G   3% /
tmpfs                           3.9G     0  3.9G   0% /dev/shm
tmpfs                           5.0M     0  5.0M   0% /run/lock
tmpfs                           3.9G     0  3.9G   0% /sys/fs/cgroup
tmpfs                           786M     0  786M   0% /run/user/1000
192.168.1.100:/volume1/backups  2.7T  1.7T  1.1T  61% /mnt/backups
```

Test your write permissions

```bash
cd /mnt/backups
touch test
```

Check on the NFS server that the file is actually there. Now you can automate this to mount at boot time. Add this entry in `/etc/fstab`

`192.168.1.100:/volume1/backups /mnt/backups nfs defaults 0 0`

Next time you start your machine the NFS share will be automatically mounted at the specified mount point.
