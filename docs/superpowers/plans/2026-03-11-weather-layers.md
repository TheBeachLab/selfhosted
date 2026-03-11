# Weather Layers Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add animated wind particles and weather overlays (temperature, precipitation, pressure isobars) as toggleable layers on the MapLibre globe at maps.beachlab.org.

**Architecture:** Server-side GRIB pipeline (cron → wgrib2 → Python → JSON grids) served as static files via Nginx. Client-side MapLibre custom WebGL layers for wind particle animation, canvas-based raster overlays for temp/precip, and d3-contour GeoJSON for isobars. All layers toggled from the existing layer control panel.

**Tech Stack:** bash + wgrib2 + Python 3 (server pipeline), MapLibre GL JS 5.9.0 + WebGL + d3-contour (client), Nginx (static serving)

**Spec:** `docs/superpowers/specs/2026-03-11-weather-layers-design.md`

---

## Chunk 1: Server-side GRIB Pipeline

### Task 1: Install wgrib2 and create directory structure

**Files:**
- Create: `/opt/weather/scripts/`, `/opt/weather/data/latest/`, `/opt/weather/data/staging/`, `/opt/weather/data/previous/`, `/opt/weather/logs/`

All commands run via `ssh pink-sudo`.

- [ ] **Step 1: Install wgrib2**

```bash
ssh pink-sudo "sudo apt-get update && sudo apt-get install -y libeccodes-tools"
# wgrib2 is not in Ubuntu repos; use eccodes grib_get_data as primary tool
# Verify:
ssh pink-sudo "grib_get_data --help 2>&1 | head -3"
```

If `grib_get_data` not available via libeccodes-tools, install via:
```bash
ssh pink-sudo "sudo apt-get install -y eccodes"
```

- [ ] **Step 2: Create directory structure**

```bash
ssh pink-sudo "sudo mkdir -p /opt/weather/{scripts,data/{latest,staging,previous},logs} && sudo chown -R pink:pink /opt/weather"
```

- [ ] **Step 3: Verify Python3 and jq available**

```bash
ssh pink-sudo "python3 --version && which jq"
```

Expected: Python 3.10.12, /usr/bin/jq

- [ ] **Step 4: Commit note** — no git commit for this task (server-only changes)

---

### Task 2: Write the GRIB-to-JSON converter script (grib2json.py)

**Files:**
- Create: `/opt/weather/scripts/grib2json.py`

This Python script reads CSV output from `grib_ls`/`grib_get_data` and produces JSON grids compatible with wind particle renderers.

- [ ] **Step 1: Write grib2json.py**

```python
#!/usr/bin/env python3
"""Convert GRIB2 CSV data (from grib_get_data) to JSON wind/weather grids.

Output format per file:
  [{"header": {...}, "data": [...]}, ...]

Wind files contain two objects (U, V components).
Scalar files contain one object.
"""
import csv
import json
import sys
import argparse
from pathlib import Path

# GRIB2 code table entries for the header
PARAM_TABLE = {
    'UGRD':  {'parameterCategory': 2, 'parameterNumber': 2, 'shortName': 'u-wind'},
    'VGRD':  {'parameterCategory': 2, 'parameterNumber': 3, 'shortName': 'v-wind'},
    'TMP':   {'parameterCategory': 0, 'parameterNumber': 0, 'shortName': 'temperature'},
    'PRATE': {'parameterCategory': 1, 'parameterNumber': 7, 'shortName': 'precipitation'},
    'PRMSL': {'parameterCategory': 3, 'parameterNumber': 1, 'shortName': 'pressure'},
}

def make_header(param_key, ref_time, nx=360, ny=181, dx=1.0, dy=1.0):
    """Build a JSON header for the given parameter."""
    p = PARAM_TABLE[param_key]
    return {
        'parameterCategory': p['parameterCategory'],
        'parameterNumber': p['parameterNumber'],
        'shortName': p['shortName'],
        'lo1': 0, 'la1': 90,
        'lo2': 359, 'la2': -90,
        'dx': dx, 'dy': dy,
        'nx': nx, 'ny': ny,
        'refTime': ref_time,
    }

def parse_grib_data(csv_path, nx=360, ny=181):
    """Parse grib_get_data CSV output into a flat array [ny*nx].

    grib_get_data output format: "  lat  lon  value"
    Grid goes from 90N,0E → 90N,359E → 89N,0E → ... → 90S,359E
    """
    data = [0.0] * (ny * nx)
    with open(csv_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('Lat'):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            lat = float(parts[0])
            lon = float(parts[1])
            val = float(parts[2])
            # Convert lat/lon to grid index
            j = round((90.0 - lat) / 1.0)  # row: 0=90N, 180=90S
            i = round(lon / 1.0) % nx       # col: 0=0E, 359=359E
            if 0 <= j < ny and 0 <= i < nx:
                data[j * nx + i] = round(val, 2)
    return data

def build_wind_json(u_csv, v_csv, ref_time, output_path, nx=360, ny=181):
    """Build wind JSON with U and V components."""
    u_data = parse_grib_data(u_csv, nx, ny)
    v_data = parse_grib_data(v_csv, nx, ny)
    result = [
        {'header': make_header('UGRD', ref_time, nx, ny), 'data': u_data},
        {'header': make_header('VGRD', ref_time, nx, ny), 'data': v_data},
    ]
    with open(output_path, 'w') as f:
        json.dump(result, f, separators=(',', ':'))

def build_scalar_json(csv_path, param_key, ref_time, output_path, nx=360, ny=181):
    """Build scalar JSON (temp, precip, pressure)."""
    data = parse_grib_data(csv_path, nx, ny)
    result = [
        {'header': make_header(param_key, ref_time, nx, ny), 'data': data},
    ]
    with open(output_path, 'w') as f:
        json.dump(result, f, separators=(',', ':'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert GRIB CSV to JSON grid')
    sub = parser.add_subparsers(dest='cmd')

    wp = sub.add_parser('wind', help='Build wind JSON from U and V CSVs')
    wp.add_argument('u_csv')
    wp.add_argument('v_csv')
    wp.add_argument('ref_time', help='ISO 8601 ref time, e.g. 2026-03-11T06:00:00Z')
    wp.add_argument('output')

    sp = sub.add_parser('scalar', help='Build scalar JSON from one CSV')
    sp.add_argument('csv')
    sp.add_argument('param', choices=list(PARAM_TABLE.keys()))
    sp.add_argument('ref_time')
    sp.add_argument('output')

    args = parser.parse_args()
    if args.cmd == 'wind':
        build_wind_json(args.u_csv, args.v_csv, args.ref_time, args.output)
    elif args.cmd == 'scalar':
        build_scalar_json(args.csv, args.param, args.ref_time, args.output)
    else:
        parser.print_help()
        sys.exit(1)
```

Upload to server:
```bash
# Write locally first, then scp
scp /tmp/grib2json.py pink-sudo:/opt/weather/scripts/grib2json.py
ssh pink-sudo "chmod +x /opt/weather/scripts/grib2json.py"
```

- [ ] **Step 2: Test with a sample — download one GFS GRIB file manually**

```bash
ssh pink-sudo 'cd /tmp && curl -s -o test_gfs.grib2 "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_1p00.pl?file=gfs.t00z.pgrb2.1p00.f000&lev_surface=on&lev_10_m_above_ground=on&var_UGRD=on&var_VGRD=on&var_TMP=on&dir=%2Fgfs.$(date -u +%Y%m%d)%2F00%2Fatmos" && ls -la test_gfs.grib2'
```

If the current cycle isn't available yet, try previous day:
```bash
ssh pink-sudo 'cd /tmp && curl -s -o test_gfs.grib2 "https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_1p00.pl?file=gfs.t00z.pgrb2.1p00.f000&lev_surface=on&lev_10_m_above_ground=on&var_UGRD=on&var_VGRD=on&var_TMP=on&dir=%2Fgfs.$(date -u -d yesterday +%Y%m%d)%2F00%2Fatmos"'
```

- [ ] **Step 3: Extract CSV and test conversion**

```bash
# Extract U-wind surface
ssh pink-sudo 'grib_get_data -w shortName=10u /tmp/test_gfs.grib2 > /tmp/u_surface.csv 2>/dev/null && head -5 /tmp/u_surface.csv'
# Extract V-wind surface
ssh pink-sudo 'grib_get_data -w shortName=10v /tmp/test_gfs.grib2 > /tmp/v_surface.csv 2>/dev/null && head -5 /tmp/v_surface.csv'
# Extract temperature
ssh pink-sudo 'grib_get_data -w shortName=2t /tmp/test_gfs.grib2 > /tmp/tmp_surface.csv 2>/dev/null && head -5 /tmp/tmp_surface.csv'
# Convert to JSON
ssh pink-sudo 'python3 /opt/weather/scripts/grib2json.py wind /tmp/u_surface.csv /tmp/v_surface.csv "2026-03-11T00:00:00Z" /tmp/test_wind.json'
ssh pink-sudo 'python3 /opt/weather/scripts/grib2json.py scalar /tmp/tmp_surface.csv TMP "2026-03-11T00:00:00Z" /tmp/test_temp.json'
# Validate
ssh pink-sudo 'jq -e ".[0].header.nx" /tmp/test_wind.json && echo "Wind OK" && jq -e ".[0].header.nx" /tmp/test_temp.json && echo "Temp OK"'
```

Expected: nx=360 for both, valid JSON arrays.

**Note on GRIB shortNames**: eccodes uses different short names than wgrib2. For GFS 1.0° at 10m above ground:
- U-wind: `10u`
- V-wind: `10v`
- Temperature at 2m: `2t`
- For pressure levels, filter by `-w shortName=u,level=850`
- PRMSL: `msl`
- PRATE: `tp` or `prate`

If shortNames differ, inspect with: `grib_ls /tmp/test_gfs.grib2`

- [ ] **Step 4: Clean up test files**

```bash
ssh pink-sudo "rm -f /tmp/test_gfs.grib2 /tmp/u_surface.csv /tmp/v_surface.csv /tmp/tmp_surface.csv /tmp/test_wind.json /tmp/test_temp.json"
```

---

### Task 3: Write the GFS fetch script (fetch_gfs.sh)

**Files:**
- Create: `/opt/weather/scripts/fetch_gfs.sh`

- [ ] **Step 1: Write fetch_gfs.sh**

```bash
#!/usr/bin/env bash
# fetch_gfs.sh — Download latest GFS cycle, extract weather grids, produce JSON
set -euo pipefail

WEATHER_DIR="/opt/weather"
SCRIPTS="$WEATHER_DIR/scripts"
STAGING="$WEATHER_DIR/data/staging"
LATEST="$WEATHER_DIR/data/latest"
PREVIOUS="$WEATHER_DIR/data/previous"
LOGFILE="$WEATHER_DIR/logs/fetch.log"

GFS_BASE="https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_1p00.pl"

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] $*"; }

# ── Determine latest available cycle ─────────────────────────────────
find_latest_cycle() {
    local today
    today=$(date -u +%Y%m%d)
    local yesterday
    yesterday=$(date -u -d "yesterday" +%Y%m%d)
    # Try cycles in reverse order: today 18z, 12z, 06z, 00z, then yesterday
    for day in "$today" "$yesterday"; do
        for cycle in 18 12 06 00; do
            local url="${GFS_BASE}?file=gfs.t${cycle}z.pgrb2.1p00.f000&dir=%2Fgfs.${day}%2F${cycle}%2Fatmos"
            if curl -sf --head "$url" >/dev/null 2>&1; then
                echo "${day}:${cycle}"
                return 0
            fi
        done
    done
    return 1
}

CYCLE_INFO=$(find_latest_cycle) || { log "ERROR: No GFS cycle available"; exit 1; }
GFS_DATE="${CYCLE_INFO%%:*}"
GFS_HOUR="${CYCLE_INFO##*:}"
REF_TIME="${GFS_DATE:0:4}-${GFS_DATE:4:2}-${GFS_DATE:6:2}T${GFS_HOUR}:00:00Z"

log "Latest cycle: ${GFS_DATE}/${GFS_HOUR}z (ref: $REF_TIME)"

# ── Check if already processed ───────────────────────────────────────
if [ -f "$LATEST/meta.json" ]; then
    CURRENT=$(python3 -c "import json; print(json.load(open('$LATEST/meta.json'))['refTime'])" 2>/dev/null || echo "")
    if [ "$CURRENT" = "$REF_TIME" ]; then
        log "Already up to date ($REF_TIME). Skipping."
        exit 0
    fi
fi

# ── Download GRIB2 ───────────────────────────────────────────────────
rm -rf "$STAGING"
mkdir -p "$STAGING/grib" "$STAGING/csv" "$STAGING/json"

GRIB_FILE="$STAGING/grib/gfs.grib2"

# Build filter URL for all needed variables
# Surface wind (10m above ground), temperature (2m), PRATE, PRMSL
# Plus pressure levels 850, 500, 250 for wind
FILTER_SURFACE="${GFS_BASE}?file=gfs.t${GFS_HOUR}z.pgrb2.1p00.f000"
FILTER_SURFACE+="&lev_10_m_above_ground=on&lev_2_m_above_ground=on&lev_surface=on&lev_mean_sea_level=on"
FILTER_SURFACE+="&var_UGRD=on&var_VGRD=on&var_TMP=on&var_PRATE=on&var_PRMSL=on"
FILTER_SURFACE+="&dir=%2Fgfs.${GFS_DATE}%2F${GFS_HOUR}%2Fatmos"

FILTER_PRESSURE="${GFS_BASE}?file=gfs.t${GFS_HOUR}z.pgrb2.1p00.f000"
FILTER_PRESSURE+="&lev_250_mb=on&lev_500_mb=on&lev_850_mb=on"
FILTER_PRESSURE+="&var_UGRD=on&var_VGRD=on"
FILTER_PRESSURE+="&dir=%2Fgfs.${GFS_DATE}%2F${GFS_HOUR}%2Fatmos"

log "Downloading surface variables..."
curl -sf -o "$STAGING/grib/surface.grib2" "$FILTER_SURFACE" || { log "ERROR: surface download failed"; exit 1; }

log "Downloading pressure level winds..."
curl -sf -o "$STAGING/grib/pressure.grib2" "$FILTER_PRESSURE" || { log "ERROR: pressure download failed"; exit 1; }

log "Downloads complete. Extracting CSV..."

# ── Extract CSV from GRIB2 ───────────────────────────────────────────
# Surface wind (10m)
grib_get_data -w shortName=10u "$STAGING/grib/surface.grib2" > "$STAGING/csv/u_surface.csv" 2>/dev/null
grib_get_data -w shortName=10v "$STAGING/grib/surface.grib2" > "$STAGING/csv/v_surface.csv" 2>/dev/null

# Temperature (2m)
grib_get_data -w shortName=2t "$STAGING/grib/surface.grib2" > "$STAGING/csv/tmp_surface.csv" 2>/dev/null

# PRMSL
grib_get_data -w shortName=msl "$STAGING/grib/surface.grib2" > "$STAGING/csv/prmsl.csv" 2>/dev/null

# PRATE (may be shortName=prate or tp depending on GFS version)
grib_get_data -w shortName=prate "$STAGING/grib/surface.grib2" > "$STAGING/csv/prate.csv" 2>/dev/null || \
grib_get_data -w shortName=tp "$STAGING/grib/surface.grib2" > "$STAGING/csv/prate.csv" 2>/dev/null || \
log "WARN: precipitation not found"

# Pressure level winds
for level in 850 500 250; do
    grib_get_data -w shortName=u,level=$level "$STAGING/grib/pressure.grib2" > "$STAGING/csv/u_${level}.csv" 2>/dev/null
    grib_get_data -w shortName=v,level=$level "$STAGING/grib/pressure.grib2" > "$STAGING/csv/v_${level}.csv" 2>/dev/null
done

log "CSV extraction complete. Converting to JSON..."

# ── Convert to JSON ──────────────────────────────────────────────────
PY="$SCRIPTS/grib2json.py"

python3 "$PY" wind "$STAGING/csv/u_surface.csv" "$STAGING/csv/v_surface.csv" "$REF_TIME" "$STAGING/json/wind-surface.json"
python3 "$PY" wind "$STAGING/csv/u_850.csv" "$STAGING/csv/v_850.csv" "$REF_TIME" "$STAGING/json/wind-850.json"
python3 "$PY" wind "$STAGING/csv/u_500.csv" "$STAGING/csv/v_500.csv" "$REF_TIME" "$STAGING/json/wind-500.json"
python3 "$PY" wind "$STAGING/csv/u_250.csv" "$STAGING/csv/v_250.csv" "$REF_TIME" "$STAGING/json/wind-250.json"
python3 "$PY" scalar "$STAGING/csv/tmp_surface.csv" TMP "$REF_TIME" "$STAGING/json/temp-surface.json"
python3 "$PY" scalar "$STAGING/csv/prmsl.csv" PRMSL "$REF_TIME" "$STAGING/json/pressure.json"

if [ -s "$STAGING/csv/prate.csv" ]; then
    python3 "$PY" scalar "$STAGING/csv/prate.csv" PRATE "$REF_TIME" "$STAGING/json/precip.json"
else
    log "WARN: skipping precipitation JSON (no data)"
fi

# ── Validate JSON ────────────────────────────────────────────────────
VALID=true
for f in "$STAGING/json/"*.json; do
    if ! jq -e '.[0].header.nx' "$f" >/dev/null 2>&1; then
        log "ERROR: invalid JSON: $f"
        VALID=false
    fi
done

if [ "$VALID" = false ]; then
    log "ERROR: JSON validation failed. Keeping current data."
    exit 1
fi

# ── Write meta.json ──────────────────────────────────────────────────
cat > "$STAGING/json/meta.json" <<METAEOF
{"refTime":"$REF_TIME","fetchedAt":"$(date -u +%Y-%m-%dT%H:%M:%SZ)","cycle":"${GFS_DATE}/${GFS_HOUR}z"}
METAEOF

# ── Atomic swap ──────────────────────────────────────────────────────
rm -rf "$PREVIOUS"
if [ -d "$LATEST" ] && [ "$(ls -A "$LATEST" 2>/dev/null)" ]; then
    mv "$LATEST" "$PREVIOUS"
fi
mkdir -p "$LATEST"
mv "$STAGING/json/"* "$LATEST/"
rm -rf "$STAGING"

log "SUCCESS: Updated to $REF_TIME ($(du -sh "$LATEST" | cut -f1) total)"
```

Upload to server:
```bash
scp /tmp/fetch_gfs.sh pink-sudo:/opt/weather/scripts/fetch_gfs.sh
ssh pink-sudo "chmod +x /opt/weather/scripts/fetch_gfs.sh"
```

- [ ] **Step 2: Run fetch_gfs.sh manually and verify output**

```bash
ssh pink-sudo "/opt/weather/scripts/fetch_gfs.sh"
ssh pink-sudo "ls -la /opt/weather/data/latest/"
ssh pink-sudo "jq '.refTime' /opt/weather/data/latest/meta.json"
ssh pink-sudo "jq '.[0].header | {nx, ny, refTime}' /opt/weather/data/latest/wind-surface.json"
```

Expected: All JSON files present, valid headers with nx=360, ny=181.

- [ ] **Step 3: Run a second time to verify skip logic**

```bash
ssh pink-sudo "/opt/weather/scripts/fetch_gfs.sh"
```

Expected: "Already up to date" message, no re-download.

---

### Task 4: Set up cron and Nginx

**Files:**
- Modify: `/etc/nginx/sites-available/maps.beachlab.org`
- Create: `/etc/logrotate.d/weather-fetch`

- [ ] **Step 1: Add cron job**

```bash
ssh pink-sudo 'sudo bash -c "echo \"10 3,9,15,21 * * * pink /opt/weather/scripts/fetch_gfs.sh >> /opt/weather/logs/fetch.log 2>&1\" > /etc/cron.d/weather-fetch && chmod 644 /etc/cron.d/weather-fetch"'
```

- [ ] **Step 2: Add Nginx location block**

```bash
ssh pink-sudo "sudo cat /etc/nginx/sites-available/maps.beachlab.org" | head -5
# Find the right insertion point (before the catch-all location /)
ssh pink-sudo 'sudo sed -i "/^    # FREE: all other Martin/i\\
    location /weather/ {\\
        alias /opt/weather/data/latest/;\\
        add_header Access-Control-Allow-Origin \"*\" always;\\
        add_header Cache-Control \"max-age=300\" always;\\
        try_files \$uri =404;\\
    }\\
" /etc/nginx/sites-available/maps.beachlab.org'
ssh pink-sudo "sudo nginx -t && sudo nginx -s reload"
```

- [ ] **Step 3: Verify Nginx serves the data**

```bash
curl -s "https://maps.beachlab.org/weather/meta.json" | jq .
curl -sI "https://maps.beachlab.org/weather/wind-surface.json" | grep -E "HTTP|Cache|Access"
```

Expected: JSON response with refTime, Cache-Control: max-age=300, CORS header.

- [ ] **Step 4: Add logrotate**

```bash
ssh pink-sudo 'sudo bash -c "cat > /etc/logrotate.d/weather-fetch <<EOF
/opt/weather/logs/fetch.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
EOF"'
```

- [ ] **Step 5: Commit pipeline documentation**

We'll write the runbook doc and commit at the end (Task 8).

---

## Chunk 2: Client-side Wind Particle Layer

### Task 5: Build custom WebGL wind particle renderer

**Files:**
- Create: `/var/www/tiles.beachlab.org/map/lib/wind-gl.js`

Since no existing library supports MapLibre 5.x globe projection, we write a custom implementation using MapLibre's `CustomLayerInterface` with `getProjectionData()`. The approach: encode wind data as a WebGL texture, run particles in a GPU shader that samples the wind texture and advects particles, render trails with a fade framebuffer.

- [ ] **Step 1: Write wind-gl.js**

This is the core file. It implements a `WindParticleLayer` class that:
1. Loads wind JSON data (U/V grids)
2. Encodes U/V as a WebGL float texture (360x181)
3. Runs a particle simulation: positions stored in a texture, updated each frame by sampling wind
4. Draws particles as points with trail fade effect
5. Integrates with MapLibre's globe projection matrix

```javascript
/**
 * wind-gl.js — WebGL wind particle layer for MapLibre GL JS 5.x (globe-aware)
 *
 * Usage:
 *   const wind = new WindParticleLayer('wind-layer', { color: [1,1,1], numParticles: 65536 });
 *   map.addLayer(wind);
 *   wind.setData(windJsonUrl);
 */
'use strict';

class WindParticleLayer {
  constructor(id, options = {}) {
    this.id = id;
    this.type = 'custom';
    this.renderingMode = '2d';

    this._numParticles = options.numParticles || 65536;
    this._fadeOpacity = options.fadeOpacity || 0.96;
    this._speedFactor = options.speedFactor || 0.25;
    this._color = options.color || [1, 1, 1]; // RGB 0-1
    this._dropRate = options.dropRate || 0.003;
    this._dropRateBump = options.dropRateBump || 0.01;

    this._windData = null;
    this._ready = false;
  }

  // ── Data loading ────────────────────────────────────────────────
  async setData(url) {
    const res = await fetch(url);
    const json = await res.json();
    // json is [uObj, vObj] each with .header and .data
    const uObj = json[0], vObj = json[1];
    this._windData = {
      width: uObj.header.nx,
      height: uObj.header.ny,
      uMin: Math.min(...uObj.data),
      uMax: Math.max(...uObj.data),
      vMin: Math.min(...vObj.data),
      vMax: Math.max(...vObj.data),
      uData: new Float32Array(uObj.data),
      vData: new Float32Array(vObj.data),
    };
    if (this._gl) this._initWindTexture();
    this._ready = true;
    if (this._map) this._map.triggerRepaint();
  }

  // ── MapLibre CustomLayerInterface ───────────────────────────────
  onAdd(map, gl) {
    this._map = map;
    this._gl = gl;

    // Particle size = sqrt(numParticles), must be power of 2 friendly
    this._particleRes = Math.ceil(Math.sqrt(this._numParticles));
    this._numParticles = this._particleRes * this._particleRes;

    this._drawProgram = this._createProgram(gl, DRAW_VERT, DRAW_FRAG);
    this._updateProgram = this._createProgram(gl, UPDATE_VERT, UPDATE_FRAG);
    this._screenProgram = this._createProgram(gl, SCREEN_VERT, SCREEN_FRAG);

    // Particle state textures (ping-pong)
    this._particleStateA = this._createParticleTexture(gl);
    this._particleStateB = this._createParticleTexture(gl);

    // Particle index buffer
    const indices = new Float32Array(this._numParticles);
    for (let i = 0; i < this._numParticles; i++) indices[i] = i;
    this._particleIndexBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this._particleIndexBuf);
    gl.bufferData(gl.ARRAY_BUFFER, indices, gl.STATIC_DRAW);

    // Quad buffer for fullscreen passes
    this._quadBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this._quadBuf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0,0,1,0,0,1,0,1,1,0,1,1]), gl.STATIC_DRAW);

    // Framebuffers for trail fade
    const ext = gl.getExtension('WEBGL_color_buffer_float') || gl.getExtension('EXT_color_buffer_float');
    this._screenTexA = this._createScreenTexture(gl);
    this._screenTexB = this._createScreenTexture(gl);
    this._fboA = this._createFbo(gl, this._screenTexA);
    this._fboB = this._createFbo(gl, this._screenTexB);

    if (this._windData) this._initWindTexture();
  }

  _initWindTexture() {
    const gl = this._gl;
    const d = this._windData;
    // Encode U/V into a single RGBA texture:
    // R = normalized U, G = normalized V, B = speed (for color), A = 1
    const pixels = new Uint8Array(d.width * d.height * 4);
    for (let i = 0; i < d.width * d.height; i++) {
      const u = d.uData[i], v = d.vData[i];
      const uNorm = (u - d.uMin) / (d.uMax - d.uMin);
      const vNorm = (v - d.vMin) / (d.vMax - d.vMin);
      const speed = Math.sqrt(u * u + v * v);
      const speedNorm = Math.min(speed / 30.0, 1.0); // 30 m/s = max
      pixels[i * 4 + 0] = Math.round(uNorm * 255);
      pixels[i * 4 + 1] = Math.round(vNorm * 255);
      pixels[i * 4 + 2] = Math.round(speedNorm * 255);
      pixels[i * 4 + 3] = 255;
    }
    if (this._windTex) gl.deleteTexture(this._windTex);
    this._windTex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this._windTex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, d.width, d.height, 0, gl.RGBA, gl.UNSIGNED_BYTE, pixels);

    // Store wind bounds as uniforms
    this._windBounds = [d.uMin, d.uMax, d.vMin, d.vMax];
  }

  render(gl, args) {
    if (!this._ready || !this._windTex) return;

    const matrix = args.defaultProjectionData.mainMatrix;

    // Save GL state
    const prevBlend = gl.getParameter(gl.BLEND);
    const prevDepth = gl.getParameter(gl.DEPTH_TEST);

    // Resize screen textures if needed
    const w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
    if (this._screenW !== w || this._screenH !== h) {
      this._screenW = w; this._screenH = h;
      this._resizeScreenTextures(gl, w, h);
    }

    // 1. Draw faded previous frame to fboB
    gl.bindFramebuffer(gl.FRAMEBUFFER, this._fboB);
    gl.viewport(0, 0, w, h);
    gl.useProgram(this._screenProgram);
    this._bindTexture(gl, this._screenTexA, 0);
    gl.uniform1i(gl.getUniformLocation(this._screenProgram, 'u_screen'), 0);
    gl.uniform1f(gl.getUniformLocation(this._screenProgram, 'u_opacity'), this._fadeOpacity);
    this._drawQuad(gl, this._screenProgram);

    // 2. Draw new particles on top
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.disable(gl.DEPTH_TEST);
    gl.useProgram(this._drawProgram);

    gl.uniformMatrix4fv(gl.getUniformLocation(this._drawProgram, 'u_matrix'), false, matrix);
    this._bindTexture(gl, this._particleStateA, 0);
    gl.uniform1i(gl.getUniformLocation(this._drawProgram, 'u_particles'), 0);
    this._bindTexture(gl, this._windTex, 1);
    gl.uniform1i(gl.getUniformLocation(this._drawProgram, 'u_wind'), 1);
    gl.uniform1f(gl.getUniformLocation(this._drawProgram, 'u_particleRes'), this._particleRes);
    gl.uniform3fv(gl.getUniformLocation(this._drawProgram, 'u_color'), this._color);

    const aIndex = gl.getAttribLocation(this._drawProgram, 'a_index');
    gl.bindBuffer(gl.ARRAY_BUFFER, this._particleIndexBuf);
    gl.enableVertexAttribArray(aIndex);
    gl.vertexAttribPointer(aIndex, 1, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.POINTS, 0, this._numParticles);
    gl.disableVertexAttribArray(aIndex);

    gl.disable(gl.BLEND);

    // 3. Composite to screen
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, w, h);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(this._screenProgram);
    this._bindTexture(gl, this._screenTexB, 0);
    gl.uniform1i(gl.getUniformLocation(this._screenProgram, 'u_screen'), 0);
    gl.uniform1f(gl.getUniformLocation(this._screenProgram, 'u_opacity'), 1.0);
    this._drawQuad(gl, this._screenProgram);

    // 4. Update particles (advect by wind)
    gl.bindFramebuffer(gl.FRAMEBUFFER, this._createFbo(gl, this._particleStateB));
    gl.viewport(0, 0, this._particleRes, this._particleRes);
    gl.disable(gl.BLEND);
    gl.useProgram(this._updateProgram);
    this._bindTexture(gl, this._particleStateA, 0);
    gl.uniform1i(gl.getUniformLocation(this._updateProgram, 'u_particles'), 0);
    this._bindTexture(gl, this._windTex, 1);
    gl.uniform1i(gl.getUniformLocation(this._updateProgram, 'u_wind'), 1);
    gl.uniform4fv(gl.getUniformLocation(this._updateProgram, 'u_windBounds'), this._windBounds);
    gl.uniform1f(gl.getUniformLocation(this._updateProgram, 'u_speedFactor'), this._speedFactor);
    gl.uniform1f(gl.getUniformLocation(this._updateProgram, 'u_dropRate'), this._dropRate);
    gl.uniform1f(gl.getUniformLocation(this._updateProgram, 'u_dropRateBump'), this._dropRateBump);
    gl.uniform1f(gl.getUniformLocation(this._updateProgram, 'u_rand'), Math.random());
    this._drawQuad(gl, this._updateProgram);

    // Swap
    [this._particleStateA, this._particleStateB] = [this._particleStateB, this._particleStateA];
    [this._screenTexA, this._screenTexB, this._fboA, this._fboB] = [this._screenTexB, this._screenTexA, this._fboB, this._fboA];

    // Restore GL state
    if (prevBlend) gl.enable(gl.BLEND); else gl.disable(gl.BLEND);
    if (prevDepth) gl.enable(gl.DEPTH_TEST); else gl.disable(gl.DEPTH_TEST);
    gl.viewport(0, 0, w, h);

    this._map.triggerRepaint();
  }

  // ── Color setter for theme changes ─────────────────────────────
  setColor(r, g, b) { this._color = [r, g, b]; }

  // ── WebGL helpers ──────────────────────────────────────────────

  _createProgram(gl, vertSrc, fragSrc) {
    const v = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(v, vertSrc); gl.compileShader(v);
    if (!gl.getShaderParameter(v, gl.COMPILE_STATUS)) console.error('Vert:', gl.getShaderInfoLog(v));
    const f = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(f, fragSrc); gl.compileShader(f);
    if (!gl.getShaderParameter(f, gl.COMPILE_STATUS)) console.error('Frag:', gl.getShaderInfoLog(f));
    const p = gl.createProgram();
    gl.attachShader(p, v); gl.attachShader(p, f); gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) console.error('Link:', gl.getProgramInfoLog(p));
    return p;
  }

  _createParticleTexture(gl) {
    const data = new Uint8Array(this._particleRes * this._particleRes * 4);
    for (let i = 0; i < data.length; i += 4) {
      data[i]     = Math.random() * 256; // lon encoded in RG
      data[i + 1] = Math.random() * 256;
      data[i + 2] = Math.random() * 256; // lat encoded in BA
      data[i + 3] = Math.random() * 256;
    }
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, this._particleRes, this._particleRes, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
    return tex;
  }

  _createScreenTexture(gl) {
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    return tex;
  }

  _resizeScreenTextures(gl, w, h) {
    for (const tex of [this._screenTexA, this._screenTexB]) {
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    }
  }

  _createFbo(gl, tex) {
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    return fbo;
  }

  _bindTexture(gl, tex, unit) {
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, tex);
  }

  _drawQuad(gl, program) {
    const aPos = gl.getAttribLocation(program, 'a_pos');
    gl.bindBuffer(gl.ARRAY_BUFFER, this._quadBuf);
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
    gl.disableVertexAttribArray(aPos);
  }

  onRemove() {
    // Cleanup textures, buffers, programs
  }
}

// ── GLSL Shaders ────────────────────────────────────────────────────

const DRAW_VERT = `
  precision highp float;
  attribute float a_index;
  uniform sampler2D u_particles;
  uniform sampler2D u_wind;
  uniform float u_particleRes;
  uniform mat4 u_matrix;
  varying float v_speed;
  void main() {
    float y = floor(a_index / u_particleRes);
    float x = a_index - y * u_particleRes;
    vec2 uv = (vec2(x, y) + 0.5) / u_particleRes;
    vec4 encoded = texture2D(u_particles, uv);
    // Decode lon/lat from RGBA
    float lon = (encoded.r * 256.0 + encoded.g) / 65535.0 * 360.0;
    float lat = (encoded.b * 256.0 + encoded.a) / 65535.0 * 180.0 - 90.0;
    // Sample wind speed for coloring
    vec2 windUV = vec2(lon / 360.0, (90.0 - lat) / 180.0);
    v_speed = texture2D(u_wind, windUV).b;
    // Project lon/lat to clip space via MapLibre matrix
    // Convert to Mercator-like coords (0-1 range)
    float mercX = lon / 360.0;
    float latRad = radians(lat);
    float mercY = (1.0 - log(tan(latRad) + 1.0 / cos(latRad)) / 3.141592653589793) / 2.0;
    gl_Position = u_matrix * vec4(mercX, mercY, 0.0, 1.0);
    gl_PointSize = mix(1.0, 2.5, v_speed);
  }
`;

const DRAW_FRAG = `
  precision highp float;
  uniform vec3 u_color;
  varying float v_speed;
  void main() {
    gl_FragColor = vec4(u_color, mix(0.3, 1.0, v_speed));
  }
`;

const UPDATE_VERT = `
  precision highp float;
  attribute vec2 a_pos;
  varying vec2 v_uv;
  void main() {
    v_uv = a_pos;
    gl_Position = vec4(a_pos * 2.0 - 1.0, 0.0, 1.0);
  }
`;

const UPDATE_FRAG = `
  precision highp float;
  uniform sampler2D u_particles;
  uniform sampler2D u_wind;
  uniform vec4 u_windBounds; // uMin, uMax, vMin, vMax
  uniform float u_speedFactor;
  uniform float u_dropRate;
  uniform float u_dropRateBump;
  uniform float u_rand;
  varying vec2 v_uv;

  // Pseudo-random
  float rand(vec2 co) {
    return fract(sin(dot(co, vec2(12.9898, 78.233))) * 43758.5453);
  }

  void main() {
    vec4 encoded = texture2D(u_particles, v_uv);
    float lon = (encoded.r * 256.0 + encoded.g) / 65535.0 * 360.0;
    float lat = (encoded.b * 256.0 + encoded.a) / 65535.0 * 180.0 - 90.0;

    vec2 windUV = vec2(lon / 360.0, (90.0 - lat) / 180.0);
    vec4 windSample = texture2D(u_wind, windUV);

    float u = mix(u_windBounds.x, u_windBounds.y, windSample.r / 255.0);
    float v = mix(u_windBounds.z, u_windBounds.w, windSample.g / 255.0);
    float speed = windSample.b;

    // Advect
    float newLon = lon + u * u_speedFactor;
    float newLat = lat + v * u_speedFactor;

    // Wrap lon
    newLon = mod(newLon + 360.0, 360.0);
    // Clamp lat
    newLat = clamp(newLat, -90.0, 90.0);

    // Random drop — respawn particles to avoid clustering
    float drop = u_dropRate + speed * u_dropRateBump;
    float r = rand(v_uv + vec2(u_rand));
    if (r < drop) {
      newLon = rand(v_uv + vec2(u_rand + 1.0)) * 360.0;
      newLat = rand(v_uv + vec2(u_rand + 2.0)) * 180.0 - 90.0;
    }

    // Encode back to RGBA
    float lonEnc = newLon / 360.0 * 65535.0;
    float latEnc = (newLat + 90.0) / 180.0 * 65535.0;
    gl_FragColor = vec4(
      floor(lonEnc / 256.0) / 255.0,
      mod(lonEnc, 256.0) / 255.0,
      floor(latEnc / 256.0) / 255.0,
      mod(latEnc, 256.0) / 255.0
    );
  }
`;

const SCREEN_VERT = `
  precision highp float;
  attribute vec2 a_pos;
  varying vec2 v_uv;
  void main() {
    v_uv = a_pos;
    gl_Position = vec4(a_pos * 2.0 - 1.0, 0.0, 1.0);
  }
`;

const SCREEN_FRAG = `
  precision highp float;
  uniform sampler2D u_screen;
  uniform float u_opacity;
  varying vec2 v_uv;
  void main() {
    vec4 color = texture2D(u_screen, v_uv);
    gl_FragColor = vec4(color.rgb, color.a * u_opacity);
  }
`;
```

Upload to server:
```bash
scp /tmp/wind-gl.js pink-sudo:/var/www/tiles.beachlab.org/map/lib/wind-gl.js
```

- [ ] **Step 2: Spike test — add wind layer to map and verify it renders**

Temporarily add to index.html to validate the WebGL layer works with globe projection before proceeding:

```bash
ssh pink-sudo 'sudo cp /var/www/tiles.beachlab.org/map/index.html /var/www/tiles.beachlab.org/map/index.html.bak'
```

Add script tag and test instantiation (detailed in Task 7). For now verify the JS file loads without errors:
```bash
curl -sI "https://maps.beachlab.org/map/lib/wind-gl.js" | head -5
```

Expected: HTTP/2 200.

**Note:** The globe projection matrix (`args.defaultProjectionData.mainMatrix`) is the key integration point. The draw vertex shader converts lon/lat to Mercator coords (0-1), then multiplies by this matrix. If globe projection distorts the particles, we'll need to use `MercatorCoordinate.fromLngLat()` in JavaScript instead and pass pre-projected positions. This is the spike — we test and iterate.

---

## Chunk 3: Client-side Weather Overlays + Integration

### Task 6: Weather overlay classes (temperature, precipitation, pressure)

**Files:**
- Create: `/var/www/tiles.beachlab.org/map/lib/weather-overlays.js`

- [ ] **Step 1: Write weather-overlays.js**

```javascript
/**
 * weather-overlays.js — Canvas-based temperature/precipitation overlays
 * and d3-contour isobar layer for MapLibre GL JS 5.x
 */
'use strict';

// ── Color ramps ─────────────────────────────────────────────────────
const TEMP_STOPS = [
  [-40, [37, 41, 130]],   // deep blue
  [-20, [65, 182, 196]],  // cyan
  [0,   [127, 205, 150]], // green
  [10,  [199, 233, 100]], // yellow-green
  [20,  [255, 237, 74]],  // yellow
  [30,  [254, 153, 41]],  // orange
  [40,  [217, 72, 1]],    // red
  [50,  [153, 0, 102]],   // magenta
];

const PRECIP_STOPS = [
  [0,     [0, 0, 0, 0]],       // transparent
  [0.001, [170, 210, 255, 80]], // light blue
  [0.005, [70, 130, 220, 140]], // blue
  [0.01,  [30, 60, 180, 180]], // dark blue
  [0.02,  [120, 40, 180, 200]], // purple
];

function lerpColor(stops, value) {
  if (value <= stops[0][0]) return stops[0][1];
  if (value >= stops[stops.length - 1][0]) return stops[stops.length - 1][1];
  for (let i = 1; i < stops.length; i++) {
    if (value <= stops[i][0]) {
      const t = (value - stops[i-1][0]) / (stops[i][0] - stops[i-1][0]);
      const a = stops[i-1][1], b = stops[i][1];
      return a.map((v, j) => Math.round(v + (b[j] - v) * t));
    }
  }
  return stops[stops.length - 1][1];
}

// ── Grid-based canvas overlay ───────────────────────────────────────
class WeatherOverlay {
  constructor(id, options = {}) {
    this.id = id;
    this.type = 'custom';
    this.renderingMode = '2d';
    this._opacity = options.opacity || 0.6;
    this._colorStops = options.colorStops || TEMP_STOPS;
    this._unit = options.unit || 'K'; // K=Kelvin, raw=raw value
    this._data = null;
    this._canvas = null;
    this._ready = false;
  }

  async setData(url) {
    const res = await fetch(url);
    const json = await res.json();
    const obj = json[0];
    this._data = {
      width: obj.header.nx,
      height: obj.header.ny,
      values: new Float32Array(obj.data),
    };
    this._renderCanvas();
    this._ready = true;
    if (this._map) this._map.triggerRepaint();
  }

  _renderCanvas() {
    if (!this._data) return;
    const d = this._data;
    if (!this._canvas) {
      this._canvas = document.createElement('canvas');
    }
    this._canvas.width = d.width;
    this._canvas.height = d.height;
    const ctx = this._canvas.getContext('2d');
    const img = ctx.createImageData(d.width, d.height);
    for (let y = 0; y < d.height; y++) {
      for (let x = 0; x < d.width; x++) {
        const idx = y * d.width + x;
        let val = d.values[idx];
        if (this._unit === 'K') val -= 273.15; // Kelvin to Celsius
        const color = lerpColor(this._colorStops, val);
        const pi = idx * 4;
        img.data[pi]     = color[0];
        img.data[pi + 1] = color[1];
        img.data[pi + 2] = color[2];
        img.data[pi + 3] = color.length > 3 ? color[3] : Math.round(this._opacity * 255);
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  onAdd(map, gl) {
    this._map = map;
    this._gl = gl;
    // Use MapLibre's image source approach: add as raster layer
    // This handles projection automatically including globe
    if (this._canvas && this._data) {
      this._addImageSource();
    }
  }

  _addImageSource() {
    const map = this._map;
    const srcId = this.id + '-src';
    const layerId = this.id + '-raster';
    if (map.getSource(srcId)) {
      map.getSource(srcId).updateImage({ url: this._canvas.toDataURL() });
      return;
    }
    map.addSource(srcId, {
      type: 'image',
      url: this._canvas.toDataURL(),
      coordinates: [
        [0, 90],     // top-left (0E, 90N)
        [360, 90],   // top-right (360E, 90N) — wraps
        [360, -90],  // bottom-right (360E, 90S)
        [0, -90],    // bottom-left (0E, 90S)
      ],
    });
    map.addLayer({
      id: layerId,
      type: 'raster',
      source: srcId,
      paint: { 'raster-opacity': this._opacity, 'raster-fade-duration': 0 },
    });
  }

  render(gl, args) {
    // Image source handles rendering; we just trigger repaints when data changes
    if (this._ready && this._canvas && this._map && !this._map.getSource(this.id + '-src')) {
      this._addImageSource();
    }
  }

  setVisibility(visible) {
    if (this._map && this._map.getLayer(this.id + '-raster')) {
      this._map.setLayoutProperty(this.id + '-raster', 'visibility', visible ? 'visible' : 'none');
    }
  }

  onRemove() {}
}

// ── Isobar layer (pressure contours) ────────────────────────────────
class IsobarLayer {
  constructor(id, options = {}) {
    this.id = id;
    this._interval = options.interval || 400; // Pa = 4hPa
    this._lineColor = options.lineColor || 'rgba(200,200,200,0.6)';
    this._data = null;
    this._map = null;
  }

  async setData(url) {
    const res = await fetch(url);
    const json = await res.json();
    const obj = json[0];
    this._data = {
      width: obj.header.nx,
      height: obj.header.ny,
      values: obj.data,
    };
    if (this._map) this._renderContours();
  }

  init(map) {
    this._map = map;
    map.addSource(this.id + '-src', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({
      id: this.id + '-lines',
      type: 'line',
      source: this.id + '-src',
      layout: { visibility: 'none' },
      paint: { 'line-color': this._lineColor, 'line-width': 0.8 },
    });
    if (this._data) this._renderContours();
  }

  _renderContours() {
    if (!this._data || !this._map || typeof d3 === 'undefined') return;
    const d = this._data;
    // Use d3-contour
    const contours = d3.contours()
      .size([d.width, d.height])
      .thresholds(d3.range(
        Math.floor(Math.min(...d.values) / this._interval) * this._interval,
        Math.ceil(Math.max(...d.values) / this._interval) * this._interval,
        this._interval
      ))(d.values);

    // Convert contour coordinates from grid to lon/lat
    const features = contours.map(c => ({
      type: 'Feature',
      properties: { pressure: Math.round(c.value / 100) }, // Pa → hPa
      geometry: {
        type: c.type,
        coordinates: c.coordinates.map(ring =>
          ring.map(polygon =>
            polygon.map(([gx, gy]) => [
              gx * (360 / d.width),           // lon
              90 - gy * (180 / d.height),      // lat
            ])
          )
        ),
      },
    }));

    this._map.getSource(this.id + '-src').setData({
      type: 'FeatureCollection',
      features,
    });
  }

  setVisibility(visible) {
    if (this._map && this._map.getLayer(this.id + '-lines')) {
      this._map.setLayoutProperty(this.id + '-lines', 'visibility', visible ? 'visible' : 'none');
    }
  }
}
```

Upload:
```bash
scp /tmp/weather-overlays.js pink-sudo:/var/www/tiles.beachlab.org/map/lib/weather-overlays.js
```

- [ ] **Step 2: Download and vendor d3-contour**

```bash
# d3-contour standalone (includes d3-array dependency)
ssh pink-sudo 'curl -sL "https://cdn.jsdelivr.net/npm/d3-contour@4/dist/d3-contour.min.js" -o /var/www/tiles.beachlab.org/map/lib/d3-contour.min.js'
ssh pink-sudo 'curl -sL "https://cdn.jsdelivr.net/npm/d3-array@3/dist/d3-array.min.js" -o /var/www/tiles.beachlab.org/map/lib/d3-array.min.js'
ssh pink-sudo 'ls -la /var/www/tiles.beachlab.org/map/lib/'
```

---

### Task 7: Integrate weather layers into index.html

**Files:**
- Modify: `/var/www/tiles.beachlab.org/map/index.html`

- [ ] **Step 1: Add script imports (before closing `</body>`)**

Add after the existing `<script src="/map/lib/maplibre-gl.js"></script>`:

```html
<script src="/map/lib/d3-array.min.js"></script>
<script src="/map/lib/d3-contour.min.js"></script>
<script src="/map/lib/wind-gl.js"></script>
<script src="/map/lib/weather-overlays.js"></script>
```

- [ ] **Step 2: Add Weather section to LayersControl panel HTML**

In the `_panel.innerHTML` template, after the Terrain section, add:

```html
<div class="section" id="weather-section">
  <div class="label">Weather</div>
  <div class="row"><label><input type="checkbox" id="weatherWind"> Wind</label>
    <select id="windLevel" style="font-size:11px;padding:1px 4px;border-radius:4px;border:1px solid #ccc;">
      <option value="surface">Surface</option>
      <option value="850">850 hPa</option>
      <option value="500">500 hPa</option>
      <option value="250">250 hPa</option>
    </select>
  </div>
  <div class="row"><label><input type="checkbox" id="weatherTemp"> Temperature</label></div>
  <div class="row"><label><input type="checkbox" id="weatherPrecip"> Precipitation</label></div>
  <div class="row"><label><input type="checkbox" id="weatherPressure"> Pressure</label></div>
  <div id="weatherTimestamp" style="font-size:10px;color:#999;margin-top:4px;"></div>
</div>
```

- [ ] **Step 3: Add weather layer initialization and toggle logic**

Add after the existing `map.on('load', ...)` block:

```javascript
// ── Weather layers ─────────────────────────────────────────────────
const WEATHER_BASE = '/weather';
let windLayer = null;
let tempOverlay = null;
let precipOverlay = null;
let isobarLayer = null;
let weatherMeta = null;

async function initWeather() {
  try {
    const metaRes = await fetch(WEATHER_BASE + '/meta.json');
    if (!metaRes.ok) {
      document.getElementById('weatherTimestamp').textContent = 'Data unavailable';
      document.querySelectorAll('#weather-section input').forEach(el => el.disabled = true);
      return;
    }
    weatherMeta = await metaRes.json();
    document.getElementById('weatherTimestamp').textContent =
      'GFS ' + weatherMeta.refTime.replace('T', ' ').replace(':00:00Z', 'z');

    // Pre-create layers (not added to map until toggled)
    windLayer = new WindParticleLayer('wind-particles', {
      numParticles: 65536,
      color: [1, 1, 1],
      speedFactor: 0.25,
      fadeOpacity: 0.96,
    });

    tempOverlay = new WeatherOverlay('weather-temp', {
      opacity: 0.5,
      colorStops: TEMP_STOPS,
      unit: 'K',
    });

    precipOverlay = new WeatherOverlay('weather-precip', {
      opacity: 0.6,
      colorStops: PRECIP_STOPS,
      unit: 'raw',
    });

    isobarLayer = new IsobarLayer('weather-isobars', {
      interval: 400,
      lineColor: 'rgba(200,200,200,0.6)',
    });
    isobarLayer.init(map);

  } catch (e) {
    console.warn('Weather init failed:', e);
    document.getElementById('weatherTimestamp').textContent = 'Data unavailable';
  }
}

// Toggle handlers
function toggleWeatherWind() {
  const on = document.getElementById('weatherWind').checked;
  if (on && windLayer) {
    const level = document.getElementById('windLevel').value;
    const url = WEATHER_BASE + '/wind-' + level + '.json';
    if (!map.getLayer('wind-particles')) map.addLayer(windLayer);
    windLayer.setData(url);
  } else if (map.getLayer('wind-particles')) {
    map.removeLayer('wind-particles');
  }
}

function toggleWeatherTemp() {
  const on = document.getElementById('weatherTemp').checked;
  if (on && tempOverlay) {
    tempOverlay.setData(WEATHER_BASE + '/temp-surface.json').then(() => {
      tempOverlay.setVisibility(true);
    });
  } else if (tempOverlay) {
    tempOverlay.setVisibility(false);
  }
}

function toggleWeatherPrecip() {
  const on = document.getElementById('weatherPrecip').checked;
  if (on && precipOverlay) {
    precipOverlay.setData(WEATHER_BASE + '/precip.json').then(() => {
      precipOverlay.setVisibility(true);
    });
  } else if (precipOverlay) {
    precipOverlay.setVisibility(false);
  }
}

function toggleWeatherPressure() {
  const on = document.getElementById('weatherPressure').checked;
  if (on && isobarLayer) {
    isobarLayer.setData(WEATHER_BASE + '/pressure.json').then(() => {
      isobarLayer.setVisibility(true);
    });
  } else if (isobarLayer) {
    isobarLayer.setVisibility(false);
  }
}

// Wind level change
document.getElementById('windLevel').addEventListener('change', () => {
  if (document.getElementById('weatherWind').checked) toggleWeatherWind();
});

// Bind checkboxes
document.getElementById('weatherWind').addEventListener('change', toggleWeatherWind);
document.getElementById('weatherTemp').addEventListener('change', toggleWeatherTemp);
document.getElementById('weatherPrecip').addEventListener('change', toggleWeatherPrecip);
document.getElementById('weatherPressure').addEventListener('change', toggleWeatherPressure);

// Adapt wind color to theme
function updateWindColor(theme) {
  if (!windLayer) return;
  const dark = ['dark', 'black', 'globe'].includes(theme);
  windLayer.setColor(dark ? 1 : 0.2, dark ? 1 : 0.2, dark ? 1 : 0.2);
}

// URL params: ?weather=wind,temp&wind-level=250
function applyWeatherUrlParams() {
  const p = new URLSearchParams(location.search);
  const layers = (p.get('weather') || '').split(',').filter(Boolean);
  const level = p.get('wind-level');
  if (level) document.getElementById('windLevel').value = level;
  if (layers.includes('wind'))  { document.getElementById('weatherWind').checked = true; toggleWeatherWind(); }
  if (layers.includes('temp'))  { document.getElementById('weatherTemp').checked = true; toggleWeatherTemp(); }
  if (layers.includes('precip')){ document.getElementById('weatherPrecip').checked = true; toggleWeatherPrecip(); }
  if (layers.includes('pressure')){ document.getElementById('weatherPressure').checked = true; toggleWeatherPressure(); }
}

map.on('load', () => {
  initWeather().then(applyWeatherUrlParams);
});
```

- [ ] **Step 4: Patch the existing setTheme function to update wind color**

In the existing `setTheme()` function, add at the end:
```javascript
updateWindColor(theme);
```

- [ ] **Step 5: Deploy and test**

```bash
# Upload the modified index.html
scp /tmp/index.html pink-sudo:/var/www/tiles.beachlab.org/map/index.html
```

Open `https://maps.beachlab.org/map/` in browser. Test:
1. Layer panel shows Weather section with timestamp
2. Toggle Wind → animated particles appear
3. Change wind level → particles update
4. Toggle Temperature → color overlay appears
5. Toggle Pressure → isobar lines appear
6. Switch themes → wind particle color adapts
7. URL params: `?weather=wind&wind-level=250`

- [ ] **Step 6: Commit**

If the spike reveals issues with globe projection in the wind shader, iterate on the vertex shader before committing. Common fixes:
- Use `maplibregl.MercatorCoordinate.fromLngLat()` in JS to pre-project
- Pass positions as attributes instead of computing in shader
- Fall back to 2D canvas overlay at zoom < 3

---

### Task 8: Documentation and final commit

**Files:**
- Create: `doc/weather-layers.md` (selfhosted repo)

- [ ] **Step 1: Write the runbook**

```markdown
# Weather Layers (maps.beachlab.org)

> Author: Claude Code — 2026-03-11

Animated wind particles and weather overlays on the MapLibre globe.

## Architecture

```
NOAA GFS → cron 4x/day → eccodes → Python → JSON → Nginx → MapLibre WebGL
```

## Data Pipeline

Script: `/opt/weather/scripts/fetch_gfs.sh`
Converter: `/opt/weather/scripts/grib2json.py`
Output: `/opt/weather/data/latest/*.json`
Cron: `/etc/cron.d/weather-fetch` (03:10, 09:10, 15:10, 21:10 UTC)

### Manual run

```bash
/opt/weather/scripts/fetch_gfs.sh
```

### Check status

```bash
cat /opt/weather/data/latest/meta.json
tail -20 /opt/weather/logs/fetch.log
```

### Dependencies

- `libeccodes-tools` (grib_get_data)
- `python3`, `jq`, `curl`

## Client Layers

- **Wind**: WebGL particle animation (`lib/wind-gl.js`), 4 pressure levels
- **Temperature**: Canvas color ramp overlay, Kelvin→Celsius
- **Precipitation**: Canvas overlay, rate-based coloring
- **Pressure**: d3-contour isobars, 4hPa interval

All toggled from the Layers panel → Weather section.

## URL Parameters

- `?weather=wind,temp,precip,pressure` — activate layers on load
- `?wind-level=250` — select pressure level (surface, 850, 500, 250)

## File Locations

| What | Path |
|---|---|
| Fetch script | `/opt/weather/scripts/fetch_gfs.sh` |
| JSON converter | `/opt/weather/scripts/grib2json.py` |
| JSON output | `/opt/weather/data/latest/` |
| Cron | `/etc/cron.d/weather-fetch` |
| Log | `/opt/weather/logs/fetch.log` |
| Logrotate | `/etc/logrotate.d/weather-fetch` |
| Wind renderer | `/var/www/tiles.beachlab.org/map/lib/wind-gl.js` |
| Weather overlays | `/var/www/tiles.beachlab.org/map/lib/weather-overlays.js` |
| Map page | `/var/www/tiles.beachlab.org/map/index.html` |
| Nginx vhost | `/etc/nginx/sites-available/maps.beachlab.org` |

## Troubleshooting

### No weather data in browser
1. Check `/opt/weather/data/latest/meta.json` exists
2. `curl https://maps.beachlab.org/weather/meta.json`
3. If 404: check Nginx config has `/weather/` location, reload

### Pipeline fails
1. `tail /opt/weather/logs/fetch.log`
2. Check NOAA availability: `curl -sI "https://nomads.ncep.noaa.gov/"`
3. Test eccodes: `grib_ls /opt/weather/data/staging/grib/surface.grib2`

### Wind particles not visible
1. Check browser console for WebGL errors
2. Verify JSON loads: `curl -s https://maps.beachlab.org/weather/wind-surface.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d[0]['data']))"`
3. Expected: 65160 (360*181)
```

- [ ] **Step 2: Commit runbook to selfhosted repo**

```bash
git add doc/weather-layers.md
git commit -m "docs: add weather layers runbook for maps.beachlab.org"
```

- [ ] **Step 3: Push selfhosted repo**

```bash
git push
```

- [ ] **Step 4: Update Watson's memory**

```bash
ssh pink-sudo 'openclaw agent --agent main -m "Weather layers deployed on maps.beachlab.org. Pipeline: /opt/weather/scripts/fetch_gfs.sh (cron 4x/day), JSON at /opt/weather/data/latest/. Client: wind particles (WebGL), temp/precip (canvas), pressure (d3-contour isobars). Runbook: selfhosted/doc/weather-layers.md. All layers toggleable from map panel." --json --timeout 30' 2>&1 | grep -v "^Config"
```

---

## Execution Order Summary

1. **Task 1**: Install eccodes, create dirs (server)
2. **Task 2**: Write + test grib2json.py (server)
3. **Task 3**: Write + test fetch_gfs.sh, run first data fetch (server)
4. **Task 4**: Cron + Nginx + logrotate (server)
5. **Task 5**: Write wind-gl.js, spike test (client)
6. **Task 6**: Write weather-overlays.js, vendor d3 (client)
7. **Task 7**: Integrate into index.html, deploy, test (client)
8. **Task 8**: Runbook doc, commit, push, notify Watson
