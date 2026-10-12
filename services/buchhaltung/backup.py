#!/usr/bin/env python3
"""Verified encrypted backup to the existing Synology NFS mount.

No source API calls. No plaintext financial originals or encryption keys on NAS.
Only manages its dedicated buchhaltung-encrypted directory; no retention deletion.
"""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import pwd
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,'/opt/buchhaltung/current')
from buchhaltung.cli import backup
from buchhaltung.config import Config
from buchhaltung.db import Database
from buchhaltung.documents import Documents


def main():
    if os.geteuid()!=0:raise SystemExit('Root orchestrates the NAS transfer; SQLite capture runs as buchhaltung.')
    os.umask(0o077)
    lock=open('/var/lib/buchhaltung/backup.lock','a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    mount=json.loads(subprocess.check_output(['findmnt','-J','-T','/mnt/nas-downloads'],text=True))['filesystems'][0]
    if mount['target']!='/mnt/nas-downloads' or mount['fstype'] not in ('nfs','nfs4') or mount['source']!='192.168.1.100:/volume1/synology':
        raise SystemExit('Expected NAS mount unavailable; refusing a backup on the root disk.')
    target=Path('/mnt/nas-downloads/backups/buchhaltung-encrypted')
    for parent in (target.parent,target):
        if parent.is_symlink():raise SystemExit('Unexpected backup path redirection.')
    target.mkdir(mode=0o700,exist_ok=True)
    target.chmod(0o700)
    free=os.statvfs(target)
    if free.f_bavail*free.f_frsize<2*1024**3:raise SystemExit('Less than 2 GiB free on the NAS.')
    account=pwd.getpwnam('buchhaltung')
    staging=Path('/var/lib/buchhaltung/backup-staging')
    if staging.is_symlink():raise SystemExit('Unexpected staging path.')
    staging.mkdir(mode=0o700,exist_ok=True);staging.chmod(0o700);os.chown(staging,account.pw_uid,account.pw_gid)
    name='buchhaltung-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.blenc'
    local=staging/name
    capture=subprocess.run(['/usr/sbin/runuser','-u','buchhaltung','--','/opt/buchhaltung/venv/bin/python',
                            '-m','buchhaltung.cli','--env-file','/etc/buchhaltung/private.env',
                            'backup','--output',str(local)],cwd='/opt/buchhaltung/current',text=True,capture_output=True,check=True)
    result=json.loads(capture.stdout)
    destination=target/name
    descriptor=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    digest=hashlib.sha256()
    with local.open('rb') as source,os.fdopen(descriptor,'wb') as output:
        while chunk:=source.read(1024*1024):output.write(chunk);digest.update(chunk)
        output.flush();os.fsync(output.fileno())
    copied=hashlib.sha256()
    with destination.open('rb') as source:
        while chunk:=source.read(1024*1024):copied.update(chunk)
    if copied.hexdigest()!=result['sha256'] or digest.hexdigest()!=result['sha256']:
        raise SystemExit('NAS bytes differ; local verified backup preserved.')
    result['path']=str(destination);result['nas_sha256_verified']=True
    last=Path('/var/lib/buchhaltung/last-backup.json')
    temporary=last.with_suffix('.tmp');temporary.write_text(json.dumps(result,sort_keys=True));temporary.chmod(0o600);os.chown(temporary,account.pw_uid,account.pw_gid);temporary.replace(last)
    local.unlink()  # This exact newly created encrypted file has an independently hashed NAS copy.
    print(json.dumps({"backup":name,"verified":True,"restored_records":result['restore']['records'],"restored_documents":result['restore']['documents']}))


if __name__=='__main__':main()
