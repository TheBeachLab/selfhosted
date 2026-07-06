# Minecraft Servers

**Author:** Fran / updated Mr. Watson (2026-07-02)

This host currently runs:

- Java server: Fabric `26.2`, world `Hariburi-World`, service-managed
- Bedrock server: separate `bedrock.service`

## Current state

| | Java | Bedrock |
|---|---|---|
| Path | `/opt/minecraft/server/` | `/home/pink/minecraftbe/bedrock/` |
| User | `minecraft` | `pink` |
| Runtime | Java 25 | N/A |
| Version | Minecraft `26.2` + Fabric Loader `0.19.3` | 1.21.x line |
| Service | `minecraft-java.service` | `bedrock.service` |
| Port | `25565/TCP` | `19132/UDP` |

## Java server

### Service control

```bash
sudo systemctl status minecraft-java.service
sudo systemctl restart minecraft-java.service
sudo journalctl -u minecraft-java.service -n 100 --no-pager
```

Main unit:

```ini
/etc/systemd/system/minecraft-java.service
```

Key paths:

```bash
/opt/minecraft/server/server.properties
/opt/minecraft/server/ops.json
/opt/minecraft/server/whitelist.json
/opt/minecraft/server/start-fabric.sh
/opt/minecraft/server/Hariburi-World/
```

### Current mods

Base stack in `/opt/minecraft/server/mods/`:

- `fabric-api`
- `lifesteal`
- `lithium`
- `ferritecore`
- `noisium`
- `LuckPerms`
- `SkinsRestorer`
- `Simple Voice Chat`
- `Chunky`

Voice Chat listens on `24454/UDP`.

### Offline launcher support / skins

Current Java auth/skin mode:

- `online-mode=false`
- `enforce-secure-profile=false`
- `SkinsRestorer` installed server-side on Fabric

What this means:

- non-premium/offline launchers can join
- skin restoration is handled server-side
- player identity is no longer verified by Mojang, so nickname trust is lower than premium mode

Recommended command for players:

```mcfunction
/skin <name>
```

Useful examples:

```mcfunction
/skin Notch
/skin url "https://example.com/skin.png"
```

Permission notes:

- default players should have at least `skinsrestorer.command`
- if you want `/skin set <name>`, also grant `skinsrestorer.command.set`

### RCON helpers

```bash
/usr/local/bin/minecraft-rcon.sh
/usr/local/bin/minecraft-chat-notify.sh
```

Examples:

```bash
/usr/local/bin/minecraft-rcon.sh list
/usr/local/bin/minecraft-rcon.sh "say test"
```

### World backups

Daily world backup runs without stopping the server:

- chat warning at `04:55 Europe/Madrid`
- backup at `05:00 Europe/Madrid`
- retention: keep last `2`

Scripts:

```bash
/usr/local/bin/minecraft-world-backup.sh
/usr/local/bin/minecraft-chat-notify.sh
```

Cron (`pink`):

```cron
CRON_TZ=Europe/Madrid
55 4 * * * /usr/local/bin/minecraft-chat-notify.sh "World backup in 5 minutes." >>/tmp/minecraft-backup-warnings.log 2>&1
0 5 * * * /usr/local/bin/minecraft-world-backup.sh >/tmp/minecraft-world-backup.log 2>&1
```

Backups land in:

```bash
/opt/minecraft/backups/worlds/
```

### Grace period trigger

There is a datapack in the world for a PvP grace period:

```bash
/opt/minecraft/server/Hariburi-World/datapacks/watson-grace-pack
```

Player command:

```mcfunction
/trigger start
```

Behavior:

- starts a `1h` grace period
- announces start in chat
- warns at `30m` and `5m`
- announces the end
- blocks PvP during the grace period using a temporary team with `friendlyFire false`

### Locator bar

The vanilla locator bar is disabled persistently in world data:

- gamerule: `locatorBar=false`
- applied directly in `Hariburi-World/level.dat`

### Watchdog / Discord

Status notifications are handled by:

```bash
/usr/local/bin/minecraft-discord-watchdog.sh
/usr/local/bin/minecraft-server-state.sh
```

The watchdog runs every minute from `pink`'s crontab.

## Bedrock server

Managed by `bedrock.service`.

```bash
sudo systemctl status bedrock.service
sudo systemctl restart bedrock.service
```

Files:

```bash
/home/pink/minecraftbe/bedrock/start.sh
/home/pink/minecraftbe/bedrock/stop.sh
/home/pink/minecraftbe/bedrock/server.properties
/home/pink/minecraftbe/bedrock/backups/
/home/pink/minecraftbe/bedrock/downloads/
```

## Quick checks

```bash
systemctl status minecraft-java.service --no-pager
systemctl status bedrock.service --no-pager
ss -tulnp | grep -E "25565|19132|24454"
```
