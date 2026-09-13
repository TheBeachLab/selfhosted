#!/usr/bin/env python3
"""One-time migration; run as taskmaster with both sync schedules stopped.

Retains v2 data/config, preserves UUIDs, and refuses a repeated migration.
Requires /opt/taskwarrior-3.5.0 and private TaskChampion client.json.
"""
from pathlib import Path
import json
import fcntl
import os
import shutil
import subprocess

os.umask(0o077)
base=Path('/home/taskmaster/nextcloud-sync')
lock=(base/'sync.lock').open('w')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert subprocess.run(['systemctl','is-active','--quiet','nextcloud-taskwarrior.timer']).returncode != 0, 'Stop timer first'
new_binary='/opt/taskwarrior-3.5.0/bin/task'
assert subprocess.check_output([new_binary,'--version'],text=True).strip()=='3.5.0'
assert not (base/'data/taskchampion.sqlite3').exists()
migration=base/'migration-v3';migration.mkdir(mode=0o700)
shutil.copytree(base/'data',migration/'v2-data')
state=Path('/home/taskmaster/.config/syncall')
assert state.is_dir()
shutil.copytree(state,migration/'v2-syncall-state')
(base/'config').mkdir(mode=0o700,exist_ok=True)
shutil.copytree(state,base/'config/syncall')
for name in ('taskrc','settings.json'):
    shutil.copy2(base/name,migration/('v2-'+name))
old_env=dict(os.environ,TASKRC=str(base/'taskrc'))
before=json.loads(subprocess.check_output(['/usr/bin/task','export'],env=old_env,stderr=subprocess.DEVNULL))
(migration/'before-export.json').write_text(json.dumps(before))
staged=migration/'v3-data';shutil.copytree(base/'data',staged)
config_lines=[line for line in (base/'taskrc').read_text().splitlines()
              if not line.startswith(('data.location=','taskd.','sync.'))]
staged_rc=migration/'import.taskrc'
staged_rc.write_text('\n'.join(config_lines)+f'\ndata.location={staged}\n')
env=dict(os.environ,TASKRC=str(staged_rc))
result=subprocess.run([new_binary,'rc.hooks=0','import-v2'],env=env,text=True,capture_output=True)
(migration/'import.log').write_text(result.stdout+result.stderr);result.check_returncode()
after=json.loads(subprocess.check_output([new_binary,'export'],env=env,stderr=subprocess.DEVNULL))
index={item['uuid']:item for item in after}
assert set(index)=={item['uuid'] for item in before}
for item in before:
    for key,value in item.items():
        if key not in ('id','urgency'):
            assert index[item['uuid']].get(key)==value, 'Migration changed source field '+key
legacy=migration/'staged-v2-files';legacy.mkdir()
for file in staged.iterdir():
    if file.suffix=='.data' or file.name in ('backlog.data','undo.data'):
        file.rename(legacy/file.name)
(base/'data').rename(base/'data-v2-20260913')
staged.rename(base/'data')
client=json.loads(Path('/home/taskmaster/taskchampion/client.json').read_text())
config_lines += [f'data.location={base}/data','sync.server.url='+client['url'],
                 'sync.server.client_id='+client['client_id'],
                 'sync.encryption_secret='+client['encryption_secret']]
(base/'taskrc').write_text('\n'.join(config_lines)+'\n')
config=json.loads((base/'settings.json').read_text())
config.pop('sync_taskd',None);config['sync_taskchampion']=True;config['task_binary']=new_binary
(base/'settings.json').write_text(json.dumps(config,indent=2)+'\n')
print('Migrated',len(after),'records, preserving all source fields and UUIDs.')
