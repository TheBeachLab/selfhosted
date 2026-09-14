#!/bin/sh
# Certbot deploy hook: load the renewed Authentik certificate without downtime.
set -eu
case "${RENEWED_LINEAGE:-}" in
  /etc/letsencrypt/live/auth.beachlab.org|/etc/letsencrypt/live/admin.beachlab.org)
    /usr/sbin/nginx -t
    /bin/systemctl reload nginx
    ;;
esac
