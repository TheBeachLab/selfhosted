#!/bin/sh
# Certbot passes the renewed certificate lineage to deploy hooks:
# https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates
set -eu
if [ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/mebuko.de ]; then
    /usr/sbin/nginx -t
    /bin/systemctl reload nginx
fi
