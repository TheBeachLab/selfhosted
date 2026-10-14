import copy
import tempfile
import sqlite3
from pathlib import Path
import unittest

from deduplicate import GuardError
from review_duplicates import candidates, execute
from review_folder_links import apply_links, revision
from test_deduplicate import MemoryCli, item


class ReviewCli(MemoryCli):
    def __init__(self):
        super().__init__()
        for i in self.items.values():
            i["revisionDate"] = "2026-10-14T00:00:00.000Z"

    def request(self, method, path, value=None):
        if path == '/sync?force=true':
            path = '/sync'
        if method == "POST" and path == "/object/folder":
            return {"id": "review-folder", "name": "Duplicados"}
        return super().request(method, path, value)


def mover(cli):
    def move(plan):
        result = []
        for i in plan["items"]:
            cli.items[i["id"]]["folderId"] = plan["folder_id"]
            result.append({"id":i["id"], "previous_folder":i["previous_folder"]})
        return result
    return move


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
            receipt = execute(cli, Path(folder) / "receipt.json", apply=True, move_metadata=mover(cli))
        self.assertTrue(receipt["verified"])
        self.assertEqual(receipt["items"], 2)
        self.assertEqual(cli.deleted, [])
        for identity in original:
            self.assertEqual(cli.items[identity]["folderId"], "review-folder")
            self.assertEqual(cli.items[identity]["login"], original[identity]["login"])

    def test_corrupted_edit_response_stops_and_does_not_delete(self):
        cli = ReviewCli()
        def corrupt(plan):
            result = mover(cli)(plan)
            cli.items['a']['login']['fido2Credentials'] = [{"keyValue":"changed"}]
            return result
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(GuardError):
            execute(cli, Path(folder) / "receipt.json", apply=True, move_metadata=corrupt)
        self.assertEqual(cli.deleted, [])


class EncryptedFolderLinks(unittest.TestCase):
    def test_chrono_nanoseconds_match_javascript_millisecond_revision(self):
        self.assertEqual(revision('2026-10-14 16:22:42.832440091'), revision('2026-10-14T16:22:42.832Z'))

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
        CREATE TABLE users(uuid TEXT,email TEXT,updated_at TEXT);
        CREATE TABLE folders(uuid TEXT,user_uuid TEXT);
        CREATE TABLE ciphers(uuid TEXT,user_uuid TEXT,organization_uuid TEXT,
            deleted_at TEXT,updated_at TEXT,data TEXT,key TEXT);
        CREATE TABLE folders_ciphers(cipher_uuid TEXT,folder_uuid TEXT);
        INSERT INTO users VALUES('owner','hola@beachlab.org','2026-10-14 00:00:00');
        INSERT INTO folders VALUES('review','owner');
        INSERT INTO ciphers VALUES('a','owner',NULL,NULL,'2026-10-14 00:00:00.000',
            'synthetic encrypted credentials','synthetic encrypted key');
        """)
        self.plan = {"account":"hola@beachlab.org", "folder_id":"review", "items":[
            {"id":"a", "previous_folder":None, "revisionDate":"2026-10-14T00:00:00.000Z"}]}

    def tearDown(self):
        self.db.close()

    def test_only_links_and_modification_timestamp_change(self):
        before = self.db.execute('SELECT data,key FROM ciphers').fetchone()
        apply_links(self.db, self.plan)
        after = self.db.execute('SELECT data,key FROM ciphers').fetchone()
        self.assertEqual(tuple(before), tuple(after))
        self.assertEqual(tuple(self.db.execute('SELECT * FROM folders_ciphers').fetchone()), ('a','review'))

    def test_concurrent_edit_or_wrong_owner_refuses_the_move(self):
        for cause in ['revision', 'owner']:
            plan = copy.deepcopy(self.plan)
            if cause == 'revision':
                plan['items'][0]['revisionDate'] = '2026-10-13T00:00:00.000Z'
            else:
                plan['account'] = 'someone-else@example.invalid'
            with self.subTest(cause=cause), self.assertRaises(RuntimeError):
                apply_links(self.db, plan)
            self.assertEqual(self.db.execute('SELECT count(*) FROM folders_ciphers').fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
