#!/usr/bin/env python3
"""Move all same-site/password candidates to Duplicados without consolidation.

Uses the official CLI to select items and create the folder, then changes
only server folder links, preserving every encrypted credential byte:
https://bitwarden.com/help/cli/#create
https://bitwarden.com/help/cli/#edit
"""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

from deduplicate import Cli, GuardError, login, passkeys, save_receipt


def host(value):
    if not value:
        return None
    text = value.strip()
    try:
        parsed = urlsplit(text if "://" in text else "https://" + text)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            return None
        if "." not in parsed.hostname and ":" not in parsed.netloc:
            return None
        if any(c.isspace() for c in parsed.netloc):
            return None
        hostname = parsed.hostname.lower().removeprefix("www.")
        port = parsed.port
        if port in {80, 443}:
            port = None
        return hostname, port
    except ValueError:
        return None


def candidates(items, wifi_folders):
    eligible = [i for i in items if i.get("type") == 1 and not i.get("deletedDate")
                and not i.get("organizationId") and i.get("folderId") not in wifi_folders
                and login(i).get("password")]
    parent = {i["id"]: i["id"] for i in eligible}

    def root(identity):
        while parent[identity] != identity:
            parent[identity] = parent[parent[identity]]
            identity = parent[identity]
        return identity

    index = {}
    for item in eligible:
        sites = {host(uri.get("uri")) for uri in login(item).get("uris") or []}
        sites.add(host(item.get("name")))
        for site in sites - {None}:
            marker = (site, login(item)["password"])
            if marker in index:
                parent[root(item["id"])] = root(index[marker])
            else:
                index[marker] = item["id"]
    grouped = defaultdict(list)
    for item in eligible:
        grouped[root(item["id"])].append(item)
    return [group for group in grouped.values() if len(group) > 1]


def optional_values(value):
    if isinstance(value, dict):
        return {k: optional_values(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [optional_values(v) for v in value]
    return value


def contents(item):
    return optional_values({k: v for k, v in item.items() if k not in {"folderId", "revisionDate"}})


def execute(cli, receipt_path, apply=False, move_metadata=None):
    status = cli.request("GET", "/status")
    if status.get("userEmail") != "hola@beachlab.org" or status.get("serverUrl", "").rstrip("/") != "https://passwords.beachlab.org":
        raise GuardError("wrong_account_or_server")
    cli.request("POST", "/sync?force=true")
    items = cli.request("GET", "/list/object/items")
    items = {i["id"]: i for i in items if not i.get("deletedDate")}
    folders = cli.request("GET", "/list/object/folders")
    wifi_folders = {f["id"] for f in folders if f.get("name") == "Wi-Fi"}
    groups = candidates(list(items.values()), wifi_folders)
    targets = {i["id"] for group in groups for i in group}
    receipt = {"before": len(items), "groups": len(groups), "items": len(targets),
               "passkey_items_in_groups": sum(bool(passkeys(items[i])) for i in targets),
               "folder": "Duplicados", "applied": apply, "moved": [],
               "candidate_groups": [[i["id"] for i in group] for group in groups]}
    save_receipt(receipt_path, receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k not in {"moved", "candidate_groups"}}), flush=True)
    if not apply or not targets:
        return receipt
    matching = [f for f in folders if f.get("name") == "Duplicados"]
    if len(matching) > 1:
        raise GuardError("multiple_review_folders")
    folder = matching[0] if matching else cli.request("POST", "/object/folder", {"name": "Duplicados"})
    folder_id = folder["id"]
    receipt["folder_id"] = folder_id
    plan = {"account": status["userEmail"], "folder_id": folder_id,
            "items": [{"id": i, "previous_folder": items[i].get("folderId"),
                       "revisionDate": items[i]["revisionDate"]} for i in sorted(targets)]}
    if move_metadata is None:
        plan_path = Path(receipt_path).with_suffix(".folder-plan.json")
        save_receipt(plan_path, plan)
        result = subprocess.run(["sudo", sys.executable, str(Path(__file__).with_name("review_folder_links.py")), str(plan_path)], capture_output=True)
        if result.returncode:
            raise GuardError("folder_metadata_move_failed")
        receipt["moved"] = json.loads(result.stdout)["moved"]
    else:
        receipt["moved"] = move_metadata(plan)
    save_receipt(receipt_path, receipt)
    cli.request("POST", "/sync?force=true")
    final = cli.request("GET", "/list/object/items")
    final = {i["id"]: i for i in final if not i.get("deletedDate")}
    if set(final) != set(items):
        raise GuardError("item_inventory_changed")
    for identity, original in items.items():
        if identity in targets:
            if contents(final[identity]) != contents(original) or final[identity].get("folderId") != folder_id:
                raise GuardError("server_content_verification_failed")
        elif final[identity] != original:
            raise GuardError("unrelated_item_change")
    receipt.update(after=len(final), verified=True,
                   passkey_credentials=sum(len(passkeys(i)) for i in final.values()),
                   wifi_items=sum(i.get("folderId") in wifi_folders for i in final.values()))
    save_receipt(receipt_path, receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k not in {"moved", "candidate_groups"}}), flush=True)
    return receipt


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bw", required=True)
    parser.add_argument("--private-dir", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    cli = Cli(args.bw, args.private_dir)
    try:
        execute(cli, args.receipt, args.apply)
    finally:
        cli.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"stopped": str(error) if isinstance(error, GuardError) else type(error).__name__}), flush=True)
        raise SystemExit(1)
