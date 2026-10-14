"""Content preservation and false-positive guards using synthetic credentials."""
import copy
import tempfile
from pathlib import Path
import unittest

from deduplicate import GuardError, covers, execute, groups, merge


def item(identity, name="example.test", uri="https://example.test", **changes):
    result = {"id": identity, "name": name, "type": 1, "folderId": None,
              "organizationId": None, "collectionIds": [], "favorite": False,
              "reprompt": 0, "fields": [], "notes": None, "passwordHistory": None,
              "login": {"username": "synthetic-user", "password": "synthetic-password",
                        "uris": [{"uri": uri, "match": None}], "totp": None,
                        "fido2Credentials": []}}
    result.update(changes)
    return result


class Preservation(unittest.TestCase):
    def test_same_password_on_different_services_is_not_a_duplicate(self):
        a = item("a")
        b = item("b", name="other.test", uri="https://other.test")
        self.assertEqual(groups([a, b], set()), [])

    def test_username_and_password_must_both_match(self):
        a, b, c = item("a"), item("b"), item("c")
        b["login"]["username"] = "another-user"
        c["login"]["password"] = "different-password"
        self.assertEqual(groups([a, b, c], set()), [])

    def test_wifi_is_excluded_even_if_it_matches_a_login(self):
        self.assertEqual(groups([item("a"), item("b", folderId="wifi")], {"wifi"}), [])

    def test_title_as_uri_matches_and_all_uri_variants_are_retained(self):
        a, b = item("a", uri="https://example.test/"), item("b", uri="http://example.test")
        self.assertEqual(len(groups([a, b], set())), 1)
        _, merged, _ = merge([a, b], {"a"})
        self.assertTrue(covers(merged, a) and covers(merged, b))
        self.assertEqual(len(merged["login"]["uris"]), 2)

    def test_passkey_item_id_and_complete_private_credential_are_preserved(self):
        a, b = item("original"), item("phone")
        credential = {"credentialId": "synthetic-id", "keyValue": "synthetic-private-key",
                      "rpId": "example.test", "counter": "0"}
        b["login"]["fido2Credentials"] = [credential]
        keep, merged, extras = merge([a, b], {"original"})
        self.assertEqual(keep["id"], "phone")
        self.assertEqual(merged["login"]["fido2Credentials"], [credential])
        self.assertEqual([e["id"] for e in extras], ["original"])

    def test_two_passkey_items_are_never_collapsed(self):
        a, b = item("a"), item("b")
        for i in (a, b):
            i["login"]["fido2Credentials"] = [{"credentialId": i["id"]}]
        with self.assertRaises(GuardError):
            merge([a, b], set())

    def test_notes_fields_names_history_and_stricter_settings_survive(self):
        a, b = item("a", notes="original note"), item("b", name="Alternate title", notes="phone note")
        a["fields"] = [{"name": "secret", "value": "synthetic", "type": 1}]
        a["passwordHistory"] = [{"password": "synthetic-old", "lastUsedDate": "2020-01-01"}]
        a["favorite"], a["reprompt"] = True, 1
        originals = copy.deepcopy([a, b])
        _, merged, _ = merge([a, b], {"a"})
        self.assertTrue(all(covers(merged, source) for source in originals))
        self.assertEqual([a, b], originals)
        damaged = copy.deepcopy(merged)
        damaged["fields"] = []
        self.assertFalse(covers(damaged, a))

    def test_conflicting_totp_folder_unknown_data_or_attachments_are_not_discarded(self):
        for change in ("totp", "folder", "unknown", "attachment"):
            a, b = item("a"), item("b")
            if change == "totp":
                b["login"]["totp"] = "synthetic-otp-seed"
            elif change == "folder":
                b["folderId"] = "another-folder"
            elif change == "unknown":
                b["newUnsupportedFeature"] = "must-survive"
            else:
                b["attachments"] = [{"id": "synthetic-attachment"}]
            with self.subTest(change=change), self.assertRaises(GuardError):
                merge([a, b], set())


class MemoryCli:
    def __init__(self, corrupt_on_sync=False):
        self.items = {i["id"]: i for i in [item("a"), item("b", name="Alias") ]}
        self.corrupt_on_sync = corrupt_on_sync
        self.syncs = 0
        self.deleted = []

    def request(self, method, path, value=None):
        if path == "/status":
            return {"userEmail": "hola@beachlab.org", "serverUrl": "https://passwords.beachlab.org"}
        if path == "/sync":
            self.syncs += 1
            if self.corrupt_on_sync and self.syncs == 2:
                self.items["a"]["login"]["password"] = "unexpected-server-change"
            return None
        if path == "/list/object/folders":
            return []
        if path == "/list/object/items":
            return copy.deepcopy([i for i in self.items.values() if not i.get("deletedDate")])
        if path == "/list/object/items?trash=true":
            return copy.deepcopy([i for i in self.items.values() if i.get("deletedDate")])
        identity = path.rsplit("/", 1)[-1]
        if method == "PUT":
            self.items[identity] = copy.deepcopy(value)
        if method == "DELETE":
            self.items[identity]["deletedDate"] = "synthetic-deletion-date"
            self.deleted.append(identity)
            return None
        return copy.deepcopy(self.items[identity])


class BatchWorkflow(unittest.TestCase):
    def test_server_readback_failure_stops_before_any_soft_deletion(self):
        cli = MemoryCli(corrupt_on_sync=True)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(GuardError):
                execute(cli, set(), Path(folder) / "receipt.json", apply=True)
        self.assertEqual(cli.deleted, [])

    def test_success_keeps_content_and_receipt_contains_only_ids_and_counts(self):
        cli = MemoryCli()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "receipt.json"
            receipt = execute(cli, set(), path, apply=True)
            serialized = path.read_text()
        self.assertEqual(receipt["after"], 1)
        self.assertEqual(receipt["trashed"], 1)
        self.assertTrue(receipt["verified"])
        self.assertNotIn("synthetic-password", serialized)
        self.assertNotIn("synthetic-user", serialized)


if __name__ == "__main__":
    unittest.main()
