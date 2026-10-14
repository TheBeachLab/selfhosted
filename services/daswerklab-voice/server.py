#!/usr/bin/env python3
"""Signed Twilio Media Streams bridge to OpenAI Realtime, with fixed handoff."""
import asyncio
import base64
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse
from websockets.asyncio.client import connect

HERE = Path(__file__).resolve().parent
LOG = logging.getLogger("daswerklab.voice")
LANGUAGES = {"es": "es-ES", "en": "en-GB", "de": "de-DE"}
PHRASES = {
    "transfer": {
        "es": "Te paso con Fran. Un momento, por favor.",
        "en": "I'll put you through to Fran. Please hold.",
        "de": "Ich verbinde Sie mit Fran. Einen Moment bitte.",
    },
    "goodbye": {"es": "Gracias por llamar. Hasta luego.",
                "en": "Thank you for calling. Goodbye.",
                "de": "Vielen Dank für Ihren Anruf. Auf Wiedersehen."},
    "unavailable": {
        "es": "El asistente no está disponible. Te paso con Fran.",
        "en": "The assistant is unavailable. I'll put you through to Fran.",
        "de": "Der Assistent ist derzeit nicht verfügbar. Ich verbinde Sie mit Fran.",
    },
}
TOOLS = [
    {"type": "function", "name": "transfer_to_fran",
     "description": "Connect the current caller to Fran's configured mobile when they ask to speak to him.",
     "parameters": {"type": "object", "properties": {"language": {"type": "string", "enum": list(LANGUAGES)}},
                    "required": ["language"], "additionalProperties": False}},
    {"type": "function", "name": "save_message",
     "description": "Save a confirmed caller message for Fran, summarized in Spanish. Does not send email or WhatsApp.",
     "parameters": {"type": "object", "properties": {
         "name": {"type": "string"}, "contact": {"type": "string"},
         "summary_es": {"type": "string"},
         "language": {"type": "string", "enum": list(LANGUAGES)}},
         "required": ["name", "contact", "summary_es", "language"], "additionalProperties": False}},
    {"type": "function", "name": "end_call", "description": "End the current call after the caller says goodbye.",
     "parameters": {"type": "object", "properties": {"language": {"type": "string", "enum": list(LANGUAGES)}},
                    "required": ["language"], "additionalProperties": False}},
]


@dataclass
class Settings:
    public_base: str
    account_sid: str
    auth_token: str = field(repr=False)
    phone_number: str
    fran_number: str
    openai_key: str = field(default="", repr=False)
    model: str = "gpt-realtime-2.1"
    voice: str = "marin"
    state_dir: Path = Path("/var/lib/daswerklab-voice")
    max_seconds: int = 600
    max_calls: int = 4
    direct_callers: tuple = ()

    def __post_init__(self):
        self.public_base = self.public_base.rstrip("/")
        parsed = urlsplit(self.public_base)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("PUBLIC_BASE_URL must be an HTTPS URL without credentials or query.")
        if not re.fullmatch(r"AC[0-9a-fA-F]{32}", self.account_sid) or not self.auth_token:
            raise ValueError("Twilio account SID and Auth Token are required.")
        for number in (self.phone_number, self.fran_number, *self.direct_callers):
            if not re.fullmatch(r"\+[1-9][0-9]{7,14}", number):
                raise ValueError("Configured phone numbers must be E.164.")
        if self.fran_number == self.phone_number:
            raise ValueError("Handoff destination must differ from the receptionist number.")
        if not 30 <= self.max_seconds <= 1800 or not 1 <= self.max_calls <= 8:
            raise ValueError("Invalid call resource limits.")

    @classmethod
    def from_env(cls):
        env = os.environ
        return cls(
            env["PUBLIC_BASE_URL"], env["TWILIO_ACCOUNT_SID"], env["TWILIO_AUTH_TOKEN"],
            env["TWILIO_PHONE_NUMBER"], env["FRAN_PHONE_NUMBER"], env.get("OPENAI_API_KEY", ""),
            env.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1"),
            env.get("OPENAI_REALTIME_VOICE", "marin"),
            Path(env.get("STATE_DIR", "/var/lib/daswerklab-voice")),
            int(env.get("MAX_CALL_SECONDS", "600")), int(env.get("MAX_CONCURRENT_CALLS", "4")),
            tuple(x.strip() for x in env.get("DIRECT_CALLERS", "").split(",") if x.strip()),
        )


@dataclass
class Call:
    sid: str
    caller: str
    language: str
    ticket: str = field(default_factory=lambda: secrets.token_urlsafe(32), repr=False)
    started: float = field(default_factory=time.monotonic)
    mode: str = "ai"
    stream_connected: bool = False
    handoffs: int = 0
    resumed: bool = False


class Messages:
    def __init__(self, state_dir):
        state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.path = state_dir / "messages.sqlite"
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, tool_call_id TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                call_sid TEXT NOT NULL, caller TEXT NOT NULL, name TEXT NOT NULL,
                contact TEXT NOT NULL, language TEXT NOT NULL, summary_es TEXT NOT NULL)""")
        self.path.chmod(0o600)

    def save(self, call, tool_call_id, args):
        for key, limit in (("name", 200), ("contact", 300), ("summary_es", 3000)):
            if not isinstance(args.get(key), str) or len(args[key]) > limit:
                raise ValueError("Invalid message fields.")
        if not args["summary_es"].strip():
            raise ValueError("An enquiry needs a summary.")
        with sqlite3.connect(self.path) as db:
            db.execute("""INSERT OR IGNORE INTO messages
                (tool_call_id, call_sid, caller, name, contact, language, summary_es)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (tool_call_id, call.sid, call.caller, args["name"], args["contact"],
                 args["language"], args["summary_es"]))
            row = db.execute("SELECT id FROM messages WHERE tool_call_id = ?", (tool_call_id,)).fetchone()
        return row[0]


def instructions(call):
    knowledge = json.loads((HERE / "knowledge.json").read_text())
    text = (HERE / "prompt.md").read_text() + "\n" + json.dumps(knowledge, ensure_ascii=False)
    text += "\nIdioma inicial: " + call.language
    if call.resumed:
        text += "\nFran no pudo atender la transferencia. Ofrece continuar o guardar un mensaje."
    return text


def session_config(settings, call):
    # OpenAI GA schema and PCMU:
    # https://developers.openai.com/api/docs/guides/realtime-conversations
    return {
        "type": "session.update",
        "session": {"type": "realtime", "model": settings.model,
                    "output_modalities": ["audio"], "instructions": instructions(call),
                    "audio": {
                        "input": {"format": {"type": "audio/pcmu"},
                                  "turn_detection": {"type": "server_vad", "threshold": 0.5,
                                                     "prefix_padding_ms": 300, "silence_duration_ms": 600,
                                                     "create_response": True, "interrupt_response": True}},
                        "output": {"format": {"type": "audio/pcmu"}, "voice": settings.voice}},
                    "tools": TOOLS, "tool_choice": "auto"},
    }


def realtime_connection(settings, call):
    # Keep credentials on the NUC; never put a key in a WebSocket query.
    # https://developers.openai.com/api/docs/guides/voice-websockets?api=realtime
    return connect(
        "wss://api.openai.com/v1/realtime?" + urlencode({"model": settings.model}),
        additional_headers={"Authorization": "Bearer " + settings.openai_key,
                            "OpenAI-Safety-Identifier": hashlib.sha256(call.caller.encode()).hexdigest()},
        open_timeout=10, close_timeout=2, max_size=2**20, max_queue=32,
    )


async def configure_session(ai, settings, call):
    await ai.send(json.dumps(session_config(settings, call)))
    for _ in range(20):
        event = json.loads(await asyncio.wait_for(ai.recv(), 10))
        if event["type"] == "session.updated":
            return
        if event["type"] == "error":
            raise RuntimeError("Realtime session configuration was rejected.")
    raise RuntimeError("Realtime session acknowledgement was not received.")


class Bridge:
    def __init__(self, socket, ai, settings, call, messages, stream_sid):
        self.socket, self.ai, self.settings, self.call, self.messages = socket, ai, settings, call, messages
        self.stream_sid = stream_sid
        self.timestamp = 0
        self.audio_started = None
        self.last_item = None
        self.generated_ms = 0
        self.marks = deque()
        self.blocked_items = set()
        self.tool_calls = set()
        self.stopping = False

    async def send_ai(self, value):
        await self.ai.send(json.dumps(value))

    async def receive_phone(self):
        while not self.stopping:
            event = await self.socket.receive_json()
            kind = event.get("event")
            if kind == "media":
                self.timestamp = int(event["media"].get("timestamp", self.timestamp))
                await self.send_ai({"type": "input_audio_buffer.append", "audio": event["media"]["payload"]})
            elif kind == "mark":
                name = event.get("mark", {}).get("name")
                if name in self.marks:
                    self.marks.remove(name)
            elif kind == "stop":
                return

    async def interrupt(self):
        if self.last_item and self.marks:
            played_ms = min(self.generated_ms, max(0, self.timestamp - self.audio_started))
            await self.send_ai({"type": "conversation.item.truncate", "item_id": self.last_item,
                                "content_index": 0, "audio_end_ms": played_ms})
            self.blocked_items.add(self.last_item)
        await self.socket.send_json({"event": "clear", "streamSid": self.stream_sid})
        self.marks.clear()
        self.last_item = None
        self.audio_started = None

    async def execute_tool(self, item):
        tool_id = item.get("call_id", "")
        if not tool_id or tool_id in self.tool_calls:
            return False
        self.tool_calls.add(tool_id)
        name = item.get("name")
        try:
            args = json.loads(item.get("arguments", "{}"))
            allowed = {"language"} if name in ("transfer_to_fran", "end_call") else {
                "name", "contact", "summary_es", "language"}
            if not isinstance(args, dict) or set(args) != allowed or args.get("language") not in LANGUAGES:
                raise ValueError("Invalid tool arguments.")
            self.call.language = args["language"]
            if name == "transfer_to_fran":
                if self.call.handoffs >= 1:
                    result = {"success": False, "reason": "Fran could not answer. Offer to save a message."}
                else:
                    self.call.mode = "transfer"
                    self.stopping = True
                    await self.socket.send_json({"event": "clear", "streamSid": self.stream_sid})
                    return True
            elif name == "end_call":
                self.call.mode = "hangup"
                self.stopping = True
                return True
            elif name == "save_message":
                result = {"success": True, "message_id": self.messages.save(self.call, tool_id, args)}
            else:
                result = {"success": False, "reason": "Unknown tool."}
        except (ValueError, TypeError, sqlite3.Error):
            result = {"success": False, "reason": "The operation could not be completed."}
        await self.send_ai({"type": "conversation.item.create", "item": {
            "type": "function_call_output", "call_id": tool_id, "output": json.dumps(result)}})
        await self.send_ai({"type": "response.create"})
        return False

    async def receive_ai(self):
        async for raw in self.ai:
            event = json.loads(raw)
            kind = event.get("type")
            if kind == "response.output_audio.delta":
                item_id = event["item_id"]
                if item_id in self.blocked_items or self.stopping:
                    continue
                if item_id != self.last_item:
                    self.last_item, self.audio_started, self.generated_ms = item_id, self.timestamp, 0
                self.generated_ms += len(base64.b64decode(event["delta"])) // 8
                await self.socket.send_json({"event": "media", "streamSid": self.stream_sid,
                                             "media": {"payload": event["delta"]}})
                mark = secrets.token_hex(8)
                self.marks.append(mark)
                await self.socket.send_json({"event": "mark", "streamSid": self.stream_sid, "mark": {"name": mark}})
            elif kind == "input_audio_buffer.speech_started":
                await self.interrupt()
            elif kind == "response.done":
                response = event.get("response", {})
                if response.get("status") == "failed":
                    self.call.mode = "unavailable"
                    return
                for item in response.get("output", []):
                    if item.get("type") == "function_call" and await self.execute_tool(item):
                        return
            elif kind == "error":
                # Do not log transcripts, phone numbers, instructions or API error payloads.
                self.call.mode = "unavailable"
                LOG.warning("Realtime emitted an error.")
                return
        if not self.stopping:
            self.call.mode = "unavailable"

    async def run(self):
        await self.send_ai({"type": "response.create", "response": {
            "instructions": "Saluda como asistente de IA de Das Werklab en el idioma inicial. "
                            + ("Fran no pudo atender; ofrece continuar o dejar un mensaje." if self.call.resumed
                               else "Pregunta brevemente cómo puedes ayudar.")}})
        remaining = max(0, self.settings.max_seconds - (time.monotonic() - self.call.started))
        tasks = [asyncio.create_task(self.receive_phone()), asyncio.create_task(self.receive_ai()),
                 asyncio.create_task(asyncio.sleep(remaining))]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if tasks[2] in done:
                self.call.mode = "hangup"
            for task in done:
                if task is not tasks[2]:
                    task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def create_app(settings=None, connector=None, probe=True):
    cfg = settings or Settings.from_env()
    connector = connector or realtime_connection
    validator = RequestValidator(cfg.auth_token)
    calls = {}
    messages = Messages(cfg.state_dir)

    @asynccontextmanager
    async def lifespan(app):
        app.state.realtime_ready = False
        if cfg.openai_key and probe:
            try:
                async with connector(cfg, Call("probe", "readiness-probe", "de")) as ai:
                    await configure_session(ai, cfg, Call("probe", "readiness-probe", "de"))
                app.state.realtime_ready = True
            except Exception as error:
                LOG.warning("Realtime readiness failed: %s", type(error).__name__)
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.calls, app.state.messages, app.state.settings = calls, messages, cfg
    app.state.realtime_ready = False

    def public_url(request):
        return cfg.public_base + request.url.path + ("?" + request.url.query if request.url.query else "")

    async def signed_form(request):
        if int(request.headers.get("content-length", "0")) > 65536:
            raise HTTPException(413)
        params = await request.form(max_fields=100)
        if not validator.validate(public_url(request), params, request.headers.get("x-twilio-signature", "")):
            raise HTTPException(403, "Invalid Twilio signature.")
        if params.get("AccountSid") != cfg.account_sid:
            raise HTTPException(403)
        return params

    def xml(value):
        return Response(str(value), media_type="application/xml")

    def say(response, phrase, language):
        response.say(PHRASES[phrase][language], language=LANGUAGES[language])

    def dial(call, phrase="transfer"):
        response = VoiceResponse()
        say(response, phrase, call.language)
        call.handoffs += 1
        call.mode = "dialing"
        # Destination and caller ID come from server configuration, never model arguments.
        # https://www.twilio.com/docs/voice/twiml/dial
        response.dial(cfg.fran_number, caller_id=cfg.phone_number, timeout=20, answer_on_bridge=True,
                      time_limit=1200, action=cfg.public_base + "/dial-ended", method="POST")
        return xml(response)

    def stream(call, renew_ticket=False):
        call.mode = "ai"
        if renew_ticket:
            call.ticket = secrets.token_urlsafe(32)
        response = VoiceResponse()
        connection = response.connect()
        media = connection.stream(url=cfg.public_base.replace("https://", "wss://", 1) + "/media")
        media.parameter(name="ticket", value=call.ticket)
        # Closing the server WebSocket releases Connect, then executes this Redirect.
        # https://www.twilio.com/docs/voice/twiml/stream
        response.redirect(cfg.public_base + "/after-stream", method="POST")
        return xml(response)

    @app.get("/healthz")
    async def health():
        ready = bool(cfg.openai_key and app.state.realtime_ready)
        return JSONResponse({"service": "daswerklab-voice", "ready": ready}, status_code=200 if ready else 503)

    @app.post("/incoming")
    async def incoming(request: Request):
        form = await signed_form(request)
        sid, caller = form.get("CallSid", ""), form.get("From", "")
        if form.get("To") != cfg.phone_number or not re.fullmatch(r"CA[0-9a-fA-F]{32}", sid):
            raise HTTPException(403)
        now = time.monotonic()
        for key in list(calls):
            if now - calls[key].started > cfg.max_seconds + 1500:
                del calls[key]
        call = calls.get(sid)
        if call is not None:
            if call.mode != "ai" or call.stream_connected:
                raise HTTPException(409)
        else:
            call = Call(sid, caller, "es" if caller == cfg.fran_number else "de")
            calls[sid] = call
        if caller in cfg.direct_callers or not cfg.openai_key or len(calls) > cfg.max_calls:
            return dial(call, "transfer" if caller in cfg.direct_callers else "unavailable")
        return stream(call)

    @app.post("/after-stream")
    async def after_stream(request: Request):
        form = await signed_form(request)
        call = calls.get(form.get("CallSid"))
        if call is None:
            raise HTTPException(404)
        if call.mode in ("transfer", "unavailable") and call.handoffs == 0:
            return dial(call, call.mode if call.mode == "unavailable" else "transfer")
        response = VoiceResponse()
        say(response, "goodbye", call.language)
        response.hangup()
        calls.pop(call.sid, None)
        return xml(response)

    @app.post("/dial-ended")
    async def dial_ended(request: Request):
        form = await signed_form(request)
        call = calls.get(form.get("CallSid"))
        if call is None:
            raise HTTPException(404)
        if form.get("DialCallStatus") in ("busy", "no-answer", "failed", "canceled") and cfg.openai_key:
            call.resumed = True
            return stream(call, renew_ticket=True)
        response = VoiceResponse()
        say(response, "goodbye", call.language)
        response.hangup()
        calls.pop(call.sid, None)
        return xml(response)

    @app.post("/status")
    async def status(request: Request):
        form = await signed_form(request)
        if form.get("CallStatus") in ("completed", "busy", "failed", "no-answer", "canceled"):
            calls.pop(form.get("CallSid"), None)
        return Response(status_code=204)

    @app.websocket("/media")
    async def media(socket: WebSocket):
        # Twilio signs the handshake too. Permit only the canonical route (and its
        # documented trailing-slash variant), not arbitrary forwarded Host headers.
        # https://www.twilio.com/docs/usage/security
        canonical = cfg.public_base + "/media"
        candidates = (canonical, canonical + "/", canonical.replace("https://", "wss://", 1),
                      canonical.replace("https://", "wss://", 1) + "/")
        if socket.url.query or not any(validator.validate(url, {}, socket.headers.get("x-twilio-signature", ""))
                                       for url in candidates):
            await socket.close(code=1008)
            return
        await socket.accept()
        call = None
        try:
            for _ in range(3):
                event = await asyncio.wait_for(socket.receive_json(), 5)
                if event.get("event") == "start":
                    break
            else:
                raise ValueError("Missing stream start.")
            start = event["start"]
            call = calls.get(start.get("callSid"))
            if (call is None or call.mode != "ai" or call.stream_connected
                    or start.get("accountSid") != cfg.account_sid
                    or not secrets.compare_digest(start.get("customParameters", {}).get("ticket", ""), call.ticket)
                    or start.get("mediaFormat") != {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}):
                call = None
                raise ValueError("Invalid stream identity.")
            call.stream_connected = True
            async with connector(cfg, call) as ai:
                await configure_session(ai, cfg, call)
                app.state.realtime_ready = True
                await Bridge(socket, ai, cfg, call, messages, start["streamSid"]).run()
        except WebSocketDisconnect:
            pass
        except Exception as error:
            LOG.warning("Voice connection ended: %s", type(error).__name__)
            if call:
                call.mode = "unavailable" if call.handoffs == 0 else "hangup"
        finally:
            if call:
                call.stream_connected = False
            try:
                await socket.close()
            except RuntimeError:
                pass

    return app
