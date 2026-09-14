#!/bin/bash
set -eu
# Fail if Internet can fall back to Docker's gateway or bypass the VPN.
if ip -4 route show default | grep -q .; then
    echo 'Unsafe non-VPN default route exists'
    exit 1
fi
if ! ip -4 route get 1.1.1.1 | grep -q 'dev tun0'; then
    echo 'Internet route is not using tun0'
    exit 1
fi
exec /etc/scripts/healthcheck.sh
