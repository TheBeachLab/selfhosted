#!/usr/bin/env python3
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("backports", Path(__file__).resolve().parents[1] / "services/node-security-dependencies.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def archive(name="zod", target="4.6.6", dependencies=None, unsafe=False):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as tar:
        data = json.dumps({"name": name, "version": target, "dependencies": dependencies or {}}).encode()
        member = tarfile.TarInfo("../escape" if unsafe else "package/package.json")
        member.size = len(data)
        tar.addfile(member, io.BytesIO(data))
    return stream.getvalue()


class BackportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.package = self.root / "node_modules/zod"
        self.package.mkdir(parents=True)
        (self.root / "package.json").write_text(json.dumps({"name": "fixture", "version": "1.0.0", "dependencies": {"zod": "4.6.5"}}))
        (self.package / "package.json").write_text(json.dumps({"name": "zod", "version": "4.6.5"}))

    def cache(self, raw):
        cache = self.root / "cache"
        cache.mkdir()
        (cache / "zod-4.6.6.tgz").write_bytes(raw)
        return cache

    def policy(self, raw):
        old = m.PATCHES[("zod", 4)]
        self.addCleanup(lambda: m.PATCHES.__setitem__(("zod", 4), old))
        m.PATCHES[("zod", 4)] = ("4.6.6", base64.b64encode(hashlib.sha512(raw).digest()).decode())

    def test_replaces_exact_pin_and_is_idempotent(self):
        raw = archive()
        self.policy(raw)
        m.apply(self.root, self.cache(raw))
        self.assertEqual(json.loads((self.root / "package.json").read_text())["dependencies"]["zod"], "4.6.6")
        self.assertEqual(m.pending(self.root), [])
        m.apply(self.root, None)

    def test_interrupted_swap_cannot_be_reported_safe(self):
        self.package.rename(self.package.with_name(".zod.security-old"))
        for operation in (lambda: m.pending(self.root), lambda: m.apply(self.root, None)):
            with self.assertRaisesRegex(ValueError, "Unfinished"):
                operation()
        self.assertFalse(self.package.exists())

    def test_interrupted_manifest_transaction_cannot_be_reported_safe(self):
        (self.root / ".security-backport-in-progress").write_text("interrupted")
        with self.assertRaisesRegex(ValueError, "Interrupted"):
            m.pending(self.root)

    def test_safe_newer_version_is_not_downgraded(self):
        (self.package / "package.json").write_text('{"name":"zod","version":"4.7.0"}')
        self.assertEqual(m.pending(self.root), [])

    def test_different_major_is_not_replaced(self):
        (self.package / "package.json").write_text('{"name":"zod","version":"5.0.0"}')
        self.assertEqual(m.pending(self.root), [])

    def test_integrity_failure_preserves_tree(self):
        with self.assertRaisesRegex(ValueError, "integrity"):
            m.apply(self.root, self.cache(b"wrong"))
        self.assertEqual(json.loads((self.package / "package.json").read_text())["version"], "4.6.5")

    def test_dependency_contract_change_is_rejected(self):
        raw = archive(dependencies={"new-package": "1.0.0"})
        self.policy(raw)
        with self.assertRaisesRegex(ValueError, "contract"):
            m.apply(self.root, self.cache(raw))
        self.assertEqual(json.loads((self.package / "package.json").read_text())["version"], "4.6.5")

    def test_archive_traversal_is_rejected(self):
        raw = archive(unsafe=True)
        self.policy(raw)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            m.apply(self.root, self.cache(raw))
        self.assertFalse((self.root / "escape").exists())


if __name__ == "__main__":
    unittest.main()
