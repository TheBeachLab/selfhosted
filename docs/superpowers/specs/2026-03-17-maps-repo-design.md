# Design Spec: `TheBeachLab/maps` — Private GitHub Monorepo

**Date:** 2026-03-17
**Status:** Approved
**Author:** Fran (brainstormed with Claude)

---

## Overview

Extract all maps-related work from `selfhosted` and `orbita-web` into a new private GitHub repository: `github.com/TheBeachLab/maps`. The repo will be a broader maps monorepo — not scoped to a single product — to support current work (maps.beachlab.org weather/fuel/wind layers, Gaia-style topo) and future map projects (toll calculator, routing, etc.).

orbita-web is **not** included. It becomes self-contained with its own grayscale style. The Gaia topo style assets move to the new repo as a maps asset, decoupled from orbita. The orbita-web grayscale migration (replacing the topo style in `OrbiterMap.svelte`, `FabLabMap.svelte`, `OrbiterForm.svelte`) is a **separate task in orbita-web** and out of scope here. `contours.js` stays in orbita-web until that migration is complete.

---

## Repository Structure

```
maps/
├── apps/
│   └── maps.beachlab.org/        # frontend: index.html, assets, etc.
│                                  # lib/ is NOT here — see shared/libs/
├── shared/
│   ├── styles/
│   │   └── topo/                 # Gaia-style builder script + generated JSON
│   └── libs/
│       ├── weather-overlays.js   # temperature/precipitation/pressure layers
│       └── contours.js           # maplibre-contour wrapper (copy, not remove from orbita-web yet)
├── scripts/
│   ├── weather/                  # GFS pipeline: fetch_gfs.sh + grib2json.py
│   └── fuel/                    # fetch_fuel_prices.py
├── config/                       # cron files, logrotate configs
├── doc/                          # runbooks (note: uses doc/, not docs/)
├── docs/
│   └── superpowers/
│       ├── specs/                # includes this spec
│       └── plans/
└── ignore/                       # gitignored (large binaries, reference assets)
    ├── gaia_gps_assets/          # Gaia GPS reference sprites, JSON, analysis
    └── dev-shots/                # development screenshots (wind, pressure PNGs)
```

`.gitignore` must cover `ignore/` and `node_modules/`.

`doc/` holds runbooks (migrated from `selfhosted/doc/` and `orbita-web/docs/`). `docs/superpowers/` holds specs and plans. The two directories coexist: runbooks go in `doc/`, design artifacts in `docs/`.

---

## Source Migration

### From `selfhosted`

Files are **moved** (removed from selfhosted after migration):

| Source | Destination |
|---|---|
| `doc/map-frontend.md` | `doc/` |
| `doc/weather-layers.md` | `doc/` |
| `doc/fuel-price-layer.md` | `doc/` |
| `doc/planet-basemap.md` | `doc/` |
| `doc/tiles-hybrid.md` | `doc/` |
| `doc/mdt02-spain.md` | `doc/` |
| `doc/airports.md` | `doc/` |
| `doc/baustellen.md` | `doc/` |
| `doc/geodata.md` | `doc/` |
| `doc/osm.md` | `doc/` |
| `scripts/fuel/fetch_fuel_prices.py` | `scripts/fuel/` |
| `config/fuel-fetch.cron` | `config/` |
| `config/fuel-logrotate.conf` | `config/` |
| `docs/superpowers/specs/2026-03-11-weather-layers-design.md` | `docs/superpowers/specs/` |
| `docs/superpowers/specs/2026-03-14-fuel-price-layer-design.md` | `docs/superpowers/specs/` |
| `docs/superpowers/specs/2026-03-17-maps-repo-design.md` (this file) | `docs/superpowers/specs/` |
| `docs/superpowers/plans/2026-03-11-weather-layers.md` | `docs/superpowers/plans/` |

PNG files in selfhosted root (`wind-*.png`, `pressure-*.png`, `weather-*.png`) are untracked in git — copy to `ignore/dev-shots/`, then delete from selfhosted root.

Frontend and GFS scripts are pulled from the server (not currently tracked in selfhosted):

| Server path | Destination | Note |
|---|---|---|
| `/var/www/tiles.beachlab.org/map/` (excluding `lib/`) | `apps/maps.beachlab.org/` | `lib/` is handled separately below |
| `/opt/weather/scripts/fetch_gfs.sh` | `scripts/weather/` | |
| `/opt/weather/scripts/grib2json.py` | `scripts/weather/` | |

The `lib/` subdirectory on the server contains several files. Their disposition:

| Server file | Tracked in maps repo | Location |
|---|---|---|
| `lib/weather-overlays.js` | Yes | `shared/libs/weather-overlays.js` |
| `lib/contours.js` | Yes (copy only) | `shared/libs/contours.js` |
| `lib/maplibre-wind-gl.js` (also called `wind-gl.js`) | No | Server-only; managed via `TheBeachLab/maplibre-wind-gl` npm package |
| `lib/d3-contour.min.js` | No | Server-only vendored dependency |
| `lib/d3-array.min.js` | No | Server-only vendored dependency |

The `apps/maps.beachlab.org/` directory does **not** contain a `lib/` subdirectory. The post-receive hook writes shared libs directly to `…/map/lib/` on deploy.

### From `orbita-web`

Files are **moved** (removed from orbita-web after migration), except `contours.js` which is **copied** (stays in orbita-web until grayscale migration):

| Source | Destination | Action |
|---|---|---|
| `tools/build_orbita_style.py` | `shared/styles/topo/` | Move |
| `tools/style-orbita.json` | `shared/styles/topo/` | Move |
| `tools/build_orbita_style_v1.py` | `shared/styles/topo/` | Move |
| `tools/style-orbita-v1.json` | `shared/styles/topo/` | Move |
| `ignore/gaia_gps_assets/` | `ignore/gaia_gps_assets/` | Move (gitignored in both) |
| `docs/gaia-to-orbita-translation.md` | `doc/` | Move |
| `docs/gaiatopo-feet-layer-analysis.md` | `doc/` | Move |
| `src/lib/contours.js` | `shared/libs/` | **Copy** (not removed from orbita-web yet) |

The `tools/` directory in orbita-web is removed after migration. `src/lib/contours.js` stays in orbita-web until the grayscale migration replaces the topo style and removes `addContourLayers` calls from the three map components.

---

## Deployment

### Server pre-requisites

Before the bare repo and post-receive hook can be set up:

1. **Create bare repo** on server:
   ```bash
   ssh -p 622 git@beachlab.org "git init --bare /home/git/public/maps.git"
   ```

2. **Passwordless sudo for git user** — the `git` user needs sudo rights for deploying scripts. Add a sudoers entry:
   ```
   git ALL=(ALL) NOPASSWD: /usr/bin/rsync, /usr/bin/cp, /usr/bin/chown
   ```
   Scope to specific destination paths if tighter control is needed. Test with:
   ```bash
   ssh -p 622 git@beachlab.org "sudo rsync --version"
   ```

### Post-receive hook

File: `/home/git/public/maps.git/hooks/post-receive` (chmod +x)

Bare repos have no working tree. The hook extracts files via `git archive` into a temp directory, deploys from there, then cleans up:

```bash
#!/bin/bash
TMPDIR=$(mktemp -d)
git archive HEAD | tar -x -C "$TMPDIR"
# rsync/cp from $TMPDIR/... to server destinations
rm -rf "$TMPDIR"
```

Deployment mapping:

| Repo path | Server destination | Owner | Method |
|---|---|---|---|
| `apps/maps.beachlab.org/` | `/var/www/tiles.beachlab.org/map/` | `git:git` | rsync |
| `shared/styles/topo/style-orbita.json` | `/var/www/tiles.beachlab.org/map/style-orbita.json` | `git:git` | cp |
| `shared/libs/weather-overlays.js` | `/var/www/tiles.beachlab.org/map/lib/weather-overlays.js` | `git:git` | cp |
| `shared/libs/contours.js` | `/var/www/tiles.beachlab.org/map/lib/contours.js` | `git:git` | cp |
| `scripts/weather/` | `/opt/weather/scripts/` | `root:root` | sudo rsync |
| `scripts/fuel/` | `/opt/fuel/scripts/` | `root:root` | sudo rsync |

**`style-orbita.json` must be committed** after each run of `build_orbita_style.py`. It is not regenerated on the server — the hook deploys the committed JSON as-is.

### Initialization order

1. Populate local repo with migrated files
2. `git init` + initial commit
3. Create private GitHub repo `TheBeachLab/maps`, push to `origin`
4. Create bare repo on server, install post-receive hook
5. `git push deploy master` to verify

### Git remotes

```bash
git remote add origin git@github.com:TheBeachLab/maps.git
git remote add deploy ssh://git@beachlab.org:622/home/git/public/maps.git
```

No CI/CD — bare repo handles deploy.

---

## Memory Migration

Claude's project memory is keyed to the working directory path. The new memory lives at:

```
~/.claude/projects/-Users-Papi-Repositories-maps/memory/
```

### Memories to migrate

| Source file | Source repo memory dir | Action |
|---|---|---|
| `memory/project_wind_libraries.md` | selfhosted | Move to maps memory |
| `memory/project_fuel_price_layer.md` | selfhosted | Move to maps memory |
| `memory/project_server_services.md` (specific sections) | selfhosted | Extract → maps memory; keep remainder in selfhosted |
| `memory/map-styling.md` | orbita-web (`memory/map-styling.md`) | Move to maps memory |

Sections to extract from `project_server_services.md` into maps memory:
- "Weather layers (deployed 2026-03-11)" — full section
- "Tiles infrastructure" — full section
- "Web properties" — only the `maps.beachlab.org` / `tiles.beachlab.org` entries; keep `beachlab.org` and `mods.beachlab.org` in selfhosted

### Memories to update after migration

- `selfhosted/memory/project_server_services.md` — remove the three sections above; add a pointer: "Maps infrastructure: see TheBeachLab/maps repo memory"
- `selfhosted/memory/MEMORY.md` — remove `project_wind_libraries` and `project_fuel_price_layer` entries
- `orbita-web/memory/MEMORY.md` — remove Map Styling entry; update component notes to reflect grayscale-only style (pending orbita-web grayscale migration task)
- `selfhosted/memory/project_open_todos.md` — stays in selfhosted; the GPU-blocked and actionable todos are server infrastructure concerns, not maps product work
- `selfhosted/memory/user_fran.md` and `selfhosted/memory/feedback_workflow.md` — cross-project preferences; **duplicate** these into maps memory so the new Claude project context has Fran's preferences and the frontend no-touch rule from the start
- `selfhosted/memory/reference_npm_token.md` — **duplicate** into maps memory; future maps packages may need npm publishing

---

## What Stays in Each Repo

### selfhosted
Retains everything not maps-specific: server infrastructure docs, GPU services, telemetry, OpenClaw, Whisper/TTS/ComfyUI, DNS, backups, web, mail, VPN, etc.

### orbita-web
Map components (`OrbiterMap.svelte`, `FabLabMap.svelte`, `OrbiterForm.svelte`) stay. `src/lib/contours.js` stays until grayscale migration. `tools/` is removed. Style transition (topo → grayscale) is a separate task tracked in orbita-web.

---

## Out of Scope

- Orbita-web grayscale migration — separate task in orbita-web
- CI/CD pipeline — bare repo deploy is sufficient
- npm workspaces — premature; add when a second JS package is needed
- `maplibre-wind-gl` migration — already has its own public repo (`TheBeachLab/maplibre-wind-gl`)
- Large tile files (planet.pmtiles, MDT02) — server-only, never tracked in git
- `d3-contour.min.js`, `d3-array.min.js` — server-only vendored deps, not tracked
