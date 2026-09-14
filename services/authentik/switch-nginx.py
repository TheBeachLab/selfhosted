#!/usr/bin/env python3
"""Stage or activate the seven-site Basic-to-passkey switch, preserving originals.
Run locally on the server as root. Activation requires an enrolled fran passkey.
No .htpasswd files are read or modified. Backups stay root-only on the server.
"""
import argparse, datetime, hashlib, json, re, shutil, subprocess
from pathlib import Path

FILES = {
    '/etc/nginx/sites-available/beachlab.org': 3,
    '/etc/nginx/snippets/deutsch-sprint.conf': 2,
    '/etc/nginx/snippets/remote-browser.conf': 1,
    '/etc/nginx/sites-available/comfyui.beachlab.org': 1,
    '/etc/nginx/sites-available/designer.daswerklab.de': 1,
}
BASE = Path('/opt/authentik')
STAGE = BASE / 'nginx-staged'
PATTERN = re.compile(r'(?m)^(\s*)auth_basic\s+"[^"\n]+";\s*\n\s*auth_basic_user_file\s+/etc/nginx/\.htpasswd-[\w-]+;')

def digest(data): return hashlib.sha256(data).hexdigest()

def prepare():
    STAGE.mkdir(mode=0o700, exist_ok=True)
    manifest = {}
    for name, count in FILES.items():
        raw = Path(name).read_bytes()
        replacement, n = PATTERN.subn(lambda m: m[1] + 'include /etc/nginx/snippets/authentik-check.conf;', raw.decode())
        if n != count: raise RuntimeError(f'{name}: expected {count} Basic blocks, found {n}; inspect before retry')
        if '/sites-available/' in name:
            marker = '    include /etc/nginx/snippets/authentik-outpost.conf;\n'
            # Add to the TLS block by locating the SSL options include, exactly once.
            replacement, n = re.subn(r'(?m)^(\s*include\s+/etc/letsencrypt/options-ssl-nginx.conf;[^\n]*\n)', lambda m: m[0] + marker, replacement)
            if n != 1: raise RuntimeError(f'{name}: expected one TLS block, found {n}')
        target = STAGE / Path(name).name
        target.write_text(replacement)
        manifest[name] = {'before': digest(raw), 'after': digest(target.read_bytes())}
    (STAGE / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print('Staged five configuration files; production authentication unchanged.')

def activate():
    query = ('from authentik.stages.authenticator_webauthn.models import WebAuthnDevice; '
             'print("ENROLLED=" + str(WebAuthnDevice.objects.filter('
             'user__username="fran",rp_id="auth.beachlab.org").count()))')
    result = subprocess.run(['docker', 'exec', 'authentik-server-1', 'ak', 'shell', '-c', query],
                            capture_output=True, text=True, check=True)
    match = re.search(r'^ENROLLED=(\d+)$', result.stdout, re.M)
    if not match or int(match[1]) < 1:
        raise RuntimeError('No verified enrolled passkey for fran at auth.beachlab.org')
    manifest = json.loads((STAGE / 'manifest.json').read_text())
    for name, hashes in manifest.items():
        if digest(Path(name).read_bytes()) != hashes['before']: raise RuntimeError(f'{name} changed since staging; inspect and restage')
        if digest((STAGE / Path(name).name).read_bytes()) != hashes['after']: raise RuntimeError('Staged configuration changed')
    backup = BASE / ('nginx-backup-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    for name in manifest: shutil.copy2(name, backup / Path(name).name)
    try:
        for snippet in ['authentik-check.conf', 'authentik-outpost.conf']:
            dest = Path('/etc/nginx/snippets') / snippet
            if dest.exists(): raise RuntimeError(f'{dest} already exists; inspect ownership')
            shutil.copyfile(BASE / snippet, dest)
            dest.chmod(0o644)
        for name in manifest: shutil.copyfile(STAGE / Path(name).name, name)
        subprocess.run(['nginx', '-t'], check=True)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
    except Exception:
        for name in manifest: shutil.copyfile(backup / Path(name).name, name)
        subprocess.run(['nginx', '-t'], check=True)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
        raise
    print('Activated; rollback originals:', backup)

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('action', choices=['prepare', 'activate']); args = p.parse_args()
    prepare() if args.action == 'prepare' else activate()
