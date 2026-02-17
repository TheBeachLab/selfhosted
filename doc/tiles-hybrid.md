# Hybrid Tiles Pipeline (Vector + Raster, future-proof, GPU-aware)

**Author:** Mr. Watson 🦄  
**Date:** 2026-02-08

<!-- vim-markdown-toc GFM -->

- [Goal](#goal)
- [Quick checks](#quick-checks)
- [1) Reality check: where GPU helps](#1-reality-check-where-gpu-helps)
- [2) Target architecture](#2-target-architecture)
- [3) Folder layout (recommended)](#3-folder-layout-recommended)
- [4) Build vector base layer (OSM)](#4-build-vector-base-layer-osm)
- [5) Build raster bathymetry/elevation layer (GEBCO)](#5-build-raster-bathymetryelevation-layer-gebco)
- [6) Serve tiles with Martin (localhost only)](#6-serve-tiles-with-martin-localhost-only)
- [7) Nginx reverse proxy (HTTPS only)](#7-nginx-reverse-proxy-https-only)
- [8) Style file (MapLibre) with vector + raster](#8-style-file-maplibre-with-vector--raster)
- [9) Add future layers quickly](#9-add-future-layers-quickly)
- [10) Ops and performance tips](#10-ops-and-performance-tips)
- [11) Security posture for tiles](#11-security-posture-for-tiles)
- [12) Production update (TiTiler + MDT02 + 3D/hillshade)](#12-production-update-titiler--mdt02--3dhillshade)
- [13) Quick rollback knobs](#13-quick-rollback-knobs)

<!-- vim-markdown-toc -->

## Goal

Build and serve vector + raster tiles through a single HTTPS endpoint, in a way that is easy to extend with new layers.

## Quick checks

```bash
systemctl status martin
curl -I http://127.0.0.1:3000/
sudo nginx -t && systemctl reload nginx
```

## 1) Reality check: where GPU helps

For map tiles, most server-side builders are still **CPU-heavy**:

- Planetiler / Tippecanoe: mostly CPU
- GDAL reprojection / tile pyramid: mostly CPU
- Tile serving: mostly network/disk

GPU is still useful in your stack for:

- AI preprocessing layers (classification/segmentation pipelines)
- Whisper/AI workloads already running on host
- Client-side map rendering (MapLibre/WebGL in browser)

So the best design is:

- Build tiles in robust CPU pipeline
- Keep GPU for AI and future derived layers

---

## 2) Target architecture

```text
Data sources
  ├─ OSM PBF (planet/regional)                -> vector base
  ├─ GEBCO/DEM/GeoTIFF/NetCDF                 -> raster overlays
  └─ Future custom layers (CSV/GeoJSON/PostGIS)

Build
  ├─ Planetiler/Tippecanoe                    -> .pmtiles / .mbtiles (vector)
  └─ GDAL                                     -> .mbtiles (raster)

Serve
  ├─ Martin (localhost:3000)                  -> tile endpoints
  └─ Nginx (443)                              -> public HTTPS
```

---

## 3) Folder layout (recommended)

```bash
sudo mkdir -p /opt/tiles/{sources,build,styles,tmp,scripts}
sudo chown -R pink:pink /opt/tiles
```

Suggested conventions:

- `/opt/tiles/sources` → raw inputs (`.pbf`, `.nc`, `.tif`, `.geojson`)
- `/opt/tiles/build` → final artifacts (`.pmtiles`, `.mbtiles`)
- `/opt/tiles/styles` → `style.json`, sprites, glyph config
- `/opt/tiles/tmp` → temporary build files

---

## 4) Build vector base layer (OSM)

### Option A: Planetiler (recommended for base maps)

> Flags vary slightly by Planetiler version. Check first:

```bash
java -jar /home/osm/planetiler.jar --help
```

Example template:

```bash
java -Xmx24g -jar /home/osm/planetiler.jar \
  --osm-path=/home/osm/downloads/osm_planet/planet-latest.osm.pbf \
  --output=/opt/tiles/build/base.pmtiles \
  --tmpdir=/opt/tiles/tmp \
  --force
```

### Option B: Tippecanoe (for custom vector datasets)

```bash
tippecanoe -o /opt/tiles/build/my-layer.mbtiles -zg --drop-densest-as-needed /opt/tiles/sources/my-layer.geojson
```

---

## 5) Build raster bathymetry/elevation layer (GEBCO)

Input example:

- `/home/osm/downloads/gebco_2025/GEBCO_2025.nc`

### 5.1 Reproject to Web Mercator

```bash
gdalwarp \
  -t_srs EPSG:3857 \
  -r bilinear \
  -multi -wo NUM_THREADS=ALL_CPUS \
  /home/osm/downloads/gebco_2025/GEBCO_2025.nc \
  /opt/tiles/tmp/gebco_3857.tif
```

### 5.2 Color relief (bathymetry palette)

Create palette file:

```bash
cat >/opt/tiles/sources/bathy-color.txt <<'EOF'
-11000  0   10  40
-8000   0   35  90
-6000   0   60 130
-4000   0   90 170
-2000   0  130 210
-500   50  170 230
0      220 220 200
500    180 210 140
2000   120 170 100
4000    90 130  80
EOF
```

Apply:

```bash
gdaldem color-relief \
  /opt/tiles/tmp/gebco_3857.tif \
  /opt/tiles/sources/bathy-color.txt \
  /opt/tiles/tmp/gebco_color.tif \
  -alpha
```

### 5.3 Convert to MBTiles

```bash
gdal_translate \
  -of MBTILES \
  /opt/tiles/tmp/gebco_color.tif \
  /opt/tiles/build/gebco_bathy.mbtiles \
  -co TILE_FORMAT=PNG \
  -co ZOOM_LEVEL_STRATEGY=AUTO
```

---

## 6) Serve tiles with Martin (localhost only)

Install Martin binary and run it bound to loopback.

Systemd unit example:

`/etc/systemd/system/martin.service`

```ini
[Unit]
Description=Martin tile server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pink
Group=pink
ExecStart=/usr/local/bin/martin --listen-address 127.0.0.1:3000 /opt/tiles/build
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now martin
sudo systemctl status martin
```

Discover available sources:

```bash
curl -s http://127.0.0.1:3000/catalog
```

---

## 7) Nginx reverse proxy (HTTPS only)

Example location in your HTTPS vhost:

```nginx
location /tiles/ {
    proxy_pass http://127.0.0.1:3000/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
}
```

Then test:

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -I https://beachlab.org/tiles/catalog
```

---

## 8) Style file (MapLibre) with vector + raster

`/opt/tiles/styles/style.json` (starter skeleton):

```json
{
  "version": 8,
  "name": "BeachLab Hybrid",
  "sources": {
    "base": {
      "type": "vector",
      "tiles": ["https://beachlab.org/tiles/base/{z}/{x}/{y}.pbf"],
      "minzoom": 0,
      "maxzoom": 14
    },
    "bathy": {
      "type": "raster",
      "tiles": ["https://beachlab.org/tiles/gebco_bathy/{z}/{x}/{y}.png"],
      "tileSize": 256,
      "minzoom": 0,
      "maxzoom": 12
    }
  },
  "layers": [
    { "id": "bathy", "type": "raster", "source": "bathy" }
  ]
}
```

> Use `/tiles/catalog` output to confirm exact source names/paths and adjust URLs.

---

## 9) Add future layers quickly

For every new layer:

1. Drop raw source into `/opt/tiles/sources`
2. Build to `/opt/tiles/build/<layer>.mbtiles` (or `.pmtiles`)
3. Confirm in `catalog`
4. Add source + layer entry in `style.json`
5. No firewall changes needed if Martin stays `127.0.0.1`

---

## 10) Ops and performance tips

- Use SSD/NVMe for `/opt/tiles/build`
- Keep big raw inputs under `/home/osm/downloads`
- Use `NUM_THREADS=ALL_CPUS` in GDAL for faster CPU builds
- Build regional extracts first, then planet-scale
- For cache/CDN later, front `/tiles/` with Cloudflare cache rules

---

## 11) Security posture for tiles

- Keep tile server bound to localhost only (`127.0.0.1`)
- Expose externally only through Nginx `443`
- Avoid opening direct tile ports in UFW
- Keep old retired domains/vhosts removed

This aligns with your current hardened setup.

---

## 12) Production update (TiTiler + MDT02 + 3D/hillshade)

Estado aplicado en `tiles.beachlab.org` (2026-02-16/17):

- Martin sigue para vector/PMTiles.
- TiTiler quedó desplegado para raster DEM MDT02.
- Nginx publica TiTiler bajo `/titiler/`.
- Frontend MapLibre (`/map/`) incluye controles:
  - toggle MDT02 raster
  - opacidad
  - fit-to-Spain
  - 3D terrain toggle
  - hillshade toggle
  - exaggeration slider

### 12.1 TiTiler container

```bash
docker ps --filter name=titiler
curl -fsS http://127.0.0.1:8081/healthz
```

Esperado: container `titiler` activo y `{"status":"ok"}`.

### 12.2 Nginx proxy

En el vhost de `tiles.beachlab.org`:

```nginx
location /titiler/ {
    proxy_pass http://127.0.0.1:8081/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Validación:

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -I https://tiles.beachlab.org/titiler/healthz
```

### 12.3 MDT02 VRT grouping (mixed CRS-safe)

VRTs activos:

- `/opt/tiles/build/mdt02_hu29.vrt`
- `/opt/tiles/build/mdt02_hu30.vrt`
- `/opt/tiles/build/mdt02_hu31.vrt`
- `/opt/tiles/build/mdt02_wgs84.vrt`
- `/opt/tiles/build/mdt02_regcan95.vrt`

Nota: evitar pipeline “all-in-one” cuando el input mezcla CRS.

### 12.4 Current caveat

El render 3D/hillshade full-country on-the-fly desde VRT gigante puede provocar:

- worker timeout
- OOM/SIGKILL
- latencia alta en zooms altos

Estrategia recomendada actual: empezar por `hu31` on-the-fly y ampliar por zonas.

## 13) Quick rollback knobs

Si 3D/hillshade degrada UX o carga servidor:

1. Desactivar terrain/hillshade en frontend (`/map/index.html`).
2. Mantener solo raster MDT02 2D + opacidad.
3. Si hace falta, subir timeout/workers de TiTiler o volver temporalmente a vector-only.

Smoke check rápido:

```bash
curl -fsS https://tiles.beachlab.org/catalog >/dev/null
curl -fsS https://tiles.beachlab.org/titiler/healthz >/dev/null
```
