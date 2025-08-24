# Geodata

## Baustelle in München

```
curl -L -o baustellen_4w.json \
"https://geoportal.muenchen.de/geoserver/mor_wfs/ows?service=WFS&version=1.1.0&request=GetFeature&typeName=mor_wfs:baustellen_4_weeks_opendata&outputFormat=application/json"
```

`daily_baustellen.sh`

```
#!/usr/bin/env bash
set -euo pipefail

BASE="https://geoportal.muenchen.de/geoserver/mor_wfs/ows"
LAYER="mor_wfs:baustellen_4_weeks_opendata"
OUTDIR="/srv/tiles/data"

# 2 semanas
curl -sL -o "$OUTDIR/baustellen_2w.json" \
"$BASE?service=WFS&version=1.1.0&request=GetFeature&typeName=$LAYER&outputFormat=application/json&srsName=EPSG:4326&CQL_FILTER=beginn<=NOW()+14%20DAYS%20AND%20(coalesce(ende,NOW())>=NOW())"

tippecanoe -zg -o "$OUTDIR/baustellen_2w.mbtiles" "$OUTDIR/baustellen_2w.json" --layer=baustellen

# 6 semanas
curl -sL -o "$OUTDIR/baustellen_6w.json" \
"$BASE?service=WFS&version=1.1.0&request=GetFeature&typeName=$LAYER&outputFormat=application/json&srsName=EPSG:4326&CQL_FILTER=beginn<=NOW()+42%20DAYS%20AND%20(coalesce(ende,NOW())>=NOW())"

tippecanoe -zg -o "$OUTDIR/baustellen_6w.mbtiles" "$OUTDIR/baustellen_6w.json" --layer=baustellen
```

```
15 6 * * * /home/tu-usuario/daily_baustellen.sh >> /var/log/baustellen_daily.log 2>&1
```
