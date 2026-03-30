# Minecraft Servers

**Author:** Fran / updated Mr. Watson 🦄 (2026-03-30)

Two servers running: Java Edition (for PC) and Bedrock Edition (for iPad/mobile).

<!-- vim-markdown-toc GFM -->

- [Current state](#current-state)
- [Java Edition](#java-edition)
- [Bedrock Edition](#bedrock-edition)
- [Quick checks](#quick-checks)

<!-- vim-markdown-toc -->

## Current state

| | Java | Bedrock |
|---|---|---|
| Path | `/opt/minecraft/server/` | `/home/pink/minecraftbe/bedrock/` |
| User | pink | pink |
| Java | OpenJDK 21 | N/A |
| Version | 1.21.x | 1.21.30.03 |
| World | Hariburi-World | — |
| Service | none (manual) | `bedrock.service` (active) |
| Port | 25565 | 19132 UDP |

## Java Edition

No systemd service — started manually via screen or similar.

```bash
# Start server
cd /opt/minecraft/server
screen -dmS minecraft java -Xmx4G -Xms1G -jar server.jar nogui

# Attach to console
screen -r minecraft

# Detach: Ctrl+A then D

# Stop (from console)
stop
```

### Config files

```bash
/opt/minecraft/server/server.properties   # main config
/opt/minecraft/server/ops.json            # operators
/opt/minecraft/server/whitelist.json      # whitelist
/opt/minecraft/server/eula.txt            # must be true
```

### Update Java server

```bash
# Download latest from https://www.minecraft.net/en-us/download/server
cd /opt/minecraft/server
wget https://piston-data.mojang.com/v1/objects/.../server.jar -O server.jar
```

### Java runtime

```bash
java --version
# openjdk 21.0.10 2026-01-20
```

If Java needs updating: `sudo apt install openjdk-21-jdk-headless`

## Bedrock Edition

Managed by `bedrock.service`. Auto-updates to latest version on each restart via `start.sh`.

```bash
# Service control
sudo systemctl status bedrock
sudo systemctl start bedrock
sudo systemctl stop bedrock
sudo systemctl restart bedrock

# Attach to server console
screen -r servername

# Detach: Ctrl+A then D
```

### Files

```bash
/home/pink/minecraftbe/bedrock/start.sh         # starts server, checks for updates
/home/pink/minecraftbe/bedrock/stop.sh          # graceful stop
/home/pink/minecraftbe/bedrock/server.properties
/home/pink/minecraftbe/bedrock/backups/         # auto-backups on start
/home/pink/minecraftbe/bedrock/downloads/       # downloaded server zips
```

### Service file

`/etc/systemd/system/bedrock.service`

```ini
[Unit]
Description=bedrock Minecraft Bedrock Server
After=network-online.target

[Service]
User=pink
WorkingDirectory=/home/pink/minecraftbe/bedrock
Type=forking
ExecStart=/bin/bash /home/pink/minecraftbe/bedrock/start.sh
ExecStop=/bin/bash /home/pink/minecraftbe/bedrock/stop.sh
GuessMainPID=no
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
```

## Quick checks

```bash
# Bedrock running?
systemctl status bedrock

# Java running?
screen -list | grep minecraft
ps aux | grep server.jar | grep -v grep

# Ports open?
ss -tulnp | grep -E "25565|19132"

# Bedrock version
ls /home/pink/minecraftbe/bedrock/downloads/ | grep bedrock-server | sort | tail -1
```
