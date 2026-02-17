# Map Frontend — Configuration Reference

**Author:** Mr. Watson 🦄  
**Date:** 2026-02-17

<!-- vim-markdown-toc GFM -->

- [Overview](#overview)
- [File locations](#file-locations)
- [Map init params](#map-init-params)
- [Style themes](#style-themes)
- [Sky (globe background)](#sky-globe-background)
- [DEM / terrain / hillshade](#dem--terrain--hillshade)
- [MDT02 raster layers](#mdt02-raster-layers)
- [Disabling / removing layers](#disabling--removing-layers)
- [URL params](#url-params)
- [Redeploy after editing](#redeploy-after-editing)

<!-- vim-markdown-toc -->

## Overview

Single-page MapLibre 5.9.0 map served at `https://maps.beachlab.org/map/` (also `tiles.beachlab.org/map/`).  
Globe projection always on. Six built-in style themes. MDT02 hillshade + 3D terrain for HU31 (on-the-fly via TiTiler).

## File locations

| File | Purpose |
|---|---|
| `/var/www/tiles.beachlab.org/map/index.html` | Main page (all JS inline) |
| `/var/www/tiles.beachlab.org/map/style-{light,dark,grayscale,white,black,bright}.json` | MapLibre style definitions |
| `/etc/nginx/sites-available/tiles.beachlab.org` | Nginx vhost (both domains + TiTiler proxy) |
| `/usr/local/etc/martin/config.yaml` | Martin tile server config |

## Map init params

In `index.html`, around the `new maplibregl.Map({…})` block:

```js
const map = new maplibregl.Map({
  container: 'map',
  style: styles[getThemeFromUrl()],  // picks from URL ?theme=
  center: [2.073, 40.727],           // initial lon/lat (HU31 area)
  zoom: 7,                           // initial zoom
  minZoom: 2,                        // globe visible from z≥2
  projection: { type: 'globe' },     // globe always on
  maplibreLogo: false,
  hash: true,                        // lat/lon/zoom in URL hash
});
```

**Common tweaks:**
- Change **initial view**: edit `center` and `zoom`.
- Change **minimum zoom**: edit `minZoom` (2 = can see full globe).
- Disable **globe**: change `projection` to `{ type: 'mercator' }` and remove the `setProjection` call in `style.load`.

## Style themes

Six Protomaps-derived styles. Buttons in the UI panel switch between them.

| Button | Style file |
|---|---|
| Light | `style-light.json` |
| Dark | `style-dark.json` |
| Grayscale | `style-grayscale.json` |
| White | `style-white.json` |
| Black | `style-black.json` |
| Bright | `style-bright.json` |

**To add/remove a theme button:**
1. Add/remove entry in the `styles` object in JS.
2. Add/remove the `<button>` in the UI panel HTML.
3. Add/remove the `.onclick` handler at the bottom of the script.

**To edit visual style** (colors, fonts, layer order): edit the corresponding `style-*.json`. Use [MapLibre style spec](https://maplibre.org/maplibre-style-spec/) as reference.

Notable layers present in all styles:
- `water` — fill layer for water bodies
- `water-stroke` — line layer on water edges (`line-color: #2e5a80`, interpolated width/opacity by zoom)
- `boundary-*`, `road-*`, `label-*` etc — standard Protomaps layers

> `water-halo` was removed (was causing a blue blur ring artifact).

## Sky (globe background)

Two-layer approach required — the `sky` style property controls atmosphere/horizon; CSS controls the actual WebGL canvas "space" around the globe.

### 1. Style-level sky (atmosphere, all 6 JSON files)

Each `style-*.json` has a root `sky` key:

```json
"sky": {
  "sky-color": "#000000",
  "horizon-color": "#000000",
  "fog-color": "#000000",
  "fog-ground-blend": 0.15,
  "horizon-fog-blend": 1.0,
  "sky-horizon-blend": 1.0,
  "atmosphere-blend": 1.0
}
```

Edit all 6 files at once:

```bash
python3 - <<'EOF'
import json, glob
sky = {
    "sky-color": "#000000", "horizon-color": "#000000", "fog-color": "#000000",
    "fog-ground-blend": 0.15, "horizon-fog-blend": 1.0,
    "sky-horizon-blend": 1.0, "atmosphere-blend": 1.0
}
for path in glob.glob('/var/www/tiles.beachlab.org/map/style-*.json'):
    s = json.load(open(path)); s['sky'] = sky
    json.dump(s, open(path,'w'), separators=(',',':'))
    print('OK:', path)
EOF
```

### 2. CSS canvas background (space outside the globe)

In `index.html` `<style>` block:

```css
html, body { height: 100%; margin: 0; background: #000; }
#map { position: absolute; inset: 0; background: #000; }
.maplibregl-canvas-container,
.maplibregl-canvas { background: #000; }
```

> Both layers are needed. The style `sky` key alone leaves white "space" visible at full zoom-out.

### JS setSky (redundant safety)

`applySkyState()` also calls `map.setSky(…)` with the same black values on every `style.load`, as a belt-and-suspenders fallback.

**To change sky/space color**: update the hex in all three places (style JSONs, CSS, `applySkyState()`).

## DEM / terrain / hillshade

Source: TiTiler serving `mdt02_hu31.vrt` on-the-fly (HU31 zone only — covers most of mainland Spain).

DEM tile URL built in `mdt02DemTileUrl()`:

```js
const vrt = encodeURIComponent('/opt/tiles/build/mdt02_hu31.vrt');
return `/titiler/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=${vrt}&resampling=bilinear&algorithm=terrainrgb&tilesize=256`;
```

**To switch DEM zone**: replace `mdt02_hu31.vrt` with `mdt02_hu30.vrt`, `mdt02_hu29.vrt`, etc.  
**To use the combined VRT** (all zones): use `mdt02_all.vrt` — may be slow / cause TiTiler OOM at high zoom.

Controls in the UI panel:
- **3D terrain** checkbox → calls `map.setTerrain(…)` with exaggeration slider value / 100
- **Hillshade** checkbox (default: on) → toggles `mdt02-hillshade` layer visibility
- **Exag.** slider (100–250, default 140) → maps to exaggeration factor 1.0–2.5

`applyTerrainState()` runs on every style reload and on checkbox/slider change.

**To disable terrain/hillshade entirely**: remove the UI row and the `applyTerrainState()` call from `style.load` and `load`.

## MDT02 raster layers

Five hidden raster overlay groups, added per zone on style load but kept invisible (`visibility: 'none'`):

| Group | VRT |
|---|---|
| `hu29` | `mdt02_hu29.vrt` |
| `hu30` | `mdt02_hu30.vrt` |
| `hu31` | `mdt02_hu31.vrt` |
| `wgs84` | `mdt02_wgs84.vrt` |
| `regcan95` | `mdt02_regcan95.vrt` |

**To show a raster layer programmatically:**

```js
map.setLayoutProperty('mdt02-layer-hu31', 'visibility', 'visible');
map.setPaintProperty('mdt02-layer-hu31', 'raster-opacity', 0.65);
```

**To remove raster layers entirely**: delete the `applyMdt02State()` call and the `mdt02Groups` / `mdt02TileUrl()` logic.

## Disabling / removing layers

| What | How |
|---|---|
| Remove a style theme | Delete button, `styles` entry, and `.onclick` |
| Remove hillshade | Remove `mdt02-hillshade` addLayer block and UI checkbox |
| Remove 3D terrain | Remove `setTerrain` call and UI checkbox + slider |
| Remove MDT02 rasters | Remove `applyMdt02State()` and related sources |
| Remove navigation control | Remove `map.addControl(new maplibregl.NavigationControl(), …)` |

## URL params

- `?theme=dark` — load a specific theme on page open (default: `light`)
- `#zoom/lat/lon` — map position (maintained by `hash: true`)

## Redeploy after editing

Files are served directly from disk — no build step needed.

```bash
# Validate JS syntax (optional sanity check)
node -e "const fs=require('fs'),vm=require('vm'); \
  const src=fs.readFileSync('/var/www/tiles.beachlab.org/map/index.html','utf8'); \
  const js=src.replace(/[\s\S]*<script>/, '').replace(/<\/script>[\s\S]*/, ''); \
  new vm.Script(js); console.log('JS syntax OK')"

# Reload nginx if you edited the vhost or added new static paths
sudo nginx -t && sudo systemctl reload nginx
```

Browser hard-refresh (`Ctrl+Shift+R`) to bypass cache.
