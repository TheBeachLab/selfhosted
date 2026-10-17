#!/usr/bin/env python3
"""Initial provisioning on the NUC. Refuses to replace an existing deployment.

https://docs.couchdb.org/en/stable/intro/security.html
https://docs.couchdb.org/en/stable/api/database/security.html
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SOURCE = Path(__file__).resolve().parent
DEPLOY = Path('/opt/obsidian-sync')
DATA = Path('/var/lib/obsidian-sync')
PRIVATE = Path('/root/.config/obsidian-sync')
VHOST = Path('/etc/nginx/sites-available/api.beachlab.org')
SNIPPET = Path('/etc/nginx/snippets/obsidian-sync.conf')


def main():
    if os.geteuid() != 0 or socket.gethostname() != 'thebeachlab':
        raise SystemExit('Run as root on thebeachlab.')
    os.umask(0o077)
    if any(p.exists() for p in (DEPLOY, DATA, PRIVATE, SNIPPET)):
        raise SystemExit('Existing Obsidian deployment found; inspect instead of overwriting.')
    original = VHOST.read_bytes()
    anchor = b'    # Default deny\n'
    if original.count(anchor) != 1:
        raise SystemExit('Unexpected HTTPS vhost; no changes made.')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 15984))
    for path in (DEPLOY, DATA, PRIVATE):
        path.mkdir(parents=True, mode=0o700)
    for name in ('data', 'etc'):
        path = DATA / name
        path.mkdir(mode=0o700)
        os.chown(path, 5984, 5984)
    shutil.copyfile(SOURCE / 'compose.yaml', DEPLOY / 'compose.yaml')
    shutil.copyfile(SOURCE / 'local.ini', DATA / 'etc/10-livesync.ini')
    os.chown(DATA / 'etc/10-livesync.ini', 5984, 5984)
    admin = secrets.token_urlsafe(36)
    password = secrets.token_urlsafe(32)
    (DEPLOY / '.env').write_text('COUCHDB_USER=obsidian-admin\nCOUCHDB_PASSWORD=' + admin + '\n')
    client = dict(url='https://api.beachlab.org/obsidian-sync', username='strategy-sync',
                  password=password, database='strategy')
    (PRIVATE / 'client.json').write_text(json.dumps(client))
    (PRIVATE / 'admin.json').write_text(json.dumps(dict(username='obsidian-admin', password=admin)))
    (PRIVATE / 'nginx-before.conf').write_bytes(original)
    subprocess.run(['docker', 'compose', '-f', str(DEPLOY / 'compose.yaml'), 'up', '-d'], check=True)
    auth = base64.b64encode(('obsidian-admin:' + admin).encode()).decode()

    def request(path, method='GET', body=None):
        headers = {'Authorization': 'Basic ' + auth}
        payload = None if body is None else json.dumps(body).encode()
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        with urlopen(Request('http://127.0.0.1:15984' + path, data=payload,
                             headers=headers, method=method), timeout=15) as response:
            return json.load(response)

    for _ in range(60):
        try:
            if request('/_up').get('status') == 'ok':
                break
        except (OSError, URLError):
            time.sleep(0.5)
    else:
        raise RuntimeError('CouchDB did not become ready; public route is still disabled.')
    for db in ('_users', '_replicator', 'strategy'):
        try:
            request('/' + db + '?n=1&q=1', 'PUT')
        except HTTPError as error:
            if error.code != 412:
                raise
    request('/_users/org.couchdb.user:strategy-sync', 'PUT',
            dict(name='strategy-sync', password=password, roles=[], type='user'))
    request('/strategy/_security', 'PUT',
            dict(admins=dict(names=[], roles=[]), members=dict(names=['strategy-sync'], roles=[])))
    shutil.copyfile(SOURCE / 'nginx.conf', SNIPPET)
    SNIPPET.chmod(0o644)
    VHOST.write_bytes(original.replace(anchor, b'    include /etc/nginx/snippets/obsidian-sync.conf;\n\n' + anchor))
    result = subprocess.run(['nginx', '-t'], capture_output=True, text=True)
    if result.returncode:
        VHOST.write_bytes(original)
        raise RuntimeError('Nginx validation failed; original vhost restored: ' + result.stderr)
    subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    print(json.dumps(dict(url=client['url'], database='strategy', username=client['username'],
                          nginx_before_sha256=hashlib.sha256(original).hexdigest(),
                          server_version=request('/')['version'])))


if __name__ == '__main__':
    main()
