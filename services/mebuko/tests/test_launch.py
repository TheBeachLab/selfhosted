import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location("mebuko_server", Path(__file__).parents[1] / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = 1791993600
        self.sent = []
        self.app = server.LaunchList(Path(self.temp.name) / "list.sqlite3", "s" * 64, "https://mebuko.de", sender=lambda *args: self.sent.append(args), clock=lambda: self.now)

    def tearDown(self):
        self.temp.cleanup()

    def subscribe(self, email="example@example.com", consent=True, ip="192.0.2.1"):
        return self.app.subscribe(email, "es", consent, "", ip)

    def test_no_subscription_without_explicit_consent(self):
        for consent in (False, None, "true", 1):
            with self.assertRaises(server.RequestError):
                self.subscribe(consent=consent)
        self.assertEqual(self.sent, [])

    def test_mail_is_pending_until_explicit_confirmation(self):
        self.subscribe()
        with self.app.connect() as db:
            row = db.execute("SELECT * FROM subscribers").fetchone()
            self.assertIsNone(row["confirmed_at"])
            self.assertEqual(row["consent_version"], server.CONSENT_VERSION)
        token = self.sent[0][1]
        self.assertEqual(self.app.confirm(token)["code"], "confirmed")
        self.now += 100
        self.app.confirm(token)
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT confirmed_at FROM subscribers").fetchone()[0], self.now - 100)

    def test_mail_failure_never_records_a_subscription(self):
        def fail(*_):
            raise OSError("synthetic provider failure")
        self.app.sender = fail
        with self.assertRaises(OSError):
            self.subscribe()
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM subscribers").fetchone()[0], 0)

    def test_links_are_purpose_bound_and_tamper_evident(self):
        self.subscribe()
        _, confirm, unsubscribe = self.sent[0]
        with self.assertRaises(server.RequestError):
            self.app.confirm(unsubscribe)
        with self.assertRaises(server.RequestError):
            self.app.unsubscribe(confirm)
        with self.assertRaises(server.RequestError):
            self.app.confirm(confirm[:-1] + ("0" if confirm[-1] != "0" else "1"))

    def test_expired_confirmations_are_refused_and_pruned(self):
        self.subscribe()
        self.now += 48 * 3600 + 1
        with self.assertRaises(server.RequestError) as error:
            self.app.confirm(self.sent[0][1])
        self.assertEqual(error.exception.code, "expired_link")
        with self.app.connect() as db:
            self.app.prune(db, self.now)
            self.assertEqual(db.execute("SELECT count(*) FROM subscribers").fetchone()[0], 0)

    def test_unsubscribe_deletes_the_address(self):
        self.subscribe()
        self.app.confirm(self.sent[0][1])
        self.assertEqual(self.app.unsubscribe(self.sent[0][2])["code"], "unsubscribed")
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM subscribers").fetchone()[0], 0)

    def test_repeats_are_rate_limited_without_a_second_email(self):
        self.subscribe()
        with self.assertRaises(server.RequestError) as error:
            self.subscribe()
        self.assertEqual(error.exception.status, 429)
        self.assertEqual(len(self.sent), 1)
        with self.app.connect() as db:
            self.assertNotIn("192.0.2.1", str([dict(r) for r in db.execute("SELECT * FROM rate_limits")]))
            self.assertNotIn("example@example.com", str([dict(r) for r in db.execute("SELECT * FROM rate_limits")]))

    def test_confirmed_address_is_not_mailed_again(self):
        self.subscribe()
        self.app.confirm(self.sent[0][1])
        self.now += 3601
        self.subscribe()
        self.assertEqual(len(self.sent), 1)

    def test_honeypot_does_not_send_or_store_mail(self):
        self.app.subscribe("example@example.com", "en", True, "bot.example", "192.0.2.1")
        self.assertEqual(self.sent, [])

    def test_launch_list_is_closed_and_removed_at_retention_end(self):
        self.subscribe()
        self.app.confirm(self.sent[0][1])
        self.now = server.RETENTION_END
        with self.assertRaises(server.RequestError):
            self.subscribe("other@example.com")
        with self.app.connect() as db:
            self.app.prune(db, self.now)
            self.assertEqual(db.execute("SELECT count(*) FROM subscribers").fetchone()[0], 0)

    def test_header_injection_and_invalid_addresses_are_rejected(self):
        for value in ("a@example.com\r\nBcc: victim@example.com", "a..b@example.com", ".a@example.com", "a@-example.com", "a@example..com", "a@localhost", None):
            with self.assertRaises(server.RequestError):
                server.normalize_email(value)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sent = []
        self.app = server.LaunchList(Path(self.temp.name) / "list.sqlite3", "s" * 64, "https://mebuko.de", sender=lambda *args: self.sent.append(args))
        self.http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.http.launch_list = self.app
        self.base = "http://127.0.0.1:" + str(self.http.server_address[1])
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post(self, path, data, origin="https://mebuko.de"):
        req = Request(self.base + path, data=json.dumps(data).encode(), headers={"Content-Type": "application/json", "Origin": origin})
        try:
            response = urlopen(req)
        except HTTPError as e:
            response = e
        with response:
            return response.status, json.loads(response.read())

    def test_cross_origin_requests_cannot_send_mail(self):
        status, _ = self.post("/api/subscribe", {"email": "example@example.com", "consent": True}, "https://attacker.example")
        self.assertEqual(status, 403)
        self.assertEqual(self.sent, [])

    def test_full_http_double_opt_in_and_withdrawal(self):
        status, _ = self.post("/api/subscribe", {"email": "example@example.com", "language": "en", "consent": True})
        self.assertEqual(status, 200)
        _, confirm, unsubscribe = self.sent[0]
        # A scanner fetching the confirmation link must not confirm the address.
        with urlopen(self.base + "/confirm?token=" + confirm) as r:
            self.assertEqual(r.status, 200)
        with self.app.connect() as db:
            self.assertIsNone(db.execute("SELECT confirmed_at FROM subscribers").fetchone()[0])
        self.assertEqual(self.post("/api/confirm", {"token": confirm})[0], 200)
        self.assertEqual(self.post("/api/unsubscribe", {"token": unsubscribe})[0], 200)
        with self.app.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM subscribers").fetchone()[0], 0)

    def test_private_files_and_paths_are_not_served(self):
        for path in ("/server.py", "/subscribers.sqlite3", "/assets/../../server.py", "/private.env"):
            with self.assertRaises(HTTPError) as e:
                urlopen(self.base + path)
            self.assertEqual(e.exception.code, 404)
            e.exception.close()

    def test_headers_and_cookie_free_page(self):
        with urlopen(self.base) as r:
            self.assertEqual(r.status, 200)
            self.assertIsNone(r.headers.get("Set-Cookie"))
            self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])
            self.assertEqual(r.headers["Referrer-Policy"], "no-referrer")
            self.assertIn(b'lang="de"', r.read())


if __name__ == "__main__":
    unittest.main()
