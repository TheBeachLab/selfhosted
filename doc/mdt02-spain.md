# CNIG MDT02 Bulk Download to Synology NAS

This document explains the exact workflow used to:

1. Collect all CNIG MDT02 direct download links (8,307 files)
2. Save them to a CSV
3. Download files in small batches to a NAS
4. Keep progress and ETA updates without blocking the pipeline on single-file failures

---

## 1) Environment used

- Source: CNIG `CentroDescargas` (MDT02 second coverage)
- Local workspace: `/home/pink/.openclaw/workspace`
- NAS mount point: `/mnt/nas-downloads`
- Target download folder: `/mnt/nas-downloads/descargas/mdt02`

The NAS mount was configured in `/etc/fstab` as:

```fstab
192.168.1.100:/volume1/synology /mnt/nas-downloads nfs defaults,nofail,_netdev 0 0
```

---

## 2) Build the full MDT02 links CSV

Script:

- `/home/pink/.openclaw/workspace/mdt02_scrape_links.py`

What it does:

- Reads CNIG MDT02 metadata page
- Crawls all `archivosSerie` pages
- Extracts `filename` + direct URL (`descargaDir?secDescDirLA=...`)
- De-duplicates by CNIG `sec`
- Supports resume via state file

Run:

```bash
cd /home/pink/.openclaw/workspace
python3 -u mdt02_scrape_links.py \
  --output mdt02_links.csv \
  --state mdt02_state.json \
  --workers 12 \
  --attempts 3 \
  --checkpoint-every 20 \
  --resume
```

Output:

- `mdt02_links.csv` with columns:
  - `filename`
  - `url`

---

## 3) Add per-file download status and download in batches

Script:

- `/home/pink/.openclaw/workspace/mdt02_download_to_nas.py`

What it does:

- Ensures CSV has third column `descargado_ok`
- Processes only pending rows (`descargado_ok != OK`)
- Downloads to NAS using temporary `.part` files
- Marks each row as:
  - `OK` (download completed)
  - `ERROR` (download failed)
- Saves CSV after each file (`--save-every 1` recommended)

Run one batch of 20:

```bash
cd /home/pink/.openclaw/workspace
python3 -u mdt02_download_to_nas.py \
  --csv /home/pink/.openclaw/workspace/mdt02_links.csv \
  --nas-dir /mnt/nas-downloads/descargas/mdt02 \
  --limit 20 \
  --sleep 1 \
  --timeout-connect 20 \
  --timeout-read 300 \
  --save-every 1
```

---

## 4) Continuous batch loop (autorun)

Script:

- `/home/pink/.openclaw/workspace/mdt02_autorun.py`

What it does:

- Runs batch downloader repeatedly (e.g., 20 files per iteration)
- Waits between batches
- Stops only if there is no progress for multiple iterations or script error
- **Configured not to stop on single-file `ERROR`** (`stop-on-error` default is effectively disabled)

Start in background with log file:

```bash
cd /home/pink/.openclaw/workspace
python3 -u /home/pink/.openclaw/workspace/mdt02_autorun.py \
  --batch-size 20 \
  --between-batches 5 \
  --sleep-between-files 1 \
  > /home/pink/.openclaw/workspace/mdt02_autorun.log 2>&1
```

Check running processes:

```bash
pgrep -af 'mdt02_autorun.py|mdt02_download_to_nas.py'
```

Watch progress log:

```bash
tail -f /home/pink/.openclaw/workspace/mdt02_autorun.log
```

---

## 5) Milestone notifications (20%, 30%, ...)

Script:

- `/home/pink/.openclaw/workspace/mdt02_milestone_check.py`

What it does:

- Reads CSV progress (`OK/ERROR/pending`)
- Computes percent complete, throughput, and ETA
- Triggers a message only when crossing milestone thresholds (20%, 30%, etc.)
- Tracks state in:
  - `/home/pink/.openclaw/workspace/mdt02_milestone_state.json`

This script was scheduled via OpenClaw cron every 10 minutes.

---

## 6) Quick status commands

Count OK/ERROR/pending:

```bash
python3 - <<'PY'
import csv
p='/home/pink/.openclaw/workspace/mdt02_links.csv'
ok=err=pend=tot=0
with open(p,encoding='utf-8',newline='') as f:
    for row in csv.DictReader(f):
        tot += 1
        v=(row.get('descargado_ok') or '').strip().upper()
        if v=='OK': ok += 1
        elif v=='ERROR': err += 1
        else: pend += 1
print({'total':tot,'ok':ok,'error':err,'pending':pend})
PY
```

Total downloaded size on NAS:

```bash
du -sh /mnt/nas-downloads/descargas/mdt02
```

Available NAS space:

```bash
df -h /mnt/nas-downloads
```

---

## 7) Operational notes

- Some CNIG files may fail temporarily; keep pipeline running and retry failed rows later.
- `ERROR` rows are intentional markers for post-pass retries.
- Downloads are resumable at workflow level because status is persisted in CSV.
- CSV is the source of truth for pipeline progress.
