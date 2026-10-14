#!/usr/bin/env python3
"""Public launch page and a consent-based, double-opt-in list. No accounting access.

Consent: GDPR Articles 6(1)(a), 7 and 13; German UWG section 7(2)(2).
https://eur-lex.europa.eu/eli/reg/2016/679/oj
https://www.gesetze-im-internet.de/uwg_2004/__7.html
"""
import argparse
import csv
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import smtplib
import sqlite3
import ssl
import threading
import time
from urllib.parse import urlsplit

PUBLIC = Path(__file__).parent / "public"
LANGUAGES = {"de", "es", "en", "fr", "it", "pt"}
CONSENT_VERSION = "launch-one-email-2026-10-14-v1"
PENDING_SECONDS = 48 * 3600
RETENTION_END = 1806537600  # 2027-04-01 00:00:00 UTC; no indefinite list.
MAIL = {
    "de": ("Bestätige deine E-Mail-Adresse für Mebuko", "Du möchtest eine E-Mail zum Start von Mebuko am 01.01.2027 erhalten.", "Bitte öffne diesen Link und bestätige deine Anmeldung:", "Der Link gilt 48 Stunden. Falls du dich nicht angemeldet hast, ignoriere diese Nachricht. Ohne Bestätigung wirst du nicht in die Liste aufgenommen.", "Anmeldung zurückziehen:"),
    "es": ("Confirma tu email para Mebuko", "Has solicitado un email para el lanzamiento de Mebuko, previsto para el 01/01/2027.", "Abre este enlace y confirma tu inscripción:", "El enlace caduca en 48 horas. Si no te has inscrito, ignora este correo. Sin confirmación no te añadiremos a la lista.", "Retirar la inscripción:"),
    "en": ("Confirm your email for Mebuko", "You requested one email when Mebuko launches, planned for 1 January 2027.", "Open this link and confirm your request:", "This link expires in 48 hours. If you did not sign up, ignore this message. You will not join the list without confirmation.", "Withdraw your request:"),
    "fr": ("Confirme ton adresse email pour Mebuko", "Tu as demandé un email pour le lancement de Mebuko, prévu le 01/01/2027.", "Ouvre ce lien et confirme ton inscription :", "Ce lien expire dans 48 heures. Si tu ne t'es pas inscrit, ignore ce message. Sans confirmation, tu ne seras pas ajouté à la liste.", "Retirer ton inscription :"),
    "it": ("Conferma la tua email per Mebuko", "Hai richiesto un'email al lancio di Mebuko, previsto per il 01/01/2027.", "Apri questo link e conferma l'iscrizione:", "Il link scade tra 48 ore. Se non ti sei iscritto, ignora questo messaggio. Senza conferma non verrai aggiunto alla lista.", "Ritira l'iscrizione:"),
    "pt": ("Confirma o teu email para o Mebuko", "Pediste um email para o lançamento do Mebuko, previsto para 01/01/2027.", "Abre este link e confirma a inscrição:", "O link expira em 48 horas. Se não te inscreveste, ignora esta mensagem. Sem confirmação não entrarás na lista.", "Retirar a inscrição:"),
}


class RequestError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


def load_env(path):
    if path:
        p = Path(path)
        if p.stat().st_mode & 0o007:
            raise ValueError("Private configuration must not be world-readable")
        for line in p.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                parts = shlex.split(line)
                if len(parts) != 1 or "=" not in parts[0]:
                    raise ValueError("Invalid private configuration line")
                key, value = parts[0].split("=", 1)
                if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                    raise ValueError("Invalid configuration key")
                os.environ[key] = value


def normalize_email(value):
    if not isinstance(value, str):
        raise RequestError(400, "invalid_email")
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value):
        raise RequestError(400, "invalid_email")
    local, domain = value.rsplit("@", 1)
    if len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in value:
        raise RequestError(400, "invalid_email")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in domain.split(".")):
        raise RequestError(400, "invalid_email")
    return value.lower()


class LaunchList:
    def __init__(self, path, secret, base_url, sender=None, clock=time.time):
        if len(secret) < 48:
            raise ValueError("A strong private token secret is required")
        self.path, self.secret, self.base = Path(path), secret.encode(), base_url.rstrip("/")
        self.sender, self.clock, self.lock = sender or self.send_mail, clock, threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS subscribers (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, language TEXT NOT NULL,
                    requested_at INTEGER NOT NULL, confirmed_at INTEGER, mailed_at INTEGER,
                    consent_version TEXT NOT NULL, nonce TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rate_limits (
                    kind TEXT NOT NULL, fingerprint TEXT NOT NULL, occurred_at INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS rate_time ON rate_limits(occurred_at);
            """)
        os.chmod(self.path, 0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA secure_delete=ON")
        return db

    def sign(self, purpose, row):
        data = f"{purpose}:{row['id']}:{row['nonce']}"
        return row["id"] + "." + hmac.new(self.secret, data.encode(), hashlib.sha256).hexdigest()

    def token_row(self, db, token, purpose):
        if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{32}\.[a-f0-9]{64}", token):
            raise RequestError(400, "invalid_link")
        row = db.execute("SELECT * FROM subscribers WHERE id=?", (token.split(".")[0],)).fetchone()
        if not row or not hmac.compare_digest(token, self.sign(purpose, row)):
            raise RequestError(400, "invalid_link")
        return row

    def fingerprint(self, value):
        return hmac.new(self.secret, value.encode(), hashlib.sha256).hexdigest()

    def prune(self, db, now):
        db.execute("DELETE FROM rate_limits WHERE occurred_at<?", (now - 86400,))
        db.execute("DELETE FROM subscribers WHERE confirmed_at IS NULL AND requested_at<?", (now - PENDING_SECONDS,))
        if now >= RETENTION_END:
            db.execute("DELETE FROM subscribers")

    def subscribe(self, email, language, consent, website, ip):
        if website:
            return {"code": "check_email"}
        if consent is not True:
            raise RequestError(400, "consent_required")
        email = normalize_email(email)
        language = language if language in LANGUAGES else "de"
        now = int(self.clock())
        if now >= RETENTION_END:
            raise RequestError(410, "list_closed")
        with self.lock, self.connect() as db:
            self.prune(db, now)
            # Only transient keyed fingerprints; no raw IP or email in rate records.
            ip_key = self.fingerprint("ip:" + ip)
            email_key = self.fingerprint("email:" + email)
            for kind, key, seconds, limit in (("ip", ip_key, 3600, 3), ("email", email_key, 3600, 1), ("global", "all", 86400, 100)):
                count = db.execute("SELECT count(*) FROM rate_limits WHERE kind=? AND fingerprint=? AND occurred_at>?", (kind, key, now - seconds)).fetchone()[0]
                if count >= limit:
                    raise RequestError(429, "rate_limit")
            old = db.execute("SELECT * FROM subscribers WHERE email=?", (email,)).fetchone()
            if old and old["confirmed_at"]:
                return {"code": "check_email"}
            row = {"id": old["id"] if old else secrets.token_hex(16), "nonce": secrets.token_hex(24), "email": email, "language": language, "requested_at": now}
            # Send before commit: provider failure must never silently accept an email.
            self.sender(row, self.sign("confirm", row), self.sign("unsubscribe", row))
            db.execute("INSERT OR REPLACE INTO subscribers VALUES (?,?,?,?,NULL,?,?,?)", (row["id"], email, language, now, now, CONSENT_VERSION, row["nonce"]))
            for kind, key in (("ip", ip_key), ("email", email_key), ("global", "all")):
                db.execute("INSERT INTO rate_limits VALUES (?,?,?)", (kind, key, now))
        return {"code": "check_email"}

    def confirm(self, token):
        now = int(self.clock())
        with self.lock, self.connect() as db:
            row = self.token_row(db, token, "confirm")
            if now - row["requested_at"] > PENDING_SECONDS or now >= RETENTION_END:
                raise RequestError(410, "expired_link")
            db.execute("UPDATE subscribers SET confirmed_at=COALESCE(confirmed_at,?) WHERE id=?", (now, row["id"]))
        return {"code": "confirmed"}

    def unsubscribe(self, token):
        with self.lock, self.connect() as db:
            row = self.token_row(db, token, "unsubscribe")
            db.execute("DELETE FROM subscribers WHERE id=?", (row["id"],))
            # Minimize residual email data after deletion; database is small.
        with self.connect() as db:
            db.execute("VACUUM")
        return {"code": "unsubscribed"}

    def send_mail(self, row, confirm, unsubscribe):
        text = MAIL[row["language"]]
        msg = EmailMessage()
        msg["Subject"] = text[0]
        msg["From"] = formataddr(("Mebuko · Francisco Sánchez Arroyo", os.environ.get("MEBUKO_MAIL_FROM", "fran@daswerklab.de")))
        msg["To"] = row["email"]
        msg["Reply-To"] = "fran@daswerklab.de"
        msg["Message-ID"] = make_msgid(domain="daswerklab.de")
        msg.set_content("\n\n".join((text[1], text[2], f"{self.base}/confirm?token={confirm}&lang={row['language']}", text[3], text[4], f"{self.base}/unsubscribe?token={unsubscribe}&lang={row['language']}", "Francisco Sánchez Arroyo\nAm Schützeneck 2a · 81241 München · Deutschland\nfran@daswerklab.de", f"Datenschutz / Privacy: {self.base}/datenschutz?lang={row['language']}")))
        # Apple official settings: https://support.apple.com/en-gb/102525
        with smtplib.SMTP("smtp.mail.me.com", 587, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(os.environ["MEBUKO_SMTP_USER"], os.environ["MEBUKO_SMTP_PASSWORD"])
            smtp.send_message(msg)


class Handler(BaseHTTPRequestHandler):
    server_version = "Mebuko"
    def log_message(self, *_):
        pass  # Nginx logs URI only, never confirmation tokens or email bodies.

    def reply(self, status, content, mime="application/json; charset=utf-8"):
        data = content if isinstance(content, bytes) else json.dumps(content).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if mime.startswith("application/json") or urlsplit(self.path).path in ("/confirm", "/unsubscribe") else "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/_health":
            return self.reply(200, {"ok": True})
        routes = {"/": "index.html", "/impressum": "impressum.html", "/datenschutz": "datenschutz.html", "/confirm": "action.html", "/unsubscribe": "action.html", "/app.js": "app.js", "/style.css": "style.css", "/robots.txt": "robots.txt", "/sitemap.xml": "sitemap.xml"}
        if path.startswith("/assets/") and re.fullmatch(r"/assets/[a-z0-9.-]+", path):
            file = PUBLIC / path.lstrip("/")
        elif path in routes:
            file = PUBLIC / routes[path]
        else:
            return self.reply(404, {"code": "not_found"})
        if not file.is_file():
            return self.reply(404, {"code": "not_found"})
        mime = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".webp": "image/webp", ".png": "image/png", ".svg": "image/svg+xml", ".txt": "text/plain; charset=utf-8", ".xml": "application/xml"}.get(file.suffix, "application/octet-stream")
        return self.reply(200, file.read_bytes(), mime)

    def do_POST(self):
        try:
            if self.headers.get("Origin") != self.server.launch_list.base:
                raise RequestError(403, "invalid_origin")
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise RequestError(415, "invalid_request")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                raise RequestError(413, "invalid_request")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise RequestError(400, "invalid_request")
            path = urlsplit(self.path).path
            if path == "/api/subscribe":
                # Trust forwarded client addresses only from the loopback Nginx proxy.
                forwarded = self.headers.get("X-Real-IP", "")
                ip = str(ipaddress.ip_address(forwarded)) if self.client_address[0] == "127.0.0.1" and forwarded else self.client_address[0]
                result = self.server.launch_list.subscribe(data.get("email"), data.get("language"), data.get("consent"), data.get("website"), ip)
            elif path == "/api/confirm":
                result = self.server.launch_list.confirm(data.get("token"))
            elif path == "/api/unsubscribe":
                result = self.server.launch_list.unsubscribe(data.get("token"))
            else:
                raise RequestError(404, "not_found")
            self.reply(200, result)
        except RequestError as e:
            self.reply(e.status, {"code": e.code})
        except (ValueError, TypeError, json.JSONDecodeError):
            self.reply(400, {"code": "invalid_request"})
        except (smtplib.SMTPException, OSError, KeyError, sqlite3.Error):
            self.reply(503, {"code": "mail_unavailable"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("serve", "prune", "export", "init"))
    parser.add_argument("--env-file")
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    load_env(args.env_file)
    base = os.environ.get("MEBUKO_BASE_URL", "https://mebuko.de")
    if base != "https://mebuko.de" and not (args.development and re.fullmatch(r"http://127\.0\.0\.1:[0-9]+", base)):
        raise ValueError("Only the canonical HTTPS origin is allowed outside development")
    app = LaunchList(os.environ.get("MEBUKO_DB", "/var/lib/mebuko/subscribers.sqlite3"), os.environ["MEBUKO_TOKEN_SECRET"], base)
    if args.command == "serve":
        server = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("MEBUKO_PORT", "8099"))), Handler)
        server.launch_list = app
        server.serve_forever()
    elif args.command == "prune":
        with app.connect() as db:
            app.prune(db, int(time.time()))
        with app.connect() as db:
            db.execute("VACUUM")
    elif args.command == "export":
        if not args.output:
            parser.error("Export requires a private --output path")
        path = Path(args.output)
        with app.connect() as db:
            rows = db.execute("SELECT * FROM subscribers WHERE confirmed_at IS NOT NULL").fetchall()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(("email", "language", "confirmed_at", "consent_version", "unsubscribe_url"))
            for r in rows:
                writer.writerow((r["email"], r["language"], r["confirmed_at"], r["consent_version"], app.base + "/unsubscribe?token=" + app.sign("unsubscribe", r) + "&lang=" + r["language"]))
    print("Mebuko command completed; no subscriber data in logs.")


if __name__ == "__main__":
    main()
