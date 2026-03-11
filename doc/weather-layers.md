# Weather Layers (maps.beachlab.org)

> Author: Claude Code — 2026-03-11

Animated wind particles and weather overlays on the MapLibre globe.

## Architecture

```
NOAA GFS (1°) → cron 4x/day → eccodes → Python → JSON → Nginx → MapLibre WebGL
```

## Data Pipeline

- Script: `/opt/weather/scripts/fetch_gfs.sh`
- Converter: `/opt/weather/scripts/grib2json.py`
- Output: `/opt/weather/data/latest/*.json`
- Cron: `/etc/cron.d/weather-fetch` (03:10, 09:10, 15:10, 21:10 UTC)
- Log: `/opt/weather/logs/fetch.log`
- Logrotate: `/etc/logrotate.d/weather-fetch`

### Manual run

```bash
/opt/weather/scripts/fetch_gfs.sh
```

### Force re-fetch (even if current cycle already downloaded)

```bash
rm /opt/weather/data/latest/meta.json
/opt/weather/scripts/fetch_gfs.sh
```

### Check status

```bash
cat /opt/weather/data/latest/meta.json
tail -20 /opt/weather/logs/fetch.log
ls -lh /opt/weather/data/latest/
```

### Dependencies

- `libeccodes-tools` (provides `grib_get_data`, `grib_ls`)
- `python3`, `jq`, `curl`

### GRIB shortNames used

| Variable | eccodes shortName | GFS filter param |
|---|---|---|
| U-wind 10m | `10u` | `var_UGRD` + `lev_10_m_above_ground` |
| V-wind 10m | `10v` | `var_VGRD` + `lev_10_m_above_ground` |
| Temperature 2m | `2t` | `var_TMP` + `lev_2_m_above_ground` |
| Pressure MSL | `prmsl` | `var_PRMSL` + `lev_mean_sea_level` |
| Precipitation | `prate` | `var_PRATE` + `lev_surface` |
| Wind at pressure levels | `u`/`v` + level filter | `var_UGRD/VGRD` + `lev_Xmb` |

## Client Layers

| Layer | File | Technique |
|---|---|---|
| Wind particles | `lib/wind-gl.js` | Custom WebGL layer, GPU particle advection |
| Temperature | `lib/weather-overlays.js` | Image source, canvas color ramp |
| Precipitation | `lib/weather-overlays.js` | Image source, canvas color ramp |
| Pressure isobars | `lib/weather-overlays.js` | d3-contour → GeoJSON lines |

All toggled from the Layers panel → Weather section. Default: all off.

Wind supports 4 pressure levels: Surface, 850 hPa, 500 hPa, 250 hPa (jet stream).

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
| d3-contour | `/var/www/tiles.beachlab.org/map/lib/d3-contour.min.js` |
| d3-array | `/var/www/tiles.beachlab.org/map/lib/d3-array.min.js` |

## Troubleshooting

### No weather data in browser

1. Check meta.json exists: `cat /opt/weather/data/latest/meta.json`
2. Check Nginx serves it: `curl https://maps.beachlab.org/weather/meta.json`
3. If 404: verify `/weather/` location block in Nginx config, then `sudo nginx -s reload`

### Pipeline fails

1. Check log: `tail /opt/weather/logs/fetch.log`
2. Check NOAA availability: `curl -sI "https://nomads.ncep.noaa.gov/"`
3. Test eccodes: download a test GRIB and run `grib_ls` on it
4. Check disk space: `df -h /opt`

### Wind particles not visible

1. Open browser console, check for WebGL shader errors
2. Verify wind JSON loads: `curl -s https://maps.beachlab.org/weather/wind-surface.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d[0]['data']))"`
3. Expected: 65160 (360 × 181)
4. Try a different theme — particles are white on dark, dark on light

### Style change breaks weather layers

Weather sources/layers get cleared on style change. The `reInitWeatherAfterStyleChange()` function re-adds them. If layers disappear after changing theme, check browser console for errors in that function.

## Data sizes

- GRIB download per cycle: ~800 KB (filtered)
- JSON output per cycle: ~4.2 MB
- Retention: 2 cycles (latest + previous) = ~8.5 MB max
- Browser: wind JSON ~700 KB per level, temp ~440 KB, pressure ~625 KB
