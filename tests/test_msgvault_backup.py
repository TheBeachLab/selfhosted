"""Guards must fail before writing to a fallback filesystem or pruning another repo."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

    def test_full_capture_requires_both_reserves(self):
        estimate = 4 * 1024**3
        for local, nas in ((estimate + backup.RESERVE - 1, 100 * 1024**3),
                           (100 * 1024**3, estimate + backup.RESERVE - 1)):
            with self.assertRaises(RuntimeError):
                backup.guard_capacity(estimate, local, nas)

    def test_unverified_capture_is_never_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary) / 'payload'
            stage.mkdir()
            archive = stage / 'archive.db'
            archive.write_bytes(b'only copy of captured data')
            with patch.object(backup, 'STAGE', stage), self.assertRaises(RuntimeError):
                backup.cleanup_uploaded({'phase': 'captured'})
            self.assertEqual(archive.read_bytes(), b'only copy of captured data')


if __name__ == '__main__':
    unittest.main()
