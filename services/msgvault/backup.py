#!/usr/bin/env python3
"""Consistent Msgvault capture followed by encrypted, isolated NAS retention.

Capture contract: kenn-io/msgvault v0.21.0, docs/usage/backup.md.
Restic contracts: restic.readthedocs.io/en/v0.12.1/{040_backup,060_forget}.html.
"""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
from zoneinfo import ZoneInfo

HOME_DIR = Path('/var/lib/msgvault')
STATE = Path('/var/lib/msgvault-backup')
NAS = Path('/mnt/nas-downloads')
STAGE = NAS / 'backups/msgvault-staging/payload'
LEGACY_STAGE = HOME_DIR / 'backup-staging/payload'
REPOSITORY = NAS / 'backups/msgvault-restic'
PASSWORD = Path('/root/.config/thebeachlab-backup/restic-password')
RESERVE = 10 * 1024**3
GC_NAME = re.compile(r'msgvault\.db\.gc-backup-[0-9]{8}-[0-9]{6}\Z')


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
    # Both the temporary capture and its encrypted backup now live on the NAS.
    if local_free < RESERVE or nas_free < 2 * estimate + RESERVE:
        raise RuntimeError('Not enough space for NAS capture and backup plus a 10 GiB reserve.')


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            digest.update(chunk)
    return digest.hexdigest()


def gc_identity(path):
    guard_paths((path,))
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError('GC recovery copy is not a regular file: ' + str(path))
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def capture_gc_backups():
    # v0.21.0 cmd/msgvault/cmd/gc.go fixes this filename beside the live DB;
    # internal/store/backup_test.go documents atomic publication of the backup.
    # These immutable recovery copies are distinct from the current native capture.
    entries = []
    for source in sorted(HOME_DIR.glob('msgvault.db.gc-backup-*')):
        if not GC_NAME.fullmatch(source.name):
            continue
        identity = gc_identity(source)
        directory = STAGE / 'gc-backups'
        directory.mkdir(mode=0o700, exist_ok=True)
        target = directory / source.name
        shutil.copyfile(source, target)
        target.chmod(0o600)
        digest = file_hash(target)
        if gc_identity(source) != identity or file_hash(source) != digest:
            raise RuntimeError('GC recovery copy changed during capture; preserving it: ' + str(source))
        entries.append({'name': source.name, 'sha256': digest,
                        'size_bytes': identity[2], 'source_identity': identity})
    return entries


def verify_gc_restore(snapshot, entry, env):
    # Stream every recovered byte; do not trust only a snapshot ID or sampled check.
    target = STAGE / 'gc-backups' / entry['name']
    digest = hashlib.sha256()
    size = 0
    with subprocess.Popen(['restic', 'dump', snapshot, str(target)], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        for chunk in iter(lambda: process.stdout.read(1024**2), b''):
            digest.update(chunk)
            size += len(chunk)
        diagnostic = process.stderr.read()
        code = process.wait()
    if code:
        (STATE / 'last-command-error.txt').write_bytes(diagnostic)
        raise RuntimeError('Restic recovery failed; preserving GC copy: ' + entry['name'])
    if size != entry['size_bytes'] or digest.hexdigest() != entry['sha256']:
        raise RuntimeError('Recovered GC copy differs; preserving local original: ' + entry['name'])


def cleanup_gc_backups(pending, env):
    results = []
    for entry in pending.get('gc_backups', []):
        if not GC_NAME.fullmatch(entry['name']):
            raise RuntimeError('Invalid GC recovery filename; refusing cleanup.')
        source = HOME_DIR / entry['name']
        verify_gc_restore(pending['gc_restic_snapshot'], entry, env)
        if source.exists() or source.is_symlink():
            if (gc_identity(source) != entry['source_identity']
                    or file_hash(source) != entry['sha256']
                    or gc_identity(source) != entry['source_identity']):
                raise RuntimeError('Local GC copy changed; preserving it: ' + str(source))
            source.unlink()
            outcome = 'removed'
        else:
            outcome = 'already_absent'
        results.append(dict(entry, restore_sha256_matches=True, cleanup=outcome))
    return results


def msgvault(*args):
    return run(['/usr/sbin/runuser', '-u', 'msgvault', '--', '/usr/bin/env',
                'MSGVAULT_HOME=' + str(HOME_DIR), '/usr/local/bin/msgvault', '--no-log-file', *args])


def capture():
    # Full temporary capture: compression is not assumed when checking capacity.
    source_bytes = sum(size_of(HOME_DIR / name) for name in
                       ('msgvault.db', 'msgvault.db-wal', 'attachments', 'tokens', 'deletions', 'config.toml', 'mcp.toml'))
    source_bytes += sum(size_of(path) for path in HOME_DIR.glob('msgvault.db.gc-backup-*')
                        if GC_NAME.fullmatch(path.name))
    estimate = int(source_bytes * 1.05) + 256 * 1024**2
    guard_capacity(estimate, shutil.disk_usage(HOME_DIR).free, shutil.disk_usage(NAS).free)
    STAGE.mkdir(mode=0o700)
    # NAS staging uses the export's ownership; the installer verifies actual
    # service-account access instead of assuming local chown semantics.
    pending = {'phase': 'capturing', 'stage': str(STAGE),
               'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
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
    # Runtime opt-ins live in service drop-ins, so recovery must include them.
    dropins = tuple(sorted(Path('/etc/systemd/system/msgvault.service.d').glob('*.conf')))
    for path in dropins:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Preserving non-regular service drop-in: ' + str(path))
    for name in (*files, *(str(path) for path in dropins)):
        destination = STAGE / 'host-files' / name.lstrip('/')
        destination.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        shutil.copyfile(name, destination)
        destination.chmod(0o600)
    pending['gc_backups'] = capture_gc_backups()
    save_json(STAGE / 'capture.json', dict(pending, version=msgvault('version').strip(),
                                          estimated_capture_bytes=estimate))
    pending['phase'] = 'captured'
    save_json(STATE / 'pending.json', pending)
    return pending


def cleanup_uploaded(pending, env=None):
    if pending.get('phase') != 'uploaded':
        raise RuntimeError('Refusing to remove a capture without a verified encrypted snapshot.')
    check_mount()
    check_repository(env)
    pending['gc_backup_cleanup'] = cleanup_gc_backups(pending, env)
    if STAGE.exists():
        guard_paths((STAGE.parent, STAGE))
        shutil.rmtree(STAGE)
    pending['temporary_cleanup_completed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_json(STATE / 'last-success.json', pending)
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
        if LEGACY_STAGE.exists() or LEGACY_STAGE.is_symlink():
            raise RuntimeError('Legacy local staging data preserved; migrate it before continuing.')
        marker = STATE / 'pending.json'
        pending = json.loads(marker.read_text()) if marker.exists() else None
        if pending and pending.get('stage') != str(STAGE):
            raise RuntimeError('Pending capture uses another staging path; preserving it.')
        if pending and pending.get('phase') == 'uploaded':
            cleanup_uploaded(pending, env)
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
        if pending.get('gc_backups') and not pending.get('gc_restic_snapshot'):
            # Keep recovery copies outside daily-current-state retention: a later
            # backup on the same day must not remove the only pre-GC database.
            result = run(['restic', 'backup', str(STAGE / 'gc-backups'),
                          '--tag', 'msgvault-gc-recovery', '--json'], env)
            summaries = [json.loads(line) for line in result.splitlines() if line.startswith('{')]
            pending['gc_restic_snapshot'] = next(item['snapshot_id'] for item in summaries
                                                if item.get('message_type') == 'summary')
            save_json(marker, pending)
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
        cleanup_uploaded(pending, env)
        print('Verified encrypted Msgvault snapshot ' + snapshot + '; temporary capture removed.')


if __name__ == '__main__':
    main()
