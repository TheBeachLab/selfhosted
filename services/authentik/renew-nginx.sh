#!/bin/sh
# Certbot deploy hook: load the renewed Authentik certificate without downtime.
set -eu
if [ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/auth.beachlab.org ]; then
    /usr/sbin/nginx -t
    /bin/systemctl reload nginx
fi
