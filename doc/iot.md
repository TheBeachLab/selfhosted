# IoT

<!-- vim-markdown-toc GFM -->

- [Node Red](#node-red)
  - [Prepare](#prepare)
  - [Install](#install)
  - [Usage](#usage)
  - [Secure with https](#secure-with-https)
  - [Secure the editor with username and password](#secure-the-editor-with-username-and-password)
- [Mosquitto broker](#mosquitto-broker)
  - [Install and test](#install-and-test)
  - [Adding users to mosquitto](#adding-users-to-mosquitto)
  - [Set user permissions](#set-user-permissions)
  - [Configure MQTT through TLS](#configure-mqtt-through-tls)
  - [Enable MQTT over websockets TLS](#enable-mqtt-over-websockets-tls)
  - [Troubleshooting MQTT](#troubleshooting-mqtt)

<!-- vim-markdown-toc -->

## Node Red

> I installed node red as a root service

### Prepare

Create a CNAME for this host like `node` and forward port 1880 to the server in the NAT. Edit the `/etc/hosts` accordingly. Also create a firewall rule.

### Install

```bash
su
apt install build-essential git
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)
npm install -g node-red-admin
```

### Usage

Autostart on boot `systemctl enable nodered.service`

Manual commands:

```bash
node-red-start
node-red-stop
node-red-restart
node-red-admin
node-red-log
```

### Secure with https

`certbot certonly --nginx -d node.beachlab.org`

Note where the certificates are located `/etc/letsencrypt/live/node.beachlab.org/`. Certificates will renew automatically, but we need to create a hook to reload node-red, when certificate is renewed..

`nano /etc/letsencrypt/renewal/node.beachlab.org.conf`

add

`renew_hook = systemctl restart nodered`

test

`certbot renew --dry-run`

and uncomment/edit the following lines

```js
https: {
    key: require("fs").readFileSync('/etc/letsencrypt/live/node.beachlab.org/privkey.pem'),
    cert: require("fs").readFileSync('/etc/letsencrypt/live/node.beachlab.org/cert.pem')
},

requireHttps: true,
```

![https-nodered](../img/https-nodered.png)

> Note: http to https redirection is not working but I don't know why. [Here they propose](https://stackoverflow.com/questions/53808673/node-red-requirehttps-does-not-work-accessing-http-does-not-redirect-to-https) a workaround.
>
> I ended up redirecting http://node.beachlab.org to https://node.beachlab.org:1880 in by creating and enabling a site in nginx
>
> ```bash
> server {
>	listen 80;
>	listen [::]:80;
>	server_name node.beachlab.org;
>	return 301 https://$host:1880$request_uri;
> }
> ```

### Secure the editor with username and password

If you use node red without user authentication anyone can take over the whole system.

`nano .node-red/settings.js`

and uncomment/edit

```js
// Securing Node-RED
// -----------------
// To password protect the Node-RED editor and admin API, the following
// property can be used. See http://nodered.org/docs/security.html for details.
adminAuth: {
    type: "credentials",
    users: [{
        username: "admin",
        password: "$2a$08$zZWtXTja0fB1pzD4sHCMyOCMYz2Z6dNbM6tl8sJogENOMcxWV9DN.",
        permissions: "*"
    }]
},
```

> Note: The above are not my real username/password. Do you think I am idiot?

To generate the password hash use `node-red-admin hash-pw`

## Mosquitto broker

In this IoT world, who doesn't need a mosquitto broker? Create a CNAME for the host `mosquitto` in your domain registrar. In your router, forward NAT port 1883 to your server. Create a firewall rule to allow 1883/tcp.

### Install and test

`sudo apt install mosquitto mosquitto-clients`

In another computer try to subscribe to your mosquitto broker

`mosquitto_sub -h mosquitto.beachlab.org -t test`

In the server publish something to the broker

`mosquitto_pub -h localhost -t test -m "hello world"`

This was my first MQTT message!

### Adding users to mosquitto

Generate a password for a specific user, in this case me, and store it in /etc/mosquitto/passwd

> WARNING: This will delete existing users and passwords
> `sudo mosquitto_passwd -c /etc/mosquitto/passwd fran`

If you need to ADD an extra USER without removing the existing ones, use this instead:

`sudo mosquitto_passwd /etc/mosquitto/passwd fmcu`

Create a config file to deny anonymous users

`sudo nano /etc/mosquitto/conf.d/default.conf`

And paste

```bash
allow_anonymous false
password_file /etc/mosquitto/passwd
```

Make sure there is a new line at the end of the file. Restart mosquitto `sudo systemctl restart mosquitto`. Now try to subscribe again to test

```bash
[unix ~]$ mosquitto_sub -h mosquitto.beachlab.org -t test
Connection error: Connection Refused: not authorised.
```

Try to send a message to this topic

```bash
pink@thebeachlab:~$ mosquitto_pub -h localhost -t test -m "hello world"
Connection error: Connection Refused: not authorised.
```

We are good. Subscribe with username and password

`mosquitto_sub -h mosquitto.beachlab.org -t test -u "fran" -P "password"`

Should be good now. And try to publish

`mosquitto_pub -h localhost -t test -u "fran" -P "password" -m "hello world"`

The message should have been received! The only problem remains is that I am sending the password unencrypted over the internet. Oh boy.... we need to use mqtt over TLS instead of over TCP

### Set user permissions
In the config file `/etc/mosquitto/mosquitto.conf` add the following line just before you read the `conf.d`folder: 

`acl_file /etc/mosquitto/aclfile` 

This will tell mosquitto where to find the access control list file. By default everything is blocked unless you unblock it. You can allow read, write or readwrite. This is a sample:

````
# This only affects clients with username "fmcu".
user fmcu
topic write fmcu/id
topic read fmcu/sun
topic read fmcu/online
topic whatever rw
````

### Configure MQTT through TLS

Let's generate the certificates

`sudo certbot certonly --nginx -d mosquitto.beachlab.org`

Open the config file and specify the location of the certificates and the port to use `sudo nano /etc/mosquitto/conf.d/default.conf` and add

```bash
listener 1883 localhost

listener 8883
certfile /etc/letsencrypt/live/mosquitto.beachlab.org/fullchain.pem
keyfile /etc/letsencrypt/live/mosquitto.beachlab.org/privkey.pem
```

1883 will now be unencrypted just for the localhost. Remember to update the firewall rules and the NAT. Reload mosquitto

`sudo systemctl restart mosquitto`

Now subscribe from localhost:

`mosquitto_sub -h localhost -t test -u "fran" -P "password"`

Publish from outside

```bash
[unix ~]$ mosquitto_pub -h mosquitto.beachlab.org -p 8883 -t "my/topic" -m "hello ssl" -u "fran" -P "password"
```
The message should have arrived. To subscribe from outside

`mosquitto_sub -h mosquitto.beachlab.org -p 8883 -t "my/topic" -u "fran" -P "password"`

### Enable MQTT over websockets TLS

`sudo nano /etc/mosquitto/conf.d/default.conf`

Add

```bash
listener 8083
protocol websockets
certfile /etc/letsencrypt/live/mosquitto.beachlab.org/fullchain.pem
keyfile /etc/letsencrypt/live/mosquitto.beachlab.org/privkey.pem
```

Add firewall rules. Adjust NAT or just like me setup a DMZ host for the damn server. I have tested it with the mobile app [owntracks](https://owntracks.org/) and it works like a charm. Coming up in IoT, storing your precious data in a database.

### Troubleshooting MQTT

Mosquitto cannot be started as a service. Service does not start, when started manually `mosquitto -c /etc/mosquitto/mosquitto.conf`complains about cannot open private key
Solved by installing acl `sudo apt install acl` and `sudo setfacl -R -m u:pink:rX /etc/letsencrypt/{live,archive}`

When pink runs it complains about permissions in /var/lib/mosquitto (belongs to mosquitto:root). No idea how to continue
Solved by:

`sudo setfacl -R -m u:mosquitto:rX /etc/letsencrypt/{live,archive}`

But also

`sudo setfacl -R -m d:u:mosquitto:rx /etc/letsencrypt/{live,archive}`

That command sets default ACLs (Access Control Lists) for the Mosquitto user on the specified directories.

Breakdown:
- sudo → run as root
- setfacl → command to set file access control lists
- -R → apply recursively to all files and subdirectories
- -m → modify (add/change) ACL entries
- d: → set a default ACL, meaning new files or dirs created under these paths will inherit this ACL
- u:mosquitto:rx → give user mosquitto read (r) and execute (x) permissions
- /etc/letsencrypt/{live,archive} → target directories

