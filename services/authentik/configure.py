#!/usr/bin/env python3
"""Configure the private private-site passkey gateway via Authentik's local API.
Run as root on the server. Schema verified against 2026.8.2 /api/v3/schema/.
Sources: https://docs.goauthentik.io/add-secure-apps/providers/proxy/forward_auth
https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/authenticator_validate
"""
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ENV = dict(line.split('=', 1) for line in Path('/opt/authentik/.env').read_text().splitlines() if '=' in line)

def api(path, data=None, method=None):
    req = Request('http://127.0.0.1:19000/api/v3/' + path,
                  data=json.dumps(data).encode() if data is not None else None,
                  headers={'Authorization': 'Bearer ' + ENV['AUTHENTIK_BOOTSTRAP_TOKEN'], 'Content-Type': 'application/json'},
                  method=method)
    try:
        with urlopen(req, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else None
    except HTTPError as error:
        raise RuntimeError(f'{method or "GET"} {path}: {error.code} {error.read().decode()}') from None

def items(path):
    return api(path + '?page_size=200&superuser_full_list=true')['results']

def upsert(path, key, value, data):
    old = next((item for item in items(path) if item.get(key) == value), None)
    if old:
        identifier = old['slug'] if path in ('core/applications/', 'flows/instances/') else old.get('pk', old.get('brand_uuid'))
        return api(f'{path}{identifier}/', data, 'PATCH')
    return api(path, {key: value, **data}, 'POST')

user = upsert('core/users/', 'username', 'fran', {'name': 'Fran', 'is_active': True, 'path': 'users', 'attributes': {'settings': {'locale': 'es'}}})
flow = upsert('flows/instances/', 'slug', 'beachlab-passkey', {
    'name': 'Beachlab passkey', 'title': 'Accede con tu passkey', 'designation': 'authentication', 'authentication': 'none'})
validate = upsert('stages/authenticator/validate/', 'name', 'beachlab-passkey-validate', {
    'not_configured_action': 'deny', 'device_classes': ['webauthn'], 'webauthn_user_verification': 'required', 'last_auth_threshold': 'seconds=0'})
login = upsert('stages/user_login/', 'name', 'beachlab-passkey-login', {'session_duration': 'hours=12'})
for order, stage in [(10, validate), (20, login)]:
    existing = next((x for x in items('flows/bindings/') if x['target'] == flow['pk'] and x['order'] == order), None)
    data = {'target': flow['pk'], 'stage': stage['pk'], 'order': order}
    api('flows/bindings/' + (str(existing['pk']) + '/' if existing else ''), data, 'PATCH' if existing else 'POST')
setup = next(x for x in items('stages/authenticator/webauthn/') if x['name'] == 'default-authenticator-webauthn-setup')
api(f'stages/authenticator/webauthn/{setup["pk"]}/', {'resident_key_requirement': 'required', 'user_verification': 'required', 'friendly_name': 'Passkey'}, 'PATCH')
flows = {x['slug']: x['pk'] for x in items('flows/instances/')}
providers = []
for slug, name, host in [('beachlab-private', 'Beachlab privado', 'beachlab.org'), ('comfyui', 'ComfyUI', 'comfyui.beachlab.org'), ('barrakuda-designer', 'Barrakuda Designer', 'designer.daswerklab.de')]:
    provider = upsert('providers/proxy/', 'name', name, {
        'external_host': 'https://' + host, 'mode': 'forward_single', 'cookie_domain': host,
        'authentication_flow': flow['pk'],
        'authorization_flow': flows['default-provider-authorization-implicit-consent'],
        'invalidation_flow': flows['default-provider-invalidation-flow'],
        'intercept_header_auth': False, 'basic_auth_enabled': False, 'skip_path_regex': '',
        'access_token_validity': 'minutes=5', 'refresh_token_validity': 'hours=12'})
    providers.append(provider['pk'])
    app = upsert('core/applications/', 'slug', slug, {'name': name, 'provider': provider['pk'], 'group': 'Servidor', 'meta_hide': slug == 'beachlab-private'})
    if not any(x['target'] == app['pk'] and x.get('user') == user['pk'] for x in items('policies/bindings/')):
        api('policies/bindings/', {'target': app['pk'], 'user': user['pk'], 'order': 0, 'failure_result': False})
for slug, name in [('deutsch', 'Deutsch Sprint'), ('whisper', 'Whisper'), ('tts', 'Qwen3-TTS'), ('drop', 'Drop'), ('browser', 'Navegador remoto'), ('transmission', 'Transmission')]:
    app = upsert('core/applications/', 'slug', slug, {'name': name, 'meta_launch_url': f'https://beachlab.org/{slug}/'+('web/' if slug=='transmission' else ''), 'group': 'Servidor'})
    if not any(x['target'] == app['pk'] and x.get('user') == user['pk'] for x in items('policies/bindings/')):
        api('policies/bindings/', {'target': app['pk'], 'user': user['pk'], 'order': 0, 'failure_result': False})
outpost = next(x for x in items('outposts/instances/') if x['name'] == 'authentik Embedded Outpost')
config = outpost['config']
config['authentik_host'] = 'https://auth.beachlab.org/'
config['authentik_host_browser'] = 'https://auth.beachlab.org/'
api(f'outposts/instances/{outpost["pk"]}/', {'providers': sorted(set(outpost['providers']) | set(providers)), 'config': config}, 'PATCH')
brand = items('core/brands/')[0]
api(f'core/brands/{brand["brand_uuid"]}/', {'branding_title': 'Beachlab', 'flow_authentication': flow['pk']}, 'PATCH')
print('Configured: passkey flow and shared-site providers; other outpost providers preserved.')

# Second operator explicitly authorized on 2026-09-14; each application remains separately assignable.
junior = upsert('core/users/', 'username', 'fran-jr', {'name': 'Fran Jr', 'is_active': True, 'path': 'users', 'attributes': {'settings': {'locale': 'es'}}})
for app in items('core/applications/'):
    if app['slug'] not in {'beachlab-private','comfyui','barrakuda-designer','deutsch','whisper','tts','drop','browser','transmission'}:
        continue
    api(f"core/applications/{app['slug']}/", {'policy_engine_mode':'any'}, 'PATCH')
    if not any(x['target'] == app['pk'] and x.get('user') == junior['pk'] for x in items('policies/bindings/')):
        api('policies/bindings/', {'target':app['pk'], 'user':junior['pk'], 'order':10, 'failure_result':False})
