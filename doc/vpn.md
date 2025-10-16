# VPN Server

The VPN server allows me to teleport home and access the LAN even when I am traveling

- [Install the server in Ubuntu Server](#install-the-server-in-ubuntu-server)
- [Set the Firewall rules](#set-the-firewall-rules)
- [Set the client side](#set-the-client-side)


## Install the server in Ubuntu Server

```
sudo apt update -y
sudo apt install wget
wget https://git.io/vpn -O openvpn-install.sh
chmod +x openvpn-install.sh
sudo ./openvpn-install.sh
```

In my case I didn't use IP since it is not fixed. I selected `beachlab.org` as the hostname. Select `UDP`, default port `1194`. Select a DNS provider (I selected Cloudflare's `1.1.1.1`). Finally select a name for the client. Every device you connect will need a separate client. The script will install OpenVPN and generate all of the required keys for usage.

Now I copy the VPN configuration file to the current user because I will get it later from the client computer

```
sudo cp /root/tblvpn.ovpn .
sudo chown pink:pink tblvpn.ovpn
```

This is my server config file in `/etc/openvpn/server/server.conf`

```bash
local 192.168.1.50
port 1194
proto udp
dev tun
ca ca.crt
cert server.crt
key server.key
dh dh.pem
auth SHA512
tls-crypt tc.key
topology subnet
server 10.8.0.0 255.255.255.0
#push "redirect-gateway def1 bypass-dhcp"
ifconfig-pool-persist ipp.txt
#push "dhcp-option DNS 1.1.1.1"
#push "dhcp-option DNS 1.0.0.1"
keepalive 10 120
cipher AES-256-CBC
user nobody
group nogroup
persist-key
persist-tun
verb 3
crl-verify crl.pem
explicit-exit-notify
```

## Set the Firewall rules

```
sudo ufw allow 1194/udp comment 'OpenVPN'
sudo ufw reload
```

And set the NAT ports in the router to route incoming traffic to that computer.

## Set the client side

Install `openvpn` in the client machine.

Get the configuration file from the client computer

`scp -P 22222 pink@beachlab.org:/home/pink/tblvpn.ovpn .`

And stablish a connection when needed

`sudo openvpn tblvpn.ovpn`

This is part of my client configuration file

```bash
client
dev tun
proto udp
remote beachlab.org 1194
resolv-retry infinite
nobind
persist-key
persist-tun
remote-cert-tls server
auth SHA512
data-ciphers-fallback AES-256-CBC
verb 3
route-nopull
route 192.168.1.0 255.255.255.0
auth-nocache
<ca>
-----BEGIN CERTIFICATE-----
MIIDQjCCAiqgAwIBAgIUKwnD9NOVkIidc7vqcGR2i67YyOkwDQYJKoZIhvcNAQEL
```

