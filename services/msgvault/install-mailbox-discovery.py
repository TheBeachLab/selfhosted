#!/usr/bin/env python3
"""Activate the tested native discovery daemon and its unattended NUC timer.

Requires the existing private Jev setup. No API keys or message bodies enter
output. Recovery receipts are private; the serving daemon performs every DB write.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

SOURCE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("jev_setup", SOURCE / "install-identity-jev.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)
LINK = Path("/usr/local/bin/msgvault")
NEW_BINARY = Path("/opt/msgvault/0.21.0-discovery-3/msgvault")
OLD_BINARY_SHA = "b2e7c862150a12a7efe7b54bcf9ae77080e98df7b43aa7253a6fba5e2ea6c91d"
PREVIOUS_DISCOVERY_SHA = "8d81836604ae2ef60238e59d831f75639f04d26ea3345ce120903b4e8636b303"
OLD_BACKUP_SHA = "943a6f4cd95a78f53752106390d2a3a561b8e66c9913d4abbd103111646734cd"
DISCOVERY_BACKUP_SHA = "65c755633be4d80b333b47ef7c4958b7f05bccf255a4d62bf6ef2b675c4951e6"
BACKUP = Path("/usr/local/sbin/msgvault-backup")
DROPIN = Path("/etc/systemd/system/msgvault.service.d/50-mailbox-discovery.conf")
RUNNER = Path("/usr/local/sbin/msgvault-mailbox-discovery")
SERVICE = Path("/etc/systemd/system/msgvault-mailbox-discovery.service")
TIMER = Path("/etc/systemd/system/msgvault-mailbox-discovery.timer")
UNITS = ["msgvault.service", "msgvault-mcp.service"]


def replace_link(target):
    temporary = LINK.with_name(".msgvault-discovery-" + uuid.uuid4().hex)
    try:
        temporary.symlink_to(target)
        os.replace(temporary, LINK)
    finally:
        temporary.unlink(missing_ok=True)


def hashes():
    return {str(p): setup.digest(p) for p in Path("/var/lib/msgvault/tokens").rglob("*") if p.is_file()}


def install_new(source, target, mode):
    with target.open("xb") as output:
        output.write(source.read_bytes())
    target.chmod(mode)


def main():
    if os.geteuid() != 0:
        raise RuntimeError("Run as root on the existing Msgvault NUC")
    os.umask(0o077)
    if not LINK.is_symlink() or not NEW_BINARY.is_file():
        raise RuntimeError("Expected the tested native build and existing daemon symlink")
    old_target = LINK.resolve(strict=True)
    if (setup.digest(old_target) not in (OLD_BINARY_SHA, PREVIOUS_DISCOVERY_SHA)
            or setup.digest(BACKUP) not in (OLD_BACKUP_SHA, DISCOVERY_BACKUP_SHA)):
        raise RuntimeError("Preserving runtime files that differ from the verified deployment")
    runtime_files = (("mailbox-discovery.conf", DROPIN, 0o644),
                     ("mailbox-discovery.py", RUNNER, 0o755),
                     (SERVICE.name, SERVICE, 0o644), (TIMER.name, TIMER, 0o644))
    for filename, target, _ in runtime_files:
        if ((target.exists() or target.is_symlink())
                and (target.is_symlink() or not target.is_file()
                     or target.read_bytes() != (SOURCE / filename).read_bytes())):
            raise RuntimeError("Preserving a different discovery installation: " + str(target))
    setup.command("sha256sum", "--check", str(NEW_BINARY.parent / "SHA256SUMS"))
    if "v0.21.0-discovery-3" not in setup.command(str(NEW_BINARY), "version"):
        raise RuntimeError("Unexpected candidate daemon version")
    before_status = setup.native_api("/api/v1/identity/scoring/status")
    if not before_status.get("ready") or before_status.get("model_id") != "jev-1.13.0":
        raise RuntimeError("Existing native Jev configuration is not ready")
    config_hash = setup.digest(setup.CONFIG)
    credential_hashes = hashes()
    timer_was_enabled = subprocess.run(["systemctl", "is-enabled", "--quiet", TIMER.name],
                                       capture_output=True).returncode == 0
    setup.command("systemctl", "start", "msgvault-backup.service")
    if setup.command("systemctl", "show", "msgvault-backup.service", "--property=Result", "--value").strip() != "success":
        raise RuntimeError("Encrypted pre-activation NAS backup did not succeed")
    checkpoint = Path("/var/lib/msgvault-backup") / ("mailbox-discovery-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    checkpoint.mkdir(mode=0o700)
    shutil.copyfile(BACKUP, checkpoint / "backup-before.py")
    fingerprint = None
    granted = False
    installed = []
    receipt = {"previous_binary": str(old_target), "new_binary": str(NEW_BINARY),
               "new_binary_sha256": setup.digest(NEW_BINARY), "config_sha256": config_hash,
               "provider": "Jev", "model": "jev-1.13.0", "checkpoint": str(checkpoint)}
    setup.save_receipt(checkpoint / "activation.json", receipt)
    try:
        subprocess.run(["systemctl", "stop", TIMER.name, SERVICE.name], capture_output=True)
        setup.command("systemctl", "stop", *UNITS)
        if setup.digest(setup.CONFIG) != config_hash or hashes() != credential_hashes:
            raise RuntimeError("Existing provider configuration changed during activation")
        for filename, target, mode in runtime_files:
            if not target.exists():
                install_new(SOURCE / filename, target, mode)
                installed.append(target)
        setup.command("systemd-analyze", "verify", str(SERVICE), str(TIMER))
        shutil.copyfile(SOURCE / "backup.py", BACKUP)
        BACKUP.chmod(0o755)
        replace_link(NEW_BINARY)
        setup.command("systemctl", "daemon-reload")
        setup.command("systemctl", "start", *UNITS)
        setup.wait_healthy()
        status = setup.native_api("/api/v1/identity/discovery/status")
        if not status.get("enabled") or not status.get("credential_available") or status.get("disclosure", {}).get("model_id") != "jev-1.13.0":
            raise RuntimeError("New native discovery configuration is not ready")
        fingerprint = status["disclosure_fingerprint"]
        decision = setup.native_api("/api/v1/identity/discovery/consent", {"disclosure_fingerprint": fingerprint})
        granted = decision.get("changed", False)
        status = setup.native_api("/api/v1/identity/discovery/status")
        if not status.get("ready"):
            raise RuntimeError("Separate native signature consent did not become active")
        # The boot timer performs the initial scan and every calendar run after
        # that. This installer does not call the run endpoint or classify mail.
        setup.command("systemctl", "enable", "--now", TIMER.name)
        setup.command("systemctl", "is-active", "--quiet", TIMER.name, *UNITS)
        if hashes() != credential_hashes or setup.digest(setup.CONFIG) != config_hash:
            raise RuntimeError("Existing credentials/configuration changed during activation")
        receipt.update(status="active", discovery_status=status,
                       credentials_unchanged=True, config_unchanged=True,
                       timer_enabled=True, activation_completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        setup.save_receipt(checkpoint / "activation.json", receipt)
        print(json.dumps({key: receipt[key] for key in
                          ("status", "model", "checkpoint", "credentials_unchanged", "config_unchanged", "timer_enabled")}))
    except Exception as error:
        receipt.update(status="activation_failed", error_class=type(error).__name__)
        # RuntimeError messages are generated by this installer or its safe
        # HTTP helper. Never persist a raw request or provider response.
        if isinstance(error, RuntimeError):
            receipt["error"] = str(error)
        setup.save_receipt(checkpoint / "activation.json", receipt)
        subprocess.run(["systemctl", "disable", "--now", TIMER.name], capture_output=True)
        subprocess.run(["systemctl", "stop", SERVICE.name], capture_output=True)
        if granted and fingerprint:
            try:
                setup.native_api("/api/v1/identity/discovery/revoke", {"disclosure_fingerprint": fingerprint})
            except Exception:
                pass
        setup.command("systemctl", "stop", *UNITS)
        replace_link(old_target)
        shutil.copyfile(checkpoint / "backup-before.py", BACKUP)
        BACKUP.chmod(0o755)
        for target in installed:
            target.unlink()
        setup.command("systemctl", "daemon-reload")
        setup.command("systemctl", "start", *UNITS)
        setup.wait_healthy()
        if timer_was_enabled:
            setup.command("systemctl", "enable", "--now", TIMER.name)
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Native discovery activation failed; inspect the private checkpoint and service state") from None
