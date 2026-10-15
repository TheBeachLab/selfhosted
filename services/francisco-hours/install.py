#!/usr/bin/env python3
"""Install the isolated hours helper without restarting the phone service."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess

SOURCE = Path(__file__).resolve().parent
ROOT = Path('/opt/francisco-hours')
SITE = Path('/etc/nginx/sites-available/daswerklab.de')
SNIPPET = Path('/etc/nginx/snippets/francisco-hours.conf')
UNIT = Path('/etc/systemd/system/francisco-hours.service')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', required=True)
    args = parser.parse_args()
    assert re.fullmatch('[0-9a-f]{40}', args.revision)
    assert os.geteuid() == 0 and socket.gethostname() == 'thebeachlab'
    assert not any(p.exists() for p in (ROOT, SNIPPET, UNIT)), 'Preserve existing installation'
    assert not subprocess.check_output(['ss', '-H', '-lnt', 'sport = :18092']).strip()
    before = SITE.read_bytes()
    marker = b'    include /etc/nginx/snippets/daswerklab-voice.conf;'
    assert before.count(marker) == 1 and b'francisco-hours' not in before
    subprocess.run(['nginx', '-t'], check=True, capture_output=True)
    release = ROOT / args.revision
    release.mkdir(parents=True, mode=0o755)
    ROOT.chmod(0o755)
    shutil.copyfile(SOURCE / 'server.py', release / 'server.py')
    (release / 'server.py').chmod(0o644)
    (ROOT / 'current').symlink_to(release)
    shutil.copyfile(SOURCE / 'francisco-hours.service', UNIT)
    UNIT.chmod(0o644)
    subprocess.run(['systemd-analyze', 'verify', str(UNIT)], check=True)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', '--now', 'francisco-hours'], check=True)
    shutil.copyfile(SOURCE / 'nginx.conf', SNIPPET)
    SNIPPET.chmod(0o644)
    after = before.replace(marker, marker + b'\n    include /etc/nginx/snippets/francisco-hours.conf;')
    assert SITE.read_bytes() == before, 'Concurrent website modification preserved'
    backup = ROOT / 'website.before'
    backup.write_bytes(before)
    backup.chmod(0o600)
    SITE.write_bytes(after)
    try:
        subprocess.run(['nginx', '-t'], check=True, capture_output=True)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    except Exception:
        assert SITE.read_bytes() == after, 'Concurrent website modification preserved'
        SITE.write_bytes(before)
        subprocess.run(['nginx', '-t'], check=True, capture_output=True)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
        raise
    print('Installed revision', args.revision)
    print('Source SHA256', hashlib.sha256((release / 'server.py').read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
