#!/usr/bin/env python3
"""Update explicitly configured NUC A records; preserve every other DNS field.

API: https://developers.cloudflare.com/api/resources/dns/subresources/records/
"""
import argparse
import ipaddress
import json
from pathlib import Path
from urllib.request import Request, urlopen


def api(token, path, method="GET", body=None):
    request = Request(
        "https://api.cloudflare.com/client/v4" + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=25) as response:
        data = json.load(response)
    if not data.get("success"):
        raise RuntimeError("Cloudflare request failed")
    return data["result"]


def reconcile(records, address, request):
    """Preflight all identities before changing any address; then verify each write."""
    ip = ipaddress.ip_address(address)
    if ip.version != 4 or not ip.is_global:
        raise ValueError("Expected a public IPv4")
    pending = []
    seen = set()
    for target in records:
        path = "/zones/{zone_id}/dns_records/{record_id}".format(**target)
        if path in seen:
            raise ValueError("Duplicate record target")
        seen.add(path)
        current = request(path)
        if current["name"] != target["name"] or current["type"] != "A" or current.get("proxied"):
            raise RuntimeError("Record identity or DNS-only policy changed: " + target["name"])
        pending.append((path, current))
    for path, current in pending:
        if current["content"] != address:
            request(path, "PATCH", {"content": address})
        after = request(path)
        keys = ("id", "name", "type", "ttl", "proxied", "comment", "tags", "settings")
        if after["content"] != address or any(after.get(k) != current.get(k) for k in keys):
            raise RuntimeError("DNS readback failed: " + current["name"])
        print(current["name"] + " IPv4 verified", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/etc/cloudflare-nuc-ddns.json")
    parser.add_argument("--token-file", default="/etc/cloudflare-arroyo.env")
    args = parser.parse_args()
    token = next(line.split("=", 1)[1].strip().strip("\"'") for line in
                 Path(args.token_file).read_text().splitlines()
                 if line.startswith("CLOUDFLARE_API_TOKEN="))
    with urlopen("https://api.ipify.org", timeout=15) as response:
        address = response.read().decode().strip()
    reconcile(json.loads(Path(args.config).read_text())["records"], address,
              lambda path, method="GET", body=None: api(token, path, method, body))


if __name__ == "__main__":
    main()
