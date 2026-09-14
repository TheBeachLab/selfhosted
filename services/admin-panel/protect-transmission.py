#!/usr/bin/env python3
"""Run as root: protect the existing Transmission route with Authentik.
RPC credentials stay in a root-readable nginx include; the upstream still requires them.
"""
import base64
from pathlib import Path
import shutil
import subprocess
from datetime import datetime,timezone
conf=Path('/etc/nginx/sites-available/beachlab.org')
secret=Path('/etc/nginx/snippets/transmission-rpc-secret.conf')
creds=Path('/home/pink/docker/transmission-vpn/rpc_creds').read_text().splitlines()
if len(creds)!=2:raise RuntimeError('Expected two-line RPC credential file')
auth=base64.b64encode(':'.join(creds).encode()).decode()
secret.touch(mode=0o600,exist_ok=True);secret.chmod(0o600)
secret.write_text('proxy_set_header Authorization "Basic '+auth+'";\n')
old=conf.read_text(); marker='location ^~ /transmission/ {'
if old.count(marker)!=1:raise RuntimeError('Transmission location must be unique')
addition='\n          include snippets/authentik-check.conf;\n          include snippets/transmission-rpc-secret.conf;'
if marker+addition not in old:
 backup=Path('/opt/authentik')/('nginx-before-transmission-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
 shutil.copy2(conf,backup)
 conf.write_text(old.replace(marker,marker+addition))
 result=subprocess.run(['nginx','-t'])
 if result.returncode:
  conf.write_text(old);raise RuntimeError('Nginx validation failed; original restored')
 subprocess.run(['systemctl','reload','nginx'],check=True)
print('Transmission protected with Authentik; RPC authentication preserved.')
