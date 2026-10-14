#!/usr/bin/env python3
"""Install an immutable, integrated Mebuko release. Does not expose Nginx or send mail."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--release", required=True)
    a = p.parse_args()
    if os.geteuid() != 0: raise SystemExit("Run as root")
    release = Path(a.release).resolve()
    if release.parent != Path("/opt/mebuko/releases") or not (release / "server.py").is_file():
        raise SystemExit("Expected a complete release under /opt/mebuko/releases")
    if subprocess.run(["getent", "passwd", "mebuko"], stdout=subprocess.DEVNULL).returncode:
        subprocess.run(["useradd", "--system", "--home-dir", "/var/lib/mebuko", "--shell", "/usr/sbin/nologin", "mebuko"], check=True)
    for path, mode in (("/var/lib/mebuko", 0o700), ("/etc/mebuko", 0o750)):
        Path(path).mkdir(parents=True, exist_ok=True, mode=mode)
        os.chmod(path, mode)
        shutil.chown(path, user="mebuko" if path.startswith("/var/") else "root", group="mebuko")
    for file in release.glob("*.service"):
        shutil.copy2(file, "/etc/systemd/system/" + file.name)
    for file in release.glob("*.timer"):
        shutil.copy2(file, "/etc/systemd/system/" + file.name)
    shutil.copy2(release / "mebuko.logrotate", "/etc/logrotate.d/mebuko")
    hook = Path("/etc/letsencrypt/renewal-hooks/deploy/50-mebuko-nginx")
    hook.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(release / "mebuko-certbot-deploy.sh", hook)
    os.chmod(hook, 0o755)
    link = Path("/opt/mebuko/current")
    if link.exists() and not link.is_symlink():
        raise RuntimeError("Refusing to replace a non-symlink runtime")
    temporary = link.with_name("next")
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError("Pending activation already exists")
    temporary.symlink_to(release)
    temporary.replace(link)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    print("Mebuko release linked; configure private environment before starting.")


if __name__ == "__main__": main()
