import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "identity_jev", ROOT / "services/msgvault/install-identity-jev.py")
jev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jev)
TEMPLATE = (ROOT / "services/msgvault/identity-jev.toml").read_bytes()


class JevSetupGuards(unittest.TestCase):
    def test_credentials_are_data_and_shell_payloads_are_rejected(self):
        self.assertEqual("synthetic_key_123456", jev.parse_credential(
            "# private file\nTYPESAFE_API_KEY='synthetic_key_123456'\n"))
        for text in ["TYPESAFE_API_KEY=", "TYPESAFE_API_KEY=$(id)",
                     "TYPESAFE_API_KEY=`id`", "TYPESAFE_API_KEY=synthetic_key_123456\nOTHER=1",
                     "TYPESAFE_API_KEY=synthetic_key_123456\nTYPESAFE_API_KEY=another_key_123456",
                     "OPENAI_API_KEY=synthetic_key_123456", "TYPESAFE_API_KEY= key_with_spaces_123456"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                jev.parse_credential(text)

    def test_credential_requires_regular_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "key.env"
            key.write_text("TYPESAFE_API_KEY=synthetic_key_123456\n")
            key.chmod(0o644)
            with self.assertRaises(ValueError):
                jev.private_credential(key)
            key.chmod(0o600)
            self.assertEqual("synthetic_key_123456", jev.private_credential(key))
            link = Path(directory) / "link.env"
            link.symlink_to(key)
            with self.assertRaises(ValueError):
                jev.private_credential(link)

    def test_other_provider_config_is_preserved_byte_for_byte(self):
        original = b'[server]\napi_key = "synthetic"\n\n[people.sweep]\nprovider = "openai"\n'
        updated = jev.scoring_config(original, TEMPLATE)
        self.assertTrue(updated.startswith(original))
        self.assertEqual(original, updated[:len(original)])
        self.assertEqual(updated, jev.scoring_config(updated, TEMPLATE))

    def test_existing_different_or_duplicate_scoring_sections_are_preserved(self):
        for original in [b'[people.identity_scoring]\nenabled = false\n', TEMPLATE + TEMPLATE]:
            with self.subTest(original=original), self.assertRaises(ValueError):
                jev.scoring_config(original, TEMPLATE)

    def test_preflight_rejects_unavailable_pinned_model_before_post(self):
        with mock.patch.object(jev, "request_json", return_value={
                "models": [{"name": "jev-latest"}]}) as request:
            with self.assertRaises(RuntimeError):
                jev.provider_preflight("synthetic_key_123456")
            self.assertEqual(1, request.call_count)

    def test_preflight_uses_synthetic_data_and_accepts_native_noul(self):
        with mock.patch.object(jev, "request_json", side_effect=[
                {"models": [{"name": jev.MODEL}]},
                {"model": jev.MODEL, "answers": {"same_person": {"type": "noul", "noul": 0.9}}},
        ]) as request:
            self.assertTrue(jev.provider_preflight("synthetic_key_123456")["synthetic_check_passed"])
            body = request.call_args_list[1].args[2]
            self.assertEqual("setup@example.invalid", body["state"]["left"]["email"])
            self.assertEqual(jev.MODEL, body["model"])
            self.assertEqual({"left", "right"}, set(body["state"]))

    def test_preflight_rejects_malformed_probabilities(self):
        invalid = [True, None, float("nan"), float("inf"), -0.1, 1.1, "0.9"]
        for probability in invalid:
            with self.subTest(probability=probability), mock.patch.object(jev, "request_json", side_effect=[
                    {"models": [{"name": jev.MODEL}]},
                    {"model": jev.MODEL, "answers": {"same_person": {"type": "noul", "noul": probability}}},
            ]), self.assertRaises(RuntimeError):
                jev.provider_preflight("synthetic_key_123456")

    def test_authenticated_requests_do_not_follow_redirects(self):
        self.assertIsNone(jev.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid"))


if __name__ == "__main__":
    unittest.main()
