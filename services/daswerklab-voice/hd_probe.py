#!/usr/bin/env python3
"""Isolated IE1 Media Streams experiment; never routes through a phone number.

Uses one temporary, incoming-only Voice SDK identity and one temporary API key.
The public listener accepts signed Twilio streams/callbacks only. The browser
page and token endpoint are served on a different, loopback-only port.

Sources checked 2026-10-15:
https://www.twilio.com/docs/voice/sdks/javascript/twiliodevice
https://www.twilio.com/docs/voice/media-streams/websocket-messages
https://github.com/twilio/twilio-node/blob/main/src/twiml/VoiceResponse.ts
https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/
"""
import argparse
import asyncio
import base64
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import xml.etree.ElementTree as ET

from aiohttp import web
from twilio.base.exceptions import TwilioRestException
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from configure_twilio import api, read_env, regional_credentials

VARIANTS = (
    ("baseline", {}),
    ("invalid_control", {"audioFormat": "hd_probe_invalid", "sampleRate": "12345"}),
    ("l16_16000", {"audioFormat": "audio/x-l16", "sampleRate": "16000"}),
    ("pcm_16000", {"audioFormat": "pcm", "sampleRate": "16000"}),
    ("pcm16_16000", {"audioFormat": "pcm16", "sampleRate": "16000"}),
)
NUMBER_FIELDS = ("sid", "phone_number", "voice_url", "voice_method",
                 "voice_fallback_url", "voice_fallback_method", "voice_application_sid",
                 "status_callback", "status_callback_method")


def utc():
    return datetime.now(timezone.utc).isoformat()


def private_json(path, value):
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(value, output, indent=2, ensure_ascii=False)
        output.write("\n")


def twiml(url, callback, attributes):
    response = ET.Element("Response")
    connect = ET.SubElement(response, "Connect")
    ET.SubElement(connect, "Stream", {"url": url, "statusCallback": callback,
                                      "statusCallbackMethod": "POST", **attributes})
    ET.SubElement(response, "Hangup")
    return ET.tostring(response, encoding="unicode")


def pcmu_decode(payload):
    samples = []
    for b in payload:
        u = (~b) & 255
        value = (((u & 15) << 3) + 132) << ((u >> 4) & 7)
        value -= 132
        samples.append(-value if u & 128 else value)
    return samples


def tone_measurements(payload, media_format):
    """Retain measurements, never audio; all input originates as synthetic tones."""
    rate = media_format.get("sampleRate", 0)
    encoding = media_format.get("encoding", "")
    if encoding == "audio/x-mulaw":
        samples = pcmu_decode(payload)
    else:
        # The preview format's byte order is not documented. Keep metadata
        # rather than guessing a PCM layout or claiming a spectral result.
        return {"analysis": "format_metadata_only"}
    if not rate or len(samples) < rate:
        return {"analysis": "insufficient_audio", "samples": len(samples)}
    samples = samples[-min(len(samples), rate * 3):]
    amplitudes = {}
    for frequency in (1000, 5500, 6500):
        if frequency >= rate / 2:
            continue
        omega = 2 * math.pi * frequency / rate
        real = sum(sample * math.cos(i * omega) for i, sample in enumerate(samples))
        imag = sum(sample * math.sin(i * omega) for i, sample in enumerate(samples))
        amplitude = 2 * math.hypot(real, imag) / len(samples) / 32768
        amplitudes[str(frequency)] = round(20 * math.log10(max(amplitude, 1e-10)), 2)
    return {"analysis": "tone_amplitude_dbfs", "tones": amplitudes,
            "samples": len(samples), "sample_rate": rate}


class Probe:
    def __init__(self, args):
        self.args = args
        self.env = read_env(args.env)
        self.credentials = regional_credentials(self.env, "ie1")
        self.client = Client(*self.credentials, region="ie1", edge="dublin")
        self.validator = RequestValidator(self.env["TWILIO_IE1_AUTH_TOKEN"])
        self.nonce = secrets.token_urlsafe(24)
        self.identity = "hd-probe-" + secrets.token_hex(8)
        self.calls = set()
        self.key = None
        self.tunnel = None
        self.token = None
        self.public_base = None
        self.registered = asyncio.Event()
        self.stop = asyncio.Event()
        self.destroyed = asyncio.Event()
        self.report = {"started_at": utc(), "region": "ie1", "edge": "dublin",
                       "destination_kind": "temporary_voice_sdk_identity",
                       "phone_number_called": False, "microphone_used": False,
                       "synthetic_tones_hz": [1000, 5500, 6500], "variants": [],
                       "browser_events": [], "cleanup": {}}
        self.report["dependencies"] = json.loads((args.runtime / "dependencies.json").read_text())
        self.by_variant = {}

    def save(self):
        private_json(self.args.runtime / "report.json", self.report)

    async def snapshot(self):
        sid = self.env["TWILIO_ACCOUNT_SID"]
        route = await asyncio.to_thread(api, "https://routes.twilio.com/v2/PhoneNumbers/%2B498951042000",
                                        (self.env["TWILIO_API_KEY"], self.env["TWILIO_API_SECRET"]))
        listing = await asyncio.to_thread(api, "https://api.dublin.ie1.twilio.com/2010-04-01/Accounts/"
                                          + sid + "/IncomingPhoneNumbers.json?PhoneNumber=%2B498951042000",
                                          self.credentials)
        rows = listing["incoming_phone_numbers"]
        if len(rows) != 1 or route["voice_region"] != "ie1":
            raise RuntimeError("Owned number/IE1 invariant not met; no resources created.")
        number = rows[0]
        return {"region": route["voice_region"], **{f: number.get(f) for f in NUMBER_FIELDS}}

    async def ui(self, request):
        if request.match_info["nonce"] != self.nonce:
            raise web.HTTPNotFound()
        html = Path(__file__).with_name("hd_probe.html").read_text()
        return web.Response(text=html.replace("__CAP__", self.nonce), content_type="text/html",
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    def local_auth(self, request):
        if not secrets.compare_digest(request.query.get("cap", ""), self.nonce):
            raise web.HTTPForbidden()

    async def config(self, request):
        self.local_auth(request)
        return web.json_response({"token": self.token, "identity": self.identity,
                                  "done": self.report.get("tests_finished", False)},
                                 headers={"Cache-Control": "no-store"})

    async def browser_report(self, request):
        self.local_auth(request)
        event = await request.json()
        if event.get("kind") not in ("registered", "error", "incoming", "accepted", "codec", "destroyed"):
            raise web.HTTPBadRequest()
        self.report["browser_events"].append({"at": utc(), **event})
        if event["kind"] == "registered":
            self.registered.set()
        if event["kind"] == "destroyed":
            self.destroyed.set()
        self.save()
        return web.json_response({"ok": True})

    async def result(self, request):
        self.local_auth(request)
        return web.json_response({"registered": self.registered.is_set(),
                                  "done": self.report.get("tests_finished", False),
                                  "variants": [{k: v for k, v in row.items() if k not in ("stream_sid", "call_sid")}
                                               for row in self.report["variants"]]})

    def valid_twilio(self, request, params, websocket=False):
        canonical = self.public_base + str(request.rel_url)
        candidates = (canonical, canonical.replace("https://", "wss://", 1)) if websocket else (canonical,)
        return any(self.validator.validate(url, params, request.headers.get("X-Twilio-Signature", ""))
                   for url in candidates)

    async def callback(self, request):
        if request.match_info["nonce"] != self.nonce:
            raise web.HTTPNotFound()
        data = dict(await request.post())
        if not self.valid_twilio(request, data) or data.get("AccountSid") != self.env["TWILIO_ACCOUNT_SID"]:
            raise web.HTTPForbidden()
        row = self.by_variant.get(request.match_info["variant"])
        if row is not None:
            row.setdefault("callbacks", []).append({key: data[key] for key in
                ("CallStatus", "StreamEvent", "StreamError", "ErrorCode", "ErrorMessage") if key in data})
            self.save()
        return web.Response(status=204)

    async def stream(self, request):
        variant = request.match_info["variant"]
        if request.match_info["nonce"] != self.nonce or variant not in self.by_variant:
            raise web.HTTPNotFound()
        if not self.valid_twilio(request, {}, websocket=True):
            raise web.HTTPForbidden()
        ws = web.WebSocketResponse(max_msg_size=1_048_576)
        await ws.prepare(request)
        row = self.by_variant[variant]
        payload = bytearray()
        async for message in ws:
            if message.type != web.WSMsgType.TEXT:
                continue
            event = json.loads(message.data)
            if event.get("event") == "start":
                start = event["start"]
                if start.get("accountSid") != self.env["TWILIO_ACCOUNT_SID"] or start.get("callSid") not in self.calls:
                    await ws.close(code=1008)
                    break
                row.update({"media_format": start.get("mediaFormat"), "stream_sid": start.get("streamSid"),
                            "start_received": True})
                self.save()
                print(json.dumps({"variant": variant, "received_format": row["media_format"]}), flush=True)
            elif event.get("event") == "media" and row.get("start_received"):
                audio = base64.b64decode(event["media"]["payload"], validate=True)
                row["audio_bytes"] = row.get("audio_bytes", 0) + len(audio)
                if len(payload) + len(audio) <= 2_000_000:
                    payload.extend(audio)
            elif event.get("event") == "stop":
                row["stop_received"] = True
                break
        row["audio_measurements"] = tone_measurements(payload, row.get("media_format") or {})
        self.save()
        return ws

    async def run_tests(self):
        await asyncio.wait_for(self.registered.wait(), 600)
        for name, attributes in VARIANTS:
            if self.stop.is_set():
                break
            row = {"name": name, "requested_attributes": attributes, "started_at": utc()}
            self.report["variants"].append(row)
            self.by_variant[name] = row
            destination = "client:" + self.identity
            assert destination.startswith("client:hd-probe-")
            suffix = "/" + self.nonce + "/" + name
            xml = twiml(self.public_base.replace("https://", "wss://") + "/media" + suffix,
                         self.public_base + "/status" + suffix, attributes)
            call = await asyncio.to_thread(self.client.calls.create, to=destination,
                from_=self.report["before"]["phone_number"], twiml=xml, timeout=15,
                time_limit=12, record=False, status_callback=self.public_base + "/status" + suffix,
                status_callback_event=["completed"])
            self.calls.add(call.sid)
            row["call_sid"] = call.sid
            self.save()
            print(json.dumps({"variant": name, "call_created": True}), flush=True)
            for _ in range(22):
                if self.stop.is_set():
                    break
                await asyncio.sleep(1)
                current = await asyncio.to_thread(self.client.calls(call.sid).fetch)
                if current.status in ("completed", "failed", "busy", "no-answer", "canceled"):
                    break
            else:
                await asyncio.to_thread(self.client.calls(call.sid).update, status="completed")
                current = await asyncio.to_thread(self.client.calls(call.sid).fetch)
            row.update({"status": current.status, "duration_seconds": current.duration,
                        "price": current.price, "price_unit": current.price_unit})
            try:
                alerts = await asyncio.to_thread(self.client.calls(call.sid).notifications.list, limit=20)
                row["notifications"] = [{"error_code": a.error_code, "message_text": a.message_text} for a in alerts]
            except TwilioRestException as error:
                row["notifications_unavailable"] = {"status": error.status, "code": error.code}
            self.save()
            if name == "baseline" and (not row.get("start_received") or row.get("audio_bytes", 0) < 1000):
                raise RuntimeError("Baseline audio failed; no HD conclusions or further test calls.")
            await asyncio.sleep(1)
        self.report["tests_finished"] = True
        self.save()
        try:
            await asyncio.wait_for(self.destroyed.wait(), 10)
        except asyncio.TimeoutError:
            pass
        self.stop.set()

    async def start_tunnel(self):
        self.tunnel = await asyncio.create_subprocess_exec(str(self.args.cloudflared),
            "tunnel", "--config", "/dev/null", "--no-autoupdate", "--protocol", "http2",
            "--url", "http://127.0.0.1:19657", stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE)
        async def find_url():
            while line := await self.tunnel.stderr.readline():
                match = re.search(rb"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if match:
                    return match[0].decode()
            raise RuntimeError("Temporary tunnel did not start.")
        self.public_base = await asyncio.wait_for(find_url(), 45)
        self.report["temporary_tunnel_host"] = self.public_base.split("://", 1)[1]
        async def drain():
            while await self.tunnel.stderr.readline():
                pass
        asyncio.create_task(drain())

    async def cleanup(self):
        for sid in self.calls:
            try:
                call = await asyncio.to_thread(self.client.calls(sid).fetch)
                if call.status not in ("completed", "failed", "busy", "no-answer", "canceled"):
                    await asyncio.to_thread(self.client.calls(sid).update, status="completed")
            except Exception as error:
                self.report["cleanup"]["call_cleanup_error"] = getattr(error, "code", type(error).__name__)
        self.report["cleanup"]["created_call_count"] = len(self.calls)
        if self.key:
            try:
                await asyncio.to_thread(self.client.keys(self.key.sid).delete)
                try:
                    await asyncio.to_thread(self.client.keys(self.key.sid).fetch)
                    self.report["cleanup"]["temporary_key_deleted"] = False
                except TwilioRestException as error:
                    self.report["cleanup"]["temporary_key_deleted"] = error.status == 404
            except Exception as error:
                self.report["cleanup"]["temporary_key_deleted"] = False
                self.report["cleanup"]["temporary_key_error"] = getattr(error, "code", type(error).__name__)
        if self.tunnel and self.tunnel.returncode is None:
            self.tunnel.terminate()
            await asyncio.wait_for(self.tunnel.wait(), 10)
            self.report["cleanup"]["tunnel_stopped"] = True
        try:
            self.report["after"] = await self.snapshot()
            self.report["production_number_config_unchanged"] = self.report["before"] == self.report["after"]
        except Exception as error:
            self.report["cleanup"]["configuration_readback_error"] = type(error).__name__
        self.report["finished_at"] = utc()
        self.save()
        if self.key and not self.report["cleanup"].get("temporary_key_deleted"):
            raise RuntimeError("Temporary key deletion unconfirmed; inspect private-state.json and report.json.")
        if self.report.get("production_number_config_unchanged") is not True:
            raise RuntimeError("Production configuration equality unconfirmed; preserved without rewriting it.")

    async def run(self):
        self.report["before"] = await self.snapshot()
        public = web.Application(client_max_size=16_384)
        public.router.add_get("/media/{nonce}/{variant}", self.stream)
        public.router.add_post("/status/{nonce}/{variant}", self.callback)
        local = web.Application(client_max_size=16_384)
        local.router.add_get("/client/{nonce}", self.ui)
        local.router.add_get("/sdk.js", lambda r: web.FileResponse(self.args.runtime / "twilio.min.js"))
        local.router.add_get("/config", self.config)
        local.router.add_get("/result", self.result)
        local.router.add_post("/report", self.browser_report)
        runners = [web.AppRunner(public, access_log=None), web.AppRunner(local, access_log=None)]
        task = None
        try:
            for runner, port in zip(runners, (19657, 19658)):
                await runner.setup()
                await web.TCPSite(runner, "127.0.0.1", port).start()
            await self.start_tunnel()
            self.key = await asyncio.to_thread(self.client.new_keys.create,
                                              friendly_name="isolated-hd-probe-20261015")
            token = AccessToken(self.env["TWILIO_ACCOUNT_SID"], self.key.sid, self.key.secret,
                                identity=self.identity, ttl=900, region="ie1")
            token.add_grant(VoiceGrant(incoming_allow=True))
            self.token = token.to_jwt()
            private_json(self.args.runtime / "private-state.json", {
                "client_url": "http://127.0.0.1:19658/client/" + self.nonce,
                "temporary_key_sid": self.key.sid, "temporary_identity": self.identity})
            self.save()
            print(json.dumps({"ready": True, "client_url": "http://127.0.0.1:19658/client/" + self.nonce,
                              "region": "ie1", "phone_number_will_not_be_called": True}), flush=True)
            task = asyncio.create_task(self.run_tests())
            task.add_done_callback(lambda finished: self.stop.set()
                                   if finished.cancelled() or finished.exception() else None)
            await asyncio.wait_for(self.stop.wait(), 900)
            if task.done():
                await task
        finally:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            try:
                await self.cleanup()
            finally:
                for runner in runners:
                    await runner.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=Path("/Users/Papi/.config/recepcionista/.env"))
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--cloudflared", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    probe = Probe(args)
    async def run():
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, probe.stop.set)
        await probe.run()
    asyncio.run(run())


if __name__ == "__main__":
    main()
