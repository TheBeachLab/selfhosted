"""A return to official must preserve data and refuse an unsafe rollback."""
import datetime
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'services/msgvault/return-to-official.py'
SPEC = importlib.util.spec_from_file_location('official_return', SOURCE)
official = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(official)


class OfficialReturnGuards(unittest.TestCase):
    def test_only_people_automation_changes_and_vectors_keep_their_exact_settings(self):
        original = (b'[server]\napi_key = "synthetic-owner"\n\n'
                    b'[people.sweep]\n  enabled = true # keep the comment\nprovider = "openai"\n'
                    b'  [people.sweep.brief]\n    enabled = true\nmin_interval = "168h"\n'
                    b'[vector]\nenabled = true\n[vector.embeddings]\nmax_input_chars = 2000\n'
                    b'[people.identity_scoring]\nenabled = true\ncredential_env = "TYPESAFE_API_KEY"\n')
        actual = official.disable_people(original)
        expected = original.replace(b'  enabled = true #', b'  enabled = false #').replace(
            b'    enabled = true\n', b'    enabled = false\n')
        self.assertEqual(expected, actual)
        self.assertEqual(actual, official.disable_people(actual))

    def test_ambiguous_settings_are_rejected_without_guessing(self):
        good = b'[people.sweep]\nenabled = true\n[people.sweep.brief]\nenabled = true\n'
        for bad in (good + b'[people.sweep]\nenabled = true\n',
                    good.replace(b'enabled = true\n', b'enabled = true\nenabled = false\n', 1),
                    good.replace(b'[people.sweep.brief]', b'[other]'),
                    good.replace(b'enabled = true', b'enabled = "true"', 1)):
            with self.subTest(bad=bad), self.assertRaises(RuntimeError):
                official.disable_people(bad)

    def test_only_the_exact_recent_completed_and_fully_restored_backup_is_accepted(self):
        now = datetime.datetime(2026, 10, 12, 20, tzinfo=datetime.timezone.utc)
        last = {'restic_snapshot': 'abcdef01', 'phase': 'uploaded',
                'completed_at': (now - datetime.timedelta(minutes=10)).isoformat()}
        proof = {'snapshot': 'abcdef01', 'official_backup_verify': 'all-packs-passed',
                 'official_restore_integrity': 'passed', 'temporary_dir_removed': True,
                 'verified_at': (now - datetime.timedelta(minutes=5)).isoformat()}
        official.require_backup('abcdef01', last, proof, now)
        cases = [(dict(last, phase='captured'), proof),
                 (dict(last, restic_snapshot='12345678'), proof),
                 (dict(last, completed_at=(now - datetime.timedelta(hours=3)).isoformat()), proof),
                 (last, dict(proof, official_restore_integrity='failed')),
                 (last, dict(proof, official_backup_verify='quick-only')),
                 (last, dict(proof, temporary_dir_removed=False)),
                 (last, dict(proof, snapshot='12345678'))]
        for previous, verified in cases:
            with self.subTest(previous=previous, verified=verified), self.assertRaises(RuntimeError):
                official.require_backup('abcdef01', previous, verified, now)

    def test_rollback_preserves_concurrent_file_changes_and_redirects(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.toml'
            config.write_bytes(b'other operation');metadata = config.stat()
            with self.assertRaises(RuntimeError):
                official.restore_owned(config, b'original', b'our update', metadata)
            self.assertEqual(b'other operation', config.read_bytes())
            link = root / 'link';link.symlink_to(config)
            with self.assertRaises(RuntimeError):
                official.restore_owned(link, b'original', b'other operation', metadata)
            self.assertTrue(link.is_symlink())
            config.write_bytes(b'our update')
            official.restore_owned(config, b'original', b'our update', metadata)
            self.assertEqual(b'original', config.read_bytes())

    def test_row_changes_and_deleted_saved_summaries_change_the_preservation_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = sqlite3.connect(str(root / 'msgvault.db'))
            db.executescript('CREATE TABLE messages(id INTEGER PRIMARY KEY, body BLOB);'
                             'CREATE TABLE person_briefs(id INTEGER PRIMARY KEY, text TEXT);'
                             "INSERT INTO messages VALUES(1,X'010203');"
                             "INSERT INTO person_briefs VALUES(1,'saved summary');")
            db.commit()
            with patch.object(official, 'DATA', root), patch.object(
                    official, 'PROTECTED_TABLES', ('messages', 'person_briefs')):
                before = official.protected_state()
                self.assertEqual(before, official.protected_state())
                db.execute("UPDATE person_briefs SET text='different summary' WHERE id=1");db.commit()
                self.assertNotEqual(before, official.protected_state())
                db.execute('DELETE FROM person_briefs');db.commit()
                self.assertEqual(0, official.protected_state()['person_briefs']['rows'])
            db.close()

    def test_identity_constants_pin_both_audited_executables(self):
        self.assertEqual(64, len(official.OFFICIAL_SHA))
        self.assertEqual(64, len(official.PATCHED_SHA))
        self.assertNotEqual(official.OFFICIAL_SHA, official.PATCHED_SHA)

    def test_failed_official_start_restores_the_previous_runtime_without_restoring_old_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, state, source = root / 'data', root / 'state', root / 'source'
            for path in (data, state, source):
                path.mkdir()
            config = data / 'config.toml'
            original = b'[people.sweep]\nenabled=true\n[people.sweep.brief]\nenabled=true\n[vector]\nenabled=true\n'
            config.write_bytes(original)
            old, stock, link = root / 'old', root / 'stock', root / 'msgvault'
            old.write_bytes(b'previous binary');stock.write_bytes(b'official binary');link.symlink_to(old)
            manifest = source / 'runtime-build.json'
            manifest.write_text(__import__('json').dumps({'binary_sha256': official.digest(old)}))
            manifest_before = manifest.read_bytes()
            retired = root / 'extension.conf';retired.write_bytes(b'owned extension')
            (source / 'extension.conf').write_bytes(retired.read_bytes())
            now = datetime.datetime.now(datetime.timezone.utc)
            last = {'restic_snapshot': 'abcdef01', 'phase': 'uploaded',
                    'completed_at': (now - datetime.timedelta(minutes=10)).isoformat()}
            proof = {'snapshot': 'abcdef01', 'official_backup_verify': 'all-packs-passed',
                     'official_restore_integrity': 'passed', 'temporary_dir_removed': True,
                     'verified_at': (now - datetime.timedelta(minutes=5)).isoformat()}
            (state / 'last-success.json').write_text(__import__('json').dumps(last))
            (state / 'official-pre-restore-proof-abcdef01.json').write_text(__import__('json').dumps(proof))
            db = sqlite3.connect(str(data / 'msgvault.db'))
            db.executescript('CREATE TABLE messages(id INTEGER PRIMARY KEY, body BLOB);'
                             'CREATE TABLE person_briefs(id INTEGER PRIMARY KEY, text TEXT);'
                             "INSERT INTO messages VALUES(1,X'010203');"
                             "INSERT INTO person_briefs VALUES(1,'saved summary');")
            db.commit();db.close()
            mapping = {'DATA': data, 'CONFIG': config, 'STATE': state, 'SOURCE': source,
                       'LINK': link, 'OFFICIAL': stock, 'OFFICIAL_SHA': official.digest(stock),
                       'PATCHED_SHA': official.digest(old), 'MANIFEST': manifest,
                       'RETIRE': {retired: 'extension.conf'},
                       'PROTECTED_TABLES': ('messages', 'person_briefs')}
            with patch.multiple(official, **mapping), patch.object(official.os, 'geteuid', return_value=0), \
                    patch.object(official, 'command') as command, \
                    patch.object(official.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                    patch.object(official, 'credentials', return_value={'credential': 'same digest'}), \
                    patch.object(official, 'profiles', return_value={'profile': 'same digest'}), \
                    patch.object(official, 'wait_healthy', side_effect=[RuntimeError('failed startup'), None]):
                before = official.protected_state()
                with self.assertRaises(RuntimeError):
                    official.run('abcdef01')
                self.assertEqual(before, official.protected_state())
                self.assertEqual(old, link.resolve())
                self.assertEqual(original, config.read_bytes())
                self.assertEqual(manifest_before, manifest.read_bytes())
                self.assertEqual(b'owned extension', retired.read_bytes())
                receipt = __import__('json').loads(next(state.glob('official-return-*/activation.json')).read_text())
                self.assertEqual('rolled-back', receipt['status'])
                self.assertIn(('systemctl', 'enable', '--now', official.TIMER), [x.args for x in command.call_args_list])
                self.assertFalse(any('msgvault-backup.timer' in x.args and x.args[1] in ('stop', 'disable')
                                     for x in command.call_args_list))


if __name__ == '__main__':
    unittest.main()
