#!/usr/bin/env python3
"""Provision a separate Authentik provider for admin.beachlab.org.
User-authorized operators: fran and fran-jr. No Authentik superuser privileges.
Uses local Authentik 2026.8.2 API; credentials stay in root-only /opt/authentik/.env.
"""
import json
from pathlib import Path
from urllib.request import Request,urlopen
E=dict(l.split('=',1) for l in Path('/opt/authentik/.env').read_text().splitlines())
HEADERS={'Authorization':'Bearer '+E['AUTHENTIK_BOOTSTRAP_TOKEN'],'Content-Type':'application/json'}
def api(p,d=None,m=None):
 with urlopen(Request('http://127.0.0.1:19000/api/v3/'+p,headers=HEADERS,data=json.dumps(d).encode() if d is not None else None,method=m),timeout=30) as r:return json.load(r)
def items(p):return api(p+'?page_size=200&superuser_full_list=true')['results']
def upsert(p,key,value,attrs):
 old=next((x for x in items(p) if x[key]==value),None)
 path=p+(str(old['slug'] if p=='core/applications/' else old['pk'])+'/' if old else '')
 return api(path,{key:value,**attrs},'PATCH' if old else 'POST')
flows={x['slug']:x['pk'] for x in items('flows/instances/')}
p=upsert('providers/proxy/','name','Administración del servidor',{'external_host':'https://admin.beachlab.org','mode':'forward_single','cookie_domain':'admin.beachlab.org','authentication_flow':flows['beachlab-passkey'],'authorization_flow':flows['default-provider-authorization-implicit-consent'],'invalidation_flow':flows['default-provider-invalidation-flow'],'intercept_header_auth':False,'basic_auth_enabled':False,'access_token_validity':'minutes=5','refresh_token_validity':'hours=12'})
app=upsert('core/applications/','slug','beachlab-admin',{'name':'Administración del servidor','provider':p['pk'],'group':'Servidor','meta_launch_url':'https://admin.beachlab.org/','policy_engine_mode':'any'})
bindings=items('policies/bindings/')
for order,username in enumerate(['fran','fran-jr']):
 user=next(x for x in items('core/users/') if x['username']==username)
 if not any(x['target']==app['pk'] and x.get('user')==user['pk'] for x in bindings):api('policies/bindings/',{'target':app['pk'],'user':user['pk'],'order':order,'failure_result':False})
 print('Admin panel access:',username)
outpost=next(x for x in items('outposts/instances/') if x['name']=='authentik Embedded Outpost')
providers=sorted(set(outpost['providers']+[p['pk']]))
api(f'outposts/instances/{outpost["pk"]}/',{'providers':providers},'PATCH')
print('Separate provider configured')
