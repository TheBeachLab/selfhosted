#!/usr/bin/env python3
"""First install on the NUC. Does not change Twilio routing or create API keys."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess

SOURCE = Path(__file__).resolve().parent
ROOT = Path("/opt/daswerklab-voice")
SITE = Path("/etc/nginx/sites-available/daswerklab.de")
SNIPPET = Path("/etc/nginx/snippets/daswerklab-voice.conf")
UNIT = Path("/etc/systemd/system/daswerklab-voice.service")
CONFIG = Path("/etc/daswerklab-voice.env")
STATE = Path("/var/lib/daswerklab-voice")
RUNTIME_FILES = ("server.py", "prompt.md", "knowledge.json", "requirements.lock")


def digest(content):
    return hashlib.sha256(content).hexdigest()


def replace_unchanged(path, expected_hash, content):
    if digest(path.read_bytes()) != expected_hash:
        raise RuntimeError("Concurrent modification preserved: " + str(path))
    tmp = path.with_name(path.name + ".voice-tmp")
    with tmp.open("xb") as output:
        output.write(content)
    shutil.copymode(path, tmp)
    tmp.replace(path)


def preflight():
    if os.geteuid() != 0 or socket.gethostname() != "thebeachlab":
        raise RuntimeError("Run as root on the NUC thebeachlab.")
    for path in (ROOT, SNIPPET, UNIT, STATE):
        if path.exists() or path.is_symlink():
            raise RuntimeError("Existing installation path preserved: " + str(path))
    try:
        pwd.getpwnam("daswerklab-voice")
    except KeyError:
        pass
    else:
        raise RuntimeError("Existing service user preserved.")
    if CONFIG.is_symlink() or not CONFIG.is_file():
        raise RuntimeError("Create the owner-only service environment file before installation.")
    stat = CONFIG.stat()
    if stat.st_uid != 0 or stat.st_mode & 0o777 != 0o600:
        raise RuntimeError("Service environment file must be root-owned with mode 0600.")
    if subprocess.check_output(["ss", "-H", "-lnt", "sport = :18090"]).strip():
        raise RuntimeError("Port 18090 is occupied; preserving existing service.")
    before = SITE.read_bytes()
    if before.count(b"    location / {") != 1 or b"daswerklab-voice.conf" in before:
        raise RuntimeError("Unexpected website configuration; preserving it.")
    if b"server_name daswerklab.de www.daswerklab.de;" not in before or b"listen 443 ssl" not in before:
        raise RuntimeError("Expected HTTPS website is unavailable.")
    subprocess.run(["nginx", "-t"], check=True, capture_output=True)
    return before


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    if not re.fullmatch("[0-9a-f]{40}", args.revision):
        raise SystemExit("Pass the integrated Git commit SHA as --revision.")
    before = preflight()
    os.umask(0o077)
    ROOT.mkdir(mode=0o755)
    ROOT.chmod(0o755)
    release = ROOT / "releases" / args.revision
    release.mkdir(parents=True, mode=0o755)
    for name in RUNTIME_FILES:
        shutil.copyfile(SOURCE / name, release / name)
        (release / name).chmod(0o644)
    (ROOT / "current").symlink_to(release)
    (ROOT / "website.before").write_bytes(before)
    subprocess.run(["python3", "-m", "venv", str(ROOT / "venv")], check=True)
    # Do not expose pip configuration or secret environment in subprocess output.
    subprocess.run([str(ROOT / "venv/bin/pip"), "--isolated", "install", "--disable-pip-version-check",
                    "--index-url", "https://pypi.org/simple",
                    "-r", str(release / "requirements.lock")], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Runtime code must be readable by the dedicated service user.
    for folder in (ROOT / "releases", release, ROOT / "venv"):
        folder.chmod(0o755)
    # venv/pip inherit the private umask; allow the service user to read runtime
    # modules while keeping root ownership and all secret files outside this tree.
    for path in (ROOT / "venv").rglob("*"):
        if path.is_symlink():
            continue
        path.chmod(0o755 if path.is_dir() else path.stat().st_mode & 0o777 | 0o444)
    subprocess.run(["useradd", "--system", "--user-group", "--home-dir", str(STATE),
                    "--no-create-home", "--shell", "/usr/sbin/nologin", "daswerklab-voice"], check=True)
    shutil.copyfile(SOURCE / "daswerklab-voice.service", UNIT)
    UNIT.chmod(0o644)
    subprocess.run(["systemd-analyze", "verify", str(UNIT)], check=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "daswerklab-voice"], check=True)
    # Staging without an OpenAI key intentionally returns ready=false/HTTP 503.
    subprocess.run(["python3", "-c",
                    "import json,urllib.request,urllib.error,time\n"
                    "for attempt in range(20):\n"
                    " try:\n"
                    "  try: r=urllib.request.urlopen('http://127.0.0.1:18090/healthz',timeout=2)\n"
                    "  except urllib.error.HTTPError as e: r=e\n"
                    "  assert json.load(r)['service']=='daswerklab-voice'\n"
                    "  break\n"
                    " except Exception:\n"
                    "  if attempt==19: raise\n"
                    "  time.sleep(.5)\n"], check=True)
    shutil.copyfile(SOURCE / "nginx.conf", SNIPPET)
    SNIPPET.chmod(0o644)
    after = before.replace(b"    location / {",
                           b"    include /etc/nginx/snippets/daswerklab-voice.conf;\n\n    location / {", 1)
    replace_unchanged(SITE, digest(before), after)
    try:
        subprocess.run(["nginx", "-t"], check=True, capture_output=True)
        subprocess.run(["systemctl", "reload", "nginx"], check=True)
    except Exception:
        replace_unchanged(SITE, digest(after), before)
        subprocess.run(["nginx", "-t"], check=True, capture_output=True)
        subprocess.run(["systemctl", "reload", "nginx"], check=True)
        raise
    receipt = {"revision": args.revision, "website_before_sha256": digest(before),
               "website_after_sha256": digest(after), "twilio_routing_changed": False,
               "runtime_files": {name: digest((release / name).read_bytes()) for name in RUNTIME_FILES}}
    (STATE / "installation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"installed": True, "revision": args.revision,
                      "endpoint": "https://daswerklab.de/voice/healthz", "twilio_activated": False}))


if __name__ == "__main__":
    main()
