#!/usr/bin/env python3
"""Return this NUC to the verified official release without replacing its data.

Release: https://github.com/kenn-io/msgvault/releases/tag/v0.21.0
The preserved executable was compared with the checksummed official archive.
A fresh, fully restored encrypted NAS snapshot is required before activation.
No provider calls, credentials, mail text or profile prose enter stdout.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

DATA = Path('/var/lib/msgvault')
CONFIG = DATA / 'config.toml'
STATE = Path('/var/lib/msgvault-backup')
SOURCE = Path(__file__).resolve().parent
LINK = Path('/usr/local/bin/msgvault')
OFFICIAL = Path('/opt/msgvault/0.21.0/msgvault')
OFFICIAL_SHA = '2e00619b03f9914aaece4f6458299dc66bc9f6386856098ea9329c889d0a5a1e'
PATCHED_SHA = '1624c33470cfc51d2b845b344b58d9da5b596ce1cd649236618225c5779cf3f0'
MANIFEST = SOURCE / 'runtime-build.json'
TIMER = 'msgvault-mailbox-discovery.timer'
DISCOVERY = 'msgvault-mailbox-discovery.service'
UNITS = ('msgvault.service', 'msgvault-mcp.service')
RETIRE = {
    Path('/etc/systemd/system/msgvault.service.d/30-people-email-evidence.conf'): 'people-email-evidence.conf',
    Path('/etc/systemd/system/msgvault.service.d/50-mailbox-discovery.conf'): 'mailbox-discovery.conf',
    Path('/etc/systemd/system/msgvault-mailbox-discovery.service'): DISCOVERY,
    Path('/etc/systemd/system/msgvault-mailbox-discovery.timer'): TIMER,
    Path('/usr/local/sbin/msgvault-mailbox-discovery'): 'mailbox-discovery.py',
}
PROTECTED_TABLES = (
    'sources', 'messages', 'message_bodies', 'message_raw', 'participants',
    'message_recipients', 'attachments', 'persons', 'person_names',
    'person_contact_points', 'person_addresses', 'person_dates', 'person_categories',
    'person_media', 'person_participants', 'person_tracking',
    'person_brief_enrollments', 'person_briefs', 'person_brief_evidence',
    'person_attribute_values', 'person_relationships', 'employments',
    'person_fact_claims', 'person_fact_claim_evidence', 'person_fact_decisions',
    'person_fact_evidence', 'person_fact_evidence_status_events',
    'person_fact_generations', 'person_fact_resolutions', 'person_inference_profiles',
    'person_inference_checks', 'person_inference_consents', 'person_match_consents',
    'person_match_judgments', 'mailbox_discovery_state', 'mailbox_discovery_budget',
    'mailbox_discovery_judgments', 'person_signed_mail_evidence',
    'person_signed_mail_watch', 'applied_migrations',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode})')
    return result.stdout


def disable_people(original):
    text = original.decode()
    for section in ('people.sweep', 'people.sweep.brief'):
        pattern = r'(?m)^[ \t]*\[' + re.escape(section) + r'\][^\n]*\n(?:[^\n]*\n?)*?(?=^[ \t]*\[|\Z)'
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            raise RuntimeError('Expected one ' + section + ' section')
        match = matches[0]
        body, count = re.subn(r'(?m)^([ \t]*enabled[ \t]*=[ \t]*)(true|false)([ \t]*(?:#[^\n]*)?)$',
                              r'\g<1>false\3', match.group())
        if count != 1:
            raise RuntimeError('Expected one enabled field in ' + section)
        text = text[:match.start()] + body + text[match.end():]
    return text.encode()


def require_backup(snapshot, last, proof, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if not re.fullmatch(r'[0-9a-f]{8,64}', snapshot):
        raise RuntimeError('Invalid backup snapshot identity')
    if (last.get('restic_snapshot') != snapshot or last.get('phase') != 'uploaded'
            or proof.get('snapshot') != snapshot
            or proof.get('official_backup_verify') != 'all-packs-passed'
            or proof.get('official_restore_integrity') != 'passed'
            or proof.get('temporary_dir_removed') is not True):
        raise RuntimeError('The exact completed NAS backup must pass a full restore')
    completed = datetime.datetime.fromisoformat(last['completed_at'])
    verified = datetime.datetime.fromisoformat(proof['verified_at'])
    if (completed.tzinfo is None or verified.tzinfo is None or verified < completed
            or not datetime.timedelta(0) <= now - completed <= datetime.timedelta(hours=2)
            or verified > now):
        raise RuntimeError('Backup verification is stale or inconsistent')


def atomic_bytes(path, content, metadata=None):
    metadata = metadata or path.stat()
    fd, name = tempfile.mkstemp(prefix='.official-return-', dir=path.parent)
    try:
        os.fchmod(fd, stat.S_IMODE(metadata.st_mode))
        os.fchown(fd, metadata.st_uid, metadata.st_gid)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def restore_owned(path, original, expected_after, metadata):
    if path.is_symlink():
        raise RuntimeError('Preserving an unexpected redirected recovery path')
    actual = path.read_bytes() if path.exists() else None
    if actual == original:
        return
    if actual != expected_after:
        raise RuntimeError('Preserving concurrent changes during rollback')
    atomic_bytes(path, original, metadata)


def replace_link(expected, target):
    if not LINK.is_symlink() or LINK.resolve(strict=True) != expected:
        raise RuntimeError('Executable selection changed; preserving it')
    temporary = LINK.with_name('.msgvault-official-' + uuid.uuid4().hex)
    try:
        temporary.symlink_to(target)
        os.replace(temporary, LINK)
    finally:
        temporary.unlink(missing_ok=True)


def protected_state():
    c = sqlite3.connect('file:' + str(DATA / 'msgvault.db') + '?mode=ro', uri=True)
    try:
        c.execute('BEGIN')
        output = {}
        for table in PROTECTED_TABLES:
            info = list(c.execute('PRAGMA table_info("' + table + '")'))
            if not info:
                raise RuntimeError('A protected archive table is missing')
            order = [r[1] for r in sorted(info, key=lambda r: r[5]) if r[5]] or [r[1] for r in info]
            h, count = hashlib.sha256(), 0
            for row in c.execute('SELECT * FROM "' + table + '" ORDER BY ' + ','.join('"' + key + '"' for key in order)):
                for value in row:
                    if isinstance(value, bytes):
                        tag, payload = b'b', value
                    elif isinstance(value, str):
                        tag, payload = b's', value.encode()
                    else:
                        tag, payload = b'j', json.dumps(value, separators=(',', ':')).encode()
                    h.update(tag)
                    h.update(len(payload).to_bytes(8, 'big'))
                    h.update(payload)
                h.update(b'\n')
                count += 1
            output[table] = {'rows': count, 'sha256': h.hexdigest()}
        if c.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or c.execute('PRAGMA foreign_key_check').fetchone():
            raise RuntimeError('Archive integrity check failed')
        return output
    finally:
        c.close()


def credentials():
    return {str(p): digest(p) for p in (DATA / 'tokens').rglob('*') if p.is_file()}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def api(path):
    section = re.search(r'(?ms)^[ \t]*\[server\][^\n]*\n(.*?)(?=^[ \t]*\[|\Z)', CONFIG.read_text())
    if section is None:
        raise RuntimeError('Missing server configuration')
    keys = re.findall(r'(?m)^[ \t]*api_key[ \t]*=[ \t]*[\"\x27]([0-9a-f]{64})[\"\x27][ \t]*$', section.group(1))
    if len(keys) != 1:
        raise RuntimeError('Expected one existing owner credential')
    request = urllib.request.Request('http://127.0.0.1:8096' + path,
                                     headers={'Authorization': 'Bearer ' + keys[0]})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            return json.loads(response.read(4 << 20))
    except urllib.error.HTTPError as error:
        raise RuntimeError('Local API returned HTTP ' + str(error.code)) from None
    except urllib.error.URLError:
        raise RuntimeError('Local API connection failed') from None


def wait_healthy():
    for attempt in range(80):
        try:
            if api('/health').get('status') == 'ok':
                return
        except RuntimeError:
            pass
        time.sleep(0.5)
    raise RuntimeError('Msgvault did not become healthy')


def profiles():
    c = sqlite3.connect('file:' + str(DATA / 'msgvault.db') + '?mode=ro', uri=True)
    try:
        people = [r[0] for r in c.execute('SELECT id FROM persons ORDER BY id')]
        brief_people = [r[0] for r in c.execute("SELECT person_id FROM person_briefs WHERE status='current' ORDER BY person_id")]
    finally:
        c.close()
    result = {}
    for person in people:
        paths = [f'/api/v1/people/{person}/profile']
        if person in brief_people:
            paths.append(f'/api/v1/people/{person}/brief')
        for path in paths:
            result[path] = hashlib.sha256(json.dumps(api(path), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return result


def run(snapshot):
    if os.geteuid() != 0 or not LINK.is_symlink():
        raise RuntimeError('Expected root on the configured NUC')
    os.umask(0o077)
    if not re.fullmatch(r'[0-9a-f]{8,64}', snapshot):
        raise RuntimeError('Invalid backup snapshot identity')
    for path in (CONFIG, OFFICIAL, MANIFEST):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('Preserving an unexpected runtime path')
    last = json.loads((STATE / 'last-success.json').read_text())
    proof = json.loads((STATE / ('official-pre-restore-proof-' + snapshot + '.json')).read_text())
    require_backup(snapshot, last, proof)
    if (STATE / 'pending.json').exists():
        raise RuntimeError('Preserving an unfinished NAS capture')
    old = LINK.resolve(strict=True)
    if digest(old) != PATCHED_SHA or digest(OFFICIAL) != OFFICIAL_SHA:
        raise RuntimeError('Executable differs from the audited release')
    command('systemctl', 'is-active', '--quiet', *UNITS, 'msgvault-backup.timer')
    command('systemctl', 'is-enabled', '--quiet', 'msgvault-backup.timer')
    original = CONFIG.read_bytes()
    updated = disable_people(original)
    config_stat = CONFIG.stat()
    saved = {}
    for path, filename in RETIRE.items():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != (SOURCE / filename).read_bytes():
            raise RuntimeError('A local extension differs; preserving it')
        saved[path] = (path.read_bytes(), path.stat())
    manifest_original, manifest_stat = MANIFEST.read_bytes(), MANIFEST.stat()
    if json.loads(manifest_original).get('binary_sha256') != PATCHED_SHA:
        raise RuntimeError('The active build receipt differs')
    manifest_updated = (json.dumps({'version': 'v0.21.0', 'binary_sha256': OFFICIAL_SHA,
                                   'upstream_commit': '598ca5cc89042ded95e484b5315cc29b9342fa42',
                                   'source_release': 'https://github.com/kenn-io/msgvault/releases/tag/v0.21.0',
                                   'patches': {}, 'pre_return_snapshot': snapshot}, indent=2) + '\n').encode()
    keys_before = credentials()
    api_before = profiles()
    timer_enabled = subprocess.run(['systemctl', 'is-enabled', '--quiet', TIMER], capture_output=True).returncode == 0
    checkpoint = STATE / ('official-return-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()))
    checkpoint.mkdir(mode=0o700)
    (checkpoint / 'config-before.toml').write_bytes(original)
    (checkpoint / 'runtime-build-before.json').write_bytes(manifest_original)
    for path, (data, _) in saved.items():
        (checkpoint / path.name).write_bytes(data)
    receipt = {'status': 'prepared', 'snapshot': snapshot, 'previous_binary': str(old),
               'official_binary': str(OFFICIAL), 'checkpoint': str(checkpoint),
               'previous_discovery_timer_enabled': timer_enabled}
    metadata = {str(path): {'uid': item.st_uid, 'gid': item.st_gid,
                           'mode': stat.S_IMODE(item.st_mode)}
                for path, item in [(CONFIG, config_stat), (MANIFEST, manifest_stat),
                                   *((path, item) for path, (_, item) in saved.items())]}
    (checkpoint / 'original-file-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    def save():
        (checkpoint / 'activation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    save()
    try:
        command('systemctl', 'disable', '--now', TIMER)
        command('systemctl', 'stop', DISCOVERY, *UNITS)
        if CONFIG.read_bytes() != original or credentials() != keys_before:
            raise RuntimeError('Configuration or credentials changed before activation')
        before = protected_state()
        (checkpoint / 'protected-before.json').write_text(json.dumps(before, indent=2) + '\n')
        atomic_bytes(CONFIG, updated)
        for path, (data, _) in saved.items():
            if path.is_symlink() or path.read_bytes() != data:
                raise RuntimeError('A retirement file changed; preserving it')
            path.unlink()
        atomic_bytes(MANIFEST, manifest_updated)
        command('systemctl', 'daemon-reload')
        replace_link(old, OFFICIAL)
        command('systemctl', 'start', *UNITS)
        wait_healthy()
        after = protected_state()
        if before != after or profiles() != api_before:
            raise RuntimeError('Archive or saved profiles changed during the switch')
        if CONFIG.read_bytes() != updated or credentials() != keys_before:
            raise RuntimeError('Configuration or credentials changed unexpectedly')
        command('systemctl', 'is-active', '--quiet', *UNITS, 'msgvault-backup.timer')
        command('systemctl', 'is-enabled', '--quiet', 'msgvault-backup.timer')
        receipt.update(status='official-active', protected_tables_identical=len(before),
                       profiles_and_briefs_identical=True, credentials_unchanged=True,
                       native_backup_timer_active=True,
                       counts={t: before[t]['rows'] for t in ('messages', 'attachments', 'persons', 'person_briefs')})
        save()
        print(json.dumps(receipt))
    except Exception as error:
        receipt.update(status='rollback-started', failure_type=type(error).__name__, failure=str(error))
        save()
        try:
            command('systemctl', 'stop', *UNITS)
            restore_owned(CONFIG, original, updated, config_stat)
            restore_owned(MANIFEST, manifest_original, manifest_updated, manifest_stat)
            for path, (data, metadata) in saved.items():
                restore_owned(path, data, None, metadata)
            command('systemctl', 'daemon-reload')
            if LINK.resolve(strict=True) == OFFICIAL:
                replace_link(OFFICIAL, old)
            elif LINK.resolve(strict=True) != old:
                raise RuntimeError('Preserving an executable chosen by another operation')
            command('systemctl', 'start', *UNITS)
            wait_healthy()
            if timer_enabled:
                command('systemctl', 'enable', '--now', TIMER)
            receipt['status'] = 'rolled-back'
        except Exception as rollback_error:
            receipt.update(status='rollback-blocked', rollback_failure=str(rollback_error))
            raise
        finally:
            save()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-snapshot', required=True)
    args = parser.parse_args()
    try:
        run(args.backup_snapshot)
    except Exception:
        raise SystemExit('Official return failed; inspect its private checkpoint and preserved runtime') from None
