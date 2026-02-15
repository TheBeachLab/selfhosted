# Planet Basemap Ops (PMTiles/MBTiles)

**Author:** Mr. Watson 🦄
**Date:** 2026-02-15

## Goal

Servir un planet basemap en `tiles.beachlab.org` con nombre estable en Martin y actualización controlada.

## Current status

- Martin sirve ahora mismo:
  - `planet_pmtiles -> https://build.protomaps.com/20260215.pmtiles`
- Endpoint OK:
  - `https://tiles.beachlab.org/planet_pmtiles/0/0/0`
- Mapa demo (MapLibre + estilo Protomaps apuntando a Martin):
  - `https://tiles.beachlab.org/map/`
  - themes: `light`, `dark`, `grayscale`, `white`, `black`
    - ejemplo: `https://tiles.beachlab.org/map/?theme=dark`
- Script de actualización ya creado:
  - `/home/osm/downloads/update_planet_pmtiles.sh`
- Estado operativo (pedido por Fran):
  - **cron semanal desactivado temporalmente** hasta que termine MDT02.

## Update script behavior (stable filename)

El script:

- consulta `https://build-metadata.protomaps.dev/builds.json`
- detecta la build más nueva
- descarga solo si hay versión nueva
- guarda con nombre estable:
  - `/opt/tiles/build/planet.pmtiles`
  - `/opt/tiles/build/planet.pmtiles.version`
- al completar, cambia Martin a source local estable:
  - `planet_pmtiles: /opt/tiles/build/planet.pmtiles`
- reinicia Martin y hace smoke test del endpoint.

## Enable weekly update (when MDT02 finishes)

Añadir en `root`:

```bash
sudo crontab -e
```

Línea:

```cron
0 2 * * 1 /home/osm/downloads/update_planet_pmtiles.sh >> /home/osm/downloads/update_planet_pmtiles.log 2>&1
```

Verificar:

```bash
sudo crontab -l -u root
sudo tail -n 100 /home/osm/downloads/update_planet_pmtiles.log
```

## Replace old planet PBF job

El cron mensual antiguo de `pink` para `download_osm_planet.sh` ya fue retirado.

## Alternative source found (free MBTiles)

OpenFreeMap publica planet en MBTiles semanalmente.

- puntero versión: `https://assets.openfreemap.com/deployed_versions/planet.txt`
- índice: `https://btrfs.openfreemap.com/files.txt`
- patrón descarga:
  - `https://btrfs.openfreemap.com/areas/planet/{version}/tiles.mbtiles`

## Data scope reality check

- **Protomaps basemap:** `z0-z15`
- **OpenFreeMap (TileJSON público):** `minzoom 0`, `maxzoom 14`
- Ninguno equivale al OSM crudo completo (no trae todos los tags/capas de OSM); son basemaps curados.
