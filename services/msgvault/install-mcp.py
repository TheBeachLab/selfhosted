#!/usr/bin/env python3
"""First installation of the private read-only MCP endpoint and stdio bridge."""
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import urlopen
import venv


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run as root on the NUC.")
    source = Path(__file__).resolve().parent
    config = Path("/var/lib/msgvault/mcp.toml")
    client = Path("/usr/local/bin/msgvault-mcp-client")
    service = Path("/etc/systemd/system/msgvault-mcp.service")
    for path in [config, client, service]:
        if path.exists() or path.is_symlink():
            raise SystemExit("Preserving existing MCP installation: " + str(path))
    if subprocess.check_output(["ss", "-H", "-lnt", "sport = :8097"], text=True).strip():
        raise SystemExit("Port 8097 is occupied.")
    base = Path("/var/lib/msgvault/config.toml").read_text()
    daemon_keys = re.findall(r'^api_key = "([0-9a-f]{64})"$', base, re.M)
    if len(daemon_keys) != 1:
        raise SystemExit("Expected one daemon API key; inspect configuration.")
    subprocess.run(["systemctl", "is-active", "--quiet", "msgvault"], check=True)
    environment = Path("/opt/msgvault/mcp-venv")
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(environment / "bin/pip"), "install", "--quiet", "--disable-pip-version-check",
                    "-r", str(source / "mcp-requirements.txt")], check=True)
    new = source.joinpath("mcp.toml.in").read_text()
    new = new.replace("__MCP_KEY__", secrets.token_hex(32)).replace("__DAEMON_KEY__", daemon_keys[0])
    fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write(new)
    account = pwd.getpwnam("msgvault")
    os.chown(config, account.pw_uid, account.pw_gid)
    shutil.copyfile(source / "mcp-client.py", client)
    client.chmod(0o755)
    shutil.copyfile(source / "msgvault-mcp.service", service)
    service.chmod(0o644)
    deployment = Path("/opt/msgvault/deployment")
    names = ["install-mcp.py", "mcp-client.py", "mcp-proxy-compat.py", "probe-mcp.py", "mcp.toml.in", "msgvault-mcp.service", "mcp-requirements.txt"]
    for name in names:
        destination = deployment / name
        if destination.exists():
            raise SystemExit("Preserving existing deployment source: " + str(destination))
        shutil.copyfile(source / name, destination)
        destination.chmod(0o755 if name.endswith(".py") else 0o644)
    subprocess.run(["systemd-analyze", "verify", str(service)], check=True)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "enable", "--now", "msgvault-mcp.service"], check=True)
    for attempt in range(30):
        try:
            with urlopen("http://127.0.0.1:8097/mcp", timeout=1):
                raise SystemExit("Unexpected unauthenticated MCP access.")
        except HTTPError as error:
            if error.code == 401:
                break
            raise
        except OSError:
            time.sleep(0.5)
    else:
        raise SystemExit("MCP did not become ready; inspect journalctl -u msgvault-mcp.")
    print("Private read-only MCP: http://127.0.0.1:8097/mcp; stdio client installed.")


if __name__ == "__main__":
    main()
