#!/usr/bin/env python3
"""Verified encrypted backup to the existing Synology NFS mount.

No source API calls. No plaintext financial originals or encryption keys on NAS.
Only manages its dedicated buchhaltung-encrypted directory; no retention deletion.
"""
from datetime import datetime, timezone
import fcntl
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
    if pwd.getpwuid(os.geteuid()).pw_name!='buchhaltung':
        raise SystemExit('Run as buchhaltung to preserve SQLite/WAL ownership.')
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
    config=Config.environment();database=Database(config.data);documents=Documents(config,database)
    name='buchhaltung-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.blenc'
    result=backup(config,database,documents,target/name)
    last=Path('/var/lib/buchhaltung/last-backup.json')
    temporary=last.with_suffix('.tmp');temporary.write_text(json.dumps(result,sort_keys=True));temporary.chmod(0o600);temporary.replace(last)
    print(json.dumps({"backup":name,"verified":True,"restored_records":result['restore']['records'],"restored_documents":result['restore']['documents']}))


if __name__=='__main__':main()
