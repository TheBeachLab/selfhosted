# SFTP Server

- [Why](#why)
- [Install](#install)
- [Configuration](#configuration)


## Why 
For some static sites and for uploading files in folders not accessible or not tracked by git.

## Install
There is nothing to install if you went through the ssh server.

## Configuration

`sudo addgroup sftp`

`sudo useradd -m ftpuser -g sftp`

`sudo passwd ftpuser`

After that you will need to reboot/logout.

`sudo nano /etc/ssh/sshd_config`

```
Match group sftp
	ChallengeResponseAuthentication no
	AuthenticationMethods password
	PasswordAuthentication yes
#	ChrootDirectory /var/www.  # otherwise broken pipe as chroot dir must be owned by root
	X11Forwarding no
	AllowTcpForwarding no
	ForceCommand internal-sftp
````

In `sudo nano /etc/pam.d/sshd` add `auth [success=done default=ignore] pam_succeed_if.so user ingroup sftp`

