# Spanish MDT02 Bulk Download to Synology NAS

> Author: Mr. Watson (OpenClaw)

This page documents the MDT02 workflow used on this server and provides a **single-script** version you can run end-to-end.

Source series page (CNIG):
- https://centrodedescargas.cnig.es/CentroDescargas/modelo-digital-terreno-mdt02-segunda-cobertura

---

## 1) Environment

- Workspace: `/home/pink/.openclaw/workspace`
- CSV: `/home/pink/.openclaw/workspace/mdt02_links.csv`
- NAS mount: `/mnt/nas-downloads`
- Download target: `/mnt/nas-downloads/descargas/mdt02`

`/etc/fstab` entry used:

```fstab
192.168.1.100:/volume1/synology /mnt/nas-downloads nfs defaults,nofail,_netdev 0 0
```

---

## 2) Single script (inline)

Save this as `mdt02.py` in your workspace.

```python
#!/usr/bin/env python3
import argparse
import csv
import math
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://centrodedescargas.cnig.es/CentroDescargas/"
SERIES_URL = BASE_URL + "modelo-digital-terreno-mdt02-segunda-cobertura"
ARCHIVOS_URL = BASE_URL + "archivosSerie"
DOWNLOAD_BASE = BASE_URL + "descargaDir?secDescDirLA="
FILENAME_RE = re.compile(r"([A-Za-z0-9_.-]+\.(?:tif|tiff|zip|asc|laz|las|gml|jp2|ecw|txt))", re.I)


def session():
    s = requests.Session()
    r = Retry(total=5, connect=5, read=5, status=5, backoff_factor=0.8,
              status_forcelist=(429, 500, 502, 503, 504),
              allowed_methods=frozenset(["GET", "POST"]))
    a = HTTPAdapter(max_retries=r)
    s.mount("https://", a)
    s.mount("http://", a)
    s.headers.update({"User-Agent": "mdt02-single-pipeline/1.0"})
    return s


def fetch_meta(s):
    h = s.get(SERIES_URL, timeout=60)
    h.raise_for_status()
    soup = BeautifulSoup(h.text, "html.parser")
    def v(i, d=""):
        e = soup.find("input", id=i)
        return (e.get("value", "").strip() if e else d) or d
    return {
        "codAgr": v("codAgr", "MOMDT"),
        "codSerie": v("codSerie", "MDT02"),
        "totalArchivos": v("totalArchivos", "8307"),
        "codTipoArchivo": v("codTipoArchivo", ""),
    }


def payload(meta, page):
    return {
        "numPagina": str(page),
        "codAgr": meta["codAgr"],
        "codSerie": meta["codSerie"],
        "coordenadas": "",
        "series": "",
        "codComAutonoma": "",
        "codProvincia": "",
        "codIne": "",
        "codTipoArchivo": meta.get("codTipoArchivo", ""),
        "codIdiomaInf": "",
        "todaEspania": "",
        "todoMundo": "",
        "idProductor": "",
        "rutaNombre": "",
        "numHoja": "",
        "numHoja25": "",
        "totalArchivos": meta["totalArchivos"],
        "codSubSerie": "",
        "contieneArc": "",
        "keySearch": "",
        "referCatastral": "",
        "orderBy": "",
    }


def parse_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.select("tr.row100"):
        a = tr.select_one("a[id^='linkDescDir_']")
        if not a:
            continue
        sec = a.get("id", "").split("_")[-1].strip()
        if not sec.isdigit():
            continue
        text = " ".join(tr.stripped_strings)
        m = FILENAME_RE.search(text)
        fn = m.group(1) if m else f"{sec}.tif"
        out.append((fn, sec))
    return out


def total_pages(html, total_hint):
    soup = BeautifulSoup(html, "html.parser")
    ids = []
    for a in soup.select("a[id^='linkPag_']"):
        sid = a.get("id", "").split("_")[-1]
        if sid.isdigit():
            ids.append(int(sid))
    if ids:
        return max(ids)
    per = max(len(soup.select("tr.row100")), 1)
    return max(1, math.ceil(total_hint / per))


def ensure_csv(csv_path):
    if not csv_path.exists():
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["filename", "url", "descargado_ok"])


def load_csv(csv_path):
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if "descargado_ok" not in r:
            r["descargado_ok"] = ""
    return rows


def save_csv(csv_path, rows):
    tmp = csv_path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["filename", "url", "descargado_ok"])
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, csv_path)


def build_links(csv_path):
    s = session()
    meta = fetch_meta(s)
    first = s.post(ARCHIVOS_URL, data=payload(meta, 1), timeout=90)
    first.raise_for_status()
    tp = total_pages(first.text, int(re.sub(r"\D", "", meta["totalArchivos"]) or "0"))

    by_name = {}
    for p in range(1, tp + 1):
        r = first if p == 1 else s.post(ARCHIVOS_URL, data=payload(meta, p), timeout=90)
        if p != 1:
            r.raise_for_status()
        for fn, sec in parse_rows(r.text):
            by_name[fn] = {"filename": fn, "url": DOWNLOAD_BASE + sec, "descargado_ok": ""}
        if p % 25 == 0 or p == 1 or p == tp:
            print(f"[LINKS] page {p}/{tp} unique={len(by_name)}", flush=True)

    rows = [by_name[k] for k in sorted(by_name.keys())]
    save_csv(csv_path, rows)
    print(f"[LINKS] wrote {len(rows)} rows -> {csv_path}", flush=True)


def download_batch(csv_path, out_dir, limit, sleep_s):
    rows = load_csv(csv_path)
    pending = [i for i, r in enumerate(rows) if (r.get("descargado_ok") or "").strip().upper() != "OK"]
    if not pending:
        print("[DL] no pending files", flush=True)
        return 0, 0, 0

    out_dir.mkdir(parents=True, exist_ok=True)
    s = session()
    ok = err = 0
    targets = pending[:limit]
    print(f"[DL] pending={len(pending)} processing={len(targets)}", flush=True)

    for n, idx in enumerate(targets, 1):
        row = rows[idx]
        fn = row["filename"]
        url = row["url"]
        dst = out_dir / fn
        part = out_dir / f".{fn}.part"
        try:
            if dst.exists() and dst.stat().st_size > 0:
                row["descargado_ok"] = "OK"
                ok += 1
                continue
            if part.exists():
                part.unlink()
            with s.get(url, stream=True, timeout=(20, 300)) as resp:
                resp.raise_for_status()
                with part.open("wb") as wf:
                    for c in resp.iter_content(1024 * 1024):
                        if c:
                            wf.write(c)
            part.replace(dst)
            row["descargado_ok"] = "OK"
            ok += 1
            print(f"[OK] {n}/{len(targets)} {fn}", flush=True)
        except Exception as e:
            row["descargado_ok"] = "ERROR"
            err += 1
            try:
                if part.exists():
                    part.unlink()
            except Exception:
                pass
            print(f"[ERROR] {n}/{len(targets)} {fn}: {e}", flush=True)
        save_csv(csv_path, rows)
        if sleep_s > 0:
            time.sleep(sleep_s)

    remaining = len([1 for r in rows if (r.get("descargado_ok") or "").strip().upper() != "OK"])
    print(f"[DL] batch done ok={ok} err={err} remaining={remaining}", flush=True)
    return ok, err, remaining


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="/home/pink/.openclaw/workspace/mdt02_links.csv")
    ap.add_argument("--out", default="/mnt/nas-downloads/descargas/mdt02")
    ap.add_argument("--prepare-links", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--batch-size", type=int, default=20)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--between-batches", type=float, default=5.0)
    args = ap.parse_args()

    csv_path = Path(args.csv)
    out_dir = Path(args.out)

    ensure_csv(csv_path)

    if args.prepare_links:
        build_links(csv_path)

    if args.run:
        stagnant = 0
        while True:
            ok, err, rem = download_batch(csv_path, out_dir, args.batch_size, args.sleep)
            if rem == 0:
                print("[DONE] all files processed", flush=True)
                break
            if ok == 0 and err == 0:
                stagnant += 1
            else:
                stagnant = 0
            if stagnant >= 3:
                print("[STOP] no progress for 3 rounds", flush=True)
                break
            time.sleep(max(args.between_batches, 0.0))


if __name__ == "__main__":
    main()
```

---

## 3) Usage

Generate the full links CSV (filename + url):

```bash
cd /home/pink/.openclaw/workspace
python3 -u mdt02.py --prepare-links
```

Run continuous batch download to NAS (keeps going, does not block on single-file failures):

```bash
cd /home/pink/.openclaw/workspace
python3 -u mdt02.py --run --batch-size 20 --sleep 1 --between-batches 5
```

---

## 4) Quick checks

Progress (OK/ERROR/pending):

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

Downloaded size:

```bash
du -sh /mnt/nas-downloads/descargas/mdt02
```

Available NAS space:

```bash
df -h /mnt/nas-downloads
```

---

## 5) Notes

- `ERROR` rows are kept intentionally so failed files can be retried later.
- The CSV is the source of truth for pipeline status.
- For user updates, send milestone notifications at 20%, 30%, 40%, etc., with refreshed ETA.
