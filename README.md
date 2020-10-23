# Selfhosted

> To become independent, you don't have to  ask for independence. To become independent you have *to be* independent.
>
> Fran Sanchez

This is the story of how I am slowly becoming independent.

![](img/suitcase.jpg)

<!-- vim-markdown-toc GFM -->

* [Why am I doing this](#why-am-i-doing-this)
* [What hardware do you need](#what-hardware-do-you-need)
* [Installing Ubuntu Server](#installing-ubuntu-server)
* [Configure ethernet](#configure-ethernet)
* [Upgrade](#upgrade)
* [Get rid of snap](#get-rid-of-snap)
* [Install sensor monitoring tools](#install-sensor-monitoring-tools)
* [Setup and secure remote ssh access](#setup-and-secure-remote-ssh-access)
	* [Don't use the default port 22](#dont-use-the-default-port-22)
	* [Ban brute force attackers](#ban-brute-force-attackers)
	* [Use 2FA verification codes](#use-2fa-verification-codes)
	* [Use ssh keys instead of password to log in via ssh](#use-ssh-keys-instead-of-password-to-log-in-via-ssh)
* [Set basic firewall rules](#set-basic-firewall-rules)
* [Nginx web server](#nginx-web-server)
	* [Install nginx and create firewall rules](#install-nginx-and-create-firewall-rules)
	* [Create and configure your websites](#create-and-configure-your-websites)
	* [Point your domain to your machine](#point-your-domain-to-your-machine)
	* [Get free trusted SSL certificates for your websites](#get-free-trusted-ssl-certificates-for-your-websites)
	* [The result](#the-result)
* [Backups with rsnapshot](#backups-with-rsnapshot)
	* [Optional. Accessing NFS drives](#optional-accessing-nfs-drives)
	* [Install and setup rsnapshot](#install-and-setup-rsnapshot)
* [WIP. Mail servers: Postfix, Dovecot and OpenDKIM](#wip-mail-servers-postfix-dovecot-and-opendkim)
	* [Postfix](#postfix)
* [Git server](#git-server)
	* [Gitlab? No, thanks](#gitlab-no-thanks)
	* [Plain git server](#plain-git-server)

<!-- vim-markdown-toc -->

## Why am I doing this

My name is Francisco, in french it means "free person" . Some people in life want performance, some other want reliability. The only thing I care about is freedom. To do what I want, when I want and how I want to.

## What hardware do you need

You will be surprised how low-tech this whole thing can go. Of course the better hardware you have the longer you will travel. But for most common needs like website, mail and so, any computer from 10 years ago will be fine. You can even use a raspberry pi and carry your server in your pocket!! My server is a 2015 Skylake i3-6100 (2 cores/4 threads) @ 3.700GHz with 8GB RAM and 500GB SSD running Ubuntu Server 20.04 LTS. It has a UPS power supply. The Internet line is a 600Mbps symmetric FTTH with dynamic IP address.

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

### Don't use the default port 22

Replace the standard ssh port `Port 22` with some other in `/etc/ssh/sshd_config`, say 22222. restart ssh `sudo service sshd restart`.

### Ban brute force attackers

Now ban for 10 minutes if someone makes multiple (10) attemps to log in:

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

### Use 2FA verification codes

Now configure 2FA. Install `sudo apt install libpam-google-authenticator`, Run `google-authenticator` and scan the qr in your mobile phone app. Edit `sudo nano /etc/pam.d/sshd` and comment out `@include common-auth`. At the bottom of the file add `auth required pam_google_authenticator.so`.

### Use ssh keys instead of password to log in via ssh

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

## Set basic firewall rules

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22222/tcp comment 'SSH'
sudo ufw allow http
sudo ufw allow https
sudo ufw enable
sudo ufw reload
```

Optionally drop pings `sudo nano /etc/ufw/before.rules` and add

```bash
-A ufw-before-input -p icmp --icmp-type echo-request -j DROP
```

And again `sudo ufw reload`

## Nginx web server

### Install nginx and create firewall rules

```bash
sudo apt install nginx
sudo ufw allow 'Nginx Full'
```

### Create and configure your websites

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

### Point your domain to your machine

For that you will need to create A records for `@` and `www` pointing to your IP. If your ISP provides you with a fixed public IP that's all you need to do.

In my case since I don't have a fixed public IP address I have [created a dynamic A record in namecheap](https://www.namecheap.com/support/knowledgebase/article.aspx/36/11/how-do-i-start-using-dynamic-dns) (where my domains are registered).

Then I use a daemon `ddclient` that uses namecheap API (it also has several others) to update the IP address in namecheap records. Install `sudo apt-get install ddclient` and configure `sudo nano /etc/ddclient/ddclient.conf`

```bash
#### Global Settings
# How often to update (seconds)
daemon=300
ssl=yes
use=web
web=dynamicdns.park-your-domain.com/getip
protocol=namecheap
server=dynamicdns.park-your-domain.com

#### beachlab.org
login=beachlab.org
password='PUT-YOUR-DOMAIN-KEY-HERE'
@.beachlab.org, www
```

Finally make `ddclient` start when you boot up your ubuntu system

```bash
sudo update-rc.d ddclient defaults
sudo update-rc.d ddclient enable
```

> Is this necessary?
>
> Point your local IP address to your machine. Get your local machine name `cat /etc/hostname` which in my case returns `thebeachlab` and point it to the **local network** fixed ip address that you set at the beginning `sudo nano /etc/host`. I have `192.168.1.50 thebeachlab` in my case.
>
> Warning: Still not sure why but 127.0.0.1 will not work. You have to use the network ip.

### Get free trusted SSL certificates for your websites

The following step is to create free trusted SSL certificates. This thing used to cost quite a lot of money but now it's pretty straight forward and there's no reason to have an unencrypted connection anymore.

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d mydomain.com -d www.mydomain.com
```

> Do I really need to remind you to replace `mydomain.com` with your actual domain name?

If you want to query the status of the auto renewal timer `sudo systemctl status certbot.timer` or you can test the auto renewal process `sudo certbot renew --dry-run`

### The result

My proud website hosted in my suitcase:

![screenshot](img/tbl.png)

## Backups with rsnapshot

> There’s no feeling more intense than starting over. If you've deleted your homework the day before it was due, as I have, or if you left your wallet at home and you have to go back, after spending an hour in the commute, if you won some money at the casino and then put all your winnings on red, but it came up black, if you got your best shirt dry-cleaned before a wedding and then immediately dropped food on it, if you won an argument with a friend and then later discovered that they just returned to their original view, starting over is harder than starting up.
>
> From the videogame "Getting Over It with Bennett Foddyd"

### Optional. Accessing NFS drives

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

### Install and setup rsnapshot

rsnapshot is a backup tool based on rsync. It's fast and can do incremental backups. Install rsnapshot `sudo apt install rsnapshot` and configure it `sudo nano /etc/rsnapshot.conf`. The most important thing to remember is **use tabs instead of spaces to separate keys and values**. Set your intervals and folders to backup. I have created 7 `beta` which I will use for the daily backups and 4 `gamma` that I will use for the weekly backups. At the moment I do not need to create any hourly backup. Also specify what to backup. rsnapshot can backup from anything to anything. In my case I hace rsnapshot locally installed and I am pushing the backups to a NFS. But I could also use a remote server with rsnapshot to pull my files via ssh.

After saving the configuration file check for errors `rsnapshot configtest`. It is advisable also to dry-run test the backup levels/intervals specified in the config file `rsnapshot -t beta`.

Automate your backups in ` crontab -e`

```bash
@daily /usr/bin/rsnapshot beta &> /dev/null
@weekly /usr/bin/rsnapshot gamma &> /dev/null
```

## WIP. Mail servers: Postfix, Dovecot and OpenDKIM

### Postfix

## Git server

### Gitlab? No, thanks

I initially started installing gitlab but I abandon. It'so, so, so, so bloated with features I don't need. It'a pain in the a$$ to configure with an already existing nginx server. And its a nightmare to later maintain it. So I uninstalled gitlab, reverted all changes and I installed a plain git server. Because in the end. all I want is a place to store my repos. This is not a multiuser environment.

### Plain git server

Begin with adding a git user `sudo adduser git` and set up a password for it. Log into the user `su git` and navigate to it's home folder `cd`. Let's now set it up to use ssh keys to log in instead of the password.

```bash
git@thebeachlab:~$ mkdir .ssh
git@thebeachlab:~$ chmod 700 .ssh/
git@thebeachlab:~$ touch .ssh/authorized_keys
git@thebeachlab:~$ chmod 600 .ssh/authorized_keys
```

Now copy one of your public keys in this file. For example I will copy my public key

```bash
[unix ~]$ cat .ssh/id_rsa.pub
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDfuWDpvaOf5T3f5E7bt22p6Irww2x5dx8HK1yGYvO85Gl9AZriR9+k7vj4Arlth4Zn3/VDe/PWXJ23xSdi1xPcu1lZJvRF7dctw59BAfX946R2wRTdTsxCO5XDYbIjX0vLopbw5B/lFd8jIr0vgcFNswtGTagvYcLnPERZzmR5fQ2cRLURUSD7axZjOv3cL2vUxdHEmUar6YG7/9eHJVHqjYSsOK68x8vpLQmm7SMfbrUIDTyCuEOujkeoRW8JDzO878zGFYtlOZuBCM72WqltmYnVRuJOyeY9AQHoVAWHcS9nj5RN1l8yJllaeJUTfRCJeH+FlOBNmhN4MQP3dwwyJR8sUyuM4qOzCdvpiuQj4P5xWQj60Su74JQcI86g0Qvtz+jnpoRwVKISgyUKjgT9OpAZV6L1ftxNVoUjvUYfkZZD7ZFGM4leDXfJYzKpo9hxLSwtLR/3R9YKnjjMS0H9r8SAaQIZKSol49BcU5QDVtx/ikczstQEVVTUwMvhMXECE0ENuAlSJZmdziyNcJzvquWOM6+TgiBT9rQNtFLmX6uv6bJN6ExyBWpMQeS9Ri1MPuHGJfFahoKd+YRkr6MHYobnHyKDQ3HaC2Y5JY+o+pHEuyz5Q0FGztzlSQ9zrNBsj4fjBuJNohNMYmjPjYRgNFFXlE/Ay2IjU7QiyR4v2Q== hola@beachlab.org
```

And paste it in the server

`git@thebeachlab:~$ nano .ssh/authorized_keys`

Alternatively you can import you public keys from github or gitlab `ssh-import-id gh:thebeachlab`. You should be able now to ssh into git user.

> Warning: If you have configured the ssh server for key and 2FA (with google auth) you will get this error
>
> ```bash
> [unix ~]$ ssh -p 22222 git@beachlab.org
> git@thebeachlab: Permission denied (keyboard-interactive).
> ```
>
> This is because you need to enable 2FA for each user. Remember to run google-authenticator and follow instructions.

Let's create a folder where we can create our bare repositories. I create them inside /var/www

```bash
cd /var/www
sudo mkdir git.beachlab.org
sudo chown git:git git.beachlab.org/
```

Now because this folder belongs to git user, from now on you can ssh and create your bare repositories

```bash
[unix ~]$ ssh -p 22222 git@beachlab.org
git@thebeachlab:~$ cd /var/www/git.beachlab.org/
git@thebeachlab:~$ mkdir myrepo.git
git@thebeachlab:~$ cd myrepo.git
git@thebeachlab:~$ git init --bare
```

Everytime you want to create a repo you have to ssh into git user and repeat these steps.

To add the remote pointing to that repository

`git remote add home ssh://git@git.beachlab.org:22222/var/www/git.beachlab.org/myrepo.git` 

You will have to enter the verification code at every push, pull or any other operation. That's quite annoying actually, but I haven't figured out any workaround yet.



Remember to update ddclient `sudo nano /etc/ddclient/ddclient.conf` and your `/etc/hosts`
