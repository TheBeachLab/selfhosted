#!/usr/bin/env python3
"""Retire the three migrated ddclient blocks after old NS caches have expired."""
import datetime
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from ddns import api

DOMAINS = {"beachlab.org", "hexxan.com", "orbita.you"}


def without_migrated_blocks(text):
    parts = re.split(r"(?m)(?=^#### )", text)
    kept = []
    for part in parts:
        heading = part.splitlines()[0].removeprefix("#### ").strip() if part else ""
        if heading in DOMAINS:
            logins = re.findall(r"(?m)^login=(.+)$", part)
            if logins != [heading]:
                raise ValueError("Unexpected login in " + heading + " block")
        else:
            kept.append(part)
    return "".join(kept)


def main():
    manifest = json.loads(Path('/etc/cloudflare-namecheap-retirement.json').read_text())
    if datetime.datetime.now(datetime.timezone.utc) < datetime.datetime.fromisoformat(manifest['not_before']):
        raise RuntimeError('Old delegation cache grace period is still active')
    if Path(manifest['complete_marker']).exists():
        return
    token = next(line.split('=', 1)[1].strip().strip("\"'") for line in
                 Path('/etc/cloudflare-arroyo.env').read_text().splitlines()
                 if line.startswith('CLOUDFLARE_API_TOKEN='))
    targets = json.loads(Path('/etc/cloudflare-nuc-ddns.json').read_text())['records']
    for zone_id in {target['zone_id'] for target in targets}:
        if api(token, '/zones/' + zone_id)['status'] != 'active':
            raise RuntimeError('Cloudflare zone is not active')
    subprocess.run(['/usr/bin/python3', '/usr/local/lib/cloudflare-ddns/ddns.py'], check=True)
    originals = {}
    for filename, digest in manifest['files'].items():
        path = Path(filename)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise RuntimeError('Configuration changed; retain it for review: ' + filename)
        originals[path] = raw
    backup = Path(manifest['backup_directory'])
    backup.mkdir(mode=0o700, parents=True, exist_ok=True)
    for i, path in enumerate(originals):
        shutil.copy2(path, backup / (str(i) + '-' + path.name))
    try:
        for path, raw in originals.items():
            path.write_text(without_migrated_blocks(raw.decode()))
        subprocess.run(['systemctl', 'restart', 'ddclient.service'], check=True)
        subprocess.run(['systemctl', 'is-active', '--quiet', 'ddclient.service'], check=True)
    except Exception:
        for path, raw in originals.items():
            path.write_bytes(raw)
        subprocess.run(['systemctl', 'restart', 'ddclient.service'], check=False)
        raise
    Path(manifest['complete_marker']).touch(mode=0o600)
    print('Retired migrated Namecheap DDNS blocks; other domains preserved', flush=True)


if __name__ == '__main__':
    main()
