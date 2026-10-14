import copy
import tempfile
from pathlib import Path
import unittest

from deduplicate import GuardError
from review_duplicates import candidates, execute
from test_deduplicate import MemoryCli, item


class ReviewCli(MemoryCli):
    def request(self, method, path, value=None):
        if method == "POST" and path == "/object/folder":
            return {"id": "review-folder", "name": "Duplicados"}
        return super().request(method, path, value)


class CandidateReview(unittest.TestCase):
    def test_different_usernames_match_when_site_and_password_match(self):
        a, b = item("a"), item("b", uri="http://www.example.test/login?next=/")
        b["login"]["username"] = "Imported from synthetic source"
        self.assertEqual(len(candidates([a, b], set())), 1)

    def test_different_passwords_or_sites_do_not_match(self):
        a, b, c = item("a"), item("b"), item("c", name="other.test", uri="https://other.test")
        b["login"]["password"] = "another-synthetic-password"
        self.assertEqual(candidates([a, b, c], set()), [])

    def test_wifi_and_passkey_only_items_stay_outside_review(self):
        a, b, c = item("a"), item("b", folderId="wifi"), item("c")
        c["login"]["password"] = None
        c["login"]["fido2Credentials"] = [{"credentialId": "synthetic"}]
        self.assertEqual(candidates([a, b, c], {"wifi"}), [])

    def test_all_candidates_are_moved_without_changing_usernames_or_passkeys(self):
        cli = ReviewCli()
        cli.items["b"]["login"]["username"] = "Synthetic import origin"
        cli.items["b"]["login"]["fido2Credentials"] = [{"keyValue": "synthetic-private-key"}]
        original = copy.deepcopy(cli.items)
        with tempfile.TemporaryDirectory() as folder:
            receipt = execute(cli, Path(folder) / "receipt.json", apply=True)
        self.assertTrue(receipt["verified"])
        self.assertEqual(receipt["items"], 2)
        self.assertEqual(cli.deleted, [])
        for identity in original:
            self.assertEqual(cli.items[identity]["folderId"], "review-folder")
            self.assertEqual(cli.items[identity]["login"], original[identity]["login"])

    def test_corrupted_edit_response_stops_and_does_not_delete(self):
        class Corrupt(ReviewCli):
            def request(self, method, path, value=None):
                result = super().request(method, path, value)
                if method == "PUT":
                    result["login"]["fido2Credentials"] = [{"keyValue": "changed"}]
                return result
        cli = Corrupt()
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(GuardError):
            execute(cli, Path(folder) / "receipt.json", apply=True)
        self.assertEqual(cli.deleted, [])


if __name__ == "__main__":
    unittest.main()
