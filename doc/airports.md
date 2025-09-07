# Airports

There is a planet database of airports in Github: https://github.com/davidmegginson/ourairports-data

Direct DL links

https://davidmegginson.github.io/ourairports-data/airports.csv
https://davidmegginson.github.io/ourairports-data/airport-frequencies.csv
https://davidmegginson.github.io/ourairports-data/runways.csv
https://davidmegginson.github.io/ourairports-data/navaids.csv
https://davidmegginson.github.io/ourairports-data/countries.csv
https://davidmegginson.github.io/ourairports-data/regions.csv
https://davidmegginson.github.io/ourairports-data/airport-comments.csv

Data dictionary: https://ourairports.com/help/data-dictionary.html

This data updates daily so I save it in in `/home/osm/downloads/airports/`

## download_airports.sh.

```bash
#!/usr/bin/env bash
set -euo pipefail

DEST_DIR="/home/osm/downloads/airports/"
LOGFILE="$DEST_DIR/ourairports.log"
mkdir -p "$DEST_DIR"

# Empty the log at the start
: > "$LOGFILE"

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

# Notify on error
trap '/usr/local/bin/notify.sh "Airports download ❌" "Download failed. Check $LOGFILE."' ERR

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Downloading into $DEST_DIR..."
  for file in "${FILES[@]}"; do
    url="$BASE_URL/$file"
    echo " → $file"
    tmpfile="$DEST_DIR/$file.part"
    if wget -q -O "$tmpfile" "$url"; then
      mv "$tmpfile" "$DEST_DIR/$file"
      echo "   ✔ $file downloaded"
    else
      rm -f "$tmpfile"
      echo "   ✘ Failed to download $file"
      exit 1
    fi
  done
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Download finished."
} >> "$LOGFILE" 2>&1
```

## Crontab

I download the data daily at 2:30 AM

```
30 2 * * * /home/osm/downloads/download_airports.sh
```

## Insert the data in Postgres Database

WIP

