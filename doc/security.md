# Setup and secure remote ssh access

<!-- vim-markdown-toc GFM -->

* [Don't use the default port 22](#dont-use-the-default-port-22)
* [Ban brute force attackers](#ban-brute-force-attackers)
* [Use 2FA verification codes](#use-2fa-verification-codes)
* [Use ssh keys instead of password to log in via ssh](#use-ssh-keys-instead-of-password-to-log-in-via-ssh)
* [Set basic firewall rules](#set-basic-firewall-rules)

<!-- vim-markdown-toc -->

## Don't use the default port 22

Replace the standard ssh port `Port 22` with some other in `/etc/ssh/sshd_config`, say 22222. restart ssh `sudo service sshd restart`.

## Ban brute force attackers

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

## Use 2FA verification codes

Now configure 2FA. Install `sudo apt install libpam-google-authenticator`, Run `google-authenticator` and scan the qr in your mobile phone app. Edit `sudo nano /etc/pam.d/sshd` and comment out `@include common-auth`. At the bottom of the file add `auth required pam_google_authenticator.so`.

## Use ssh keys instead of password to log in via ssh

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


