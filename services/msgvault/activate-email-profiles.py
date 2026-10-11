#!/usr/bin/env python3
"""Activate the tested native build on the existing NUC, with rollback.

The daemon continues to own all database writes. An encrypted NAS backup must
succeed before replacing the binary. Credentials are hashed, never printed.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import subprocess
import time
import urllib.request
import uuid

STOCK_SHA256 = "2e00619b03f9914aaece4f6458299dc66bc9f6386856098ea9329c889d0a5a1e"
NEW_BINARY = Path("/opt/msgvault/0.21.0-email-2/msgvault")
LINK = Path("/usr/local/bin/msgvault")
DROPIN = Path("/etc/systemd/system/msgvault.service.d/30-people-email-evidence.conf")
UNITS = ["msgvault.service", "msgvault-mcp.service"]
CONFIG = Path("/var/lib/msgvault/config.toml")


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def credentials():
    return {
        str(p): digest(p)
        for p in Path("/var/lib/msgvault/tokens").glob("**/*.json")
        if "provider" in str(p)
    }


def owner_key():
    config = Path("/var/lib/msgvault/config.toml").read_text()
    section = re.search(r"(?ms)^\[server\]\s*\n(.*?)(?=^\[|\Z)", config).group(1)
    return re.search(r"(?m)^\s*api_key\s*=\s*[^\n]*?([0-9a-f]{64})", section).group(1)


def health():
    request = urllib.request.Request(
        "http://127.0.0.1:8096/health",
        headers={"Authorization": "Bearer " + owner_key()},
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        payload = json.load(response)
    if payload.get("status") != "ok":
        raise RuntimeError("Native health did not report ok")
    return payload


def wait_ready():
    for _ in range(30):
        try:
            return health()
        except (OSError, ValueError, RuntimeError):
            time.sleep(1)
    raise RuntimeError("Daemon did not become healthy within 30 seconds")


def replace_link(target):
    temporary = LINK.with_name(".msgvault-email-" + uuid.uuid4().hex)
    try:
        temporary.symlink_to(target)
        os.replace(temporary, LINK)
    finally:
        temporary.unlink(missing_ok=True)


def email_provider_config(original):
    text = original.decode()
    pattern = r"(?ms)^([ \t]*\[people\.sweep\.providers\.openai\][^\n]*\n)(.*?)(?=^[ \t]*\[|\Z)"
    found = re.search(pattern, text)
    if found is None:
        raise RuntimeError("Expected the existing named OpenAI provider")
    body = found.group(2)
    for field, value in [("output_mode", "json_object"), ("source_since", "2023-01-01")]:
        body, count = re.subn(r'(?m)^(\s*' + field + r'\s*=\s*)"[^"\n]*"',
                              lambda m: m.group(1) + json.dumps(value), body)
        if count != 1:
            raise RuntimeError("Expected exactly one provider field: " + field)
    return (text[:found.start(2)] + body + text[found.end(2):]).encode()


def save_config(content):
    metadata = CONFIG.stat()
    fd, name = tempfile.mkstemp(prefix=".email-profiles-", dir=CONFIG.parent)
    try:
        os.fchmod(fd, metadata.st_mode & 0o777)
        os.fchown(fd, metadata.st_uid, metadata.st_gid)
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, CONFIG)
    finally:
        Path(name).unlink(missing_ok=True)


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run with sudo on the existing Msgvault host")
    os.umask(0o077)
    if not LINK.is_symlink() or not NEW_BINARY.is_file():
        raise SystemExit("Expected existing symlink and tested native build")
    old_target = LINK.resolve(strict=True)
    previous_local = Path("/opt/msgvault/0.21.0-email-1/msgvault")
    if old_target == previous_local:
        command("sha256sum", "--check", str(previous_local.parent / "SHA256SUMS"))
    elif digest(old_target) != STOCK_SHA256:
        raise SystemExit("Existing daemon differs from the verified stock build; preserving it")
    command("sha256sum", "--check", str(NEW_BINARY.parent / "SHA256SUMS"))
    version = command(str(NEW_BINARY), "version")
    if "v0.21.0-email-2" not in version:
        raise SystemExit("Unexpected candidate build")
    content = Path(__file__).with_name("people-email-evidence.conf").read_bytes()
    previous_dropin = DROPIN.is_file() and not DROPIN.is_symlink() and DROPIN.read_bytes() == content
    if (DROPIN.exists() or DROPIN.is_symlink()) and not previous_dropin:
        raise SystemExit("Preserving existing email-evidence drop-in")
    # The existing backup runner checks the NAS mount and encrypted repository.
    command("systemctl", "start", "msgvault-backup.service")
    result = command("systemctl", "show", "msgvault-backup.service", "--property=Result", "--value").strip()
    if result != "success":
        raise SystemExit("Encrypted NAS backup did not succeed")
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    checkpoint = Path("/var/lib/msgvault-backup") / ("email-profiles-" + stamp)
    checkpoint.mkdir(mode=0o700)
    receipt = {
        "old_binary": str(old_target), "old_sha256": digest(old_target),
        "new_binary": str(NEW_BINARY), "new_sha256": digest(NEW_BINARY),
        "credential_hashes_before": credentials(), "nas_backup": result,
    }
    original_config = CONFIG.read_bytes()
    updated_config = email_provider_config(original_config)
    (checkpoint / "config-before.toml").write_bytes(original_config)
    (checkpoint / "activation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    try:
        command("systemctl", "stop", *UNITS)
        if CONFIG.read_bytes() != original_config:
            raise RuntimeError("Configuration changed during activation; preserving it")
        save_config(updated_config)
        DROPIN.parent.mkdir(mode=0o755, exist_ok=True)
        if not previous_dropin:
            with DROPIN.open("xb") as output:
                output.write(content)
        DROPIN.chmod(0o644)
        replace_link(NEW_BINARY)
        command("systemctl", "daemon-reload")
        command("systemctl", "start", *UNITS)
        receipt["health"] = wait_ready()
        command("systemctl", "is-active", *UNITS)
        receipt["credential_hashes_after"] = credentials()
        if receipt["credential_hashes_after"] != receipt["credential_hashes_before"]:
            raise RuntimeError("Provider credential files changed unexpectedly")
        receipt["activated"] = True
    except BaseException:
        command("systemctl", "stop", *UNITS)
        replace_link(old_target)
        if not previous_dropin and DROPIN.is_file() and DROPIN.read_bytes() == content:
            DROPIN.unlink()
        if CONFIG.read_bytes() == updated_config:
            save_config(original_config)
        command("systemctl", "daemon-reload")
        command("systemctl", "start", *UNITS)
        wait_ready()
        receipt["activated"] = False
        receipt["rolled_back"] = True
        (checkpoint / "activation.json").write_text(json.dumps(receipt, indent=2) + "\n")
        raise
    (checkpoint / "activation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"activated": True, "checkpoint": str(checkpoint), "version": "v0.21.0-email-2"}))


if __name__ == "__main__":
    main()
