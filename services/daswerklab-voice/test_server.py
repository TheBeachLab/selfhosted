import asyncio
import base64
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from twilio.request_validator import RequestValidator

from server import Bridge, Call, Messages, Settings, create_app, session_config
import configure_twilio
import install

SID = "AC" + "1" * 32
CALL_SID = "CA" + "2" * 32
STREAM_SID = "MZ" + "3" * 32
TOKEN = "synthetic-unit-test-token"
PUBLIC = "https://example.org/voice"
NUMBER = "+498955555555"
FRAN = "+491700000001"
CALLER = "+491700000002"
AUDIO = base64.b64encode(b"\xff" * 160).decode()


class FakeAI:
    def __init__(self, greeting_events=()):
        self.sent = []
        self.events = asyncio.Queue()
        self.greeting_events = list(greeting_events)

    async def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        if event["type"] == "session.update":
            self.events.put_nowait(json.dumps({"type": "session.updated"}))
        elif event["type"] == "response.create":
            for reply in self.greeting_events:
                self.events.put_nowait(json.dumps(reply))
            self.greeting_events.clear()

    async def recv(self):
        return await self.events.get()

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.recv()


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send_json(self, value):
        self.sent.append(value)


class VoiceHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(PUBLIC, SID, TOKEN, NUMBER, FRAN, "synthetic-openai-test-key",
                                 state_dir=Path(self.temp.name))
        self.ai_instances = []
        self.greeting_events = [{"type": "response.output_audio.delta", "item_id": "greeting", "delta": AUDIO}]

        @asynccontextmanager
        async def fake_connector(settings, call):
            ai = FakeAI(self.greeting_events)
            self.ai_instances.append(ai)
            yield ai

        self.app = create_app(self.settings, fake_connector, probe=False)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.form = {"AccountSid": SID, "CallSid": CALL_SID, "From": CALLER, "To": NUMBER}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def post(self, path, form=None):
        data = self.form if form is None else form
        signature = RequestValidator(TOKEN).compute_signature(PUBLIC + path, data)
        return self.client.post(path, data=data, headers={"X-Twilio-Signature": signature})

    def start_event(self, ticket):
        return {"event": "start", "start": {"accountSid": SID, "callSid": CALL_SID,
                "streamSid": STREAM_SID, "customParameters": {"ticket": ticket},
                "mediaFormat": {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}}}

    def socket(self):
        signature = RequestValidator(TOKEN).compute_signature(PUBLIC + "/media", {})
        return self.client.websocket_connect("/media", headers={"X-Twilio-Signature": signature})

    def test_unsigned_webhooks_are_rejected(self):
        self.assertEqual(self.client.post("/incoming", data=self.form).status_code, 403)
        self.assertFalse(self.app.state.calls)

    def test_signature_covers_full_form_and_configured_account(self):
        data = dict(self.form, AccountSid="AC" + "9" * 32)
        self.assertEqual(self.post("/incoming", data).status_code, 403)
        data = dict(self.form, To="+498966666666")
        self.assertEqual(self.post("/incoming", data).status_code, 403)

    def test_replays_before_stream_connection_keep_same_ticket(self):
        response = self.post("/incoming")
        xml = ET.fromstring(response.text)
        self.assertEqual(xml.find(".//Stream").get("url"), "wss://example.org/voice/media")
        self.assertEqual(xml.find("Redirect").text, PUBLIC + "/after-stream")
        ticket = xml.find(".//Parameter").get("value")
        repeat = ET.fromstring(self.post("/incoming").text)
        self.assertEqual(repeat.find(".//Parameter").get("value"), ticket)

    def test_fran_mobile_starts_in_german_without_bypassing_agent(self):
        self.post("/incoming", dict(self.form, From=FRAN))
        self.assertEqual(self.app.state.calls[CALL_SID].language, "de")
        self.assertEqual(self.app.state.calls[CALL_SID].mode, "ai")

    def test_no_api_key_routes_to_fixed_mobile_without_creating_realtime(self):
        self.settings.openai_key = ""
        xml = ET.fromstring(self.post("/incoming").text)
        self.assertEqual(xml.find("Dial").text, FRAN)
        self.assertEqual(xml.find("Dial").get("callerId"), NUMBER)
        self.assertFalse(self.ai_instances)
        self.assertEqual(self.client.get("/healthz").status_code, 503)

    def test_accepted_caller_bypasses_ai_only_when_explicitly_listed(self):
        self.settings.direct_callers = (CALLER,)
        xml = ET.fromstring(self.post("/incoming").text)
        self.assertEqual(xml.find("Dial").text, FRAN)
        self.assertIsNone(xml.find("Connect"))

    def test_unsigned_socket_is_rejected_before_connecting_openai(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/media"):
                pass
        self.assertFalse(self.ai_instances)

    def test_stream_ticket_and_media_format_are_checked(self):
        self.post("/incoming")
        with self.socket() as socket:
            socket.send_json(self.start_event("wrong-ticket"))
            with self.assertRaises(WebSocketDisconnect):
                socket.receive_json()
        self.assertFalse(self.ai_instances)
        self.assertFalse(self.app.state.calls[CALL_SID].stream_connected)

    def test_signed_stream_returns_mulaw_audio_and_accounts_for_playback(self):
        self.post("/incoming")
        ticket = self.app.state.calls[CALL_SID].ticket
        with self.socket() as socket:
            socket.send_json({"event": "connected"})
            socket.send_json(self.start_event(ticket))
            media = socket.receive_json()
            mark = socket.receive_json()
            self.assertEqual(media["media"]["payload"], AUDIO)
            self.assertEqual(media["streamSid"], STREAM_SID)
            self.assertEqual(mark["event"], "mark")
            socket.send_json({"event": "media", "media": {"timestamp": "20", "payload": AUDIO}})
            socket.send_json({"event": "mark", "mark": mark["mark"]})
            socket.send_json({"event": "stop"})
            with self.assertRaises(WebSocketDisconnect):
                socket.receive_json()
        config = self.ai_instances[0].sent[0]["session"]
        self.assertEqual(config["audio"]["input"]["format"]["type"], "audio/pcmu")
        self.assertEqual(config["audio"]["output"]["format"]["type"], "audio/pcmu")
        self.assertIn({"type": "input_audio_buffer.append", "audio": AUDIO}, self.ai_instances[0].sent)

    def test_transfer_closes_stream_then_dials_fixed_number_in_selected_language(self):
        tool = {"type": "function_call", "name": "transfer_to_fran", "call_id": "tool-handoff",
                "arguments": json.dumps({"language": "en"})}
        self.greeting_events = [{"type": "response.done", "response": {
            "status": "completed", "output": [tool]}}]
        self.post("/incoming")
        ticket = self.app.state.calls[CALL_SID].ticket
        with self.socket() as socket:
            socket.send_json(self.start_event(ticket))
            self.assertEqual(socket.receive_json()["event"], "clear")
            with self.assertRaises(WebSocketDisconnect):
                socket.receive_json()
        xml = ET.fromstring(self.post("/after-stream").text)
        self.assertEqual(xml.find("Dial").text, FRAN)
        self.assertEqual(xml.find("Say").get("language"), "en-GB")
        self.assertEqual(self.app.state.calls[CALL_SID].handoffs, 1)
        response = self.post("/dial-ended", dict(self.form, DialCallStatus="no-answer"))
        self.assertIsNotNone(ET.fromstring(response.text).find("Connect"))
        self.assertTrue(self.app.state.calls[CALL_SID].resumed)
        self.assertNotEqual(self.app.state.calls[CALL_SID].ticket, ticket)

    def test_completed_call_removes_temporary_context(self):
        self.post("/incoming")
        self.assertEqual(self.post("/status", dict(self.form, CallStatus="completed")).status_code, 204)
        self.assertFalse(self.app.state.calls)

    def test_peer_hangup_during_final_close_does_not_escape_the_endpoint(self):
        self.post("/incoming")
        start = self.start_event(self.app.state.calls[CALL_SID].ticket)
        signature = RequestValidator(TOKEN).compute_signature(PUBLIC + "/media", {})

        class HungUpSocket(FakeSocket):
            url = SimpleNamespace(query="")
            headers = {"x-twilio-signature": signature}

            async def accept(self):
                pass

            async def receive_json(self):
                if not hasattr(self, "started"):
                    self.started = True
                    return start
                return {"event": "stop"}

            async def close(self, **kwargs):
                raise WebSocketDisconnect(code=1000)

        endpoint = next(route.endpoint for route in self.app.routes if route.path == "/media")
        asyncio.run(endpoint(HungUpSocket()))
        self.assertFalse(self.app.state.calls[CALL_SID].stream_connected)


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cfg = Settings(PUBLIC, SID, TOKEN, NUMBER, FRAN, state_dir=Path(self.temp.name))
        self.call = Call(CALL_SID, CALLER, "de")
        self.ai, self.socket = FakeAI(), FakeSocket()
        self.messages = Messages(Path(self.temp.name))
        self.bridge = Bridge(self.socket, self.ai, self.cfg, self.call, self.messages, STREAM_SID)

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_arbitrary_transfer_destinations_are_rejected(self):
        result = await self.bridge.execute_tool({"name": "transfer_to_fran", "call_id": "bad-destination",
            "arguments": json.dumps({"language": "es", "number": "+441111111111"})})
        self.assertFalse(result)
        self.assertEqual(self.call.mode, "ai")
        output = json.loads(self.ai.sent[0]["item"]["output"])
        self.assertFalse(output["success"])

    async def test_interruption_clears_queue_and_truncates_only_unheard_audio(self):
        self.bridge.last_item = "item-1"
        self.bridge.audio_started, self.bridge.timestamp, self.bridge.generated_ms = 1000, 1040, 100
        self.bridge.marks.append("mark-1")
        await self.bridge.interrupt()
        self.assertEqual(self.ai.sent[0], {"type": "conversation.item.truncate", "item_id": "item-1",
                                        "content_index": 0, "audio_end_ms": 40})
        self.assertEqual(self.socket.sent[0]["event"], "clear")
        self.assertFalse(self.bridge.marks)
        self.assertIn("item-1", self.bridge.blocked_items)

    async def test_confirmed_message_is_saved_once_with_private_permissions(self):
        args = {"language": "de", "name": "Cliente de prueba", "contact": "test@example.org",
                "summary_es": "Solicita asesoramiento sobre sensores."}
        item = {"name": "save_message", "call_id": "message-tool", "arguments": json.dumps(args)}
        await self.bridge.execute_tool(item)
        await self.bridge.execute_tool(item)
        with sqlite3.connect(self.messages.path) as db:
            rows = db.execute("SELECT summary_es, language FROM messages").fetchall()
        self.assertEqual(rows, [(args["summary_es"], "de")])
        self.assertEqual(self.messages.path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(json.loads(self.ai.sent[0]["item"]["output"])["success"])

    async def test_failed_handoff_is_not_repeated_automatically(self):
        self.call.handoffs = 1
        self.assertFalse(await self.bridge.execute_tool({"name": "transfer_to_fran", "call_id": "second",
                                                       "arguments": '{"language":"es"}'}))
        self.assertEqual(self.call.mode, "ai")
        self.assertFalse(json.loads(self.ai.sent[0]["item"]["output"])["success"])

    async def test_handoff_language_variants_use_same_destination(self):
        for lang in ("es", "en", "de"):
            self.bridge.stopping = False
            self.assertTrue(await self.bridge.execute_tool({"name": "transfer_to_fran", "call_id": lang,
                                                           "arguments": json.dumps({"language": lang})}))
            self.assertEqual(self.call.language, lang)
            self.assertEqual(self.call.mode, "transfer")

    async def test_configuration_refuses_self_transfer_loop(self):
        with self.assertRaises(ValueError):
            Settings(PUBLIC, SID, TOKEN, NUMBER, NUMBER)

    async def test_session_includes_source_facts_and_three_languages(self):
        session = session_config(self.cfg, self.call)["session"]
        self.assertIn("español, inglés y alemán", session["instructions"])
        self.assertIn("https://daswerklab.de/es/", session["instructions"])
        self.assertIn("Desarrollo de sistemas", session["instructions"])
        self.assertEqual({t["name"] for t in session["tools"]},
                         {"transfer_to_fran", "save_message", "end_call"})


class DeploymentGuardTests(unittest.TestCase):
    def test_ie1_uses_its_own_auth_token_without_requiring_a_new_api_key(self):
        env = {"TWILIO_ACCOUNT_SID": SID, "TWILIO_AUTH_TOKEN": "us1-token",
               "TWILIO_IE1_AUTH_TOKEN": "ie1-token"}
        self.assertEqual(configure_twilio.regional_credentials(env, "ie1"), (SID, "ie1-token"))

    def test_ie1_never_authenticates_with_us1_credentials(self):
        env = {"TWILIO_ACCOUNT_SID": SID, "TWILIO_AUTH_TOKEN": "us1-token",
               "TWILIO_API_KEY": "us1-key", "TWILIO_API_SECRET": "us1-secret"}
        with self.assertRaises(KeyError):
            configure_twilio.regional_credentials(env, "ie1")

    def test_concurrent_nginx_edit_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "site.conf"
            path.write_bytes(b"another conversation changed this")
            with self.assertRaises(RuntimeError):
                install.replace_unchanged(path, install.digest(b"before"), b"our change")
            self.assertEqual(path.read_bytes(), b"another conversation changed this")

    def test_compare_and_replace_preserves_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "site.conf"
            path.write_bytes(b"before")
            path.chmod(0o640)
            install.replace_unchanged(path, install.digest(b"before"), b"after")
            self.assertEqual(path.read_bytes(), b"after")
            self.assertEqual(path.stat().st_mode & 0o777, 0o640)

    def activation_case(self, folder, extra=()):
        env = Path(folder) / "env"
        env.write_text("TWILIO_ACCOUNT_SID=" + SID +
                       "\nTWILIO_API_KEY=synthetic-key\nTWILIO_API_SECRET=synthetic-secret\n")
        return ["configure_twilio.py", "--env", str(env), "--activate", "--region", "us1",
                "--receipt", str(Path(folder) / "receipt.json"), *extra]

    def test_twilio_activation_cannot_run_before_realtime_is_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("sys.argv", self.activation_case(folder, ("--allow-region-change",))), \
                 patch.object(configure_twilio, "api", return_value={"account_sid": SID, "voice_region": "ie1"}) as api, \
                 patch.object(configure_twilio, "require_ready", side_effect=RuntimeError("not ready")):
                with self.assertRaisesRegex(RuntimeError, "not ready"):
                    configure_twilio.main()
                self.assertEqual(api.call_count, 1)
                self.assertEqual(len(api.call_args.args), 2)  # GET only.
                self.assertFalse((Path(folder) / "receipt.json").exists())

    def test_twilio_region_change_requires_explicit_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("sys.argv", self.activation_case(folder)), \
                 patch.object(configure_twilio, "api", return_value={"account_sid": SID, "voice_region": "ie1"}) as api, \
                 patch.object(configure_twilio, "require_ready"):
                with self.assertRaisesRegex(RuntimeError, "allow-region-change"):
                    configure_twilio.main()
                self.assertEqual(api.call_count, 1)
                self.assertFalse((Path(folder) / "receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
