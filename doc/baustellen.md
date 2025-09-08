# Baustellen in München

You can download the Baustellen in Munich without a token

```bash
curl -L -o baustellen_4w.json \
"https://geoportal.muenchen.de/geoserver/mor_wfs/ows?service=WFS&version=1.1.0&request=GetFeature&typeName=mor_wfs:baustellen_4_weeks_opendata&outputFormat=application/json"
```

I have a executable script `download_muc_baustellen.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

OUTDIR="/home/osm/downloads/muc_baustellen"
LOGFILE="$OUTDIR/muc_baustellen.log"
mkdir -p "$OUTDIR"

# Reset log each run
: > "$LOGFILE"

# Notify on error
trap '/usr/local/bin/notify.sh "Baustellen download ❌" "Download failed. Check $LOGFILE."' ERR

URL="https://geoportal.muenchen.de/geoserver/mor_wfs/ows?service=WFS&version=1.1.0&request=GetFeature&typeName=mor_wfs:baustellen_4_weeks_opendata&outputFormat=application/json"

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting download…"

  tmpfile="$OUTDIR/baustellen_4w.json.part"
  if curl -fsSL -o "$tmpfile" "$URL"; then
    mv "$tmpfile" "$OUTDIR/baustellen_4w.json"
    echo "   ✔ Download successful"
  else
    rm -f "$tmpfile"
    echo "   ✘ Download failed"
    exit 1
  fi

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Finished."
} >> "$LOGFILE" 2>&1
```

Then I have a crontab to download the Baustellen everyday at 3:30 AM because they update around 3:00 AM
```
30 3 * * * /home/osm/downloads/download_muc_baustellen.sh
```

### Notes
- Test manually with: `bash download_muc_baustellen.sh && cat /home/osm/downloads/muc_baustellen/muc_baustellen.log`
- Final JSON is stored at: `/home/osm/downloads/muc_baustellen/baustellen_4w.json`

