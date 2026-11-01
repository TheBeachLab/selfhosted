# Grok Bot box

Fran's AI assistant Linux machine. Verified on 2026-11-01.

## Tailscale

`grokbot-box` joined the GitHub tailnet `thebeachlab.github` at
`100.65.1.62`. Installed from the Tailscale 1.104.4 static binaries, with
`accept-dns` false and `accept-routes` false. There is no systemd unit. It
autostarts via `/home/box/.local/share/tailscale/ts-start.sh`, and tailscaled
state is in `/home/box/.local/share/tailscale/`.

Per Fran's choice there is no tailnet ACL restriction on this node, so it
can reach all of his machines.

## SSH

The box has its own ed25519 key, comment `grokbot-box@TheBeachLab`. Login
with that key worked on 2026-11-01:

- NUC: `pink@100.91.63.61` port 622
- Liderflor VPS: `root@100.84.36.22`
- pibot1: `operator@100.123.199.49`
- Synology NAS (diskstation): `unix@100.92.107.45` port 22222. Port 22 on
  that address also answers SSH; see [NAS](nas.md).
- lider-server (Windows): `lider@100.70.25.37`. The key is in
  `C:\ProgramData\ssh\administrators_authorized_keys`. That file's ACL was
  temporarily given Modify, then restored to `SYSTEM:(R)` and
  `Administradores:(R)`.

The key is not on laborpc-1 (`100.74.127.28`) or x220 (`100.95.99.50`).
Both were offline on 2026-11-01.
