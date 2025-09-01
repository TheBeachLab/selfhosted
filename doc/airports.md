# Airports

Github: https://github.com/davidmegginson/ourairports-data

Direct links

https://davidmegginson.github.io/ourairports-data/airports.csv
https://davidmegginson.github.io/ourairports-data/airport-frequencies.csv
https://davidmegginson.github.io/ourairports-data/runways.csv
https://davidmegginson.github.io/ourairports-data/navaids.csv
https://davidmegginson.github.io/ourairports-data/countries.csv
https://davidmegginson.github.io/ourairports-data/regions.csv
https://davidmegginson.github.io/ourairports-data/airport-comments.csv

Data dictionary: https://ourairports.com/help/data-dictionary.html


Data en /home/osm/airports/

## descargar_airports.sh.

```
#!/usr/bin/env bash
set -e

DEST_DIR="/home/osm/airports/csv"
mkdir -p "$DEST_DIR"

FILES=(
  "airports.csv"
  "airport-frequencies.csv"
  "runways.csv"
  "navaids.csv"
  "countries.csv"
  "regions.csv"
  "airport-comments.csv"
)
BASE_URL="https://davidmegginson.github.io/ourairports-data"

echo "Descargando archivos en $DEST_DIR..."
for file in "${FILES[@]}"; do
  url="$BASE_URL/$file"
  echo " → $file"
  wget -q --show-progress -O "$DEST_DIR/$file" "$url"
done

echo "Descarga completada."
```

## Crontab

```
# Bajar airports cada dia a las 2am
0 2 * * * /home/osm/airports/descargar_airports.sh >> /home/osm/airports/csv/descargar_airports.log 2>&1 
```


