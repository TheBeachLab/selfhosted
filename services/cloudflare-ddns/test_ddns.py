import copy
import unittest
from ddns import reconcile


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.record = {"id": "r", "name": "example.org", "type": "A",
                       "content": "8.8.8.8", "ttl": 1800, "proxied": False,
                       "comment": "keep", "tags": ["owner:nuc"]}
        self.target = [{"zone_id": "z", "record_id": "r", "name": "example.org"}]
        self.writes = []

    def request(self, path, method="GET", body=None):
        if method == "PATCH":
            self.writes.append(body)
            self.record.update(body)
        return copy.deepcopy(self.record)

    def test_changes_only_address_and_is_idempotent(self):
        reconcile(self.target, "1.1.1.1", self.request)
        reconcile(self.target, "1.1.1.1", self.request)
        self.assertEqual(self.writes, [{"content": "1.1.1.1"}])
        self.assertEqual(self.record["ttl"], 1800)
        self.assertEqual(self.record["comment"], "keep")

    def test_rejects_private_address_without_requests(self):
        with self.assertRaises(ValueError):
            reconcile(self.target, "192.168.1.2", lambda *a: self.fail("unexpected API"))

    def test_preflights_all_names_before_writes(self):
        targets = self.target + [{"zone_id": "z", "record_id": "other", "name": "wrong.org"}]
        with self.assertRaises(RuntimeError):
            reconcile(targets, "1.1.1.1", self.request)
        self.assertEqual(self.writes, [])

    def test_refuses_proxied_record(self):
        self.record["proxied"] = True
        with self.assertRaises(RuntimeError):
            reconcile(self.target, "1.1.1.1", self.request)
        self.assertEqual(self.writes, [])

    def test_detects_failed_write(self):
        def stale(path, method="GET", body=None):
            return copy.deepcopy(self.record)
        with self.assertRaises(RuntimeError):
            reconcile(self.target, "1.1.1.1", stale)


if __name__ == "__main__":
    unittest.main()
