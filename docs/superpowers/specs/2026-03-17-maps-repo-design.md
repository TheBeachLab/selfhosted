# Design Spec: `TheBeachLab/maps` — Private GitHub Monorepo

**Date:** 2026-03-17
**Status:** Approved
**Author:** Fran (brainstormed with Claude)

---

## Overview

Extract all maps-related work from `selfhosted` and `orbita-web` into a new private GitHub repository: `github.com/TheBeachLab/maps`. The repo will be a broader maps monorepo — not scoped to a single product — to support current work (maps.beachlab.org weather/fuel/wind layers, Gaia-style topo) and future map projects (toll calculator, routing, etc.).

orbita-web is **not** included. It becomes self-contained with its own grayscale style. The Gaia topo style assets move to the new repo as a maps asset, decoupled from orbita.

---

## Repository Structure

```
maps/
├── apps/
│   └── maps.beachlab.org/        # frontend: index.html, lib/, assets
├── shared/
│   ├── styles/
│   │   └── topo/                 # Gaia-style builder script + generated JSON
│   └── libs/
│       ├── weather-overlays.js   # temperature/precipitation/pressure layers
│       └── contours.js           # maplibre-contour wrapper
├── scripts/
│   ├── weather/                  # GFS pipeline: fetch_gfs.sh + grib2json.py
│   └── fuel/                    # fetch_fuel_prices.py
├── config/                       # cron files, logrotate configs
├── doc/                          # runbooks
├── docs/
│   └── superpowers/
│       ├── specs/
│       └── plans/
└── ignore/                       # gitignored (large binaries, reference assets)
    ├── gaia_gps_assets/          # Gaia GPS reference sprites, JSON, analysis
    └── dev-shots/                # development screenshots (wind, pressure PNGs)
```

`.gitignore` must cover `ignore/` and `node_modules/`.

---

## Source Migration

### From `selfhosted`

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
| `docs/superpowers/plans/2026-03-11-weather-layers.md` | `docs/superpowers/plans/` |
| All `wind-*.png` / `pressure-*.png` / `weather-*.png` in repo root | `ignore/dev-shots/` |

Frontend and GFS scripts are pulled from the server (not currently tracked in selfhosted):

| Server path | Destination |
|---|---|
| `/var/www/tiles.beachlab.org/map/` (all files) | `apps/maps.beachlab.org/` |
| `/opt/weather/scripts/fetch_gfs.sh` | `scripts/weather/` |
| `/opt/weather/scripts/grib2json.py` | `scripts/weather/` |

### From `orbita-web`

| Source | Destination |
|---|---|
| `tools/build_orbita_style.py` | `shared/styles/topo/` |
| `tools/style-orbita.json` | `shared/styles/topo/` |
| `tools/build_orbita_style_v1.py` | `shared/styles/topo/` |
| `tools/style-orbita-v1.json` | `shared/styles/topo/` |
| `ignore/gaia_gps_assets/` | `ignore/gaia_gps_assets/` |
| `docs/gaia-to-orbita-translation.md` | `doc/` |
| `docs/gaiatopo-feet-layer-analysis.md` | `doc/` |
| `src/lib/contours.js` | `shared/libs/` |

After migration, remove all moved files from orbita-web. orbita-web will add a simple grayscale MapLibre style inline or as a local file — no dependency on the maps repo.

---

## Deployment

### Bare repo on server

Create a bare repo at `/home/git/public/maps.git` on beachlab.org. Add it as a git remote named `deploy`:

```bash
git remote add deploy ssh://git@beachlab.org:622/home/git/public/maps.git
```

A `post-receive` hook deploys changed directories to their server destinations:

| Repo path | Server destination | Owner |
|---|---|---|
| `apps/maps.beachlab.org/` | `/var/www/tiles.beachlab.org/map/` | `git:git` |
| `shared/styles/topo/style-orbita.json` | `/var/www/tiles.beachlab.org/map/style-orbita.json` | `git:git` |
| `shared/libs/weather-overlays.js` | `/var/www/tiles.beachlab.org/map/lib/weather-overlays.js` | `git:git` |
| `shared/libs/contours.js` | `/var/www/tiles.beachlab.org/map/lib/contours.js` | `git:git` |
| `scripts/weather/` | `/opt/weather/scripts/` | `root:root` |
| `scripts/fuel/` | `/opt/fuel/scripts/` | `root:root` |

The hook uses `rsync` for directory deployments and `cp` for individual files. Scripts directories require `sudo` — the `git` user needs passwordless sudo for those specific paths.

### GitHub remote

```bash
git remote add origin git@github.com:TheBeachLab/maps.git
```

Push to both remotes independently. No GitHub Actions CI/CD — the bare repo handles deploy.

---

## Memory Migration

Claude's project memory is keyed to the working directory path. The new memory lives at:

```
~/.claude/projects/-Users-Papi-Repositories-maps/memory/
```

### Memories to migrate

| Source file | Source repo | Action |
|---|---|---|
| `project_wind_libraries.md` | selfhosted | Move to maps memory |
| `project_fuel_price_layer.md` | selfhosted | Move to maps memory |
| `project_server_services.md` (maps sections) | selfhosted | Extract maps sections → maps memory; keep server/infra sections in selfhosted |
| `map-styling.md` | orbita-web | Move to maps memory |

### Memories to update after migration

- `selfhosted/memory/project_server_services.md` — remove weather layers, tiles frontend, fuel data sections; add reference pointer to maps repo
- `orbita-web/memory/MEMORY.md` — remove Map Styling section; update OrbiterMap/FabLabMap to note grayscale-only style

---

## What Stays in Each Repo

### selfhosted
Retains everything not maps-specific: server infrastructure docs, GPU services, telemetry, OpenClaw, Whisper/TTS/ComfyUI, DNS, backups, web, mail, VPN, etc. Maps sections in `project_server_services.md` are replaced with a pointer to the maps repo.

### orbita-web
Map components (`OrbiterMap.svelte`, `FabLabMap.svelte`) stay — they're tightly coupled to orbita auth/data. Style becomes a simple grayscale defined locally. `src/lib/contours.js` is removed (no longer needed without topo style). `tools/` directory is removed after migration.

---

## Out of Scope

- No CI/CD pipeline (bare repo deploy is sufficient)
- No npm workspaces (premature — add when a second JS package is needed)
- No `maplibre-wind-gl` migration (already has its own public repo: `TheBeachLab/maplibre-wind-gl`)
- No large tile files (planet.pmtiles, MDT02) — server-only, never tracked in git
