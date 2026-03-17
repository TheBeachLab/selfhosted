# Maps Repo Setup Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the private `TheBeachLab/maps` GitHub monorepo by migrating files from `selfhosted` and `orbita-web`, setting up server deployment via a bare repo + post-receive hook, simplifying orbita-web to a local grayscale style, and migrating Claude project memories.

**Architecture:** Three phases — (1) populate the new local repo by migrating files from two source repos and pulling live files from the server; (2) clean up orbita-web by replacing the topo style with a self-contained grayscale style and removing all topo dependencies; (3) wire up server deployment and migrate Claude memories.

**Tech Stack:** Git, GitHub CLI (`gh`), MapLibre GL JS style spec, Svelte 5, Astro, SSH port 622 (`ssh -p 622 pink@beachlab.org`, git user `git@beachlab.org`)

---

## Chunk 1: Create maps repo + migrate files

### Task 1: Initialize local maps repo

**Files:**
- Create: `/Users/Papi/Repositories/maps/.gitignore`
- Create: `/Users/Papi/Repositories/maps/README.md`

- [ ] **Step 1: Create directory and init git**

```bash
mkdir -p /Users/Papi/Repositories/maps
cd /Users/Papi/Repositories/maps
git init
```
Expected: `Initialized empty Git repository in …/maps/.git/`

- [ ] **Step 2: Create directory structure**

```bash
mkdir -p apps/maps.beachlab.org \
         shared/styles/topo \
         shared/libs \
         scripts/weather \
         scripts/fuel \
         config \
         doc \
         docs/superpowers/specs \
         docs/superpowers/plans \
         ignore/gaia_gps_assets \
         ignore/dev-shots
```

- [ ] **Step 3: Write .gitignore**

```
ignore/
node_modules/
*.pyc
__pycache__/
.DS_Store
```

- [ ] **Step 4: Write README.md**

```markdown
# maps

Private monorepo for all maps-related work at beachlab.org.

## Structure

- `apps/maps.beachlab.org/` — public maps frontend
- `shared/styles/topo/` — Gaia-inspired topo style (builder + JSON)
- `shared/libs/` — shared JS libraries (weather-overlays, contours)
- `scripts/weather/` — GFS weather data pipeline
- `scripts/fuel/` — fuel price fetcher
- `config/` — cron and system configs
- `doc/` — runbooks
- `docs/superpowers/` — specs and implementation plans
```

- [ ] **Step 5: Initial commit**

```bash
cd /Users/Papi/Repositories/maps
git add .
git commit -m "chore: initialize maps monorepo structure"
```

---

### Task 2: Migrate selfhosted doc files

From the selfhosted git status: `doc/fuel-price-layer.md` is **untracked** (`??`), `doc/planet-basemap.md` is tracked+modified, all others are tracked+unmodified. Handle accordingly.

**Files to move (9 tracked):**
`map-frontend.md`, `weather-layers.md`, `planet-basemap.md`, `tiles-hybrid.md`, `mdt02-spain.md`, `airports.md`, `baustellen.md`, `geodata.md`, `osm.md`

**Files to move (1 untracked):**
`fuel-price-layer.md`

- [ ] **Step 1: Copy all 10 doc files to maps**

```bash
cd /Users/Papi/Repositories/selfhosted
cp doc/map-frontend.md doc/weather-layers.md doc/fuel-price-layer.md \
   doc/planet-basemap.md doc/tiles-hybrid.md doc/mdt02-spain.md \
   doc/airports.md doc/baustellen.md doc/geodata.md doc/osm.md \
   /Users/Papi/Repositories/maps/doc/
```

- [ ] **Step 2: Remove tracked files from selfhosted via git rm**

```bash
cd /Users/Papi/Repositories/selfhosted
git rm doc/map-frontend.md doc/weather-layers.md doc/planet-basemap.md \
       doc/tiles-hybrid.md doc/mdt02-spain.md doc/airports.md \
       doc/baustellen.md doc/geodata.md doc/osm.md
```

- [ ] **Step 3: Remove the untracked file from selfhosted**

```bash
rm /Users/Papi/Repositories/selfhosted/doc/fuel-price-layer.md
```

- [ ] **Step 4: Update selfhosted README.md — remove map entries from TOC**

Open `/Users/Papi/Repositories/selfhosted/README.md` and remove these TOC lines:
- `[Planet Basemap Ops (PMTiles/MBTiles)](doc/planet-basemap.md)`
- `[Spanish CNIG MDT02 Bulk Download to Synology NAS](doc/mdt02-spain.md)`
- `[Hybrid Tiles Pipeline (Vector + Raster)](doc/tiles-hybrid.md)`
- `[Airports Database](doc/airports.md)`
- `[Baustellen in München](doc/baustellen.md)`
- `[Open Geo Data](doc/geodata.md)`
- `[OSM Server](doc/osm.md)`
- Any weather-layers, fuel-price-layer, map-frontend entries if present

- [ ] **Step 5: Commit selfhosted**

```bash
cd /Users/Papi/Repositories/selfhosted
git add README.md
git commit -m "chore: move maps docs to TheBeachLab/maps repo"
```

- [ ] **Step 6: Commit maps**

```bash
cd /Users/Papi/Repositories/maps
git add doc/
git commit -m "docs: migrate runbooks from selfhosted"
```

---

### Task 3: Migrate selfhosted scripts, config, specs, plans

From git status: `config/` and `scripts/` are **untracked** directories. `docs/superpowers/specs/2026-03-14-fuel-price-layer-design.md` is **untracked**. The weather spec and this plan file status are unknown — check first.

- [ ] **Step 1: Check tracking status of spec files**

```bash
cd /Users/Papi/Repositories/selfhosted
git status docs/superpowers/
```
Note which files show as `??` (untracked) vs clean (tracked).

- [ ] **Step 2: Copy files to maps**

```bash
cd /Users/Papi/Repositories/selfhosted
cp scripts/fuel/fetch_fuel_prices.py /Users/Papi/Repositories/maps/scripts/fuel/
cp config/fuel-fetch.cron config/fuel-logrotate.conf /Users/Papi/Repositories/maps/config/
cp docs/superpowers/specs/2026-03-11-weather-layers-design.md \
   docs/superpowers/specs/2026-03-14-fuel-price-layer-design.md \
   docs/superpowers/specs/2026-03-17-maps-repo-design.md \
   /Users/Papi/Repositories/maps/docs/superpowers/specs/
cp docs/superpowers/plans/2026-03-11-weather-layers.md \
   /Users/Papi/Repositories/maps/docs/superpowers/plans/
# Also copy this plan file to maps (will be removed from selfhosted in Task 12)
cp docs/superpowers/plans/2026-03-17-maps-repo-setup.md \
   /Users/Papi/Repositories/maps/docs/superpowers/plans/
```

- [ ] **Step 3: Remove from selfhosted — tracked files use git rm, untracked use rm**

For untracked items (always safe to `rm` regardless of tracking status):
```bash
cd /Users/Papi/Repositories/selfhosted
rm -rf scripts/fuel/
rm -rf config/
rm -f docs/superpowers/specs/2026-03-14-fuel-price-layer-design.md
```

For tracked spec files (use `git rm`; skip if they turned out untracked in Step 1):
```bash
git rm docs/superpowers/specs/2026-03-11-weather-layers-design.md \
       docs/superpowers/specs/2026-03-17-maps-repo-design.md \
       docs/superpowers/plans/2026-03-11-weather-layers.md
```

If any `git rm` fails with "did not match any files", those files are untracked — use `rm -f` on them instead.

- [ ] **Step 4: Commit selfhosted**

```bash
cd /Users/Papi/Repositories/selfhosted
git commit -m "chore: move scripts, config, specs to TheBeachLab/maps repo"
```

If nothing was staged (all files were untracked), skip this step.

- [ ] **Step 5: Commit maps**

```bash
cd /Users/Papi/Repositories/maps
git add scripts/ config/ docs/
git commit -m "chore: migrate scripts, config, specs from selfhosted"
```

---

### Task 4: Move dev screenshots

These files are **untracked** in selfhosted (confirmed `??` in git status).

- [ ] **Step 1: Copy PNGs to maps ignore**

```bash
cd /Users/Papi/Repositories/selfhosted
cp wind-*.png pressure-*.png weather-*.png /Users/Papi/Repositories/maps/ignore/dev-shots/
```

- [ ] **Step 2: Verify the copy succeeded**

```bash
ls /Users/Papi/Repositories/maps/ignore/dev-shots/ | wc -l
```
Expected: ~80 files.

- [ ] **Step 3: Delete from selfhosted root**

```bash
cd /Users/Papi/Repositories/selfhosted
rm -f wind-*.png pressure-*.png weather-*.png
```

- [ ] **Step 4: Verify selfhosted root has no PNG files**

```bash
ls /Users/Papi/Repositories/selfhosted/*.png 2>/dev/null && echo "STILL PRESENT" || echo "OK"
```
Expected: `OK`

---

### Task 5: Pull frontend and libs from server

Server SSH: port **622**. All `rsync` calls use `-e "ssh -p 622"`, all `scp` calls use `-P 622`.

- [ ] **Step 1: Verify server lib/ contents before copying**

```bash
ssh -p 622 pink@beachlab.org "ls /var/www/tiles.beachlab.org/map/lib/"
```
Expected output includes: `weather-overlays.js`, `contours.js`
Note any other files (d3-contour.min.js, d3-array.min.js, maplibre-wind-gl.js) — these are NOT pulled (server-only).

- [ ] **Step 2: Pull frontend files (excluding lib/)**

```bash
rsync -av -e "ssh -p 622" \
  --exclude='lib/' \
  pink@beachlab.org:/var/www/tiles.beachlab.org/map/ \
  /Users/Papi/Repositories/maps/apps/maps.beachlab.org/
```

- [ ] **Step 3: Verify index.html landed, no lib/ present**

```bash
ls /Users/Papi/Repositories/maps/apps/maps.beachlab.org/
```
Expected: `index.html` present, no `lib/` directory.

- [ ] **Step 4: Pull shared libs**

```bash
scp -P 622 pink@beachlab.org:/var/www/tiles.beachlab.org/map/lib/weather-overlays.js \
  /Users/Papi/Repositories/maps/shared/libs/
scp -P 622 pink@beachlab.org:/var/www/tiles.beachlab.org/map/lib/contours.js \
  /Users/Papi/Repositories/maps/shared/libs/
```

- [ ] **Step 5: Pull GFS scripts**

```bash
scp -P 622 pink@beachlab.org:/opt/weather/scripts/fetch_gfs.sh \
  /Users/Papi/Repositories/maps/scripts/weather/
scp -P 622 pink@beachlab.org:/opt/weather/scripts/grib2json.py \
  /Users/Papi/Repositories/maps/scripts/weather/
```

- [ ] **Step 6: Commit**

```bash
cd /Users/Papi/Repositories/maps
git add apps/ shared/libs/ scripts/weather/
git commit -m "chore: pull frontend, shared libs, and GFS scripts from server"
```

---

### Task 6: Migrate files from orbita-web

First check orbita-web git tracking status for the files to move, since tools/ may or may not be tracked.

- [ ] **Step 1: Check orbita-web tracking status**

```bash
cd /Users/Papi/Repositories/orbita-web
git status tools/ docs/gaia* src/lib/contours.js
```
Note which show as `??` (untracked) vs tracked.

- [ ] **Step 2: Copy style tools to maps**

```bash
cp /Users/Papi/Repositories/orbita-web/tools/build_orbita_style.py \
   /Users/Papi/Repositories/orbita-web/tools/style-orbita.json \
   /Users/Papi/Repositories/orbita-web/tools/build_orbita_style_v1.py \
   /Users/Papi/Repositories/orbita-web/tools/style-orbita-v1.json \
   /Users/Papi/Repositories/maps/shared/styles/topo/
```

- [ ] **Step 3: Copy gaia_gps_assets to maps**

The source is `orbita-web/ignore/gaia_gps_assets/` (inside the gitignored `ignore/` dir):
```bash
cp -r /Users/Papi/Repositories/orbita-web/ignore/gaia_gps_assets/ \
      /Users/Papi/Repositories/maps/ignore/gaia_gps_assets/
```

- [ ] **Step 4: Copy gaia analysis docs to maps**

```bash
cp /Users/Papi/Repositories/orbita-web/docs/gaia-to-orbita-translation.md \
   /Users/Papi/Repositories/orbita-web/docs/gaiatopo-feet-layer-analysis.md \
   /Users/Papi/Repositories/maps/doc/
```

- [ ] **Step 5: Copy contours.js — use orbita-web version as canonical**

The orbita-web `src/lib/contours.js` is the maintained source; the server version (already in maps/shared/libs/) may differ. Overwrite with the orbita-web version:
```bash
cp /Users/Papi/Repositories/orbita-web/src/lib/contours.js \
   /Users/Papi/Repositories/maps/shared/libs/contours.js
```

- [ ] **Step 6: Remove files from orbita-web**

For tracked files, use `git rm`. For untracked files, use `rm`. Based on Step 1 results:

If `tools/` is tracked:
```bash
cd /Users/Papi/Repositories/orbita-web
git rm tools/build_orbita_style.py tools/style-orbita.json \
       tools/build_orbita_style_v1.py tools/style-orbita-v1.json
```
If `tools/` is untracked:
```bash
rm -rf /Users/Papi/Repositories/orbita-web/tools/
```

If `docs/gaia*` are tracked:
```bash
cd /Users/Papi/Repositories/orbita-web
git rm docs/gaia-to-orbita-translation.md docs/gaiatopo-feet-layer-analysis.md
```
If untracked:
```bash
rm /Users/Papi/Repositories/orbita-web/docs/gaia-to-orbita-translation.md \
   /Users/Papi/Repositories/orbita-web/docs/gaiatopo-feet-layer-analysis.md
```

For `src/lib/contours.js` — this will be removed as part of orbita-web cleanup in Task 11.
For `ignore/gaia_gps_assets/` — gitignored, not tracked; just delete:
```bash
rm -rf /Users/Papi/Repositories/orbita-web/ignore/gaia_gps_assets/
```

- [ ] **Step 7: Commit orbita-web**

```bash
cd /Users/Papi/Repositories/orbita-web
git commit -m "chore: move map style tools and topo docs to TheBeachLab/maps"
```
(If nothing staged because files were untracked, skip this step.)

- [ ] **Step 8: Commit maps**

```bash
cd /Users/Papi/Repositories/maps
git add shared/styles/topo/ shared/libs/contours.js doc/gaia-to-orbita-translation.md doc/gaiatopo-feet-layer-analysis.md
git commit -m "chore: migrate topo style, gaia assets, and contours from orbita-web"
```

---

### Task 7: Create GitHub repo and push

- [ ] **Step 1: Create private GitHub repo (no automatic push)**

```bash
cd /Users/Papi/Repositories/maps
gh repo create TheBeachLab/maps --private --source=. --remote=origin --no-push
```
Expected: `✓ Created repository TheBeachLab/maps on GitHub`

- [ ] **Step 2: Push to origin**

```bash
git push -u origin master
```

- [ ] **Step 3: Verify on GitHub**

```bash
gh repo view TheBeachLab/maps
```
Expected: private repo with correct file tree.

---

## Chunk 2: orbita-web grayscale migration + server deployment

### Task 8: Write orbita-web grayscale style

The style is a JS object exported from `src/lib/map-style.js` — imported directly by Svelte components, no network fetch. Fonts from Protomaps CDN. Tiles from `pmtiles://https://maps.beachlab.org/data/planet.pmtiles`. Protomaps v4 schema: `kind` property (not `pmap:kind`), source layers: `earth`, `water`, `landcover`, `landuse`, `roads`, `buildings`, `places`, `boundaries`.

**Files:**
- Create: `orbita-web/src/lib/map-style.js`

- [ ] **Step 1: Create map-style.js**

Create `/Users/Papi/Repositories/orbita-web/src/lib/map-style.js`:

```javascript
// Grayscale MapLibre style for orbita.you
// Protomaps v4 schema — property "kind" (NOT "pmap:kind"), source layers:
// earth, water, landcover, landuse, roads, buildings, places, boundaries.
// Hillshade via AWS terrain tiles (terrarium encoding, raster-dem source).
// No sprite, no icon layers — any icon-referencing layer would fail without a sprite.
// All filters use EXPRESSION syntax (["get", "kind"]) — NEVER mix with legacy syntax.
// maxZoom 14 enforced on map instances (city level — project locations not pin-pointable).

export const GRAYSCALE_STYLE = {
  version: 8,
  name: 'Orbita Grayscale',
  glyphs: 'https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf',
  sources: {
    protomaps: {
      type: 'vector',
      url: 'pmtiles://https://maps.beachlab.org/data/planet.pmtiles',
      attribution: "<a href='https://protomaps.com'>Protomaps</a> © <a href='https://openstreetmap.org'>OpenStreetMap</a>"
    },
    terrain: {
      type: 'raster-dem',
      url: 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png',
      encoding: 'terrarium',
      tileSize: 256,
      maxzoom: 15
    }
  },
  // NOTE: Do NOT add a top-level `terrain` property here.
  // That enables 3D terrain mode which is not wanted.
  // The `hillshade` layer type reads the raster-dem source directly for 2D shading.
  layers: [
    { id: 'background', type: 'background',
      paint: { 'background-color': '#f0f0f0' } },

    { id: 'earth', type: 'fill',
      source: 'protomaps', 'source-layer': 'earth',
      paint: { 'fill-color': '#e8e8e8' } },

    { id: 'water', type: 'fill',
      source: 'protomaps', 'source-layer': 'water',
      filter: ['!=', ['get', 'kind'], 'ocean'],
      paint: { 'fill-color': '#b8cdd4' } },

    { id: 'landuse-green', type: 'fill',
      source: 'protomaps', 'source-layer': 'landuse',
      filter: ['in', ['get', 'kind'], ['literal',
        ['park', 'national_park', 'nature_reserve', 'wood', 'forest']]],
      paint: { 'fill-color': '#d8e4d8', 'fill-opacity': 0.6 } },

    { id: 'hillshade', type: 'hillshade',
      source: 'terrain',
      paint: {
        'hillshade-shadow-color': '#888888',
        'hillshade-highlight-color': '#ffffff',
        'hillshade-exaggeration': 0.35
      } },

    { id: 'road-highway-case', type: 'line',
      source: 'protomaps', 'source-layer': 'roads',
      filter: ['==', ['get', 'kind'], 'highway'],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#aaaaaa',
        'line-width': ['interpolate', ['linear'], ['zoom'], 6, 2, 14, 7] } },

    { id: 'road-highway', type: 'line',
      source: 'protomaps', 'source-layer': 'roads',
      filter: ['==', ['get', 'kind'], 'highway'],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#f5f5f5',
        'line-width': ['interpolate', ['linear'], ['zoom'], 6, 1, 14, 5] } },

    { id: 'road-major', type: 'line',
      source: 'protomaps', 'source-layer': 'roads',
      filter: ['==', ['get', 'kind'], 'major_road'],
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#cccccc',
        'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.8, 14, 3] } },

    { id: 'road-minor', type: 'line',
      source: 'protomaps', 'source-layer': 'roads',
      filter: ['in', ['get', 'kind'], ['literal', ['minor_road', 'other']]],
      minzoom: 12,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#dddddd', 'line-width': 1 } },

    { id: 'buildings', type: 'fill',
      source: 'protomaps', 'source-layer': 'buildings',
      minzoom: 13,
      paint: { 'fill-color': '#d8d8d8', 'fill-outline-color': '#c0c0c0' } },

    { id: 'boundary-country', type: 'line',
      source: 'protomaps', 'source-layer': 'boundaries',
      filter: ['<=', ['get', 'kind_detail'], 2],
      paint: { 'line-color': '#999999', 'line-width': 1.5 } },

    { id: 'boundary-state', type: 'line',
      source: 'protomaps', 'source-layer': 'boundaries',
      filter: ['>', ['get', 'kind_detail'], 2],
      paint: { 'line-color': '#b0b0b0', 'line-width': 0.8,
               'line-dasharray': [4, 3] } },

    { id: 'place-country', type: 'symbol',
      source: 'protomaps', 'source-layer': 'places',
      filter: ['==', ['get', 'kind'], 'country'],
      layout: { 'text-field': ['get', 'name'],
        'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 2, 10, 6, 14],
        'text-max-width': 6 },
      paint: { 'text-color': '#333333',
               'text-halo-color': '#f0f0f0', 'text-halo-width': 1.5 } },

    { id: 'place-region', type: 'symbol',
      source: 'protomaps', 'source-layer': 'places',
      filter: ['==', ['get', 'kind'], 'region'],
      minzoom: 5,
      layout: { 'text-field': ['get', 'name'],
        'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 5, 9, 10, 12] },
      paint: { 'text-color': '#555555',
               'text-halo-color': '#f0f0f0', 'text-halo-width': 1.5 } },

    { id: 'place-locality', type: 'symbol',
      source: 'protomaps', 'source-layer': 'places',
      filter: ['==', ['get', 'kind'], 'locality'],
      minzoom: 6,
      layout: { 'text-field': ['get', 'name'],
        'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 6, 8, 14, 14] },
      paint: { 'text-color': '#444444',
               'text-halo-color': '#f0f0f0', 'text-halo-width': 1.5 } }
  ]
};
```

- [ ] **Step 2: Commit**

```bash
cd /Users/Papi/Repositories/orbita-web
git add src/lib/map-style.js
git commit -m "feat: add grayscale MapLibre style (hillshade, no contours, max z14)"
```

---

### Task 9: Update OrbiterMap.svelte

**Files:**
- Modify: `orbita-web/src/components/OrbiterMap.svelte`

Line references from known state: import on line 5, `styleUrl` prop on line 11, `style: styleUrl` on line 287, `addContourLayers` call on line 297.

- [ ] **Step 1: Remove contours import (line 5)**

Remove: `import { addContourLayers } from '../lib/contours.js';`

- [ ] **Step 2: Add GRAYSCALE_STYLE import at top with other imports**

Add after the maplibre/pmtiles imports:
```javascript
import { GRAYSCALE_STYLE } from '../lib/map-style.js';
```

- [ ] **Step 3: Remove styleUrl prop, it is no longer needed**

Remove from `$props()` destructure:
```javascript
styleUrl = 'https://maps.beachlab.org/map/style-orbita.json',
```

- [ ] **Step 4: Update map constructor (around line 287)**

Change:
```javascript
style: styleUrl,
```
To:
```javascript
style: GRAYSCALE_STYLE,
maxZoom: 14,
```

- [ ] **Step 5: Remove addContourLayers call (around line 297)**

Remove: `addContourLayers(m, maplibregl);`

- [ ] **Step 6: Build check**

```bash
cd /Users/Papi/Repositories/orbita-web
npm run build 2>&1 | tail -20
```
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add src/components/OrbiterMap.svelte
git commit -m "refactor: replace topo style with grayscale, remove contours, cap zoom at 14"
```

---

### Task 10: Update FabLabMap.svelte

**Files:**
- Modify: `orbita-web/src/components/FabLabMap.svelte`

Line references: import line 5, style URL line 138, addContourLayers line 148.

- [ ] **Step 1: Edit FabLabMap.svelte**

Remove line 5: `import { addContourLayers } from '../lib/contours.js';`

Add with other imports: `import { GRAYSCALE_STYLE } from '../lib/map-style.js';`

Change line 138:
```javascript
style: 'https://maps.beachlab.org/map/style-orbita.json',
```
To:
```javascript
style: GRAYSCALE_STYLE,
maxZoom: 14,
```

Remove line 148: `addContourLayers(m, maplibregl);`

- [ ] **Step 2: Build check**

```bash
cd /Users/Papi/Repositories/orbita-web
npm run build 2>&1 | tail -20
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/components/FabLabMap.svelte
git commit -m "refactor: replace topo style with grayscale in FabLabMap"
```

---

### Task 11: Update OrbiterForm.svelte + remove contours.js

**Files:**
- Modify: `orbita-web/src/components/OrbiterForm.svelte`
- Delete: `orbita-web/src/lib/contours.js`

Line references: import line 5, style URL line 197, addContourLayers line 206.

- [ ] **Step 1: Edit OrbiterForm.svelte**

Remove line 5: `import { addContourLayers } from '../lib/contours.js';`

Add with other imports: `import { GRAYSCALE_STYLE } from '../lib/map-style.js';`

Change line 197:
```javascript
style: 'https://maps.beachlab.org/map/style-orbita.json',
```
To:
```javascript
style: GRAYSCALE_STYLE,
maxZoom: 14,
```

Remove line 206: `m.on('load', () => addContourLayers(m, maplibregl));`

- [ ] **Step 2: Remove contours.js from orbita-web**

`contours.js` is untracked in orbita-web (confirmed from git status — `??` prefix). Use plain `rm`:
```bash
rm /Users/Papi/Repositories/orbita-web/src/lib/contours.js
```

- [ ] **Step 3: Final build verification — no contours imports anywhere**

```bash
cd /Users/Papi/Repositories/orbita-web
grep -r "contours" src/ && echo "STILL REFERENCED" || echo "OK"
npm run build 2>&1 | tail -20
```
Expected: `OK` from grep, clean build.

- [ ] **Step 4: Commit**

```bash
git add src/components/OrbiterForm.svelte
git commit -m "refactor: replace topo style with grayscale in OrbiterForm, remove contours.js"
```

---

### Task 12: Set up server deployment

- [ ] **Step 1: Create bare repo on server**

```bash
ssh -p 622 git@beachlab.org "git init --bare /home/git/public/maps.git"
```
Expected: `Initialized empty Git repository in /home/git/public/maps.git/`

- [ ] **Step 2: Add passwordless sudo for git user on server**

```bash
ssh -p 622 pink@beachlab.org \
  "echo 'git ALL=(ALL) NOPASSWD: /usr/bin/rsync, /usr/bin/cp, /usr/bin/chown' | sudo tee /etc/sudoers.d/git-maps && sudo chmod 440 /etc/sudoers.d/git-maps"
```

Verify:
```bash
ssh -p 622 git@beachlab.org "sudo rsync --version" 2>&1 | head -1
```
Expected: `rsync  version ...`

- [ ] **Step 3: Write and install post-receive hook**

```bash
cat > /tmp/maps-post-receive << 'HOOK'
#!/bin/bash
set -e
TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

git archive HEAD | tar -x -C "$TMPDIR"

# Frontend (excludes lib/ — handled separately below)
rsync -a --delete --exclude='lib/' "$TMPDIR/apps/maps.beachlab.org/" /var/www/tiles.beachlab.org/map/
chown -R git:git /var/www/tiles.beachlab.org/map/

# Shared libs → map/lib/
mkdir -p /var/www/tiles.beachlab.org/map/lib/
cp "$TMPDIR/shared/libs/weather-overlays.js" /var/www/tiles.beachlab.org/map/lib/weather-overlays.js
cp "$TMPDIR/shared/libs/contours.js" /var/www/tiles.beachlab.org/map/lib/contours.js
chown git:git /var/www/tiles.beachlab.org/map/lib/weather-overlays.js \
              /var/www/tiles.beachlab.org/map/lib/contours.js

# Topo style JSON
cp "$TMPDIR/shared/styles/topo/style-orbita.json" /var/www/tiles.beachlab.org/map/style-orbita.json
chown git:git /var/www/tiles.beachlab.org/map/style-orbita.json

# Weather scripts
sudo rsync -a "$TMPDIR/scripts/weather/" /opt/weather/scripts/
sudo chown -R root:root /opt/weather/scripts/
sudo chmod +x /opt/weather/scripts/fetch_gfs.sh

# Fuel scripts
sudo rsync -a "$TMPDIR/scripts/fuel/" /opt/fuel/scripts/
sudo chown -R root:root /opt/fuel/scripts/

echo "maps deploy complete"
HOOK

scp -P 622 /tmp/maps-post-receive pink@beachlab.org:/tmp/maps-post-receive
ssh -p 622 pink@beachlab.org \
  "sudo cp /tmp/maps-post-receive /home/git/public/maps.git/hooks/post-receive && \
   sudo chmod +x /home/git/public/maps.git/hooks/post-receive && \
   sudo chown git:git /home/git/public/maps.git/hooks/post-receive"
```

- [ ] **Step 4: Add deploy remote and push**

```bash
cd /Users/Papi/Repositories/maps
git remote add deploy ssh://git@beachlab.org:622/home/git/public/maps.git
git push deploy master
```
Expected: hook output ends with `maps deploy complete`

- [ ] **Step 5: Verify deployed files on server**

```bash
ssh -p 622 pink@beachlab.org \
  "ls /var/www/tiles.beachlab.org/map/index.html && \
   ls /var/www/tiles.beachlab.org/map/lib/weather-overlays.js && \
   ls /var/www/tiles.beachlab.org/map/style-orbita.json && \
   echo ALL OK"
```
Expected: `ALL OK`

- [ ] **Step 6: Remove plan file from selfhosted**

```bash
cd /Users/Papi/Repositories/selfhosted
git rm docs/superpowers/plans/2026-03-17-maps-repo-setup.md 2>/dev/null || \
  rm -f docs/superpowers/plans/2026-03-17-maps-repo-setup.md
git commit -m "chore: move maps implementation plan to TheBeachLab/maps repo" 2>/dev/null || true
```

---

## Chunk 3: Memory migration

### Task 13: Create maps project memory

Memory directory path is derived from the working directory. The maps repo is created at `/Users/Papi/Repositories/maps` (Task 1+7 of Chunk 1). Claude Code auto-loads memory from `~/.claude/projects/-Users-Papi-Repositories-maps/memory/` whenever it is opened with that working directory. Create it now so it is ready on first open.

- [ ] **Step 1: Create memory directory**

```bash
mkdir -p ~/.claude/projects/-Users-Papi-Repositories-maps/memory
```

- [ ] **Step 2: Copy cross-project memories (user, feedback, npm token, server access)**

```bash
SH=~/.claude/projects/-Users-Papi-Repositories-selfhosted/memory
MAPS=~/.claude/projects/-Users-Papi-Repositories-maps/memory

cp $SH/user_fran.md $MAPS/
cp $SH/feedback_workflow.md $MAPS/
cp $SH/reference_npm_token.md $MAPS/
cp $SH/reference_server_access.md $MAPS/
```

- [ ] **Step 3: Move wind libraries memory to maps**

```bash
mv $SH/project_wind_libraries.md $MAPS/
```

- [ ] **Step 4: Move fuel price layer memory to maps**

```bash
mv $SH/project_fuel_price_layer.md $MAPS/
```

- [ ] **Step 5: Move map-styling memory from orbita-web to maps**

```bash
ORBITA=~/.claude/projects/-Users-Papi-Repositories-orbita-web/memory
mv $ORBITA/map-styling.md $MAPS/map_styling.md
```

- [ ] **Step 6: Create maps infrastructure memory file**

Create `$MAPS/project_server_services.md`:

```markdown
---
name: Maps infrastructure on beachlab.org
description: Deployment paths, services, and configs for maps.beachlab.org / tiles.beachlab.org
type: project
---

## Weather layers (deployed 2026-03-11)
- GFS pipeline: `scripts/weather/fetch_gfs.sh` + `grib2json.py` → `/opt/weather/scripts/`
- Cron: `/etc/cron.d/weather-fetch` (03:10, 09:10, 15:10, 21:10 UTC)
- JSON output: `/opt/weather/data/latest/` (~4.2 MB/cycle)
- Nginx: `location /weather/` in maps.beachlab.org config
- Runbook: `doc/weather-layers.md`

## Tiles infrastructure
- PMTiles planet basemap: `/opt/tiles/build/planet.pmtiles` (125 GiB, Protomaps 20260216)
- Weekly updater: `/home/osm/downloads/update_planet_pmtiles.sh` (cron Mon 02:00 as root)
- MDT02 dataset: 941 GiB, 8307 files, 100% downloaded
- MDT02 VRTs: `/opt/tiles/build/mdt02_{hu29,hu30,hu31,wgs84,regcan95,all}.vrt`
- Tile API keys: `/etc/nginx/conf.d/tile-apikeys.conf` (still test keys)
- Martin v1.3.1, SSL cert valid until 2026-05-16

## maps.beachlab.org web property
- Working tree: `/var/www/tiles.beachlab.org/map/`
- Bare repo: `/home/git/public/maps.git` (post-receive deploys from TheBeachLab/maps)
- Nginx: `/etc/nginx/sites-available/maps.beachlab.org`
- MapLibre GL JS 5.9.0, globe projection, themes: light/dark/grayscale/white/black/bright
- Styles served from: `/var/www/tiles.beachlab.org/map/`
- Server libs (NOT in repo): `maplibre-wind-gl.js`, `d3-contour.min.js`, `d3-array.min.js`

## Fuel pipeline
- Fetch script: `scripts/fuel/fetch_fuel_prices.py` → `/opt/fuel/scripts/`
- Cron: `config/fuel-fetch.cron` → `/etc/cron.d/`
- Data: `/opt/fuel/data/latest/` — ~43,000 stations (ES/FR/IT/AT)
- Routes: `/opt/fuel/data/latest/routes-malpensa-sitges.geojson`
- Runbook: `doc/fuel-price-layer.md`
```

- [ ] **Step 7: Create maps MEMORY.md index**

Create `$MAPS/MEMORY.md`:

```markdown
# Memory Index

## User
- [user_fran.md](user_fran.md) — Fran's preferences, communication style, security rule

## Feedback
- [feedback_workflow.md](feedback_workflow.md) — Frontend no-touch rule, doc commit flow, CSS workflow

## Project
- [project_server_services.md](project_server_services.md) — Maps infra: deployment paths, weather layers, tiles, fuel pipeline
- [project_wind_libraries.md](project_wind_libraries.md) — maplibre-wind-gl.js (WebGL) and weather-overlays.js libraries
- [project_fuel_price_layer.md](project_fuel_price_layer.md) — Diesel price layer for maps.beachlab.org
- [map_styling.md](map_styling.md) — Gaia GPS-inspired topo style: architecture, zoom transitions, Protomaps schema

## Reference
- [reference_server_access.md](reference_server_access.md) — SSH aliases, server users, shell aliases
- [reference_npm_token.md](reference_npm_token.md) — npm publish token for all packages (expires ~2026-06-11)
```

- [ ] **Step 8: Update selfhosted project_server_services.md — remove maps sections**

Open `$SH/project_server_services.md`. Remove:
- The entire "Weather layers (deployed 2026-03-11)" section
- The entire "Tiles infrastructure" section
- From "Web properties": remove the `tiles.beachlab.org/map/` entry

Add at the end:
```markdown
## Maps infrastructure
See `/Users/Papi/Repositories/maps` repo memory (`project_server_services.md`).
```

- [ ] **Step 9: Update selfhosted MEMORY.md — remove migrated entries**

Open `$SH/MEMORY.md`. Remove lines:
- `- [project_wind_libraries.md](project_wind_libraries.md) …`
- `- [project_fuel_price_layer.md](project_fuel_price_layer.md) …`

**Do NOT remove `project_open_todos.md`** — GPU-blocked and server todos are server infrastructure concerns, not maps product work. They stay in selfhosted.

Add under Reference:
```markdown
- [reference_maps_repo.md](reference_maps_repo.md) — pointer to TheBeachLab/maps private repo
```

- [ ] **Step 10: Create reference_maps_repo.md in selfhosted memory**

Create `$SH/reference_maps_repo.md`:

```markdown
---
name: Maps repo reference
description: Pointer to TheBeachLab/maps where all maps infrastructure and frontend live
type: reference
---

All maps.beachlab.org work lives in the private repo: github.com/TheBeachLab/maps

Local path: /Users/Papi/Repositories/maps
Deploy remote: ssh://git@beachlab.org:622/home/git/public/maps.git
GitHub: https://github.com/TheBeachLab/maps
```

- [ ] **Step 11: Update orbita-web MEMORY.md — remove map-styling entry**

Open `$ORBITA/MEMORY.md`. Remove the `map-styling.md` line. Update the Map Styling section in the main MEMORY.md body to note: "Map styling: grayscale only — defined in `src/lib/map-style.js`. Hillshade, max zoom 14, no contours. Topo style work moved to TheBeachLab/maps."
