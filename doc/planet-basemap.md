# Planet Basemap Ops (PMTiles/MBTiles)

**Author:** Mr. Watson 🦄
**Date:** 2026-02-17

## Goal

Servir `planet_pmtiles` en `tiles.beachlab.org` con alta disponibilidad y nombre estable local (`/opt/tiles/build/planet.pmtiles`).

## Current status

- Martin está sirviendo actualmente source remoto (fail-safe):
  - `planet_pmtiles -> https://build.protomaps.com/20260216.pmtiles`
- Endpoint público OK:
  - `https://tiles.beachlab.org/planet_pmtiles/0/0/0`
- Mapa demo:
  - `https://tiles.beachlab.org/map/`
  - themes: `light`, `dark`, `grayscale`, `white`, `black`, `bright`
- Update script:
  - `/home/osm/downloads/update_planet_pmtiles.sh`
- Cron semanal activo (root):
  - `0 2 * * 1 /home/osm/downloads/update_planet_pmtiles.sh >> /home/osm/downloads/update_planet_pmtiles.log 2>&1`

## Incident log (local PMTiles)

Síntoma visto al activar local:

- Martin `500`
- `Moka cache fetch error: IO Error Invalid gzip header`
- desde cliente: `curl: (92) HTTP/2 stream 0 was not closed cleanly`

Interpretación operativa: archivo local probablemente incompleto/corrupto.

Acción aplicada:

1. fallback a source remoto (servicio recuperado)
2. hardening del downloader (HTTP/1.1 + retries)
3. re-descarga limpia del último build para volver a local estable

## Downloader behavior (stable filename)

El script:

- consulta `https://build-metadata.protomaps.dev/builds.json`
- detecta la build más nueva (`*.pmtiles`)
- descarga solo si hay versión nueva
- usa descarga robusta:

```bash
curl --http1.1 -fL --retry 20 --retry-all-errors --retry-delay 10 --continue-at - -o /opt/tiles/build/planet.pmtiles.part "$URL"
```

- valida tamaño final
- activa nombre estable:
  - `/opt/tiles/build/planet.pmtiles`
  - `/opt/tiles/build/planet.pmtiles.version`
- cambia Martin a source local estable
- reinicia Martin y hace smoke test

## Force clean re-download (manual)

```bash
sudo rm -f /opt/tiles/build/planet.pmtiles /opt/tiles/build/planet.pmtiles.version /opt/tiles/build/planet.pmtiles.part
sudo /home/osm/downloads/update_planet_pmtiles.sh
```

Logs:

```bash
tail -f /home/osm/downloads/update_planet_pmtiles.log
```

## Verify

```bash
curl -fsS https://tiles.beachlab.org/catalog | jq
curl -I https://tiles.beachlab.org/planet_pmtiles/0/0/0
systemctl status martin --no-pager
```

## Replace old planet PBF job

El cron mensual antiguo de `pink` para `download_osm_planet.sh` fue retirado.

## Data scope reality check

- **Protomaps basemap:** `z0-z15`
- **OpenFreeMap TileJSON público:** hasta `z14`
- Ninguno equivale a OSM crudo completo (son basemaps curados).
