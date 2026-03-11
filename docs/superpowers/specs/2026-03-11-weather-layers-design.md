# Weather Layers for maps.beachlab.org

**Date**: 2026-03-11
**Status**: Approved
**Author**: Claude Code + Fran

## Goal

Add animated wind particles and weather data overlays (temperature, precipitation, pressure) as toggleable layers on the existing MapLibre globe at `maps.beachlab.org/map/`. Data sourced from NOAA GFS, processed server-side, rendered client-side with WebGL.

## Architecture

```
NOAA GFS (GRIB2, 4x/day)
    │  cron every 3h
    ▼
/opt/weather/scripts/fetch_gfs.sh
    │  wgrib2 extract → JSON grids
    ▼
/opt/weather/data/latest/*.json
    │  Nginx static serving
    ▼
maps.beachlab.org/weather/*.json
    │
    ▼
MapLibre GL (browser)
    ├─ Wind particle layer (WebGL)
    ├─ Temperature overlay (canvas color ramp)
    ├─ Precipitation overlay (canvas color ramp)
    └─ Pressure isobars (GeoJSON contour lines)
```

## Server-side: GRIB Pipeline

### Dependencies

- `wgrib2` — GRIB2 extraction and conversion (CPU-only, no GPU)
- `curl` — download from NOAA
- `jq` — JSON validation

### Data source

- NOAA GFS 0.5° or 1.0° resolution (nomads.ncep.noaa.gov)
- 4 cycles/day: 00z, 06z, 12z, 18z
- Available ~3.5h after cycle time

### Variables extracted per cycle

| Variable | GRIB2 match | Levels | Output file |
|---|---|---|---|
| U-wind | UGRD | surface, 850mb, 500mb, 250mb | `wind-surface.json`, `wind-850.json`, `wind-500.json`, `wind-250.json` |
| V-wind | VGRD | (same) | (embedded in same files as U) |
| Temperature | TMP | surface (2m) | `temp-surface.json` |
| Precipitation rate | PRATE | surface | `precip.json` |
| Mean sea level pressure | PRMSL | msl | `pressure.json` |

### JSON grid format

Each JSON file contains:

```json
{
  "header": {
    "parameterCategory": 2,
    "parameterNumber": 2,
    "lo1": 0, "la1": 90,
    "lo2": 359, "la2": -90,
    "dx": 1, "dy": 1,
    "nx": 360, "ny": 181,
    "refTime": "2026-03-11T06:00:00Z"
  },
  "data": [...]
}
```

This format is compatible with the mapbox-gl-wind-layer library (based on the earth.nullschool JSON grid format). Wind files contain two entries (U and V components).

### Download size

- Cherry-picked GRIB2 per cycle: ~200MB
- Processed JSON output: ~15-20MB per cycle
- Retention: latest 2 cycles (~40MB max on disk)

### Script: `/opt/weather/scripts/fetch_gfs.sh`

Behavior:
1. Determine latest available GFS cycle (check NOAA nomads index)
2. Skip if already downloaded (compare with `/opt/weather/data/latest/meta.json`)
3. Download GRIB2 file with `curl` (filtered by variable/level via NOAA filter URL)
4. Extract with `wgrib2` to CSV, convert to JSON grids
5. Validate JSON with `jq -e`
6. Atomic swap: write to `staging/`, then `mv` to `latest/`
7. Delete previous-but-one cycle

### Cron

```
10 3,9,15,21 * * * /opt/weather/scripts/fetch_gfs.sh >> /opt/weather/logs/fetch.log 2>&1
```

Offset by 3h10m from cycle times (00z+3h10m=03:10, etc.) to allow NOAA processing time.

### Directory layout

```
/opt/weather/
├── scripts/
│   └── fetch_gfs.sh
├── data/
│   ├── latest/          ← served by Nginx
│   │   ├── meta.json
│   │   ├── wind-surface.json
│   │   ├── wind-850.json
│   │   ├── wind-500.json
│   │   ├── wind-250.json
│   │   ├── temp-surface.json
│   │   ├── precip.json
│   │   └── pressure.json
│   ├── staging/         ← atomic write target
│   └── previous/        ← fallback cycle
└── logs/
    └── fetch.log
```

## Nginx Configuration

Add to `/etc/nginx/sites-available/maps.beachlab.org`:

```nginx
location /weather/ {
    alias /opt/weather/data/latest/;
    add_header Access-Control-Allow-Origin "*" always;
    add_header Cache-Control "max-age=300" always;
    try_files $uri =404;
}
```

5-minute cache — browser re-checks periodically but doesn't hammer the server.

## Client-side: MapLibre Layers

### Wind particle layer

- Based on `mapbox-gl-wind-layer` (github.com/sakitam-gis/wind-layer or similar fork compatible with MapLibre)
- Vendored into `/var/www/tiles.beachlab.org/map/lib/`
- Implemented as custom MapLibre layer (`onAdd`, `render` WebGL hooks)
- Particle behavior:
  - Count: ~5000-8000 (adaptive to zoom level)
  - Speed: scaled by wind magnitude
  - Trail: fade factor 0.96 (configurable)
  - Color: white on dark/black themes, dark gray on light/white themes, adapts via theme callback
- Pressure level selector: radio buttons in layer panel (Surface / 850hPa / 500hPa / 250hPa)
- Data: fetches `/weather/wind-{level}.json`, re-fetches when level changes

### Temperature overlay

- Canvas-based: create offscreen canvas, bilinear-interpolate the 360x181 grid to viewport pixels
- Color ramp: blue (-40°C) → cyan (-20°C) → green (0°C) → yellow (20°C) → red (40°C) → magenta (50°C)
- Rendered as MapLibre custom layer with transparency (~0.6 opacity)
- Updates on map move (re-renders visible portion)

### Precipitation overlay

- Same technique as temperature
- Color ramp: transparent (0) → light blue (light rain) → blue → purple (heavy rain)
- Only values above threshold rendered (avoid painting entire ocean blue)

### Pressure / isobars

- Client-side contour generation using marching squares on the 360x181 grid
- Contour interval: 4hPa
- Rendered as GeoJSON `line` source + layer in MapLibre
- Styled: thin white/gray lines with pressure labels at intervals

### Layer panel integration

New section in the existing `.layers-ctrl-panel`:

```
── WEATHER ──────────────
☐ Wind          [Surface ▾]
☐ Temperature
☐ Precipitation
☐ Pressure (isobars)

GFS 2026-03-11 06:00 UTC
```

- Checkboxes toggle each layer independently
- Wind has a dropdown/radio for pressure level
- Timestamp badge shows data currency, fetched from `meta.json`
- All off by default (existing map unchanged)

### URL parameters

Extend existing URL param handling:

- `?weather=wind,temp` — activate specified layers on load
- `?wind-level=250` — set wind pressure level

## File inventory

### New server files
- `/opt/weather/scripts/fetch_gfs.sh`
- `/opt/weather/data/` directory tree
- Cron entry (root)

### Modified server files
- `/etc/nginx/sites-available/maps.beachlab.org` — add `/weather/` location

### New client files
- `/var/www/tiles.beachlab.org/map/lib/wind-gl.js` — vendored wind particle renderer

### Modified client files
- `/var/www/tiles.beachlab.org/map/index.html` — weather layer classes, panel section, script imports

### New doc
- `selfhosted/doc/weather-layers.md` — runbook

## Out of scope

- Forecast hours (only analysis/nowcast)
- Ocean currents, waves, aerosols (future)
- Mobile-specific optimizations
- Offline/PWA caching of weather data

## Risks

- **NOAA availability**: GFS data can be delayed or unavailable. Script handles gracefully (keeps previous cycle, logs warning).
- **wgrib2 install**: may need to compile from source on the server. Fallback: use `eccodes` (apt-installable) with `grib_get_data`.
- **Browser performance**: wind particles on globe projection are GPU-intensive. Particle count adapts to zoom. Users can toggle off.
- **Disk**: minimal (~50MB). No risk.
