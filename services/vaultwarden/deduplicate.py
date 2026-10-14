#!/usr/bin/env python3
"""Consolidate personal login copies through an unlocked official Bitwarden CLI.

No decrypted vault, password digest, or session is written to the receipt.
CLI edit replaces an item; soft deletion is recoverable in Trash:
https://bitwarden.com/help/cli/#edit
https://bitwarden.com/help/cli/#delete
"""
import argparse
from collections import Counter, defaultdict
import copy
import http.client
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import time
from urllib.parse import urlsplit


class GuardError(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def unique(values):
    seen, result = set(), []
    for value in values:
        marker = canonical(value)
        if marker not in seen:
            seen.add(marker)
            result.append(copy.deepcopy(value))
    return result


def login(item):
    return item.get("login") or {}


def passkeys(item):
    return login(item).get("fido2Credentials") or []


def site(value):
    """Normalize only HTTP scheme/host casing and the empty root path."""
    if not value:
        return None
    text = value.strip()
    try:
        parsed = urlsplit(text if "://" in text else "https://" + text)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        # Do not turn arbitrary human-readable titles into sites.
        if "." not in parsed.hostname and ":" not in parsed.netloc:
            return None
        if parsed.username or any(c.isspace() for c in parsed.netloc):
            return None
        path = "" if parsed.path == "/" else parsed.path
        return (parsed.netloc.lower(), path, parsed.query, parsed.fragment)
    except ValueError:
        return None


def groups(items, wifi_folders):
    eligible = [i for i in items if i.get("type") == 1 and not i.get("deletedDate")
                and i.get("folderId") not in wifi_folders and login(i).get("password")]
    parent = {i["id"]: i["id"] for i in eligible}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    index = {}
    for item in eligible:
        identity = (login(item).get("username"), login(item)["password"])
        keys = set()
        for uri in login(item).get("uris") or []:
            normalized = site(uri.get("uri"))
            if normalized:
                keys.add(("site", normalized))
        normalized_name = site(item.get("name"))
        if normalized_name:
            keys.add(("site", normalized_name))
        if item.get("name"):
            keys.add(("name", item["name"].strip().casefold()))
        for key in keys:
            marker = (identity, key)
            if marker in index:
                parent[root(item["id"])] = root(index[marker])
            else:
                index[marker] = item["id"]
    grouped = defaultdict(list)
    for item in eligible:
        grouped[root(item["id"])].append(item)
    return [g for g in grouped.values() if len(g) > 1]


METADATA = {"object", "id", "creationDate", "revisionDate", "deletedDate"}
MERGEABLE = {"name", "notes", "fields", "passwordHistory", "favorite", "reprompt", "login"}
LOGIN_MERGEABLE = {"uris", "fido2Credentials", "passwordRevisionDate"}


def merge(group, baseline):
    protected = [i for i in group if passkeys(i)]
    # Keep every existing passkey-bearing item ID. Never consolidate two of them.
    if len(protected) > 1:
        raise GuardError("multiple_passkey_items")
    keep = protected[0] if protected else min(
        group, key=lambda i: (i["id"] in baseline, i.get("creationDate") or "", i["id"]))
    for source in group:
        if source.get("attachments"):
            raise GuardError("attachments_require_manual_review")
        for key in set(keep) | set(source):
            if key not in METADATA | MERGEABLE and keep.get(key) != source.get(key):
                raise GuardError("different_unmergeable_item_data")
        for key in set(login(keep)) | set(login(source)):
            if key not in LOGIN_MERGEABLE and login(keep).get(key) != login(source).get(key):
                raise GuardError("different_login_data")
    merged = copy.deepcopy(keep)
    merged["login"]["uris"] = unique(
        u for item in group for u in login(item).get("uris") or [])
    merged["login"]["fido2Credentials"] = copy.deepcopy(passkeys(keep))
    merged["fields"] = unique(f for item in group for f in item.get("fields") or [])
    names = unique(i["name"] for i in group if i.get("name") and i["name"] != keep["name"])
    for name in names:
        alias = {"name": "Nombre anterior (importación)", "value": name, "type": 0}
        if alias not in merged["fields"]:
            merged["fields"].append(alias)
    notes = unique(i["notes"] for i in group if i.get("notes"))
    merged["notes"] = "\n\n---\n\n".join(notes) if notes else keep.get("notes")
    histories = unique(h for item in group for h in item.get("passwordHistory") or [])
    merged["passwordHistory"] = histories or keep.get("passwordHistory")
    merged["favorite"] = any(i.get("favorite") for i in group)
    merged["reprompt"] = max(i.get("reprompt") or 0 for i in group)
    return keep, merged, [i for i in group if i["id"] != keep["id"]]


def uri_values(item):
    return {(u.get("uri"), u.get("match")) for u in login(item).get("uris") or []}


def covers(target, source):
    """Content guard independent of the item selection and serialization path."""
    for key in set(target) | set(source):
        if key not in METADATA | MERGEABLE and target.get(key) != source.get(key):
            return False
    for key in set(login(target)) | set(login(source)):
        if key not in LOGIN_MERGEABLE and login(target).get(key) != login(source).get(key):
            return False
    if login(target).get("username") != login(source).get("username"):
        return False
    if login(target).get("password") != login(source).get("password"):
        return False
    if not uri_values(source) <= uri_values(target):
        return False
    if not {canonical(f) for f in source.get("fields") or []} <= {
            canonical(f) for f in target.get("fields") or []}:
        return False
    if source.get("notes") and source["notes"] not in (target.get("notes") or ""):
        return False
    if source.get("name") != target.get("name") and not any(
            f.get("name") == "Nombre anterior (importación)" and f.get("value") == source.get("name")
            for f in target.get("fields") or []):
        return False
    if not {canonical(k) for k in passkeys(source)} <= {canonical(k) for k in passkeys(target)}:
        return False
    if not {canonical(h) for h in source.get("passwordHistory") or []} <= {
            canonical(h) for h in target.get("passwordHistory") or []}:
        return False
    if source.get("favorite") and not target.get("favorite"):
        return False
    if (target.get("reprompt") or 0) < (source.get("reprompt") or 0):
        return False
    return True


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", 8087, timeout=90)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self.path))


class Cli:
    def __init__(self, executable, private_dir):
        self.private = Path(private_dir)
        if stat.S_IMODE(self.private.stat().st_mode) != 0o700:
            raise GuardError("private_directory_must_be_0700")
        session_path = self.private / "session"
        if stat.S_IMODE(session_path.stat().st_mode) != 0o600:
            raise GuardError("session_file_must_be_0600")
        session = session_path.read_text().strip()
        if not re.fullmatch(r"[A-Za-z0-9+/=]{32,}", session):
            raise GuardError("login_not_completed")
        self.socket = self.private / "cli.sock"
        if self.socket.exists():
            raise GuardError("cli_socket_already_exists")
        env = dict(os.environ, BW_SESSION=session, BW_NOINTERACTION="true",
                   BITWARDENCLI_APPDATA_DIR=str(self.private / "profile"))
        self.process = subprocess.Popen(
            [executable, "serve", "--hostname", "unix://" + str(self.socket)],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if self.socket.exists():
                self.socket.chmod(0o600)
                break
            if self.process.poll() is not None:
                raise GuardError("cli_start_failed")
            time.sleep(0.1)
        else:
            self.close()
            raise GuardError("cli_start_timeout")

    def request(self, method, path, value=None):
        conn = UnixConnection(self.socket)
        try:
            body = json.dumps(value) if value is not None else None
            conn.request(method, path, body, {"Host": "localhost:8087", "Content-Type": "application/json"})
            response = conn.getresponse()
            data = json.loads(response.read())
            if response.status != 200 or not data.get("success"):
                raise GuardError("cli_request_failed_" + str(response.status))
            result = data.get("data")
            if isinstance(result, dict) and result.get("object") == "template":
                return result.get("template")
            return result.get("data") if isinstance(result, dict) and result.get("object") in {"list", "string"} else result
        finally:
            conn.close()

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.socket.unlink(missing_ok=True)


def save_receipt(path, receipt):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    with open(temporary, "w", opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        json.dump(receipt, stream, indent=2)
    temporary.replace(path)


def execute(cli, baseline, receipt_path, apply=False, batch_size=25):
    status = cli.request("GET", "/status")
    if status.get("userEmail") != "hola@beachlab.org" or status.get("serverUrl", "").rstrip("/") != "https://passwords.beachlab.org":
        raise GuardError("wrong_account_or_server")
    cli.request("POST", "/sync")
    items = cli.request("GET", "/list/object/items")
    folders = cli.request("GET", "/list/object/folders")
    wifi_folders = {f["id"] for f in folders if f.get("name") == "Wi-Fi"}
    original = {i["id"]: i for i in items if not i.get("deletedDate")}
    protected = {i["id"]: copy.deepcopy(passkeys(i)) for i in original.values() if passkeys(i)}
    plans, skipped = [], Counter()
    for group in groups(list(original.values()), wifi_folders):
        try:
            plans.append((group, *merge(group, baseline)))
        except GuardError as error:
            skipped[str(error)] += 1
    receipt = {"before": len(original), "groups": len(plans), "skipped": dict(skipped),
               "planned_removals": sum(len(p[3]) for p in plans), "passkey_items": len(protected),
               "completed": [], "applied": apply}
    save_receipt(receipt_path, receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k != "completed"}), flush=True)
    if not apply:
        return receipt
    for start in range(0, len(plans), batch_size):
        batch = plans[start:start + batch_size]
        # Edit sends lastKnownRevisionDate. Re-read the whole batch from the
        # server before any soft deletion, avoiding a full-vault pull per item.
        for group, keep, merged, _ in batch:
            for source in group:
                if cli.request("GET", "/object/item/" + source["id"]) != source:
                    raise GuardError("concurrent_item_change")
            if any(not covers(merged, source) for source in group):
                raise GuardError("merge_does_not_preserve_content")
            if merged != keep:
                result = cli.request("PUT", "/object/item/" + keep["id"], merged)
                if any(not covers(result, source) for source in group) or passkeys(result) != passkeys(keep):
                    raise GuardError("edit_response_verification_failed")
        cli.request("POST", "/sync")
        for group, keep, _, extras in batch:
            verified = cli.request("GET", "/object/item/" + keep["id"])
            if any(not covers(verified, source) for source in group) or passkeys(verified) != passkeys(keep):
                raise GuardError("server_merge_verification_failed")
            for extra in extras:
                if cli.request("GET", "/object/item/" + extra["id"]) != extra:
                    raise GuardError("concurrent_extra_change")
                if passkeys(extra) or extra["id"] in protected:
                    raise GuardError("refusing_passkey_deletion")
        for group, keep, _, extras in batch:
            for extra in extras:
                cli.request("DELETE", "/object/item/" + extra["id"])
            receipt["completed"].append({"kept": keep["id"], "trashed": [i["id"] for i in extras]})
            save_receipt(receipt_path, receipt)
        print(json.dumps({"groups_completed": len(receipt["completed"]), "total_groups": len(plans)}), flush=True)
    cli.request("POST", "/sync")
    final = cli.request("GET", "/list/object/items")
    final = {i["id"]: i for i in final if not i.get("deletedDate")}
    trashed = {i["id"] for i in cli.request("GET", "/list/object/items?trash=true")}
    deleted = {i for record in receipt["completed"] for i in record["trashed"]}
    if set(final) != set(original) - deleted or not deleted <= trashed:
        raise GuardError("final_item_inventory_mismatch")
    if any(i not in final or passkeys(final[i]) != keys for i, keys in protected.items()):
        raise GuardError("final_passkey_verification_failed")
    touched = {p[1]["id"] for p in plans} | deleted
    if any(final[i] != source for i, source in original.items() if i not in touched):
        raise GuardError("unrelated_item_change")
    for group, keep, _, _ in plans:
        if any(not covers(final[keep["id"]], source) for source in group):
            raise GuardError("final_content_verification_failed")
    receipt.update(after=len(final), trashed=len(deleted), verified=True,
                   passkey_credentials=sum(len(passkeys(i)) for i in final.values()),
                   wifi_items=sum(i.get("folderId") in wifi_folders for i in final.values()))
    save_receipt(receipt_path, receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k != "completed"}), flush=True)
    return receipt


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bw", required=True)
    parser.add_argument("--private-dir", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--batch-size", type=int, default=25)
    args = parser.parse_args()
    baseline = {i["id"] for i in json.loads(Path(args.baseline).read_text())["items"]}
    cli = Cli(args.bw, args.private_dir)
    try:
        if not 1 <= args.batch_size <= 50:
            raise GuardError("batch_size_out_of_range")
        execute(cli, baseline, args.receipt, args.apply, args.batch_size)
    finally:
        cli.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Exception representations can include a decrypted request or response.
        print(json.dumps({"stopped": str(error) if isinstance(error, GuardError) else type(error).__name__}), flush=True)
        raise SystemExit(1)
