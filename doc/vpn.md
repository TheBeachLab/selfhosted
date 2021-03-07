# VPN Server

The VPN server allows me to teleport home and access the LAN even when I am traveling

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

