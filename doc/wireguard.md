# WireGuard Setup: Raspberry Pi (Starlink) ↔ Server (beachlab.org) ↔ Laptop

This guide describes how to configure a private, persistent WireGuard VPN between:
- Server: beachlab.org (10.10.10.1)
- Raspberry Pi: behind Starlink (10.10.10.2)
- Laptop: external device (10.10.10.3)

The server acts as the central hub, reachable from anywhere. 
All traffic between nodes is encrypted and routed through beachlab.org.

## 1. Install WireGuard

Run on all three devices:
```bash
sudo apt update
sudo apt install -y wireguard
```

## 2. Generate Keys

On each device:
```bash
wg genkey | tee privatekey | wg pubkey > publickey
```
Save both keys. Each device will have:
- A private key (kept secret)
- A public key (shared with others)

## 3. Server Configuration (/etc/wireguard/wg0.conf)

```ini
[Interface]
Address = 10.10.10.1/24
ListenPort = 51820
PrivateKey = <SERVER_PRIVATE_KEY>

# Raspberry Pi
[Peer]
PublicKey = <PI_PUBLIC_KEY>
AllowedIPs = 10.10.10.2/32

# Laptop
[Peer]
PublicKey = <LAPTOP_PUBLIC_KEY>
AllowedIPs = 10.10.10.3/32
```

## 4. Raspberry Pi Configuration (/etc/wireguard/wg0.conf)

```ini
[Interface]
Address = 10.10.10.2/24
PrivateKey = <PI_PRIVATE_KEY>

[Peer]
PublicKey = <SERVER_PUBLIC_KEY>
Endpoint = beachlab.org:51820
AllowedIPs = 10.10.10.0/24
PersistentKeepalive = 25
```

Notes:
- The Pi connects outbound to beachlab.org, which bypasses Starlink’s CGNAT.
- PersistentKeepalive ensures reconnection every 25 seconds.

## 5. Laptop Configuration (/etc/wireguard/wg0.conf)

```ini
[Interface]
Address = 10.10.10.3/24
PrivateKey = <LAPTOP_PRIVATE_KEY>

[Peer]
PublicKey = <SERVER_PUBLIC_KEY>
Endpoint = beachlab.org:51820
AllowedIPs = 10.10.10.0/24
PersistentKeepalive = 25
```

## 6. Enable IP Forwarding on the Server

```bash
sudo sysctl -w net.ipv4.ip_forward=1
```
Make it permanent in /etc/sysctl.conf:
```
net.ipv4.ip_forward=1
```

## 7. Open the WireGuard Port (Server Only)

```bash
sudo ufw allow 51820/udp
```

## 8. Start and Enable the Interface

Run on all three systems:
```bash
sudo systemctl enable wg-quick@wg0
sudo systemctl start wg-quick@wg0
```

Check status:
```bash
sudo wg show
```

## 9. Test Connectivity

From the server:
```bash
ping -c3 10.10.10.2   # Raspberry Pi
ping -c3 10.10.10.3   # Laptop
```

From the Pi:
```bash
ping -c3 10.10.10.1
```

## 10. Result

You now have a private VPN network:
- 10.10.10.1 → beachlab.org (hub)
- 10.10.10.2 → Raspberry Pi (Starlink)
- 10.10.10.3 → Laptop

Each node can securely reach the others, for example:

```bash
ssh admin@10.10.10.2
ssh user@10.10.10.3
curl http://10.10.10.2:8080
```

The VPN is persistent, fast, and independent of Starlink’s NAT or dynamic IP changes.
