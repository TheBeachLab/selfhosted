#!/usr/bin/env python3
"""Provision only Msgvault and Fran's access; never rerun global configure.py.

API fields were checked against the NUC's Authentik 2026.8.2 schema.
https://docs.goauthentik.io/add-secure-apps/providers/proxy/forward_auth/
https://docs.goauthentik.io/add-secure-apps/applications/manage_apps/
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen

HOST = "msgvault.beachlab.org"
MARKER = "NUC archive; managed by selfhosted/services/msgvault."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run as root on the NUC.")
    env = dict(line.split("=", 1) for line in Path("/opt/authentik/.env").read_text().splitlines() if "=" in line)

    def api(path, data=None, method=None):
        request = Request(
            "http://127.0.0.1:19000/api/v3/" + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Authorization": "Bearer " + env["AUTHENTIK_BOOTSTRAP_TOKEN"], "Content-Type": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except HTTPError as error:
            raise RuntimeError(f"{method or 'GET'} {path}: HTTP {error.code}") from None

    def items(path):
        page = api(path + "?page_size=200&superuser_full_list=true")
        if page.get("pagination", {}).get("total_pages", 1) > 1:
            raise RuntimeError("Inventory exceeded one page; inspect before provisioning.")
        return page["results"]

    flows = {flow["slug"]: flow for flow in items("flows/instances/")}
    flow = flows["beachlab-passkey"]
    stages = items("stages/authenticator/validate/")
    validate = next(stage for stage in stages if stage["name"] == "beachlab-passkey-validate")
    if (validate["device_classes"] != ["webauthn"] or validate["not_configured_action"] != "deny"
            or validate["webauthn_user_verification"] != "required"):
        raise RuntimeError("The existing flow is not the expected passkey-only flow.")
    bindings = [binding for binding in items("flows/bindings/") if binding["target"] == flow["pk"]]
    if not any(binding["stage"] == validate["pk"] for binding in bindings):
        raise RuntimeError("The passkey stage is not bound to the authentication flow.")
    user = next(user for user in items("core/users/") if user["username"] == "fran")
    if not user["is_active"]:
        raise RuntimeError("Fran's account is disabled.")
    query = ("from authentik.stages.authenticator_webauthn.models import WebAuthnDevice; "
             "print('ENROLLED=' + str(WebAuthnDevice.objects.filter("
             "user__username='fran',rp_id='auth.beachlab.org').count()))")
    result = subprocess.run(["docker", "exec", "authentik-server-1", "ak", "shell", "-c", query],
                            text=True, capture_output=True, check=True)
    enrolled = re.search(r"^ENROLLED=(\d+)$", result.stdout, re.M)
    if not enrolled or int(enrolled[1]) < 1:
        raise RuntimeError("Fran has no enrolled passkey for auth.beachlab.org.")

    providers = items("providers/proxy/")
    apps = items("core/applications/")
    provider = next((item for item in providers if item["external_host"].rstrip("/") == "https://" + HOST), None)
    app = next((item for item in apps if item["slug"] == "msgvault"), None)
    if app and app.get("meta_description") != MARKER:
        raise RuntimeError("An existing Msgvault application has uncertain ownership.")
    if provider and (not app or app.get("provider") != provider["pk"]):
        raise RuntimeError("An existing Msgvault provider has uncertain ownership.")
    outpost = next(item for item in items("outposts/instances/") if item["name"] == "authentik Embedded Outpost")
    print(f"Plan: https://{HOST}; existing beachlab-passkey flow; access only for fran.")
    if not args.apply:
        return

    backup_dir = Path("/opt/msgvault/backups")
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    backup_dir.chmod(0o700)
    backup = backup_dir / ("authentik-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump({"provider": provider, "application": app, "outpost": outpost}, output, indent=2)

    provider_data = {
        "name": "Msgvault", "external_host": "https://" + HOST,
        "mode": "forward_single", "cookie_domain": HOST,
        "authentication_flow": flow["pk"],
        "authorization_flow": flows["default-provider-authorization-implicit-consent"]["pk"],
        "invalidation_flow": flows["default-provider-invalidation-flow"]["pk"],
        "intercept_header_auth": False, "basic_auth_enabled": False, "skip_path_regex": "",
        "access_token_validity": "minutes=5", "refresh_token_validity": "hours=12",
    }
    if provider:
        if any(provider.get(key) != value for key, value in provider_data.items()):
            raise RuntimeError("Existing provider differs from the expected Msgvault configuration.")
    else:
        provider = api("providers/proxy/", provider_data, "POST")
    app_data = {
        "name": "Msgvault", "slug": "msgvault", "provider": provider["pk"],
        "group": "Servidor", "policy_engine_mode": "all",
        "meta_description": MARKER, "meta_launch_url": "https://" + HOST + "/",
    }
    if app:
        if any(app.get(key) != value for key, value in app_data.items()):
            raise RuntimeError("Existing application differs from the expected Msgvault configuration.")
    else:
        app = api("core/applications/", app_data, "POST")
    access = [binding for binding in items("policies/bindings/") if binding["target"] == app["pk"]]
    if access:
        if (len(access) != 1 or access[0].get("user") != user["pk"]
                or not access[0]["enabled"] or access[0]["negate"] or access[0]["failure_result"]
                or access[0].get("group") or access[0].get("policy")):
            raise RuntimeError("Existing access bindings differ; inspect before exposing the archive.")
    else:
        api("policies/bindings/", {"target": app["pk"], "user": user["pk"], "order": 0,
                                   "enabled": True, "negate": False, "failure_result": False}, "POST")

    # Read immediately before writing; preserve every unrelated provider/config.
    current = api(f"outposts/instances/{outpost['pk']}/")
    expected = sorted(set(current["providers"]) | {provider["pk"]})
    if current["providers"] != expected:
        api(f"outposts/instances/{outpost['pk']}/", {"providers": expected}, "PATCH")
    after = api(f"outposts/instances/{outpost['pk']}/")
    if sorted(after["providers"]) != expected or after["config"] != current["config"]:
        raise RuntimeError("Outpost readback differs; inspect before exposing the archive.")
    print(f"Provisioned Msgvault provider {provider['pk']}; access only for fran. Backup: {backup}")


if __name__ == "__main__":
    main()
