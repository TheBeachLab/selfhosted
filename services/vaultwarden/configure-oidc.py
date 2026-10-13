#!/usr/bin/env python3
"""Provision Passwords OIDC and Fran's access using the existing passkey flow.

https://github.com/dani-garcia/vaultwarden/wiki/Enabling-SSO-support-using-OpenId-Connect
https://docs.goauthentik.io/add-secure-apps/providers/oauth2/
Fields verified against the NUC's Authentik 2026.8.2 API schema.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path('/opt/vaultwarden')
EMAIL_EXPRESSION = '''if request.user.username != "fran":
    return {}
# Administrative mapping explicitly requested by Fran; only this application.
return {"email": "hola@beachlab.org", "email_verified": True}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run as root on the NUC.')
    os.umask(0o077)
    env = dict(l.split('=', 1) for l in Path('/opt/authentik/.env').read_text().splitlines() if '=' in l)

    def api(path, data=None, method=None):
        request = Request('http://127.0.0.1:19000/api/v3/' + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer ' + env['AUTHENTIK_BOOTSTRAP_TOKEN'], 'Content-Type': 'application/json'},
            method=method)
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except HTTPError as error:
            # Responses can contain OAuth credentials; keep diagnostics private.
            (ROOT / 'oidc-error.json').write_bytes(error.read())
            raise RuntimeError(f'{method or "GET"} {path}: HTTP {error.code}; private diagnostic in /opt/vaultwarden.') from None

    def items(path):
        result = api(path + '?page_size=200&superuser_full_list=true')
        if result.get('pagination', {}).get('total_pages', 1) > 1:
            raise RuntimeError('Inventory exceeds one page; inspect before provisioning.')
        return result['results']

    flows = {x['slug']: x for x in items('flows/instances/')}
    flow = flows['beachlab-passkey']
    stage = next(x for x in items('stages/authenticator/validate/') if x['name'] == 'beachlab-passkey-validate')
    if (stage['device_classes'] != ['webauthn'] or stage['not_configured_action'] != 'deny'
            or stage['webauthn_user_verification'] != 'required'):
        raise RuntimeError('Existing authentication flow is not passkey-only.')
    if not any(x['target'] == flow['pk'] and x['stage'] == stage['pk'] for x in items('flows/bindings/')):
        raise RuntimeError('Passkey validation stage is not bound to the flow.')
    user = next(x for x in items('core/users/') if x['username'] == 'fran')
    if not user['is_active']:
        raise RuntimeError('Fran is inactive.')
    query = "from authentik.stages.authenticator_webauthn.models import WebAuthnDevice; print('PASSKEYS=' + str(WebAuthnDevice.objects.filter(user__username='fran',rp_id='auth.beachlab.org').count()))"
    readback = subprocess.run(['docker', 'exec', 'authentik-server-1', 'ak', 'shell', '-c', query],
                              text=True, capture_output=True, check=True).stdout
    if not any(l.startswith('PASSKEYS=') and int(l.split('=', 1)[1]) > 0 for l in readback.splitlines()):
        raise RuntimeError('Fran has no enrolled Authentik passkey.')
    if any(x['slug'] == 'passwords' for x in items('core/applications/')):
        raise RuntimeError('Preserving an existing Passwords application.')
    if any(x['name'] == 'Passwords OIDC' for x in items('providers/oauth2/')):
        raise RuntimeError('Preserving an existing Passwords provider.')
    mappings = items('propertymappings/provider/scope/')
    if any(x['name'] == 'Passwords Fran email' for x in mappings):
        raise RuntimeError('Preserving an existing Passwords email mapping.')
    defaults = {x['scope_name']: x['pk'] for x in mappings if (x.get('managed') or '').startswith('goauthentik.io/providers/oauth2/')}
    key = next(x for x in items('crypto/certificatekeypairs/') if x['name'] == 'authentik Self-signed Certificate')
    schema = api('schema/?format=json')['components']['schemas']
    grant_schema = schema['OAuth2ProviderRequest']['properties']['grant_types']['items']
    grant_values = schema[grant_schema['$ref'].split('/')[-1]]['enum']
    if not {'authorization_code', 'refresh_token'}.issubset(grant_values):
        raise RuntimeError('Unexpected grant type schema.')
    current = (ROOT / '.env').read_text()
    if 'VAULTWARDEN_SSO_' in current:
        raise RuntimeError('Preserving existing Vaultwarden OIDC credentials.')
    print('Passwords OIDC: existing passkey flow; access only for fran; email hola@beachlab.org.')
    if not args.apply:
        return
    mapping = api('propertymappings/provider/scope/', {'name': 'Passwords Fran email',
        'scope_name': 'email', 'expression': EMAIL_EXPRESSION,
        'description': 'Private Passwords email mapping for Fran, requested 2026-10-13.'}, 'POST')
    client_id, secret = 'beachlab-passwords', secrets.token_urlsafe(48)
    provider = api('providers/oauth2/', {'name': 'Passwords OIDC',
        'authentication_flow': flow['pk'],
        'authorization_flow': flows['default-provider-authorization-implicit-consent']['pk'],
        'invalidation_flow': flows['default-provider-invalidation-flow']['pk'],
        'client_type': 'confidential', 'client_id': client_id, 'client_secret': secret,
        'grant_types': ['authorization_code', 'refresh_token'],
        'redirect_uris': [{'matching_mode': 'strict', 'url': 'https://passwords.beachlab.org/identity/connect/oidc-signin'}],
        'property_mappings': [defaults['openid'], defaults['profile'], defaults['offline_access'], mapping['pk']],
        'signing_key': key['pk'], 'encryption_key': None, 'sub_mode': 'hashed_user_id',
        'issuer_mode': 'per_provider', 'include_claims_in_id_token': True,
        'access_code_validity': 'minutes=1', 'access_token_validity': 'minutes=15',
        'refresh_token_validity': 'hours=12'}, 'POST')
    app = api('core/applications/', {'name': 'Passwords', 'slug': 'passwords', 'provider': provider['pk'],
        'meta_launch_url': 'https://passwords.beachlab.org',
        'meta_description': 'Contraseñas personales de Fran.', 'policy_engine_mode': 'any'}, 'POST')
    binding = api('policies/bindings/', {'target': app['pk'], 'user': user['pk'], 'order': 0,
        'enabled': True, 'negate': False, 'failure_result': False}, 'POST')
    (ROOT / '.env').write_text(current + f'VAULTWARDEN_SSO_CLIENT_ID={client_id}\nVAULTWARDEN_SSO_CLIENT_SECRET={secret}\n')
    (ROOT / '.env').chmod(0o600)
    (ROOT / 'oidc-provision.json').write_text(json.dumps({'provider': provider['pk'], 'application': app['pk'],
        'mapping': mapping['pk'], 'binding': binding['pk'], 'user': user['pk'],
        'authority': 'https://auth.beachlab.org/application/o/passwords/'}, indent=2) + '\n')
    result = api(f'providers/oauth2/{provider["pk"]}/')
    bindings = [x for x in items('policies/bindings/') if x['target'] == app['pk']]
    if result['authentication_flow'] != flow['pk'] or len(bindings) != 1 or bindings[0]['user'] != user['pk']:
        raise RuntimeError('OIDC access readback did not match the requested configuration.')
    print('Passwords OIDC provider and Fran-only binding verified.')


if __name__ == '__main__':
    main()
