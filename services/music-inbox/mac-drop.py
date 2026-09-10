#!/usr/bin/env python3
"""Move stable audio uploads only after a verified Nextcloud file API receipt."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

INBOX=Path.home()/'Music'/'Para Nextcloud'
STATE=Path.home()/'Library'/'Application Support'/'Music Drop'
EXTENSIONS={'.mp3','.m4a','.flac','.wav','.aif','.aiff','.ogg','.opus','.aac','.wma','.ape'}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def stamp(path):
    s=path.stat();return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns

def send(path,meta):
    command='sudo -n -u www-data php /opt/music-inbox/receive-drop.php '+shlex.quote(json.dumps(meta,ensure_ascii=False))
    with path.open('rb') as f:
        r=subprocess.run(['/usr/bin/ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','pink-sudo',command],stdin=f,capture_output=True,text=True,timeout=1800)
    if r.returncode:raise RuntimeError(r.stderr.strip() or 'Upload failed')
    return json.loads(r.stdout)

def transfer(path,inbox,state,transport=send):
    before=stamp(path)
    meta={'relative':path.relative_to(inbox).as_posix(),'size':before[2],'sha256':digest(path)}
    if stamp(path)!=before:raise RuntimeError('Source changed while hashing')
    response=transport(path,meta)
    if response.get('sha256')!=meta['sha256'] or response.get('size')!=meta['size'] or not response.get('file_id'):
        raise RuntimeError('Server did not confirm matching contents')
    if stamp(path)!=before or digest(path)!=meta['sha256']:
        raise RuntimeError('Source changed while uploading; retained locally')
    entry={'time':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'local_path':str(path),'server':response,'action':'verified transfer; removing local inbox copy'}
    with (state/'transfers.jsonl').open('a') as f:
        f.write(json.dumps(entry,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
    path.unlink()
    return response

def run(inbox=INBOX,state=STATE):
    state.mkdir(parents=True,exist_ok=True);inbox.mkdir(parents=True,exist_ok=True)
    with (state/'lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        errors=[];sent=0
        for directory,dirs,files in os.walk(inbox,followlinks=False):
            dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(directory)/d).is_symlink()]
            for name in files:
                path=Path(directory)/name
                if name.startswith('.') or path.is_symlink() or path.suffix.lower() not in EXTENSIONS:continue
                try:
                    s=path.stat()
                    if s.st_size==0 or time.time()-s.st_mtime<120:continue
                    response=transfer(path,inbox,state);sent+=1
                    print('Transferred:',path,'->',response['path'],flush=True)
                except Exception as e:
                    errors.append({'path':str(path),'error':str(e)})
                    print('Retained:',path,':',str(e),flush=True)
            if errors:break # retry connectivity failures next minute, not for every file
        status={'time':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'transferred':sent,'errors':errors}
        temp=state/'status.json.tmp';temp.write_text(json.dumps(status,ensure_ascii=False,indent=2));temp.replace(state/'status.json')

if __name__=='__main__':run()
