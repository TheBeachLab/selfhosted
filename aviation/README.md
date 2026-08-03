# Aviation data service

This directory documents the deployment boundary for the public aviation-data
API used by a separate client application. The service source code lives in its
own repository; this repository does not duplicate that code or its private
deployment configuration.

## Public architecture

- A TLS reverse proxy exposes the versioned API.
- A FastAPI service refreshes METAR, TAF, SIGMET and NOTAM caches from upstream
  providers.
- Empty upstream responses preserve the last known good cache instead of
  replacing it with an empty result.
- Authentication material is service-specific, rotated independently and kept
  outside Git.
- The backend is stateless apart from optional cache storage.

## Deployment invariants

1. Keep the application listener private to the host.
2. Expose it only through the TLS reverse proxy.
3. Store API credentials in a root-readable environment file or equivalent
   secret store; never place a generated value in documentation, source, build
   settings or logs.
4. Apply request limits at the proxy and validate health before directing
   clients to a new deployment.
5. Keep per-user upstream authorization separate from shared server caches.

The public API hostname and complete deployment procedure belong with the
service repository and deployment inventory, where they can be kept current.
