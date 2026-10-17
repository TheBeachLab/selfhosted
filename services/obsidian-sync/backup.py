#!/usr/bin/env python3
"""Consistent CouchDB capture, encrypted NAS backup, optional restore check.

https://docs.couchdb.org/en/stable/maintenance/backups.html
https://restic.readthedocs.io/en/stable/040_backup.html
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.request import urlopen, Request
import base64

STATE = Path('/var/lib/obsidian-sync-backup')
STAGE = STATE / 'payload'
NAS = Path('/mnt/nas-downloads')
REPOSITORY = NAS / 'backups/obsidian-sync-restic'


def run(args, env=None):
    result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=1800)
    if result.returncode:
        (STATE / 'last-error.txt').write_text(result.stdout + result.stderr)
        raise RuntimeError('Command failed; private diagnostic: ' + str(STATE / 'last-error.txt'))
    return result.stdout


def digest_tree(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def ready():
    creds = json.loads(Path('/root/.config/obsidian-sync/admin.json').read_text())
    auth = base64.b64encode((creds['username'] + ':' + creds['password']).encode()).decode()
    for _ in range(60):
        try:
            req = Request('http://127.0.0.1:15984/_up', headers={'Authorization': 'Basic ' + auth})
            with urlopen(req, timeout=2) as response:
                if json.load(response).get('status') == 'ok':
                    return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError('CouchDB did not become ready after capture.')


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--verify-restore', action='store_true')
    options = args.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run as root.')
    os.umask(0o077)
    STATE.mkdir(mode=0o700, exist_ok=True)
    with open('/run/lock/obsidian-sync-backup.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for p in (STATE, STAGE, NAS, REPOSITORY, Path('/var/lib/obsidian-sync'), Path('/opt/obsidian-sync')):
            if p.is_symlink() or p.resolve() != p:
                raise RuntimeError('Unexpected redirected path: ' + str(p))
        mount = json.loads(run(['findmnt', '--json', '-o', 'SOURCE,FSTYPE,TARGET', '-T', str(NAS)]))['filesystems'][0]
        if (mount.get('target') != str(NAS) or mount.get('fstype') not in ('nfs', 'nfs4')
                or mount.get('source') != '192.168.1.100:/volume1/synology'):
            raise RuntimeError('Expected Synology NFS mount unavailable.')
        if min(shutil.disk_usage(STATE).free, shutil.disk_usage(NAS).free) < 1024**3:
            raise RuntimeError('Backup requires 1 GiB free locally and on the NAS.')
        env = dict(os.environ, RESTIC_REPOSITORY=str(REPOSITORY),
                   RESTIC_PASSWORD_FILE='/root/.config/thebeachlab-backup/restic-password',
                   RESTIC_CACHE_DIR=str(STATE / 'restic-cache'))
        identity = STATE / 'repository.json'
        if not identity.exists():
            if REPOSITORY.exists() and any(REPOSITORY.iterdir()):
                raise RuntimeError('Existing backup repository needs an identity review.')
            run(['restic', 'init'], env)
            identity.write_text(run(['restic', 'cat', 'config'], env))
        expected = json.loads(identity.read_text())['id']
        if json.loads(run(['restic', 'cat', 'config'], env))['id'] != expected:
            raise RuntimeError('Backup repository identity mismatch.')
        container = json.loads(run(['docker', 'inspect', '--format', '{{json .State}}', 'obsidian-couchdb']))
        if not container['Running'] or container['Paused'] or container['Restarting']:
            raise RuntimeError('CouchDB must be running before capture.')
        try:
            run(['docker', 'stop', '--time', '30', 'obsidian-couchdb'])
            if STAGE.exists():
                shutil.rmtree(STAGE)
            STAGE.mkdir(mode=0o700)
            shutil.copytree('/var/lib/obsidian-sync', STAGE / 'couchdb', symlinks=True)
            shutil.copytree('/opt/obsidian-sync', STAGE / 'deployment', symlinks=True)
            shutil.copytree('/root/.config/obsidian-sync', STAGE / 'administration', symlinks=True)
            shutil.copyfile('/etc/nginx/snippets/obsidian-sync.conf', STAGE / 'nginx.conf')
        finally:
            run(['docker', 'start', 'obsidian-couchdb'])
            ready()
        hashes = digest_tree(STAGE)
        output = run(['restic', 'backup', str(STAGE), '--tag', 'obsidian-sync', '--json'], env)
        summary = next(json.loads(line) for line in output.splitlines()
                       if json.loads(line).get('message_type') == 'summary')
        snapshot = summary['snapshot_id']
        receipt = dict(time=datetime.now(timezone.utc).isoformat(), snapshot=snapshot,
                       files=len(hashes), restored=False)
        if options.verify_restore:
            with tempfile.TemporaryDirectory(prefix='obsidian-restore-', dir='/var/tmp') as tmp:
                run(['restic', 'restore', snapshot, '--target', tmp], env)
                restored = Path(tmp) / STAGE.relative_to('/')
                if digest_tree(restored) != hashes:
                    raise RuntimeError('Restored files differ from the captured backup.')
            receipt['restored'] = True
        run(['restic', 'forget', '--keep-daily', '7', '--keep-weekly', '4', '--keep-monthly', '6', '--prune'], env)
        (STATE / 'last-success.json').write_text(json.dumps(receipt, indent=2))
        print(json.dumps(receipt))


if __name__ == '__main__':
    main()
