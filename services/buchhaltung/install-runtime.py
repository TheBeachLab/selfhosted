#!/usr/bin/env python3
"""Scoped NUC runtime setup after code, dist and tests have been checked.

Run as root on the NUC; only manages Buchhaltung's paths and service.
Does not modify shared Authentik flows or existing applications/vhosts.
Never prints generated credentials or the environment file.
"""
import argparse
import base64
import grp
import os
from pathlib import Path
import pwd
import secrets
import subprocess


def run(*args):
    subprocess.run(list(args),check=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--release',type=Path,required=True)
    args=parser.parse_args()
    release=args.release.resolve()
    if os.geteuid()!=0 or not str(release).startswith('/opt/buchhaltung/releases/') or not (release/'frontend/dist/index.html').is_file():
        raise SystemExit('Requires root and a tested /opt/buchhaltung/releases/<revision> artifact.')
    try:
        account=pwd.getpwnam('buchhaltung')
    except KeyError:
        run('useradd','--system','--home-dir','/var/lib/buchhaltung','--shell','/usr/sbin/nologin','buchhaltung')
        account=pwd.getpwnam('buchhaltung')
    data=Path('/var/lib/buchhaltung')
    data.mkdir(mode=0o700,exist_ok=True)
    data.chmod(0o700);os.chown(data,account.pw_uid,account.pw_gid)
    env_dir=Path('/etc/buchhaltung');env_dir.mkdir(mode=0o750,exist_ok=True)
    env_dir.chmod(0o750);os.chown(env_dir,0,account.pw_gid)
    env=env_dir/'private.env'
    if not env.exists():
        proxy=secrets.token_urlsafe(48)
        key=base64.b64encode(secrets.token_bytes(32)).decode()
        descriptor=os.open(env,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o640)
        with os.fdopen(descriptor,'w') as output:
            output.write('BUCHHALTUNG_DATA=/var/lib/buchhaltung\nBUCHHALTUNG_ORIGIN=https://buchhaltung.beachlab.org\n')
            output.write('BUCHHALTUNG_VALIDATOR=/opt/buchhaltung/vendor/xrechnung\n')
            output.write('BUCHHALTUNG_PROXY_SECRET='+proxy+'\nBUCHHALTUNG_DOCUMENT_KEY='+key+'\n')
        os.chown(env,0,account.pw_gid)
    else:
        values=dict(line.split('=',1) for line in env.read_text().splitlines() if '=' in line)
        proxy=values['BUCHHALTUNG_PROXY_SECRET']
        if len(proxy)<32:raise SystemExit('Existing credential invalid; refusing to replace it.')
    env.chmod(0o640);os.chown(env,0,account.pw_gid)
    snippet=Path('/etc/nginx/snippets/buchhaltung-proxy-secret.conf')
    content='proxy_set_header X-Buchhaltung-Proxy "'+proxy+'";\n'
    if snippet.exists() and snippet.read_text()!=content:
        raise SystemExit('Existing proxy snippet differs; inspect before changing access.')
    if not snippet.exists():
        descriptor=os.open(snippet,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w') as output:output.write(content)
    venv=Path('/opt/buchhaltung/venv')
    if not venv.is_dir():run('python3','-m','venv',str(venv))
    run(str(venv/'bin/python'),'-m','pip','install','--quiet','-r',str(release/'requirements.txt'))
    run('python3',str(release/'install-validator.py'),'--destination','/opt/buchhaltung/vendor/xrechnung')
    unit=Path('/etc/systemd/system/buchhaltung.service')
    unit.write_bytes((release/'buchhaltung.service').read_bytes());unit.chmod(0o644)
    current=Path('/opt/buchhaltung/current')
    if current.exists() and not current.is_symlink():raise SystemExit('Current is not a release symlink; inspect ownership.')
    previous=str(current.resolve()) if current.exists() else None
    if previous:Path('/opt/buchhaltung/previous-release').write_text(previous+'\n')
    temporary=Path('/opt/buchhaltung/.next-current')
    if temporary.exists() or temporary.is_symlink():raise SystemExit('Another deployment may be pending.')
    temporary.symlink_to(release);os.replace(temporary,current)
    run('systemctl','daemon-reload')
    run('systemctl','enable','--now','buchhaltung.service')
    run('systemctl','restart','buchhaltung.service')
    print('Buchhaltung runtime activated. Verify authenticated loopback/public state before claiming deployment.')


if __name__=='__main__':main()
