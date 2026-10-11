"""Guards must fail before writing to a fallback filesystem or pruning another repo."""
import importlib.util
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'services/msgvault/backup.py'
SPEC = importlib.util.spec_from_file_location('msgvault_backup', SOURCE)
backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup)


class BackupGuards(unittest.TestCase):
    def test_mount_loss_and_wrong_share_fail_closed(self):
        for mount in ({'target': '/', 'fstype': 'ext4', 'source': '/dev/nvme0n1p2'},
                      {'target': str(backup.NAS), 'fstype': 'nfs4', 'source': 'other:/volume1/synology'}):
            with self.assertRaises(RuntimeError):
                backup.guard_mount(mount)
        backup.guard_mount({'target': str(backup.NAS), 'fstype': 'nfs4',
                            'source': '192.168.1.100:/volume1/synology'})

    def test_repository_swap_blocks_retention(self):
        for expected, actual in (('', 'new-repo'), ('original-repo', 'other-repo')):
            with self.assertRaises(RuntimeError):
                backup.guard_identity(expected, actual)

    def test_redirected_backup_path_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            other = root / 'other-repository'
            other.mkdir()
            (other / 'existing-data').write_bytes(b'preserve')
            redirected = root / 'backup'
            redirected.symlink_to(other, target_is_directory=True)
            with self.assertRaises(RuntimeError):
                backup.guard_paths((redirected / 'new-repository',))
            self.assertEqual((other / 'existing-data').read_bytes(), b'preserve')
            self.assertFalse((other / 'new-repository').exists())

    def test_nas_capacity_covers_temporary_and_encrypted_copies(self):
        estimate = 4 * 1024**3
        for local, nas in ((backup.RESERVE - 1, 100 * 1024**3),
                           (100 * 1024**3, 2 * estimate + backup.RESERVE - 1)):
            with self.assertRaises(RuntimeError):
                backup.guard_capacity(estimate, local, nas)
        backup.guard_capacity(estimate, backup.RESERVE, 2 * estimate + backup.RESERVE)

    def test_unverified_capture_is_never_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary) / 'payload'
            stage.mkdir()
            archive = stage / 'archive.db'
            archive.write_bytes(b'only copy of captured data')
            with patch.object(backup, 'STAGE', stage), self.assertRaises(RuntimeError):
                backup.cleanup_uploaded({'phase': 'captured'})
            self.assertEqual(archive.read_bytes(), b'only copy of captured data')

    def test_failed_or_different_restic_recovery_preserves_gc_original(self):
        data = b'archived database bytes'
        entry = {'name': 'msgvault.db.gc-backup-20261011-114000',
                 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        for recovered, status in ((data, 1), (b'different database', 0)):
            process = MagicMock()
            process.stdout = io.BytesIO(recovered)
            process.stderr = io.BytesIO(b'recovery failed')
            process.wait.return_value = status
            process.__enter__.return_value = process
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                source = root / entry['name']
                source.write_bytes(data)
                entry['source_identity'] = backup.gc_identity(source)
                pending = {'gc_backups': [entry], 'gc_restic_snapshot': 'recovery-id'}
                with patch.object(backup, 'STATE', root), patch.object(backup, 'HOME_DIR', root), \
                        patch.object(backup.subprocess, 'Popen', return_value=process), \
                        self.assertRaises(RuntimeError):
                    backup.cleanup_gc_backups(pending, {})
                self.assertEqual(source.read_bytes(), data)

    def test_gc_copy_replaced_after_capture_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            name = 'msgvault.db.gc-backup-20261011-114000'
            source = root / name
            source.write_bytes(b'original')
            entry = {'name': name, 'source_identity': backup.gc_identity(source),
                     'size_bytes': source.stat().st_size, 'sha256': backup.file_hash(source)}
            source.unlink()
            source.write_bytes(b'replacement belongs to another operation')
            with patch.object(backup, 'HOME_DIR', root), \
                    patch.object(backup, 'verify_gc_restore'), self.assertRaises(RuntimeError):
                backup.cleanup_gc_backups({'gc_backups': [entry], 'gc_restic_snapshot': 'id'}, {})
            self.assertEqual(source.read_bytes(), b'replacement belongs to another operation')

    def test_verified_gc_cleanup_leaves_live_database_and_other_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            live = root / 'msgvault.db'
            live.write_bytes(b'live database')
            other = root / 'unrelated-copy.db'
            other.write_bytes(b'preserve')
            stage = root / 'nas-stage'
            stage.mkdir()
            source = root / 'msgvault.db.gc-backup-20261011-114000'
            source.write_bytes(b'recovery database')
            with patch.object(backup, 'HOME_DIR', root), patch.object(backup, 'STAGE', stage):
                entries = backup.capture_gc_backups()
                with patch.object(backup, 'verify_gc_restore') as verify:
                    result = backup.cleanup_gc_backups({'gc_backups': entries,
                                                       'gc_restic_snapshot': 'id'}, {})
                verify.assert_called_once_with('id', entries[0], {})
            self.assertFalse(source.exists())
            self.assertEqual(live.read_bytes(), b'live database')
            self.assertEqual(other.read_bytes(), b'preserve')
            self.assertEqual(result[0]['cleanup'], 'removed')
            self.assertTrue(result[0]['restore_sha256_matches'])

    def test_gc_symlink_is_preserved_and_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = root / 'other-database'
            original.write_bytes(b'preserve')
            source = root / 'msgvault.db.gc-backup-20261011-114000'
            source.symlink_to(original)
            with patch.object(backup, 'HOME_DIR', root), self.assertRaises(RuntimeError):
                backup.capture_gc_backups()
            self.assertTrue(source.is_symlink())
            self.assertEqual(original.read_bytes(), b'preserve')

    def test_mount_loss_during_uploaded_cleanup_preserves_both_copies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            stage = root / 'nas-stage'
            stage.mkdir()
            staged = stage / 'archive'
            staged.write_bytes(b'captured bytes')
            original = root / 'msgvault.db.gc-backup-20261011-114000'
            original.write_bytes(b'recovery bytes')
            with patch.object(backup, 'STAGE', stage), \
                    patch.object(backup, 'check_mount', side_effect=RuntimeError('NAS missing')), \
                    patch.object(backup, 'cleanup_gc_backups') as cleanup, \
                    self.assertRaises(RuntimeError):
                backup.cleanup_uploaded({'phase': 'uploaded'}, {})
            cleanup.assert_not_called()
            self.assertEqual(staged.read_bytes(), b'captured bytes')
            self.assertEqual(original.read_bytes(), b'recovery bytes')


if __name__ == '__main__':
    unittest.main()
