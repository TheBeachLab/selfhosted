#!/usr/bin/env python3
"""Consistent Msgvault capture followed by encrypted, isolated NAS retention.

Capture contract: kenn-io/msgvault v0.21.0, docs/usage/backup.md.
Restic contracts: restic.readthedocs.io/en/v0.12.1/{040_backup,060_forget}.html.
"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import subprocess
from zoneinfo import ZoneInfo

HOME_DIR = Path('/var/lib/msgvault')
STATE = Path('/var/lib/msgvault-backup')
STAGE = HOME_DIR / 'backup-staging/payload'
NAS = Path('/mnt/nas-downloads')
REPOSITORY = NAS / 'backups/msgvault-restic'
PASSWORD = Path('/root/.config/thebeachlab-backup/restic-password')
RESERVE = 10 * 1024**3


def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def run(args, env=None):
    result = subprocess.run(args, env=env, text=True, capture_output=True)
    if result.returncode:
        diagnostic = STATE / 'last-command-error.txt'
        diagnostic.write_text(result.stdout + result.stderr)
        diagnostic.chmod(0o600)
        raise RuntimeError(f'{args[0]} failed ({result.returncode}); private diagnostic: {diagnostic}')
    return result.stdout


def guard_mount(mount):
    if (mount['target'] != str(NAS) or mount['fstype'] not in ('nfs', 'nfs4')
            or mount['source'] != '192.168.1.100:/volume1/synology'):
        raise RuntimeError('Expected Synology NFS mount is unavailable; no backup writes allowed.')


def guard_paths(paths):
    for path in paths:
        if path.is_symlink() or path.resolve() != path:
            raise RuntimeError('Unexpected path redirection: ' + str(path))


def check_mount():
    mounts = json.loads(run(['findmnt', '--json', '-o', 'SOURCE,FSTYPE,TARGET', '-T', str(NAS)]))
    guard_mount(mounts['filesystems'][0])


def environment():
    return dict(os.environ, RESTIC_REPOSITORY=str(REPOSITORY),
                RESTIC_PASSWORD_FILE=str(PASSWORD), RESTIC_CACHE_DIR=str(STATE / 'restic-cache'))


def guard_identity(expected, actual):
    if not expected or actual != expected:
        raise RuntimeError('Backup repository identity changed; refusing capture or retention.')


def check_repository(env):
    expected = json.loads((STATE / 'repository.json').read_text())['id']
    guard_identity(expected, json.loads(run(['restic', 'cat', 'config'], env))['id'])


def size_of(path):
    if not path.exists():
        return 0
    if path.is_symlink():
        raise RuntimeError('Unexpected symlink in capture size inventory: ' + str(path))
    if path.is_file():
        return path.stat().st_size
    return sum(size_of(child) for child in path.iterdir())


def guard_capacity(estimate, local_free, nas_free):
    if local_free < estimate + RESERVE or nas_free < estimate + RESERVE:
        raise RuntimeError('Not enough space for a complete capture plus a 10 GiB reserve.')


def msgvault(*args):
    return run(['/usr/sbin/runuser', '-u', 'msgvault', '--', '/usr/bin/env',
                'MSGVAULT_HOME=' + str(HOME_DIR), '/usr/local/bin/msgvault', '--no-log-file', *args])


def capture():
    # Full temporary capture: compression is not assumed when checking capacity.
    source_bytes = sum(size_of(HOME_DIR / name) for name in
                       ('msgvault.db', 'msgvault.db-wal', 'attachments', 'tokens', 'deletions', 'config.toml', 'mcp.toml'))
    estimate = int(source_bytes * 1.05) + 256 * 1024**2
    guard_capacity(estimate, shutil.disk_usage(HOME_DIR).free, shutil.disk_usage(NAS).free)
    STAGE.mkdir(mode=0o700)
    user = pwd.getpwnam('msgvault')
    os.chown(STAGE, user.pw_uid, user.pw_gid)
    pending = {'phase': 'capturing', 'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    save_json(STATE / 'pending.json', pending)
    archive = str(STAGE / 'archive')
    msgvault('backup', 'init', '--repo', archive)
    msgvault('backup', 'create', '--repo', archive, '--jobs', '1', '--tag', 'nas-daily',
             '--include-config', '--include-tokens', '--allow-plaintext-secrets')
    msgvault('backup', 'verify', '--repo', archive, '--jobs', '1', '--quick')
    # Native extras cover config.toml and OAuth tokens. Preserve host access too.
    files = ('/var/lib/msgvault/mcp.toml', '/etc/systemd/system/msgvault.service',
             '/etc/systemd/system/msgvault-mcp.service', '/etc/systemd/system/msgvault-backup.service',
             '/etc/systemd/system/msgvault-backup.timer', '/etc/nginx/sites-available/msgvault.beachlab.org',
             '/etc/nginx/snippets/msgvault-api-key.conf')
    for name in files:
        destination = STAGE / 'host-files' / name.lstrip('/')
        destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        shutil.copyfile(name, destination)
        destination.chmod(0o600)
    save_json(STAGE / 'capture.json', dict(pending, version=msgvault('version').strip(),
                                          estimated_capture_bytes=estimate))
    pending['phase'] = 'captured'
    save_json(STATE / 'pending.json', pending)
    return pending


def cleanup_uploaded(pending):
    if pending.get('phase') != 'uploaded':
        raise RuntimeError('Refusing to remove a capture without a verified encrypted snapshot.')
    if STAGE.exists():
        if STAGE.is_symlink() or STAGE.parent.is_symlink():
            raise RuntimeError('Unexpected staging symlink; preserving it.')
        shutil.rmtree(STAGE)
    (STATE / 'pending.json').unlink()


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run as root on the NUC.')
    os.umask(0o077)
    guard_paths((HOME_DIR, STATE, STAGE.parent, STAGE, REPOSITORY))
    with (STATE / 'run.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_mount()
        env = environment()
        check_repository(env)
        marker = STATE / 'pending.json'
        pending = json.loads(marker.read_text()) if marker.exists() else None
        if pending and pending.get('phase') == 'uploaded':
            cleanup_uploaded(pending)
            pending = None
        if pending:
            if pending.get('phase') != 'captured' or not STAGE.is_dir():
                raise RuntimeError('Incomplete capture preserved; inspect private state before retrying.')
            print('Retrying the retained coherent capture from ' + pending['captured_at'], flush=True)
            guard_capacity(0, shutil.disk_usage(HOME_DIR).free, shutil.disk_usage(NAS).free)
        else:
            if STAGE.exists():
                raise RuntimeError('Unowned staging data preserved; refusing to overwrite it.')
            pending = capture()
        result = run(['restic', 'backup', str(STAGE), '--tag', 'msgvault', '--json'], env)
        summaries = [json.loads(line) for line in result.splitlines() if line.startswith('{')]
        snapshot = next(item['snapshot_id'] for item in summaries if item.get('message_type') == 'summary')
        check_args = ['restic', 'check', '--read-data' if
                      datetime.datetime.now(ZoneInfo('Europe/Madrid')).weekday() == 6
                      else '--read-data-subset=5%']
        run(check_args, env)
        check_mount()
        check_repository(env)
        run(['restic', 'forget', '--host', socket.gethostname(), '--tag', 'msgvault',
             '--keep-daily', '7', '--keep-weekly', '4', '--keep-monthly', '6', '--prune'], env)
        pending.update(phase='uploaded', restic_snapshot=snapshot,
                       completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        save_json(STATE / 'last-success.json', pending)
        save_json(marker, pending)
        cleanup_uploaded(pending)
        print('Verified encrypted Msgvault snapshot ' + snapshot + '; temporary capture removed.')


if __name__ == '__main__':
    main()
