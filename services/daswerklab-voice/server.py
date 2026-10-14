#!/usr/bin/env python3
"""Signed Twilio bridge to OpenAI conversation and selectable streamed speech."""
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
    voice: str = "cedar"
    state_dir: Path = Path("/var/lib/daswerklab-voice")
    max_seconds: int = 600
    max_calls: int = 4
    direct_callers: tuple = ()
    vad_threshold: float = 0.8
    noise_reduction: str = "near_field"
    voice_provider: str = "openai"
    eleven_key: str = field(default="", repr=False)
    eleven_voice: str = "cllvQaMvj0ZKxH88HGEn"
    eleven_model: str = "eleven_v4_turbo"

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
        if not 0 <= self.vad_threshold <= 1 or self.noise_reduction not in ("near_field", "far_field", "off"):
            raise ValueError("Invalid voice activity or noise reduction setting.")
        if self.voice_provider not in ("openai", "elevenlabs"):
            raise ValueError("Invalid voice provider.")
        if self.voice_provider == "elevenlabs" and (not self.eleven_key
                or not re.fullmatch(r"[A-Za-z0-9]{20}", self.eleven_voice)
                or self.eleven_model != "eleven_v4_turbo"):
            raise ValueError("ElevenLabs requires its key, voice ID and supported streaming model.")

    @classmethod
    def from_env(cls):
        env = os.environ
        return cls(
            env["PUBLIC_BASE_URL"], env["TWILIO_ACCOUNT_SID"], env["TWILIO_AUTH_TOKEN"],
            env["TWILIO_PHONE_NUMBER"], env["FRAN_PHONE_NUMBER"], env.get("OPENAI_API_KEY", ""),
            env.get("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1"),
            env.get("OPENAI_REALTIME_VOICE", "cedar"),
            Path(env.get("STATE_DIR", "/var/lib/daswerklab-voice")),
            int(env.get("MAX_CALL_SECONDS", "600")), int(env.get("MAX_CONCURRENT_CALLS", "4")),
            tuple(x.strip() for x in env.get("DIRECT_CALLERS", "").split(",") if x.strip()),
            float(env.get("VAD_THRESHOLD", "0.8")), env.get("INPUT_NOISE_REDUCTION", "near_field"),
            env.get("VOICE_PROVIDER", "openai"), env.get("ELEVENLABS_API_KEY", ""),
            env.get("ELEVENLABS_VOICE_ID", "cllvQaMvj0ZKxH88HGEn"),
            env.get("ELEVENLABS_MODEL", "eleven_v4_turbo"),
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
        text += "\nFran no pudo atender la transferencia. Ofrece continuar o dejar un mensaje."
    return text


def session_config(settings, call):
    # OpenAI GA schema and PCMU:
    # https://developers.openai.com/api/docs/guides/realtime-conversations
    config = {
        "type": "session.update",
        "session": {"type": "realtime", "model": settings.model,
                    "output_modalities": ["audio"], "instructions": instructions(call),
                    "audio": {
                        "input": {"format": {"type": "audio/pcmu"},
                                  # Filter telephone microphone noise before VAD. A higher
                                  # threshold reduces false starts while retaining spoken barge-in.
                                  # https://developers.openai.com/api/reference/resources/realtime/client-events
                                  "noise_reduction": (None if settings.noise_reduction == "off" else
                                                      {"type": settings.noise_reduction}),
                                  "turn_detection": {"type": "server_vad", "threshold": settings.vad_threshold,
                                                     "prefix_padding_ms": 300, "silence_duration_ms": 600,
                                                     "create_response": True, "interrupt_response": True}},
                        "output": {"format": {"type": "audio/pcmu"}, "voice": settings.voice}},
                    "tools": TOOLS, "tool_choice": "auto"},
    }
    if settings.voice_provider == "elevenlabs":
        # OpenAI still understands caller audio and chooses tools. ElevenLabs
        # speaks streamed output_text; there is no second generated OpenAI voice.
        config["session"]["output_modalities"] = ["text"]
        del config["session"]["audio"]["output"]
        if settings.eleven_voice == "cllvQaMvj0ZKxH88HGEn":
            config["session"]["instructions"] += "\nLa voz es femenina; usa formas femeninas al presentarte en alemán."
    return config


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


def eleven_connection(settings):
    # v4 Turbo uses Text to Dialogue, not the legacy TTS stream-input endpoint.
    # https://elevenlabs.io/docs/eleven-api/guides/how-to/websockets/realtime-tdd
    return connect("wss://api.elevenlabs.io/v1/text-to-dialogue/stream-input?" + urlencode({
        "model_id": settings.eleven_model, "output_format": "ulaw_8000", "sync_alignment": "true"}),
        additional_headers={"xi-api-key": settings.eleven_key}, open_timeout=10, close_timeout=2,
        max_size=2**20, max_queue=32)


async def probe_eleven(settings, connector):
    # Register the voice and close without text: check authentication/configuration
    # without synthesizing a greeting on each service start.
    async with connector(settings) as speech:
        await speech.send(json.dumps({"voices": [settings.eleven_voice]}))
        await speech.send(json.dumps({"close_socket": True}))
        for _ in range(10):
            event = json.loads(await asyncio.wait_for(speech.recv(), 10))
            if event.get("error"):
                raise RuntimeError("ElevenLabs rejected the speech configuration.")
            if event.get("is_final"):
                return
    raise RuntimeError("ElevenLabs did not acknowledge the speech configuration.")


@dataclass
class Utterance:
    item_id: str
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=64))
    text: str = ""
    audio_ms: int = 0
    alignment: list = field(default_factory=list)
    finished: bool = False
    cancelled: bool = False
    task: object = None

    def heard_text(self, played_ms):
        # Alignment times are relative to their audio chunk. Never substitute the
        # complete generated text when timing is unavailable: it may be unheard.
        return "".join(char for end, char in self.alignment if end <= played_ms).strip()


class ElevenSpeech:
    def __init__(self, bridge, connector):
        self.bridge, self.connector = bridge, connector
        self.entries, self.repairs = {}, []
        self.failures = asyncio.Queue(maxsize=1)

    def completed(self, task):
        if not task.cancelled() and task.exception() is not None and self.failures.empty():
            self.failures.put_nowait(True)

    async def failure(self):
        await self.failures.get()
        raise RuntimeError("External speech generation failed.")

    def feed(self, item_id, text):
        if item_id in self.bridge.blocked_items or self.bridge.stopping:
            return
        entry = self.entries.get(item_id)
        if entry is None:
            entry = self.entries[item_id] = Utterance(item_id)
            entry.task = asyncio.create_task(self.synthesize(entry))
            entry.task.add_done_callback(self.completed)
        if entry.finished or entry.cancelled:
            return
        if not isinstance(text, str) or len(entry.text) + len(text) > 8000:
            raise ValueError("Speech response exceeded its text limit.")
        entry.text += text
        entry.queue.put_nowait(text)

    def finish(self, item_id):
        entry = self.entries.get(item_id)
        if entry and not entry.finished and not entry.cancelled:
            entry.finished = True
            entry.queue.put_nowait(None)

    async def synthesize(self, entry):
        async with self.connector(self.bridge.settings) as speech:
            await speech.send(json.dumps({"voices": [self.bridge.settings.eleven_voice]}))

            async def send_text():
                while True:
                    text = await entry.queue.get()
                    if text is None:
                        await speech.send(json.dumps({"close_socket": True}))
                        return
                    await speech.send(json.dumps({"inputs": [{"text": text,
                        "voice_id": self.bridge.settings.eleven_voice, "new_turn": False}]}))

            sender = asyncio.create_task(send_text())
            try:
                while True:
                    event = json.loads(await asyncio.wait_for(speech.recv(), 20))
                    if event.get("error"):
                        raise RuntimeError("ElevenLabs rejected speech generation.")
                    if event.get("audio") and not entry.cancelled:
                        audio = base64.b64decode(event["audio"], validate=True)
                        offset = entry.audio_ms
                        alignment = event.get("alignment") or {}
                        chars, starts, lengths = (alignment.get("chars", []),
                            alignment.get("char_start_times_ms", []), alignment.get("char_durations_ms", []))
                        if len(chars) == len(starts) == len(lengths):
                            entry.alignment.extend((offset + float(start) + float(length), char)
                                for char, start, length in zip(chars, starts, lengths))
                        entry.audio_ms += len(audio) // 8
                        await self.bridge.send_audio(entry.item_id, event["audio"])
                    if event.get("is_final"):
                        await sender
                        return
            finally:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)

    async def interrupt(self):
        bridge = self.bridge
        async with bridge.audio_lock:
            for entry in self.entries.values():
                pending = not entry.task.done() or entry.item_id == bridge.last_item and bool(bridge.marks)
                if not pending or entry.cancelled:
                    continue
                played = (min(bridge.generated_ms, max(0, bridge.timestamp - bridge.audio_started))
                          if entry.item_id == bridge.last_item and bridge.audio_started is not None else 0)
                self.repairs.append((entry.item_id, entry.heard_text(played),
                                     bridge.previous_items.get(entry.item_id) or "root"))
                entry.cancelled = True
                bridge.blocked_items.add(entry.item_id)
                entry.task.cancel()
            await bridge.socket.send_json({"event": "clear", "streamSid": bridge.stream_sid})
            bridge.marks.clear()
            bridge.last_item, bridge.audio_started = None, None
        if not bridge.active_response:
            await self.repair_history()

    async def repair_history(self):
        # item.truncate applies to audio, not text. Remove unplayed assistant text
        # and retain only words covered by the speech provider's timing alignment.
        # https://developers.openai.com/api/reference/resources/realtime/client-events
        replacements = {}
        for item_id, heard, previous in self.repairs:
            previous = replacements.get(previous, previous)
            await self.bridge.send_ai({"type": "conversation.item.delete", "item_id": item_id})
            if heard:
                replacement = "item_" + secrets.token_hex(12)
                await self.bridge.send_ai({"type": "conversation.item.create", "previous_item_id": previous, "item": {
                    "id": replacement, "type": "message", "role": "assistant", "content": [
                        {"type": "output_text", "text": heard + " [interrupted]"}]}})
                replacements[item_id] = replacement
            else:
                replacements[item_id] = previous
        self.repairs.clear()

    async def close(self):
        tasks = [entry.task for entry in self.entries.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class Bridge:
    def __init__(self, socket, ai, settings, call, messages, stream_sid, speech_connector=None):
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
        self.audio_lock = asyncio.Lock()
        self.active_response = None
        self.previous_items = {}
        self.speech = (ElevenSpeech(self, speech_connector or eleven_connection)
                       if settings.voice_provider == "elevenlabs" else None)

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
        if self.speech:
            await self.speech.interrupt()
            return
        if self.last_item and self.marks:
            played_ms = min(self.generated_ms, max(0, self.timestamp - self.audio_started))
            await self.send_ai({"type": "conversation.item.truncate", "item_id": self.last_item,
                                "content_index": 0, "audio_end_ms": played_ms})
            self.blocked_items.add(self.last_item)
        await self.socket.send_json({"event": "clear", "streamSid": self.stream_sid})
        self.marks.clear()
        self.last_item = None
        self.audio_started = None

    async def send_audio(self, item_id, payload):
        # Serialize speech packets with clear so a suspended send cannot deliver
        # stale voice after the caller's interruption.
        async with self.audio_lock:
            if item_id in self.blocked_items or self.stopping:
                return
            if item_id != self.last_item:
                self.last_item, self.audio_started, self.generated_ms = item_id, self.timestamp, 0
            self.generated_ms += len(base64.b64decode(payload)) // 8
            await self.socket.send_json({"event": "media", "streamSid": self.stream_sid,
                                         "media": {"payload": payload}})
            mark = secrets.token_hex(8)
            self.marks.append(mark)
            await self.socket.send_json({"event": "mark", "streamSid": self.stream_sid, "mark": {"name": mark}})

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
                    async with self.audio_lock:
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
                if not self.speech:
                    await self.send_audio(event["item_id"], event["delta"])
            elif kind == "response.created":
                self.active_response = event["response"]["id"]
            elif kind == "conversation.item.added":
                self.previous_items[event["item"]["id"]] = event.get("previous_item_id")
            elif kind == "response.output_text.delta" and self.speech:
                self.speech.feed(event["item_id"], event["delta"])
            elif kind == "response.output_text.done" and self.speech:
                self.speech.finish(event["item_id"])
            elif kind == "input_audio_buffer.speech_started":
                await self.interrupt()
            elif kind == "response.done":
                self.active_response = None
                response = event.get("response", {})
                if self.speech:
                    for item in response.get("output", []):
                        if item.get("type") == "message":
                            self.speech.finish(item["id"])
                    await self.speech.repair_history()
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
            # Per-response instructions override the session's instructions;
            # include the actual language rather than referring to its default.
            # https://developers.openai.com/api/reference/resources/realtime/client-events
            "instructions": "Give this greeting entirely in " + LANGUAGES[self.call.language]
                            + ". Introduce yourself as Fran's virtual assistant at Das Werklab. "
                            + ("Use the feminine grammatical form for your role. "
                               if self.speech and self.settings.eleven_voice == "cllvQaMvj0ZKxH88HGEn" else "")
                            + ("Fran could not answer; offer to continue or leave a message." if self.call.resumed
                               else "Briefly ask how you can help.")}})
        remaining = max(0, self.settings.max_seconds - (time.monotonic() - self.call.started))
        tasks = [asyncio.create_task(self.receive_phone()), asyncio.create_task(self.receive_ai()),
                 asyncio.create_task(asyncio.sleep(remaining))]
        if self.speech:
            tasks.append(asyncio.create_task(self.speech.failure()))
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
            if self.speech:
                await self.speech.close()


def create_app(settings=None, connector=None, probe=True, speech_connector=None):
    cfg = settings or Settings.from_env()
    connector = connector or realtime_connection
    speech_connector = speech_connector or eleven_connection
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
                if cfg.voice_provider == "elevenlabs":
                    await probe_eleven(cfg, speech_connector)
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
            call = Call(sid, caller, "de")
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
                await Bridge(socket, ai, cfg, call, messages, start["streamSid"], speech_connector).run()
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
            except (RuntimeError, WebSocketDisconnect):
                pass

    return app
