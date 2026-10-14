#!/usr/bin/env python3
"""Inspect/activate the owned number only after the NUC reports Realtime ready."""
import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

FIELDS = ("voice_url", "voice_method", "voice_fallback_url", "voice_fallback_method",
          "status_callback", "status_callback_method")
PARAMS = ("VoiceUrl", "VoiceMethod", "VoiceFallbackUrl", "VoiceFallbackMethod",
          "StatusCallback", "StatusCallbackMethod")
REGIONS = {"us1": ("api.twilio.com", "TWILIO_API_KEY", "TWILIO_API_SECRET"),
           "ie1": ("api.dublin.ie1.twilio.com", "TWILIO_IE1_API_KEY", "TWILIO_IE1_API_SECRET")}


def read_env(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip().removeprefix("export ")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def api(url, credentials, data=None):
    basic = base64.b64encode((credentials[0] + ":" + credentials[1]).encode()).decode()
    request = urllib.request.Request(url, data=None if data is None else urllib.parse.urlencode(data).encode(),
                                     headers={"Authorization": "Basic " + basic})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def require_ready(base):
    with urllib.request.urlopen(base + "/healthz", timeout=10) as response:
        health = json.load(response)
    if health.get("service") != "daswerklab-voice" or health.get("ready") is not True:
        raise RuntimeError("Realtime is not ready; preserving Twilio configuration.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, default=Path("/Users/Papi/.config/recepcionista/.env"))
    parser.add_argument("--number", default="+498951042000")
    parser.add_argument("--base-url", default="https://daswerklab.de/voice")
    parser.add_argument("--region", choices=REGIONS)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--allow-region-change", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    env = read_env(args.env)
    global_creds = (env["TWILIO_API_KEY"], env["TWILIO_API_SECRET"])
    routing_url = "https://routes.twilio.com/v2/PhoneNumbers/" + urllib.parse.quote(args.number, safe="")
    before_route = api(routing_url, global_creds)
    if before_route["account_sid"] != env["TWILIO_ACCOUNT_SID"]:
        raise RuntimeError("Number does not belong to the configured account.")
    active = before_route["voice_region"]
    selected = args.region or active
    host, key_var, secret_var = REGIONS[selected]
    if not args.activate:
        print(json.dumps({"number": args.number, "active_region": active, "target_region": selected,
                          "regional_credentials_present": bool(env.get(key_var) and env.get(secret_var)),
                          "activated": False}))
        return
    if not args.receipt or args.receipt.exists() or args.receipt.is_symlink():
        raise RuntimeError("Pass a new owner-only receipt file for activation and rollback evidence.")
    require_ready(args.base_url)
    if selected != active and not args.allow_region_change:
        raise RuntimeError("Region differs; explicit --allow-region-change is required.")
    regional_creds = (env[key_var], env[secret_var])
    root = "https://" + host + "/2010-04-01/Accounts/" + env["TWILIO_ACCOUNT_SID"]
    listing = api(root + "/IncomingPhoneNumbers.json?" +
                  urllib.parse.urlencode({"PhoneNumber": args.number}), regional_creds)
    found = [n for n in listing["incoming_phone_numbers"] if n["phone_number"] == args.number]
    if len(found) != 1:
        raise RuntimeError("Owned number could not be identified uniquely; preserving configuration.")
    before = found[0]
    number_url = root + "/IncomingPhoneNumbers/" + before["sid"] + ".json"
    current = api(number_url, regional_creds)
    if any(current.get(field) != before.get(field) for field in FIELDS):
        raise RuntimeError("Concurrent voice configuration change preserved.")
    updates = {"VoiceUrl": args.base_url + "/incoming", "VoiceMethod": "POST",
               "StatusCallback": args.base_url + "/status", "StatusCallbackMethod": "POST"}
    os.umask(0o077)
    receipt = {"number": args.number, "number_sid": before["sid"], "previous_region": active,
               "target_region": selected, "previous_config": {key: before.get(key) for key in FIELDS},
               "requested_config": updates, "started_at": datetime.now(timezone.utc).isoformat(),
               "activated": False}
    args.receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with args.receipt.open("x") as output:
        json.dump(receipt, output, indent=2)
    api(number_url, regional_creds, updates)
    after = api(number_url, regional_creds)
    if after.get("voice_url") != updates["VoiceUrl"] or after.get("status_callback") != updates["StatusCallback"]:
        raise RuntimeError("Voice webhook readback did not match; inspect the saved receipt.")
    if selected != active:
        current_route = api(routing_url, global_creds)
        if current_route["voice_region"] != active:
            raise RuntimeError("Concurrent regional routing change preserved; inspect the saved receipt.")
        api(routing_url, global_creds, {"VoiceRegion": selected})
    after_route = api(routing_url, global_creds)
    if after_route["voice_region"] != selected:
        raise RuntimeError("Routing readback did not match; inspect the saved receipt.")
    receipt.update({"activated": True, "finished_at": datetime.now(timezone.utc).isoformat()})
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"number": args.number, "region": selected, "voice_url": after["voice_url"],
                      "activated": True, "real_call_tested": False}))


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit("Provider HTTP " + str(error.code) + "; credentials and response bodies withheld.")
    except (KeyError, RuntimeError) as error:
        if isinstance(error, KeyError):
            raise SystemExit("A required regional credential is missing; preserving remaining configuration.")
        raise SystemExit(str(error))
