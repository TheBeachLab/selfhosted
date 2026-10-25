#!/usr/bin/env bash
# Run on the NUC after editorial approval and review of content/ + media/.
set -euo pipefail
exec 9>/run/lock/housing-podcast-publish.lock
flock -n 9 || { echo 'A publication is already running.' >&2; exit 1; }
release="$(date -u +%Y%m%dT%H%M%SZ)-$$"
private=/home/git/podcast
public=/var/www/podcast
python3 /usr/local/lib/housing-podcast/build.py \
    --content "$private/content" --media "$private/media" \
    --output "$public/releases/$release"
chmod -R a+rX "$public/releases/$release"
ln -s "releases/$release" "$public/current.next"
mv -Tf "$public/current.next" "$public/current"
printf 'Activated %s\n' "$release"
