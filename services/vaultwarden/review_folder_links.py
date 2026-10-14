#!/usr/bin/env python3
"""Move personal folder links while preserving every encrypted cipher byte.

Schema verified on Vaultwarden 1.37.4: folders_ciphers(cipher_uuid,folder_uuid),
ciphers(user_uuid,organization_uuid,updated_at), folders(user_uuid,uuid).
The root runner shares the backup lock and briefly stops Vaultwarden.
"""
from datetime import datetime, timezone
import fcntl
import json
import os
import re
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen


def revision(value):
    # Vaultwarden/Chrono stores nanoseconds; Ubuntu's Python 3.10 accepts
    # microseconds. JS client revision dates expose milliseconds.
    value = re.sub(r"(\.\d{6})\d+", r"\1", value)
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat(timespec="milliseconds")


def apply_links(db, plan):
    db.row_factory = sqlite3.Row
    db.execute("BEGIN IMMEDIATE")
    try:
        user = db.execute("SELECT uuid FROM users WHERE email=?", (plan["account"],)).fetchone()
        if not user:
            raise RuntimeError("wrong_account")
        owner = user[0]
        folder = db.execute("SELECT user_uuid FROM folders WHERE uuid=?", (plan["folder_id"],)).fetchone()
        if not folder or folder[0] != owner:
            raise RuntimeError("wrong_folder_owner")
        originals = {}
        for item in plan["items"]:
            identity = item["id"]
            if identity in originals:
                raise RuntimeError("duplicate_plan_id")
            row = db.execute("SELECT * FROM ciphers WHERE uuid=?", (identity,)).fetchone()
            if not row or row["user_uuid"] != owner or row["organization_uuid"] or row["deleted_at"]:
                raise RuntimeError("wrong_cipher_owner_or_deleted")
            if revision(row["updated_at"]) != revision(item["revisionDate"]):
                raise RuntimeError("concurrent_cipher_change")
            linked = db.execute("SELECT folder_uuid FROM folders_ciphers WHERE cipher_uuid=?", (identity,)).fetchall()
            if [r[0] for r in linked] != ([] if not item["previous_folder"] else [item["previous_folder"]]):
                raise RuntimeError("concurrent_folder_change")
            originals[identity] = dict(row)
        moved = []
        for item in plan["items"]:
            if item["previous_folder"] == plan["folder_id"]:
                continue
            identity = item["id"]
            db.execute("DELETE FROM folders_ciphers WHERE cipher_uuid=?", (identity,))
            db.execute("INSERT INTO folders_ciphers(cipher_uuid,folder_uuid) VALUES(?,?)", (identity, plan["folder_id"]))
            db.execute("UPDATE ciphers SET updated_at=? WHERE uuid=?", (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" "), identity))
            moved.append({"id": identity, "previous_folder": item["previous_folder"]})
        for identity, original in originals.items():
            current = dict(db.execute("SELECT * FROM ciphers WHERE uuid=?", (identity,)).fetchone())
            if {k:v for k,v in current.items() if k != "updated_at"} != {k:v for k,v in original.items() if k != "updated_at"}:
                raise RuntimeError("encrypted_cipher_bytes_changed")
        if moved:
            # Clients can skip sync when the account revision is unchanged.
            db.execute("UPDATE users SET updated_at=? WHERE uuid=?", (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" "), owner))
        db.commit()
        return moved
    except BaseException:
        db.rollback()
        raise


def main():
    if os.geteuid() != 0:
        raise RuntimeError("root_required")
    plan = json.loads(Path(sys.argv[1]).read_text())
    with open("/run/lock/vaultwarden-backup.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(subprocess.check_output(["docker", "inspect", "--format", "{{json .State}}", "vaultwarden"]))
        if not state["Running"] or state.get("Paused") or state.get("Restarting"):
            raise RuntimeError("vault_must_be_running")
        subprocess.run(["docker", "stop", "--time", "30", "vaultwarden"], check=True, stdout=subprocess.DEVNULL)
        try:
            db = sqlite3.connect("/var/lib/vaultwarden/db.sqlite3")
            try:
                moved = apply_links(db, plan)
            finally:
                db.close()
        finally:
            subprocess.run(["docker", "start", "vaultwarden"], check=True, stdout=subprocess.DEVNULL)
        for _ in range(60):
            try:
                if urlopen("http://127.0.0.1:18080/alive", timeout=1).status == 200:
                    print(json.dumps({"moved": moved, "encrypted_cipher_bytes_unchanged": True}))
                    return
            except OSError:
                pass
            time.sleep(0.5)
        raise RuntimeError("vault_restart_not_ready")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"stopped": type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
