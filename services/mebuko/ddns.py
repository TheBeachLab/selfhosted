#!/usr/bin/env python3
"""Update only Mebuko's apex A record using the existing root-only Cloud token.

Official API: https://docs.hetzner.cloud/reference/cloud#zone-rrset-actions
Uses set_records, preserving the RRSet without a delete/recreate window.
"""
import ipaddress
import json
from pathlib import Path
import re
import time
from urllib.parse import quote
from urllib.request import Request, urlopen


def main():
    text = Path("/etc/hetzner-ddns.env").read_text()
    match = re.search(r'^HETZNER_TOKEN=["\x27]?([^"\x27\n]+)', text, re.M)
    if not match:
        raise RuntimeError("Existing Cloud token is unavailable")
    token = match.group(1)
    def api(path, body=None):
        request = Request("https://api.hetzner.cloud/v1" + path, data=None if body is None else json.dumps(body).encode(), headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    ip = urlopen("https://api.ipify.org", timeout=15).read().decode().strip()
    address = ipaddress.ip_address(ip)
    if address.version != 4 or not address.is_global:
        raise RuntimeError("Public IPv4 check failed")
    zone = api("/zones/mebuko.de")["zone"]
    if zone["name"] != "mebuko.de" or zone["mode"] != "primary":
        raise RuntimeError("Unexpected zone; no updates made")
    route = f"/zones/{zone['id']}/rrsets/{quote('@', safe='')}/A"
    rrset = api(route)["rrset"]
    if [r["value"] for r in rrset["records"]] == [ip]:
        print("Mebuko DNS already matches the NUC IPv4.")
        return
    action = api(route + "/actions/set_records", {"records": [{"value": ip, "comment": "NUC; scoped DDNS update."}]})["action"]
    for _ in range(15):
        action = api(f"/zones/{zone['id']}/actions/{action['id']}")["action"]
        if action["status"] == "success":
            break
        if action["status"] == "error":
            raise RuntimeError("DNS update failed")
        time.sleep(1)
    else:
        raise RuntimeError("DNS update still pending")
    if [r["value"] for r in api(route)["rrset"]["records"]] != [ip]:
        raise RuntimeError("DNS readback failed")
    print("Mebuko IPv4 updated and verified.")


if __name__ == "__main__":
    main()
