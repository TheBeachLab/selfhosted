"""Ownership, mount and availability guards for the NUC installation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import backup
import install


class InstallationGuards(unittest.TestCase):
    def test_existing_service_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'compose.yaml'
            path.write_text('existing service')
            with self.assertRaises(RuntimeError):
                install.guard_new_paths([path])
            self.assertEqual(path.read_text(), 'existing service')

    def test_broken_symlink_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'enabled'
            path.symlink_to(Path(folder) / 'missing')
            with self.assertRaises(RuntimeError):
                install.guard_new_paths([path])
            self.assertTrue(path.is_symlink())

    def test_concurrent_nginx_change_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'nginx.conf'
            path.write_bytes(b'another conversation changed this')
            with self.assertRaises(RuntimeError):
                install.replace_if_unchanged(path, install.digest(b'old config'), b'our config')
            self.assertEqual(path.read_bytes(), b'another conversation changed this')
            self.assertEqual(len(list(Path(folder).iterdir())), 1)


class BackupGuards(unittest.TestCase):
    def test_nas_outage_cannot_write_to_root_filesystem(self):
        for mount in ({'target': '/', 'fstype': 'ext4', 'source': '/dev/nvme0n1p2'},
                      {'target': '/mnt/nas-downloads', 'fstype': 'nfs4', 'source': 'wrong:/share'}):
            with self.assertRaises(RuntimeError):
                backup.guard_mount(mount)

    def test_stopped_container_is_preserved(self):
        with patch.object(backup, 'run', return_value=json.dumps({'Running': False})) as run:
            with self.assertRaises(RuntimeError):
                backup.capture()
            self.assertEqual(run.call_count, 1)

    def test_capture_failure_restarts_vault(self):
        events = []
        def run(args, env=None):
            events.append(args[:2])
            return json.dumps({'Running': True}) if args[1] == 'inspect' else ''
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(backup, 'STAGE', Path(folder) / 'payload'), \
                patch.object(backup, 'run', side_effect=run), \
                patch.object(backup.shutil, 'copytree', side_effect=OSError('copy failed')), \
                patch.object(backup, 'ready') as ready:
            with self.assertRaises(OSError):
                backup.capture()
            self.assertEqual(events, [['docker', 'inspect'], ['docker', 'stop'], ['docker', 'start']])
            ready.assert_called_once()


if __name__ == '__main__':
    unittest.main()
