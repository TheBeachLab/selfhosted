#!/usr/bin/env python3
"""Consistent encrypted Mebuko backup, with a scoped restore test.

Uses the server's installed Restic binary, a dedicated repository and key, and
SQLite's backup API rather than copying a database under concurrent writes.
https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup
https://restic.readthedocs.io/en/stable/060_forget.html
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile

REPO = "/mnt/nas-downloads/backups/mebuko-encrypted"
KEY = "/root/.config/mebuko-backup/restic-password"
STATE = Path("/var/lib/mebuko-backup")


def restic(*args):
    env = dict(os.environ, RESTIC_REPOSITORY=REPO, RESTIC_PASSWORD_FILE=KEY)
    result = subprocess.run(["restic", *args], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        raise RuntimeError("Mebuko Restic command failed; private details suppressed")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-restore", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run as root")
    if not Path("/mnt/nas-downloads").is_mount():
        raise RuntimeError("NAS is not mounted; refusing a local-disk fallback")
    STATE.mkdir(mode=0o700, exist_ok=True)
    os.chmod(STATE, 0o700)
    stage = STATE / "snapshot"
    stage.mkdir(mode=0o700, exist_ok=True)
    source = sqlite3.connect("file:/var/lib/mebuko/subscribers.sqlite3?mode=ro", uri=True)
    dest = sqlite3.connect(stage / "subscribers.sqlite3")
    source.backup(dest)
    if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("Consistent snapshot integrity failed")
    count = dest.execute("SELECT count(*) FROM subscribers").fetchone()[0]
    source.close(); dest.close()
    os.chmod(stage / "subscribers.sqlite3", 0o600)
    paths = [str(stage), "/etc/mebuko", "/etc/systemd/system/mebuko.service"]
    for p in ("/etc/nginx/sites-available/mebuko.de", "/etc/letsencrypt/renewal/mebuko.de.conf", "/etc/letsencrypt/archive/mebuko.de"):
        if Path(p).exists(): paths.append(p)
    lines = restic("backup", "--json", "--tag", "mebuko", *paths)
    summary = next(json.loads(line) for line in lines.splitlines() if json.loads(line).get("message_type") == "summary")
    snapshot = summary["snapshot_id"]
    if args.verify_restore:
        with tempfile.TemporaryDirectory(prefix="restore-", dir=STATE) as root:
            restic("restore", snapshot, "--target", root)
            restored = Path(root) / str(stage).lstrip("/") / "subscribers.sqlite3"
            if hashlib.sha256(restored.read_bytes()).digest() != hashlib.sha256((stage / "subscribers.sqlite3").read_bytes()).digest():
                raise RuntimeError("Restored SQLite hash mismatch")
            with sqlite3.connect(restored) as db:
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("SELECT count(*) FROM subscribers").fetchone()[0] != count:
                    raise RuntimeError("Restored SQLite integrity mismatch")
            original_env = Path("/etc/mebuko/private.env")
            restored_env = Path(root) / "etc/mebuko/private.env"
            if original_env.read_bytes() != restored_env.read_bytes():
                raise RuntimeError("Restored private configuration mismatch")
    # Isolated repository: never run retention against the host/accounting backups.
    restic("forget", "--keep-within", "30d", "--group-by", "", "--prune")
    (STATE / "last-backup.json").write_text(json.dumps({"snapshot_id": snapshot, "restore_verified": args.verify_restore}) + "\n")
    print("Mebuko encrypted backup completed; restore verified:", args.verify_restore)


if __name__ == "__main__":
    main()
