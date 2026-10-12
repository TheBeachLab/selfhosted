#!/usr/bin/env python3
"""Upgrade native signed-mail briefs with a verified NAS backup and rollback.

No credentials or mail text enter stdout. The timer and daemon own analysis.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import uuid

SOURCE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("setup", SOURCE / "install-identity-jev.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)
LINK = Path("/usr/local/bin/msgvault")
NEW = Path("/opt/msgvault/0.21.0-signed-brief-1/msgvault")
OLD_SHA = "f4b5b18271d014b2310a6b297206b0c77d858c4d84c2ce23ecb23e1426daab95"
RUNNER = Path("/usr/local/sbin/msgvault-mailbox-discovery")
TIMER = "msgvault-mailbox-discovery.timer"
SERVICE = "msgvault-mailbox-discovery.service"
UNITS = ["msgvault.service", "msgvault-mcp.service"]


def replace_link(target):
    temporary = LINK.with_name(".msgvault-signed-" + uuid.uuid4().hex)
    try:
        temporary.symlink_to(target)
        os.replace(temporary, LINK)
    finally:
        temporary.unlink(missing_ok=True)


def credential_hashes():
    return {str(p): setup.digest(p) for p in Path("/var/lib/msgvault/tokens").rglob("*") if p.is_file()}


def archive_hashes():
    con = sqlite3.connect("file:/var/lib/msgvault/msgvault.db?mode=ro", uri=True)
    try:
        return {str(r[0]): hashlib.sha256(json.dumps(r[1:-1], ensure_ascii=False).encode() + (r[-1] or b"")).hexdigest()
                for r in con.execute("SELECT m.id,m.source_id,m.sender_id,m.subject,b.body_text,b.body_html,r.raw_data FROM messages m LEFT JOIN message_bodies b ON b.message_id=m.id LEFT JOIN message_raw r ON r.message_id=m.id")}
    finally:
        con.close()


def main():
    if os.geteuid() != 0 or not LINK.is_symlink() or not NEW.is_file():
        raise RuntimeError("Expected root on the configured Msgvault NUC")
    os.umask(0o077)
    old = LINK.resolve(strict=True)
    if setup.digest(old) != OLD_SHA or RUNNER.is_symlink():
        raise RuntimeError("Existing runtime differs; preserving it")
    previous_runner = RUNNER.read_bytes()
    expected_runner = SOURCE / "mailbox-discovery-before.py"
    if previous_runner != expected_runner.read_bytes():
        raise RuntimeError("Existing timer runner differs; preserving it")
    setup.command("sha256sum", "--check", str(NEW.parent / "SHA256SUMS"))
    if "v0.21.0-signed-brief-1" not in setup.command(str(NEW), "version"):
        raise RuntimeError("Unexpected tested build")
    if not setup.native_api("/api/v1/identity/discovery/status").get("ready"):
        raise RuntimeError("Existing Jev discovery is not ready")
    config_hash = setup.digest(setup.CONFIG)
    keys_before = credential_hashes()
    setup.command("systemctl", "start", "msgvault-backup.service")
    if setup.command("systemctl", "show", "msgvault-backup.service", "--property=Result", "--value").strip() != "success":
        raise RuntimeError("Pre-upgrade encrypted NAS backup failed")
    checkpoint = Path("/var/lib/msgvault-backup") / ("signed-brief-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    checkpoint.mkdir(mode=0o700)
    (checkpoint / "runner-before.py").write_bytes(previous_runner)
    timer_enabled = subprocess.run(["systemctl", "is-enabled", "--quiet", TIMER], capture_output=True).returncode == 0
    receipt = {"previous_binary": str(old), "new_binary": str(NEW), "new_sha256": setup.digest(NEW), "checkpoint": str(checkpoint)}
    setup.save_receipt(checkpoint / "activation.json", receipt)
    try:
        setup.command("systemctl", "stop", TIMER, SERVICE, *UNITS)
        if setup.digest(setup.CONFIG) != config_hash or credential_hashes() != keys_before:
            raise RuntimeError("Provider setup changed during upgrade")
        # Stop the daemon before reading the original content invariant.
        before = archive_hashes()
        setup.save_receipt(checkpoint / "archive-before.json", before)
        shutil.copyfile(SOURCE / "mailbox-discovery.py", RUNNER)
        RUNNER.chmod(0o755)
        replace_link(NEW)
        setup.command("systemctl", "start", *UNITS)
        setup.wait_healthy()
        if not setup.native_api("/api/v1/identity/discovery/status").get("ready"):
            raise RuntimeError("Discovery consent is not ready after upgrade")
        setup.command("systemctl", "enable", "--now", TIMER)
        setup.command("systemctl", "is-active", "--quiet", TIMER, *UNITS)
        if setup.digest(setup.CONFIG) != config_hash or credential_hashes() != keys_before:
            raise RuntimeError("Provider setup changed unexpectedly")
        receipt.update(status="active", config_unchanged=True, credentials_unchanged=True, timer_enabled=True)
        setup.save_receipt(checkpoint / "activation.json", receipt)
        print(json.dumps(receipt))
    except Exception:
        subprocess.run(["systemctl", "stop", TIMER, SERVICE, *UNITS], capture_output=True)
        replace_link(old)
        RUNNER.write_bytes(previous_runner)
        RUNNER.chmod(0o755)
        setup.command("systemctl", "start", *UNITS)
        setup.wait_healthy()
        if timer_enabled:
            setup.command("systemctl", "enable", "--now", TIMER)
        receipt.update(status="rolled_back")
        setup.save_receipt(checkpoint / "activation.json", receipt)
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Signed-mail upgrade failed; inspect its private checkpoint") from None
