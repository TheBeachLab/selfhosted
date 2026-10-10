#!/usr/bin/env bash
# First installation only; preserve an existing archive and its credentials.
# Official release and checksum:
# https://github.com/kenn-io/msgvault/releases/tag/v0.21.0
set -euo pipefail

MSGVAULT_VERSION=0.21.0
MSGVAULT_ARCHIVE_SHA256=56b2438eab14f3cadd15b6edecc4ea30454b6584c1039c2d5593a0afa77d7497
MSGVAULT_SOURCE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if [[ $EUID -ne 0 ]]; then
    echo 'Run this installer with sudo.' >&2
    exit 1
fi
if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
    echo 'This pinned installer requires Linux x86_64.' >&2
    exit 1
fi
for existing in /opt/msgvault /var/lib/msgvault /usr/local/bin/msgvault /etc/systemd/system/msgvault.service; do
    if [[ -e $existing || -L $existing ]]; then
        echo "Preserving existing installation: $existing" >&2
        exit 1
    fi
done
for required in curl sha256sum tar python3 systemctl systemd-analyze ss useradd; do
    command -v "$required" >/dev/null
done
if ss -H -lnt 'sport = :8096' | read -r _; then
    echo 'Port 8096 is already in use.' >&2
    exit 1
fi
MSGVAULT_STAGE=$(mktemp -d /var/tmp/msgvault-install.XXXXXX)
trap 'rm -rf -- "$MSGVAULT_STAGE"' EXIT
MSGVAULT_ARCHIVE="msgvault_${MSGVAULT_VERSION}_linux_amd64.tar.gz"
curl --fail --location --silent --show-error --retry 3 \
    "https://github.com/kenn-io/msgvault/releases/download/v${MSGVAULT_VERSION}/${MSGVAULT_ARCHIVE}" \
    -o "$MSGVAULT_STAGE/$MSGVAULT_ARCHIVE"
printf '%s  %s\n' "$MSGVAULT_ARCHIVE_SHA256" "$MSGVAULT_STAGE/$MSGVAULT_ARCHIVE" | sha256sum --check
tar -xzf "$MSGVAULT_STAGE/$MSGVAULT_ARCHIVE" -C "$MSGVAULT_STAGE" \
    --no-same-owner --no-same-permissions msgvault
"$MSGVAULT_STAGE/msgvault" version

if getent passwd msgvault >/dev/null; then
    echo 'Preserving existing msgvault user; inspect it before installation.' >&2
    exit 1
fi
useradd --system --user-group --home-dir /var/lib/msgvault --no-create-home \
    --shell /usr/sbin/nologin msgvault
install -d -o root -g root -m 0755 "/opt/msgvault/$MSGVAULT_VERSION"
install -o root -g root -m 0755 "$MSGVAULT_STAGE/msgvault" "/opt/msgvault/$MSGVAULT_VERSION/msgvault"
ln -s "/opt/msgvault/$MSGVAULT_VERSION/msgvault" /usr/local/bin/msgvault
install -d -o msgvault -g msgvault -m 0700 /var/lib/msgvault
python3 - "$MSGVAULT_SOURCE_DIR/config.toml.in" <<'PY'
from pathlib import Path
import os, pwd, secrets, sys
config = Path(sys.argv[1]).read_text()
config = config.replace('__API_KEY__', secrets.token_hex(32))
path = '/var/lib/msgvault/config.toml'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as output:
    output.write(config)
account = pwd.getpwnam('msgvault')
os.chown(path, account.pw_uid, account.pw_gid)
PY
# The supervised serve process initializes the database. init-db also routes
# through a daemon and cannot bootstrap with daemon_auto_start=false.
install -o root -g root -m 0644 "$MSGVAULT_SOURCE_DIR/msgvault.service" /etc/systemd/system/msgvault.service
systemd-analyze verify /etc/systemd/system/msgvault.service
systemctl daemon-reload
systemctl enable --now msgvault.service
python3 - <<'PY'
import time
from urllib.request import urlopen
for attempt in range(60):
    try:
        with urlopen('http://127.0.0.1:8096/health', timeout=1) as response:
            if response.status == 200:
                break
    except OSError:
        pass
    time.sleep(0.5)
else:
    raise SystemExit('Service did not become ready; inspect journalctl -u msgvault')
PY
echo 'Local backend: http://127.0.0.1:8096/'
