# Obsidian

<!-- vim-markdown-toc GFM -->

- [Notes and Canvas](#notes-and-canvas)
- [The vaults on the Mac](#the-vaults-on-the-mac)
- [Run it on the NUC](#run-it-on-the-nuc)

<!-- vim-markdown-toc -->

Obsidian is already installed on the Mac. I couldn't find an Obsidian service
or application in the NUC folders I looked at. The browser setup below is WIP.

## Notes and Canvas

The notes are plain Markdown files. Write `[[Another note]]` to link them.
[Graph view](https://help.obsidian.md/plugins/graph) draws those links.

[Canvas](https://help.obsidian.md/plugins/canvas) lets me arrange notes and cards
and draw connections by hand. It saves a `.canvas` file in the vault.

For an agent loop I would draw the idea here, then write the actual nodes and
conditions in [LangGraph](langgraph.md).

## The vaults on the Mac

The project-knowledge pilot uses these folders:

```text
/Users/Papi/Repositories/project-knowledge/vaults/strategy/
/Users/Papi/Repositories/project-knowledge/vaults/hariburi/
```

I can edit `Inicio`, `Decisiones` and `Reuniones`. The files in
`Fuentes/` are generated. To fix one, edit the original and run the pilot's
indexer again. Its README and `AGENTS.md` explain the commands.

## Run it on the NUC

The [LinuxServer image](https://docs.linuxserver.io/images/docker-obsidian/)
runs Obsidian in a remote desktop that opens in the browser. The image uses
`/config` for its files and serves HTTPS on container port 3001.

Use a separate config folder, such as `/srv/obsidian/config/`, and mount only
the vault I want to open. Keep the whole home folder and the Docker socket out
of the container. The desktop includes a terminal.

Ports 3000 and 3001 were already in use on the NUC. Map a free host port, for
example `127.0.0.1:18889:3001`, then connect from the Mac:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:18889:127.0.0.1:18889 pink-sudo
```

Open `https://127.0.0.1:18889/`. The container uses a self-signed certificate.
Keep it behind SSH for now. For public access, set up [Authentik](authentik.md)
and TLS first.

Choose one place for the original vault before adding sync between the Mac
and the NUC. Back up the vault and the config folder together.
