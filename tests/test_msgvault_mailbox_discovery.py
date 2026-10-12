"""Exercise the unattended runner against a real synthetic HTTP daemon."""
import contextlib
import importlib.util
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "services/msgvault/mailbox-discovery.py"
SPEC = importlib.util.spec_from_file_location("mailbox_runner", SOURCE)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class RunnerContract(unittest.TestCase):
    def serve(self, payload):
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                calls.append((self.path, self.headers.get("Authorization"),
                              self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, calls

    def test_timer_calls_native_worker_and_logs_counts_only(self):
        server, calls = self.serve({"scanned_messages": 20, "candidates": 1,
                                   "provider_requests": 1, "next_cursor": 0,
                                   "results": [{"status": "shared", "email": "private@example.test",
                                                "own_signature": "private text"}]})
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.toml"
            config.write_text('[server]\napi_key="' + 'f' * 64 + '"\n')
            output = io.StringIO()
            with patch.object(runner, "CONFIG", config), \
                    patch.object(runner, "ORIGIN", f"http://127.0.0.1:{server.server_port}"), \
                    contextlib.redirect_stdout(output):
                runner.run()
        self.assertEqual(calls, [("/api/v1/identity/discovery/run", "Bearer " + "f" * 64, b'{"limit":8}')])
        counts = json.loads(output.getvalue())
        self.assertEqual(counts["shared"], 1)
        self.assertNotIn("private", output.getvalue())
        self.assertNotIn("f" * 64, output.getvalue())

    def test_partial_failure_is_a_failed_service_run(self):
        server, _ = self.serve({"scanned_messages": 20, "candidates": 1,
                               "provider_requests": 1, "next_cursor": 0,
                               "results": [], "error": "provider_request_failed"})
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.toml"
            config.write_text("[server]\n  api_key='" + 'f' * 64 + "'\n")
            with patch.object(runner, "CONFIG", config), \
                    patch.object(runner, "ORIGIN", f"http://127.0.0.1:{server.server_port}"), \
                    contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                runner.run()


if __name__ == "__main__":
    unittest.main()
