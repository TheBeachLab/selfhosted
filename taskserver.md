# Task server (taskwarrior)

<!-- vim-markdown-toc GFM -->

* [Prerrequisites](#prerrequisites)
* [Install](#install)
* [Configure](#configure)
* [Copy the certificates in the machine/device where client taskwarrior is](#copy-the-certificates-in-the-machinedevice-where-client-taskwarrior-is)
* [Sync](#sync)

<!-- vim-markdown-toc -->

It is a bit tedious but worth it

## Prerrequisites

```bash
sudo apt install g++
sudo apt install libgnutls28-dev
sudo apt install uuid-dev
sudo apt install cmake
sudo apt install gnutls-bin
```

## Install

```bash
sudo adduser taskmaster
usermod -aG sudo taskmaster
su taskmaster
git clone --recurse-submodules=yes https://github.com/GothenburgBitFactory/taskserver.git taskserver.git
cmake -DCMAKE_BUILD_TYPE=release .
make
cd test
make
./run_all
cd ..
sudo make install
```

## Configure

```bash
export TASKDDATA=~/taskd
mkdir -p $TASKDDATA
cd taskserver.git
cp -R pki ~/taskd
taskd init
nano ~/taskd/pki/vars
```

In `vars` we have information about the server

```bash
BITS=4096
EXPIRATION_DAYS=3650
ORGANIZATION="The Beach Lab"
CN=beachlab.org
COUNTRY=ES
STATE="Barcelona"
LOCALITY="Sitges"
```

Generate and install the server certificates

```bash
./generate
cp client* $TASKDDATA
cp server* $TASKDDATA
cp ca.cert.pem  $TASKDDATA
taskd config --force client.cert $TASKDDATA/client.cert.pem
taskd config --force client.key  $TASKDDATA/client.key.pem
taskd config --force server.cert $TASKDDATA/server.cert.pem
taskd config --force server.key  $TASKDDATA/server.key.pem
taskd config --force server.crl  $TASKDDATA/server.crl.pem
taskd config --force ca.cert  $TASKDDATA/ca.cert.pem
```

Configure the server settings

```bash
taskd config --force log $PWD/taskd.log
taskd config --force pid.file $PWD/taskd.pid
taskd config --force server localhost:53589
cd /home/taskmaster/taskserver.git/scripts/systemd/
cp /home/taskmaster/taskserver.git/scripts/systemd/taskd.service ~
```

Edit the service daemon `nano taskd.service`

```bash
[Unit]
Description=Secure server providing multi-user, multi-client access to task data
Requires=network.target
After=network.target
Documentation=http://taskwarrior.org/docs/

[Service]
ExecStart=/usr/local/bin/taskd server --data /home/taskmaster/taskd
Restart=on-abort
Type=simple
User=taskmaster
Group=taskmaster
WorkingDirectory=/home/taskmaster/taskd
PrivateTmp=true

[Install]
WantedBy=multi-user.target
cp taskd.service /etc/systemd/system
systemctl daemon-reload
systemctl start taskd.service
systemctl status taskd.service
systemctl enable taskd.service
systemctl enable taskd.service
```

Add org and users

```bash
taskd add org TBL --data ~/taskd
taskd add user 'TBL' 'Fran Sanchez' --data ~/taskd
cd taskd/pki
./generate.client fran_sanchez
```

This will generate a certificate and a private key for the user fran_sanchez

## Copy the certificates in the machine/device where client taskwarrior is

Remember taskmaster user must have keys in .ssh folder and 2FA enabled

```bash
scp -P 622 taskmaster@beachlab.org:/home/taskmaster/taskd/pki/fran_sanchez.cert.pem ~/.task
scp -P 622 taskmaster@beachlab.org:/home/taskmaster/taskd/pki/fran_sanchez.key.pem ~/.task
scp -P 622 taskmaster@beachlab.org:/home/taskmaster/taskd/pki/ca.cert.pem ~/.task
```

Add the certificates to taskwarrior

```bash
task config taskd.certificate -- ~/.task/fran_sanchez.cert.pem
task config taskd.key -- ~/.task/fran_sanchez.key.pem
task config taskd.ca -- ~/.task/ca.cert.pem
```

Set the server parameters

```bash
task config taskd.server      -- beachlab.org:53589
task config taskd.credentials -- TBL/Fran Sanchez/YOUR-CREDENTIALS-HERE
```

> TODO: Where did the credentials come from?

## Sync

`task sync`

