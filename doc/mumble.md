# Mumble Server (murmur)

Mumble is a low latency voice chat service. Before you start, decide the host (walkie.beachlab.org) and the port (50000) and modify your `/etc/hosts/`, add an CNAME record, set up NAT port forwarding and create a firewall rule.

```bash
sudo ufw allow 50000
sudo ufw reload
sudo ufw status
```

Install the required packages and perform initial configuration

```bash
sudo add-apt-repository ppa:mumble/release
sudo apt update
sudo apt install mumble-server
sudo apt install sqlite
sudo dpkg-reconfigure mumble-server
```

Dig in more advanced config `sudo nano /etc/mumble-server.ini`. Change the port, the host and other parameters

```
; Port to bind TCP and UDP sockets to.
port=50000

; Specific IP or hostname to bind to.
; If this is left blank (default), Murmur will bind to all available addresses.
host=walkie.beachlab.org

; Password to join server.
serverpassword=supersecret

; Maximum number of concurrent clients allowed.
users=20

; Maximum depth of channel nesting. Note that some databases like MySQL using
; InnoDB will fail when operating on deeply nested channels.
channelnestinglimit=4

; Maximum number of channels per server. 0 for unlimited. Note that an
; excessive number of channels will impact server performance
channelcountlimit=100

; Maximum length of text messages in characters. 0 for no limit.
textmessagelength=500

; If you only wish to give your "Root" channel a custom name, then only
; uncomment the 'registerName' parameter.
;
registerName=Beach Lab Fun
```

Reload the server if you make changes `sudo service mumble-server restart`



