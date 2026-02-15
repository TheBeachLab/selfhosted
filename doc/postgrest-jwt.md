# PostgREST JWT Gateway (Nginx + auth_request)

**Author:** Mr. Watson 🦄
**Date:** 2026-02-15

<!-- vim-markdown-toc GFM -->

- [Goal](#goal)
- [What was configured](#what-was-configured)
- [Architecture](#architecture)
- [Files](#files)
- [Routes](#routes)
- [Secrets and keys](#secrets-and-keys)
- [Operations](#operations)
- [Add/rotate API keys](#addrotate-api-keys)
- [Promote from free to paid roles](#promote-from-free-to-paid-roles)
- [Rollback](#rollback)
- [Notes](#notes)

<!-- vim-markdown-toc -->

## Goal

Add a self-hosted JWT access layer in front of PostgREST for monetizable endpoints, without breaking existing routes.

## What was configured

- New local auth service validates `X-API-Key` and signs short-lived JWTs
- Nginx uses `auth_request` to call that service
- Protected routes inject `Authorization: Bearer <jwt>` to PostgREST
- Existing `beachlab.org/api/telemetry/...` remains unchanged

## Architecture

```text
Client
  -> Nginx (api.beachlab.org)
      -> /telemetry/public/*  -> PostgREST (anon)
      -> /telemetry/pro/*     -> auth_request -> auth-jwt service
                                   (if valid key => signed JWT)
                                -> PostgREST (JWT role)
```

## Files

- `/usr/local/bin/auth_jwt_service.py`
- `/etc/auth-jwt-service.env`
- `/etc/auth-jwt-keys.csv`
- `/etc/systemd/system/auth-jwt.service`
- `/etc/postgrest-telemetry.conf`
- `/etc/nginx/sites-available/api.beachlab.org`

## Routes

Public (no key):

- `https://api.beachlab.org/telemetry/public/telemetry_latest?limit=1`

Protected (requires `X-API-Key`):

- `https://api.beachlab.org/telemetry/pro/telemetry_latest?limit=1`

Auth health:

- `https://api.beachlab.org/auth/health`

## Secrets and keys

Current runtime secrets are stored in:

- `/etc/auth-jwt-service.env` (`JWT_SECRET`, TTL, host/port)
- `/etc/auth-jwt-keys.csv` (api_key, role, plan, enabled)

Permissions:

```bash
sudo chmod 600 /etc/auth-jwt-service.env /etc/auth-jwt-keys.csv
```

## Operations

```bash
# service health
systemctl status auth-jwt postgrest-telemetry nginx

# auth service logs
journalctl -u auth-jwt -n 80 --no-pager

# local tests (force host header to local nginx)
curl -ks -H 'Host: api.beachlab.org' https://127.0.0.1/auth/health
curl -ks -o /dev/null -w '%{http_code}\n' \
  -H 'Host: api.beachlab.org' \
  https://127.0.0.1/telemetry/public/telemetry_latest?limit=1
curl -ks -o /dev/null -w '%{http_code}\n' \
  -H 'Host: api.beachlab.org' \
  https://127.0.0.1/telemetry/pro/telemetry_latest?limit=1
curl -ks -o /dev/null -w '%{http_code}\n' \
  -H 'Host: api.beachlab.org' \
  -H 'X-API-Key: <YOUR_KEY>' \
  https://127.0.0.1/telemetry/pro/telemetry_latest?limit=1
```

Expected:

- public: `200`
- protected without key: `401`
- protected with valid key: `200`

## Add/rotate API keys

Append new keys:

```bash
NEW_KEY=$(openssl rand -hex 24)
echo "$NEW_KEY,web_anon,free,1" | sudo tee -a /etc/auth-jwt-keys.csv
sudo systemctl restart auth-jwt
```

Disable a key by setting enabled column to `0`.

## Promote from free to paid roles

Current example key uses role `web_anon`.

For paid datasets:

1. Create a dedicated DB role (example: `web_paid`)
2. Grant only paid objects to that role
3. Apply RLS where needed
4. Map paid keys to `web_paid` in `/etc/auth-jwt-keys.csv`

Example key row:

```text
<api_key>,web_paid,pro,1
```

## Rollback

Restore backups and reload:

```bash
# restore previous nginx file (pick your timestamp)
sudo cp /etc/nginx/sites-available/api.beachlab.org.bak.<timestamp> /etc/nginx/sites-available/api.beachlab.org

# restore previous PostgREST config (pick your timestamp)
sudo cp /etc/postgrest-telemetry.conf.bak.<timestamp> /etc/postgrest-telemetry.conf

sudo nginx -t && sudo systemctl reload nginx
sudo systemctl restart postgrest-telemetry
sudo systemctl disable --now auth-jwt
```

## Notes

- This design is fully self-hosted, no SaaS/free-tier dependency.
- Keep PostgREST bound to localhost and expose only through Nginx.
- Add rate limits in Nginx as next step if needed (`limit_req`).
