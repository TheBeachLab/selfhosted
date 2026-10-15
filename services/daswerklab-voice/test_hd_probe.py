"""Safety checks for the isolated laboratory; no Twilio/network calls."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator

from hd_probe import Probe


class SignatureTests(unittest.TestCase):
    def setUp(self):
        self.probe = Probe.__new__(Probe)
        self.probe.public_base = "https://probe.example.invalid"
        self.probe.validator = RequestValidator("a-test-secret-that-is-32-bytes-long")
        self.path = "/media/nonce/baseline"

    def request(self, url):
        signature = self.probe.validator.compute_signature(url, {})
        return SimpleNamespace(rel_url=self.path, headers={"X-Twilio-Signature": signature})

    def test_real_wss_signature_is_accepted_without_disabling_validation(self):
        request = self.request("wss://probe.example.invalid" + self.path)
        self.assertTrue(self.probe.valid_twilio(request, {}, websocket=True))
        self.assertFalse(self.probe.valid_twilio(request, {}))

    def test_wrong_path_and_unsigned_requests_remain_rejected(self):
        request = self.request("wss://probe.example.invalid/media/other/baseline")
        self.assertFalse(self.probe.valid_twilio(request, {}, websocket=True))
        request.headers = {}
        self.assertFalse(self.probe.valid_twilio(request, {}, websocket=True))


class CleanupTests(unittest.IsolatedAsyncioTestCase):
    async def make_probe(self, directory):
        probe = Probe.__new__(Probe)
        probe.args = SimpleNamespace(runtime=Path(directory))
        probe.calls = {"CA-created-only-by-this-probe"}
        probe.key = None
        probe.tunnel = None
        probe.report = {"before": {"region": "ie1"}, "cleanup": {}}
        probe.snapshot = AsyncMock(return_value={"region": "ie1"})
        resource = Mock()
        resource.fetch.return_value = SimpleNamespace(status="in-progress")
        probe.client = Mock()
        probe.client.calls.return_value = resource
        return probe, resource

    async def test_only_created_calls_are_ended(self):
        with TemporaryDirectory() as directory:
            probe, resource = await self.make_probe(directory)
            await probe.cleanup()
            self.assertTrue(probe.client.calls.called)
            self.assertTrue(all(item.args == ("CA-created-only-by-this-probe",)
                                for item in probe.client.calls.call_args_list))
            resource.update.assert_called_once_with(status="completed")
            self.assertTrue(probe.report["production_number_config_unchanged"])

    async def test_key_cleanup_failure_still_stops_tunnel_and_preserves_readback(self):
        with TemporaryDirectory() as directory:
            probe, _ = await self.make_probe(directory)
            probe.key = SimpleNamespace(sid="SK-temporary")
            probe.client.keys.return_value.delete.side_effect = TwilioRestException(
                503, "/Keys/SK-temporary", code=20500, msg="Temporary outage")
            probe.tunnel = SimpleNamespace(returncode=None, terminate=Mock(), wait=AsyncMock(return_value=0))
            with self.assertRaisesRegex(RuntimeError, "key deletion unconfirmed"):
                await probe.cleanup()
            probe.tunnel.terminate.assert_called_once()
            self.assertTrue(probe.report["cleanup"]["tunnel_stopped"])
            self.assertTrue(probe.report["production_number_config_unchanged"])


if __name__ == "__main__":
    unittest.main()
