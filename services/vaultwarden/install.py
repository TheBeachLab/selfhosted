#!/usr/bin/env python3
"""First installation of Passwords on the NUC; refuse existing service paths."""
import ctypes
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import shutil
import socket
import subprocess
import sys

SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE))
import backup

ROOT = Path('/opt/vaultwarden')
SITE = Path('/etc/nginx/sites-available/passwords.beachlab.org')
ENABLED = Path('/etc/nginx/sites-enabled/passwords.beachlab.org')
HOOK = Path('/etc/letsencrypt/renewal-hooks/deploy/50-vaultwarden-nginx')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def guard_new_paths(paths):
    for path in paths:
        if path.exists() or path.is_symlink():
            raise RuntimeError('Preserving existing installation path: ' + str(path))


def replace_if_unchanged(path, expected, content):
    if digest(path.read_bytes()) != expected:
        raise RuntimeError('Concurrent change preserved: ' + str(path))
    tmp = path.with_name(path.name + '.vaultwarden-tmp')
    with tmp.open('xb') as output:
        output.write(content)
    shutil.copymode(path, tmp)
    tmp.replace(path)


def admin_hash(token):
    # https://github.com/dani-garcia/vaultwarden/wiki/Enabling-admin-page#secure-the-admin_token
    library = ctypes.CDLL(ctypes.util.find_library('argon2'))
    fn = library.argon2id_hash_encoded
    fn.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                  ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
                  ctypes.c_void_p, ctypes.c_size_t]
    fn.restype = ctypes.c_int
    raw, salt = token.encode(), secrets.token_bytes(32)
    output = ctypes.create_string_buffer(256)
    if fn(3, 65536, 4, raw, len(raw), salt, len(salt), 32, output, len(output)) != 0:
        raise RuntimeError('Argon2id hash generation failed.')
    return output.value.decode()


def main():
    if os.geteuid() != 0 or sys.platform != 'linux' or socket.gethostname() != 'thebeachlab':
        raise SystemExit('Run as root on the NUC thebeachlab.')
    os.umask(0o077)
    guard_new_paths([ROOT, backup.DATA, backup.STATE, backup.REPOSITORY, SITE, ENABLED, HOOK,
        Path('/usr/local/sbin/vaultwarden-backup'), Path('/usr/local/sbin/vaultwarden-invite'),
        Path('/etc/systemd/system/vaultwarden-backup.service'),
        Path('/etc/systemd/system/vaultwarden-backup.timer')])
    if not ctypes.util.find_library('argon2') or not backup.PASSWORD.is_file():
        raise RuntimeError('Required libargon2 or root-only Restic password is unavailable.')
    if subprocess.check_output(['ss', '-H', '-lnt', 'sport = :18080']).strip():
        raise RuntimeError('Port 18080 is already in use.')
    if subprocess.run(['docker', 'container', 'inspect', 'vaultwarden'], capture_output=True).returncode == 0:
        raise RuntimeError('Preserving existing Vaultwarden container.')
    try:
        pwd.getpwnam('vaultwarden')
    except KeyError:
        pass
    else:
        raise RuntimeError('Preserving existing Vaultwarden service user.')
    mounts = subprocess.check_output(['findmnt', '--json', '-o', 'SOURCE,FSTYPE,TARGET',
                                     '-T', str(backup.NAS)], text=True)
    backup.guard_mount(json.loads(mounts)['filesystems'][0])
    subprocess.run(['nginx', '-t'], check=True)
    for path in (ROOT, backup.STATE):
        path.mkdir(mode=0o700)
    shutil.copytree(SOURCE, ROOT / 'deployment', ignore=shutil.ignore_patterns('__pycache__'))
    subprocess.run(['useradd', '--system', '--user-group', '--home-dir', str(backup.DATA),
                    '--no-create-home', '--shell', '/usr/sbin/nologin', 'vaultwarden'], check=True)
    account = pwd.getpwnam('vaultwarden')
    backup.DATA.mkdir(mode=0o700)
    os.chown(backup.DATA, account.pw_uid, account.pw_gid)
    token = secrets.token_urlsafe(48)
    (ROOT / 'admin-token').write_text(token + '\n')
    (ROOT / '.env').write_text(f"VAULTWARDEN_UID={account.pw_uid}\nVAULTWARDEN_GID={account.pw_gid}\n"
                             f"VAULTWARDEN_ADMIN_TOKEN='{admin_hash(token)}'\n")
    for name in ('admin-token', '.env'):
        (ROOT / name).chmod(0o600)
    subprocess.run(['python3', str(SOURCE / 'configure-oidc.py'), '--apply'], check=True)
    shutil.copyfile(SOURCE / 'compose.yaml', ROOT / 'compose.yaml')
    run = backup.run
    compose = ['docker', 'compose', '--project-directory', str(ROOT), '-f', str(ROOT / 'compose.yaml')]
    run(compose + ['config', '--quiet'])
    run(compose + ['pull'])
    run(compose + ['up', '-d', '--wait', '--wait-timeout', '90'])
    backup.ready()
    bootstrap = (SOURCE / 'http-bootstrap.conf').read_bytes()
    SITE.write_bytes(bootstrap)
    SITE.chmod(0o644)
    ENABLED.symlink_to(SITE)
    run(['nginx', '-t'])
    run(['systemctl', 'reload', 'nginx'])
    run(['certbot', 'certonly', '--webroot', '-w', '/var/www/letsencrypt',
         '--cert-name', 'passwords.beachlab.org', '-d', 'passwords.beachlab.org', '--non-interactive'])
    final = (SOURCE / 'nginx.conf').read_bytes()
    replace_if_unchanged(SITE, digest(bootstrap), final)
    try:
        run(['nginx', '-t'])
        run(['systemctl', 'reload', 'nginx'])
    except Exception:
        replace_if_unchanged(SITE, digest(final), bootstrap)
        run(['nginx', '-t'])
        run(['systemctl', 'reload', 'nginx'])
        raise
    shutil.copyfile(SOURCE / '50-vaultwarden-nginx', HOOK)
    HOOK.chmod(0o755)
    for name in ('backup', 'invite'):
        dst = Path('/usr/local/sbin/vaultwarden-' + name)
        shutil.copyfile(SOURCE / (name + '.py'), dst)
        dst.chmod(0o755)
    run(['/usr/local/sbin/vaultwarden-invite', 'hola@beachlab.org'])
    backup.REPOSITORY.mkdir(mode=0o700)
    env = backup.environment()
    run(['restic', 'init'], env)
    identity = json.loads(run(['restic', 'cat', 'config'], env))['id']
    (backup.STATE / 'repository.json').write_text(json.dumps({'id': identity}) + '\n')
    for name in ('vaultwarden-backup.service', 'vaultwarden-backup.timer'):
        dst = Path('/etc/systemd/system') / name
        shutil.copyfile(SOURCE / name, dst)
        dst.chmod(0o644)
    run(['systemd-analyze', 'verify', '/etc/systemd/system/vaultwarden-backup.service',
         '/etc/systemd/system/vaultwarden-backup.timer'])
    run(['systemctl', 'daemon-reload'])
    run(['systemctl', 'enable', '--now', 'vaultwarden-backup.timer'])
    print('Vaultwarden installed: https://passwords.beachlab.org/')
    print('Sign in through Authentik with Fran\'s passkey and choose the vault master password.')


if __name__ == '__main__':
    main()
