#!/usr/bin/env python3
"""First NUC installation; preserves original config, existing NAS jobs and secrets."""
import datetime
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
from urllib.request import Request, urlopen


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run as root on the NUC.')
    os.umask(0o077)
    source = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('backup', source / 'backup.py')
    backup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backup)
    backup.guard_paths((backup.HOME_DIR, backup.STATE, backup.STAGE.parent,
                        backup.REPOSITORY, backup.PASSWORD))
    client = Path('/usr/local/sbin/msgvault-backup')
    units = [Path('/etc/systemd/system') / name for name in ('msgvault-backup.service', 'msgvault-backup.timer')]
    for path in [client, *units, backup.STATE, backup.STAGE.parent, backup.REPOSITORY]:
        if path.exists() or path.is_symlink():
            raise SystemExit('Preserving existing installation: ' + str(path))
    mount = json.loads(subprocess.check_output(['findmnt', '--json', '-o', 'SOURCE,FSTYPE,TARGET', '-T', str(backup.NAS)], text=True))
    backup.guard_mount(mount['filesystems'][0])
    password_stat = backup.PASSWORD.stat()
    if password_stat.st_uid != 0 or stat.S_IMODE(password_stat.st_mode) != 0o600:
        raise SystemExit('Expected existing root-only Restic password.')
    recovery = backup.NAS / 'backups/thebeachlab-restic-password'
    if not hmac.compare_digest(backup.PASSWORD.read_bytes().rstrip(b'\r\n'), recovery.read_bytes().rstrip(b'\r\n')):
        raise SystemExit('Existing private NAS recovery password differs; preserving both.')
    subprocess.run(['systemctl', 'is-active', '--quiet', 'msgvault.service'], check=True)
    config = backup.HOME_DIR / 'config.toml'
    owner_key = re.search(r'(?m)^api_key\s*=\s*"([^"\n]+)"', config.read_text()).group(1)
    def api(method, body=None, etag=None):
        headers = {'X-API-Key': owner_key, 'Content-Type': 'application/json'}
        if method == 'PATCH':
            # API 3.0.0 patchSettings requires the latest strong If-Match ETag.
            assert etag, 'Expected a version from GET /api/v1/settings'
            headers['If-Match'] = etag
        request = Request('http://127.0.0.1:8096/api/v1/settings', method=method,
                          headers=headers,
                          data=json.dumps(body).encode() if body else None)
        with urlopen(request, timeout=20) as response:
            return json.load(response), response.headers.get('ETag')
    before, etag = api('GET')
    profile = json.loads((source / 'storage-settings.json').read_text())
    existing = {item['key']: item for item in before['settings']}
    for update in profile['updates']:
        item = existing[update['key']]
        assert not item.get('read_only') and item['kind'] in update['value'], update['key']
    old = Path('/opt/msgvault/backups') / ('storage-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    old.mkdir(mode=0o700)
    shutil.copyfile(config, old / 'config.toml')
    (old / 'config.toml').chmod(0o600)
    backup.STATE.mkdir(mode=0o700)
    (backup.STATE / 'restic-cache').mkdir(mode=0o700)
    backup.STAGE.parent.mkdir(mode=0o700)
    subprocess.run(['/usr/sbin/runuser', '-u', 'msgvault', '--',
                    'test', '-w', str(backup.STAGE.parent)], check=True)
    backup.REPOSITORY.mkdir(mode=0o700)
    env = backup.environment()
    backup.run(['restic', 'init'], env)
    identity = json.loads(backup.run(['restic', 'cat', 'config'], env))['id']
    backup.save_json(backup.STATE / 'repository.json', {'id': identity, 'path': str(backup.REPOSITORY)})
    shutil.copyfile(source / 'backup.py', client)
    client.chmod(0o755)
    for unit in units:
        shutil.copyfile(source / unit.name, unit)
        unit.chmod(0o644)
    for name in ('backup.py', 'install-backup.py', 'msgvault-backup.service', 'msgvault-backup.timer', 'storage-settings.json'):
        destination = Path('/opt/msgvault/deployment') / name
        if destination.exists():
            raise SystemExit('Preserving existing deployment source: ' + str(destination))
        shutil.copyfile(source / name, destination)
        destination.chmod(0o755 if name.endswith('.py') else 0o644)
    subprocess.run(['systemd-analyze', 'verify', *map(str, units)], check=True)
    api('PATCH', profile, etag)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'restart', 'msgvault.service', 'msgvault-mcp.service'], check=True)
    for attempt in range(40):
        try:
            after, _ = api('GET')
            break
        except OSError:
            time.sleep(0.5)
    else:
        raise SystemExit('Msgvault did not become ready after applying settings.')
    values = {item['key']: item.get('value') for item in after['settings'] if item['kind'] != 'secret'}
    wanted = {item['key']: item['value'] for item in profile['updates']}
    for key, value in values.items():
        assert value == wanted.get(key, existing[key].get('value')), key
    subprocess.run(['systemctl', 'enable', '--now', 'msgvault-backup.timer'], check=True)
    subprocess.run(['systemctl', 'start', 'msgvault-backup.service'], check=True)
    print('Encrypted NAS backup installed; storage profile verified; original config:', old)


if __name__ == '__main__':
    main()
