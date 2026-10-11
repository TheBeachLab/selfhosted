"""Verify binary checksums and CLI failures on Python 3.10 and newer."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'services/openhab/selfhosted_hash.py'
SPEC = importlib.util.spec_from_file_location('selfhosted_hash', SOURCE)
file_hash = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(file_hash)


class FileHash(unittest.TestCase):
    def test_known_vectors_include_binary_data_across_chunk_boundary(self):
        # The final vector was independently checked with system shasum -a 256.
        vectors = [
            (b'', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
            (b'abc', 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'),
            (bytes(range(256)) * 5000 + b'last partial block',
             '6ea9b4a68b2684ad164431faf2055f68d02939d2206226dc41dbbafba610a040'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'payload.bin'
            for payload, expected in vectors:
                with self.subTest(size=len(payload)):
                    path.write_bytes(payload)
                    self.assertEqual(file_hash.file_sha256(path), expected)
                    self.assertEqual(file_hash.file_sha256(str(path)), expected)

    def test_cli_handles_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'backup with spaces.zip'
            path.write_bytes(b'abc')
            result = subprocess.run([sys.executable, '-B', str(SOURCE), str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout,
                             'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
                             + '  ' + str(path) + '\n')

    def test_missing_file_returns_error_without_a_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / 'missing.zip'
            with self.assertRaises(FileNotFoundError):
                file_hash.file_sha256(missing)
            result = subprocess.run([sys.executable, '-B', str(SOURCE), str(missing)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertIn('selfhosted_hash:', result.stderr)


if __name__ == '__main__':
    unittest.main()
