#!/usr/bin/env python3
"""Apply only Beachlab's appearance through the Authentik 2026.8.2 API.

Run on pink-sudo as root. Default is a read-only plan. Never call configure.py.
Sources and operator validation/rollback: doc/authentik.md, Beach Lab branding.
"""

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


BASE = "http://127.0.0.1:19000"
HOST = "auth.beachlab.org"
ASSETS = Path(__file__).parent / "branding" / "assets"
CSS = Path(__file__).parent / "branding" / "beachlab.css"
FIELDS = (
    "branding_logo", "branding_favicon", "branding_default_flow_background",
    "branding_custom_css",
)
MEDIA = ("beachlab-logo.svg", "beachlab-favicon.svg", "beachlab-caustics.png")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def protected(brand):
    return {key: value for key, value in brand.items() if key not in FIELDS}


class API:
    def __init__(self):
        values = {}
        for line in Path("/opt/authentik/.env").read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip("\"'")
        self.token = values["AUTHENTIK_BOOTSTRAP_TOKEN"]

    def request(self, path, data=None, method="GET", content_type="application/json"):
        body = json.dumps(data).encode() if isinstance(data, dict) else data
        request = Request(
            BASE + "/api/v3/" + path, data=body, method=method,
            headers={"Authorization": "Bearer " + self.token,
                     "Content-Type": content_type, "Host": HOST},
        )
        try:
            with urlopen(request, timeout=30) as response:
                result = response.read()
                return json.loads(result) if result else None
        except HTTPError as error:
            # Response bodies can contain credentials or signed media URLs.
            raise RuntimeError(f"{method} {path.split('?')[0]}: HTTP {error.code}") from None

    def file_bytes(self, url):
        # The file list's signed URL is used in memory only; never log it.
        parts = urlsplit(url)
        if not parts.path.startswith("/files/media/public/"):
            raise RuntimeError("Unexpected media URL; refusing a different backend")
        request = Request(BASE + parts.path + "?" + parts.query, headers={"Host": HOST})
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as error:
            raise RuntimeError(f"Media verification: HTTP {error.code}") from None

    def upload(self, name, content):
        boundary = "BeachlabBranding" + uuid.uuid4().hex
        mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"name\"\r\n\r\n{name}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"usage\"\r\n\r\nmedia\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{Path(name).name}\"\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        self.request("admin/file/", body, "POST", "multipart/form-data; boundary=" + boundary)


def current_brand(api):
    version = api.request("admin/version/")["version_current"]
    if version != "2026.8.2":
        raise RuntimeError(f"Review CSS against installed Authentik {version} before applying")
    current = api.request("core/brands/current/")
    response = api.request("core/brands/?page_size=200")
    if response["pagination"]["count"] > 200:
        raise RuntimeError("Brand list exceeds this script's bounded selection")
    candidates = [brand for brand in response["results"]
                  if brand["domain"] == current["matched_domain"]]
    if len(candidates) != 1:
        raise RuntimeError("Cannot identify exactly one brand for auth.beachlab.org")
    brand = candidates[0]
    if brand["domain"] != HOST and not (brand["default"] and brand["domain"] == "authentik-default"):
        raise RuntimeError("Current brand is neither auth.beachlab.org nor the established default")
    if current.get("flow_authentication") != "beachlab-passkey":
        raise RuntimeError("Unexpected authentication flow; refusing to apply branding")
    return brand


def desired_branding():
    contents = {name: (ASSETS / name).read_bytes() for name in MEDIA}
    css = CSS.read_text()
    for key, name in (("UNIVERS_THIN", "univers-thin.woff2"),
                      ("UNIVERS_LIGHT", "univers-light.woff2")):
        font = base64.b64encode((ASSETS / name).read_bytes()).decode()
        css = css.replace("{{" + key + "}}", "data:font/woff2;base64," + font)
    if "{{" in css:
        raise RuntimeError("Unresolved CSS font placeholder")
    revision = digest({"css": css, "assets": {
        name: hashlib.sha256(content).hexdigest() for name, content in contents.items()
    }})[:12]
    prefix = "branding/beachlab-" + revision + "/"
    return {
        "branding_logo": prefix + "beachlab-logo.svg",
        "branding_favicon": prefix + "beachlab-favicon.svg",
        "branding_default_flow_background": prefix + "beachlab-caustics.png",
        # DRF's model TextField -> CharField trims surrounding whitespace.
        # Keep the revision tied to the source package, then send canonical CSS.
        "branding_custom_css": css.strip(),
    }, {prefix + name: content for name, content in contents.items()}


def save_backup(directory, payload):
    directory = directory.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.stat().st_mode & 0o077:
        raise RuntimeError("Backup directory must be private (mode 0700)")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / (stamp + "-" + uuid.uuid4().hex[:8] + ".json")
    with path.open("x") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return path


def verify(api, before, wanted):
    after = api.request(f"core/brands/{before['brand_uuid']}/")
    if any(after[field] != wanted[field] for field in FIELDS):
        raise RuntimeError("Branding readback differs; use the saved backup to investigate")
    if protected(after) != protected(before):
        raise RuntimeError("Non-branding fields changed during the operation; investigate concurrency")
    return after


def apply(api, brand, wanted, files, backup_dir):
    if all(brand[field] == wanted[field] for field in FIELDS):
        print("Branding already matches; no changes.")
        return
    backup = save_backup(backup_dir, {
        "format": 1, "host": HOST, "brand_uuid": brand["brand_uuid"],
        "before": {field: brand[field] for field in FIELDS}, "after": wanted,
        "protected_sha256": digest(protected(brand)),
        "assets_sha256": {name: hashlib.sha256(content).hexdigest()
                          for name, content in files.items()},
    })
    print("Private rollback backup: " + str(backup))
    existing = {item["name"]: item for item in api.request("admin/file/?manageable_only=true")}
    for name, content in files.items():
        if name in existing:
            if api.file_bytes(existing[name]["url"]) != content:
                raise RuntimeError("Existing immutable branding asset differs: " + name)
        else:
            api.upload(name, content)
    # Verify every asset through Authentik before referencing it from the brand.
    existing = {item["name"]: item for item in api.request("admin/file/?manageable_only=true")}
    for name, content in files.items():
        if name not in existing or api.file_bytes(existing[name]["url"]) != content:
            raise RuntimeError("Uploaded media did not verify: " + name)
    fresh = api.request(f"core/brands/{brand['brand_uuid']}/")
    if fresh != brand:
        raise RuntimeError("Brand changed since the plan; refusing to overwrite concurrent work")
    api.request(f"core/brands/{brand['brand_uuid']}/", wanted, "PATCH")
    verify(api, brand, wanted)
    print("Applied four appearance fields; all other brand fields unchanged.")


def rollback(api, brand, path):
    saved = json.loads(path.read_text())
    if (saved.get("format"), saved.get("host"), saved.get("brand_uuid")) != (1, HOST, brand["brand_uuid"]):
        raise RuntimeError("Backup does not identify this brand")
    if set(saved["before"]) != set(FIELDS) or set(saved["after"]) != set(FIELDS):
        raise RuntimeError("Backup contains fields outside the branding scope")
    # Accept backups from the first application, whose proposed CSS still
    # included a final newline; the API persisted its stripped equivalent.
    for state in ("before", "after"):
        saved[state]["branding_custom_css"] = saved[state]["branding_custom_css"].strip()
    if all(brand[field] == saved["before"][field] for field in FIELDS):
        print("Backup branding already restored; no changes.")
        return
    if any(brand[field] != saved["after"][field] for field in FIELDS):
        raise RuntimeError("Branding was changed after this backup; refusing to overwrite it")
    api.request(f"core/brands/{brand['brand_uuid']}/", saved["before"], "PATCH")
    verify(api, brand, saved["before"])
    print("Restored four appearance fields; other brand fields unchanged. Media retained.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--dry-run", action="store_true", help="read-only plan (default)")
    action.add_argument("--apply", action="store_true", help="upload immutable media and PATCH appearance")
    action.add_argument("--rollback", type=Path, help="restore appearance from this private backup")
    parser.add_argument("--backup-dir", type=Path, default=Path("/opt/authentik/branding-backups"))
    args = parser.parse_args()
    os.umask(0o077)
    api = API()
    brand = current_brand(api)
    print(f"Selected {HOST}: domain={brand['domain']}, default={brand['default']}")
    if args.rollback:
        rollback(api, brand, args.rollback)
        return
    wanted, files = desired_branding()
    print("Appearance fields: " + ", ".join(FIELDS))
    print(f"Assets: {len(files)} immutable media files, {sum(map(len, files.values()))} bytes; "
          f"CSS with embedded fonts: {len(wanted['branding_custom_css'].encode())} bytes.")
    if args.apply:
        apply(api, brand, wanted, files, args.backup_dir)
    else:
        print("Read-only plan; no brand, file or backup writes.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, KeyError, ValueError, URLError) as error:
        print("Branding failed: " + str(error), file=sys.stderr)
        sys.exit(1)
