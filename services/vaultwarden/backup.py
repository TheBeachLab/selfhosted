#!/usr/bin/env python3
"""Capture a stopped vault, restart it, then encrypt the capture on the NAS.

https://github.com/dani-garcia/vaultwarden/wiki/Backing-up-your-vault
https://restic.readthedocs.io/en/v0.12.1/040_backup.html
"""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import time
from urllib.request import urlopen

DATA = Path('/var/lib/vaultwarden')
STATE = Path('/var/lib/vaultwarden-backup')
STAGE = STATE / 'payload'
NAS = Path('/mnt/nas-downloads')
REPOSITORY = NAS / 'backups/vaultwarden-restic'
PASSWORD = Path('/root/.config/thebeachlab-backup/restic-password')


def run(args, env=None):
    result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=3300)
    if result.returncode:
        path = STATE / 'last-command-error.txt'
        path.write_text(result.stdout + result.stderr)
        path.chmod(0o600)
        raise RuntimeError(f'{args[0]} failed; private diagnostic: {path}')
    return result.stdout


def guard_mount(mount):
    if (mount.get('target') != str(NAS) or mount.get('fstype') not in ('nfs', 'nfs4')
            or mount.get('source') != '192.168.1.100:/volume1/synology'):
        raise RuntimeError('Expected Synology NFS mount is unavailable; no backup writes allowed.')


def check_mount():
    mount = json.loads(run(['findmnt', '--json', '-o', 'SOURCE,FSTYPE,TARGET', '-T', str(NAS)]))
    guard_mount(mount['filesystems'][0])


def environment():
    return dict(os.environ, RESTIC_REPOSITORY=str(REPOSITORY),
                RESTIC_PASSWORD_FILE=str(PASSWORD), RESTIC_CACHE_DIR=str(STATE / 'restic-cache'))


def ready():
    for _ in range(60):
        try:
            with urlopen('http://127.0.0.1:18080/alive', timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError('Vaultwarden did not become ready; inspect the container.')


def capture():
    info = json.loads(run(['docker', 'inspect', '--format', '{{json .State}}', 'vaultwarden']))
    if not info['Running'] or info.get('Paused') or info.get('Restarting'):
        raise RuntimeError('Vaultwarden must be running before capture.')
    # Stop briefly so attachments and SQLite describe the same point in time.
    # Restart on every exit, including a copy or integrity-check failure.
    try:
        run(['docker', 'stop', '--time', '30', 'vaultwarden'])
        if STAGE.exists():
            shutil.rmtree(STAGE)
        STAGE.mkdir(mode=0o700)
        shutil.copytree(DATA, STAGE / 'data')
        with sqlite3.connect(f'file:{STAGE / "data/db.sqlite3"}?mode=ro', uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Captured SQLite database failed integrity_check.')
        shutil.copytree('/opt/vaultwarden', STAGE / 'deployment')
    finally:
        run(['docker', 'start', 'vaultwarden'])
        ready()


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run as root on the NUC.')
    os.umask(0o077)
    with open('/run/lock/vaultwarden-backup.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for path in (DATA, STATE, STAGE, NAS, REPOSITORY):
            if path.is_symlink() or path.resolve() != path:
                raise RuntimeError('Unexpected path redirection: ' + str(path))
        check_mount()
        if min(shutil.disk_usage(STATE).free, shutil.disk_usage(NAS).free) < 1024**3:
            raise RuntimeError('Backup requires at least 1 GiB free locally and on the NAS.')
        env = environment()
        expected = json.loads((STATE / 'repository.json').read_text())['id']
        if json.loads(run(['restic', 'cat', 'config'], env))['id'] != expected:
            raise RuntimeError('Backup repository identity changed.')
        capture()
        check_mount()
        output = run(['restic', 'backup', str(STAGE), '--tag', 'vaultwarden', '--json'], env)
        summaries = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
        snapshot = next(item['snapshot_id'] for item in summaries if item.get('message_type') == 'summary')
        run(['restic', 'check'], env)
        run(['restic', 'forget', '--host', socket.gethostname(), '--tag', 'vaultwarden',
             '--keep-daily', '7', '--keep-weekly', '4', '--keep-monthly', '6', '--prune'], env)
        proof = {'completed_at': datetime.now(timezone.utc).isoformat(), 'snapshot': snapshot,
                 'sqlite_sha256': hashlib.sha256((STAGE / 'data/db.sqlite3').read_bytes()).hexdigest(),
                 'repository': str(REPOSITORY)}
        (STATE / 'last-success.json').write_text(json.dumps(proof, indent=2) + '\n')
        shutil.rmtree(STAGE)
        print('Vaultwarden NAS backup verified: ' + snapshot)


if __name__ == '__main__':
    main()
