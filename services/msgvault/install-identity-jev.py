#!/usr/bin/env python3
"""Enable Msgvault's native Jev scorer on the existing NUC.

Install the private TYPESAFE_API_KEY env file beforehand. No key values enter
Git, command arguments or output. The serving daemon owns consent and journal
writes. Scoring is operator-started and never accepts identity links.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

HOME_DIR = Path("/var/lib/msgvault")
CONFIG = HOME_DIR / "config.toml"
ENV_FILE = HOME_DIR / "tokens/identity-jev.env"
DROPIN = Path("/etc/systemd/system/msgvault.service.d/40-identity-jev.conf")
UNITS = ["msgvault.service", "msgvault-mcp.service"]
MODEL = "jev-1.13.0"
ORIGIN = "https://api.typesafe.ai"
SOURCE = Path(__file__).resolve().parent


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_credential(text):
    """Parse data; never source a shell file or interpolate its value."""
    lines = [line.strip() for line in text.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) != 1 or not lines[0].startswith("TYPESAFE_API_KEY="):
        raise ValueError("Expected exactly one TYPESAFE_API_KEY assignment")
    key = lines[0].split("=", 1)[1]
    if len(key) >= 2 and key[0] in "\"'" and key[-1] == key[0]:
        key = key[1:-1]
    if not re.fullmatch(r"[A-Za-z0-9._:-]{16,4096}", key):
        raise ValueError("Jev credential is empty or has an unsupported format")
    return key


def private_credential(path):
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError("Expected a regular private credential file with mode 0600")
    return parse_credential(path.read_text())


def scoring_config(original, template):
    """Preserve existing sections byte for byte and reject conflicting ownership."""
    text = original.decode()
    pattern = r"(?ms)^[ \t]*\[people\.identity_scoring\][^\n]*\n(.*?)(?=^[ \t]*\[|\Z)"
    matches = list(re.finditer(pattern, text))
    expected = re.search(pattern, template.decode())
    if expected is None:
        raise ValueError("Identity scoring template has no section")
    if matches:
        if len(matches) != 1 or matches[0].group(0).strip() != expected.group(0).strip():
            raise ValueError("Preserving an existing identity scoring configuration")
        return original
    return original + (b"" if original.endswith(b"\n\n") else b"\n\n") + template


def atomic_config(content):
    metadata = CONFIG.stat()
    fd, name = tempfile.mkstemp(prefix=".identity-jev-", dir=CONFIG.parent)
    try:
        os.fchmod(fd, stat.S_IMODE(metadata.st_mode))
        os.fchown(fd, metadata.st_uid, metadata.st_gid)
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, CONFIG)
    finally:
        Path(name).unlink(missing_ok=True)


def request_json(url, key, body=None):
    headers = {"Authorization": "Bearer " + key,
               "User-Agent": "msgvault-identity-setup/1"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(url, headers=headers, data=data)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            return json.loads(response.read(1 << 20))
    except urllib.error.HTTPError as error:
        raise RuntimeError("API returned HTTP " + str(error.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("API connection failed") from None


def provider_preflight(key):
    models = request_json(ORIGIN + "/v1/models", key)
    if not any(row.get("name") == MODEL for row in models.get("models", [])):
        raise RuntimeError("TypeSafe account does not expose the native pinned Jev model")
    # Synthetic fixture only; no archive identities leave the host in preflight.
    result = request_json(ORIGIN + "/v1/systemone", key, {
        "model": MODEL,
        "state": {"left": {"name": "Setup fixture", "email": "setup@example.invalid"},
                  "right": {"name": "Setup fixture", "email": "setup@example.invalid"}},
        "questions": {"same_person": {"type": "noul", "instructions":
            "Do left and right describe the same synthetic fixture?"}},
    })
    answer = result.get("answers", {}).get("same_person", {})
    probability = answer.get("noul")
    if (result.get("model") != MODEL or answer.get("type") != "noul"
            or isinstance(probability, bool) or not isinstance(probability, (float, int))
            or not math.isfinite(probability) or not 0 <= probability <= 1):
        raise RuntimeError("Jev response failed native model/Noul validation")
    return {"model": MODEL, "synthetic_check_passed": True}


def owner_key():
    text = CONFIG.read_text()
    section = re.search(r"(?ms)^\[server\]\s*\n(.*?)(?=^\[|\Z)", text)
    if section is None:
        raise RuntimeError("Expected existing Msgvault server configuration")
    match = re.search(r"(?m)^\s*api_key\s*=\s*[^\n]*?([0-9a-f]{64})", section.group(1))
    if match is None:
        raise RuntimeError("Expected existing Msgvault owner credential")
    return match.group(1)


def native_api(path, body=None):
    return request_json("http://127.0.0.1:8096" + path, owner_key(), body)


def wait_healthy():
    for _ in range(30):
        try:
            if native_api("/health").get("status") == "ok":
                return
        except (OSError, ValueError, RuntimeError):
            pass
        time.sleep(1)
    raise RuntimeError("Existing daemon did not become healthy")


def save_receipt(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(0o600)


def main():
    if os.geteuid() != 0:
        raise RuntimeError("Run as root on the existing Msgvault NUC")
    os.umask(0o077)
    key = private_credential(ENV_FILE)
    metadata = CONFIG.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RuntimeError("Expected the private regular Msgvault configuration")
    original = CONFIG.read_bytes()
    updated = scoring_config(original, (SOURCE / "identity-jev.toml").read_bytes())
    dropin = (SOURCE / "identity-jev.conf").read_bytes()
    previous_dropin = DROPIN.is_file() and not DROPIN.is_symlink() and DROPIN.read_bytes() == dropin
    if (DROPIN.exists() or DROPIN.is_symlink()) and not previous_dropin:
        raise RuntimeError("Preserving an existing identity scoring drop-in")
    for unit in UNITS:
        command("systemctl", "is-active", "--quiet", unit)
    receipt = {"provider_preflight": provider_preflight(key), "archive_provider_requests": 0}
    command("systemctl", "start", "msgvault-backup.service")
    if command("systemctl", "show", "msgvault-backup.service", "--property=Result", "--value").strip() != "success":
        raise RuntimeError("Encrypted NAS backup did not succeed")
    checkpoint = Path("/var/lib/msgvault-backup") / ("identity-jev-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    checkpoint.mkdir(mode=0o700)
    (checkpoint / "config-before.toml").write_bytes(original)
    credential_hashes = {str(p): digest(p) for p in (HOME_DIR / "tokens").glob("**/*.json") if "provider" in str(p)}
    fingerprint = None
    granted = False
    try:
        command("systemctl", "stop", *UNITS)
        if CONFIG.read_bytes() != original:
            raise RuntimeError("Configuration changed during setup; preserving it")
        atomic_config(updated)
        DROPIN.parent.mkdir(mode=0o755, exist_ok=True)
        if not previous_dropin:
            with DROPIN.open("xb") as output:
                output.write(dropin)
            DROPIN.chmod(0o644)
        command("systemctl", "daemon-reload")
        command("systemctl", "start", *UNITS)
        wait_healthy()
        status = native_api("/api/v1/identity/scoring/status")
        if not status.get("enabled") or not status.get("credential_available") or status.get("model_id") != MODEL:
            raise RuntimeError("Native identity scorer configuration failed readback")
        fingerprint = status["disclosure_fingerprint"]
        if not status.get("consent_active"):
            decision = native_api("/api/v1/identity/scoring/consent", {"disclosure_fingerprint": fingerprint})
            if not decision.get("consent_active"):
                raise RuntimeError("Native identity consent failed readback")
            granted = True
        receipt["status"] = native_api("/api/v1/identity/scoring/status")
        if not receipt["status"].get("ready"):
            raise RuntimeError("Native identity scorer is not ready")
        if credential_hashes != {str(p): digest(p) for p in (HOME_DIR / "tokens").glob("**/*.json") if "provider" in str(p)}:
            raise RuntimeError("Existing provider credential files changed")
        command("systemctl", "is-active", *UNITS)
        receipt["activated"] = True
    except BaseException:
        if granted:
            try:
                native_api("/api/v1/identity/scoring/revoke", {"disclosure_fingerprint": fingerprint})
            except (OSError, ValueError, RuntimeError):
                receipt["consent_revoke_failed"] = True
        command("systemctl", "stop", *UNITS)
        if CONFIG.read_bytes() == updated:
            atomic_config(original)
        elif CONFIG.read_bytes() != original:
            receipt["configuration_changed_preserved"] = True
        if not previous_dropin and DROPIN.is_file() and not DROPIN.is_symlink() and DROPIN.read_bytes() == dropin:
            DROPIN.unlink()
        command("systemctl", "daemon-reload")
        command("systemctl", "start", *UNITS)
        wait_healthy()
        receipt.update(activated=False, rolled_back=True)
        save_receipt(checkpoint / "activation.json", receipt)
        raise
    save_receipt(checkpoint / "activation.json", receipt)
    print(json.dumps({"activated": True, "ready": True, "model": MODEL, "checkpoint": str(checkpoint)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not emit request objects, vendor bodies, secret values or tracebacks.
        print(json.dumps({"activated": False, "error": str(error)}))
        raise SystemExit(1) from None
