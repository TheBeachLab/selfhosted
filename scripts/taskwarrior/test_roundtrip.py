"""Integration check restricted to a prepared, otherwise empty test collection."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import caldav

base = Path(sys.argv[1])
config = json.loads((base / 'settings.json').read_text())
assert len(config['calendars']) == 1 and config['calendars'][0]['project'] == 'Probe'
client = caldav.DAVClient(url=config['dav_url'], username=config['username'], password=Path(config['password_file']).read_text().strip())
cal = caldav.Calendar(client=client, url=config['calendars'][0]['url'])
env = dict(os.environ, TASKRC=str(base / 'taskrc'))

def task(*args):
    return subprocess.check_output(['task', 'rc.confirmation=no', *args], env=env, stderr=subprocess.DEVNULL, text=True)

def sync():
    subprocess.run([sys.executable, str(base.parent / 'sync_nextcloud.py'), str(base / 'settings.json')], check=True)

def items():
    return json.loads(task('export'))

def remote():
    ts = cal.todos(include_completed=True)
    assert len(ts) == 1
    return ts[0]

sync()
uid = items()[0]['uuid']
assert items()[0]['status'] == 'pending'
task(uid, 'modify', 'description:Temporary adapter verification edited 4d39898e')
sync()
assert str(remote().icalendar_component['SUMMARY']).endswith('edited 4d39898e')
print('PASS remote creation and local edit without priority')
r = remote();c = r.icalendar_component
c['SUMMARY'] = 'Temporary remote edited 4d39898e'
c.pop('PRIORITY',None);c.add('PRIORITY', 1);c.add('DUE', dt.date(2026, 10, 1))
c.pop('LAST-MODIFIED',None);c.add('LAST-MODIFIED', dt.datetime.now(dt.timezone.utc));r.save()
sync()
x=items()[0];assert x['priority']=='H' and x['ncallday']=='yes' and x['due'].startswith('20261001')
task(uid,'modify','description:Temporary preserve date 4d39898e');sync()
d=remote().icalendar_component['DUE'].dt
assert type(d) is dt.date
print('PASS remote edit, priority and date-only preservation')
task(uid,'done');sync();assert str(remote().icalendar_component['STATUS'])=='COMPLETED'
assert 'COMPLETED' in remote().icalendar_component
r=remote();r.icalendar_component['STATUS']='NEEDS-ACTION';r.icalendar_component.pop('COMPLETED',None);r.save();sync()
assert items()[0]['status']=='pending'
print('PASS local completion and remote reopening')
remote().delete();sync();assert items()[0]['status']=='deleted'
print('PASS remote deletion')
task('add','Temporary local creation 4d39898e','project:Probe');sync()
x=next(x for x in items() if x['status']=='pending');assert str(remote().icalendar_component['SUMMARY'])=='Temporary local creation 4d39898e'
task(x['uuid'],'delete');sync();assert len(cal.todos(include_completed=True))==0
print('PASS local creation and deletion; remote fixture cleaned')
sync()
print('PASS empty repeat sync')
task('add','Temporary field clearing 4d39898e','project:Probe','due:2026-10-02','priority:H','+probe');sync()
r=remote()
for key in ('DUE','PRIORITY','CATEGORIES'):
    r.icalendar_component.pop(key,None)
r.save();sync()
x=next(x for x in items() if x['status']=='pending')
assert not x.get('due') and not x.get('priority') and not x.get('tags')
r.delete();sync()
print('PASS remote clearing deadline, priority and tags; fixture cleaned')
# A fresh/incorrect replica must not be interpreted as mass deletion.
task('add','Temporary missing replica guard 4d39898e','project:Probe');sync()
uid=next(x['uuid'] for x in items() if x['status']=='pending')
(base/'data').rename(base/'data-guard-preserved')
(base/'data').mkdir()
failed=subprocess.run([sys.executable,str(base.parent/'sync_nextcloud.py'),str(base/'settings.json')],capture_output=True,text=True)
assert failed.returncode != 0 and 'missing mapped UUIDs' in failed.stderr
assert str(remote().icalendar_component['SUMMARY'])=='Temporary missing replica guard 4d39898e'
(base/'data').rename(base/'data-guard-empty')
(base/'data-guard-preserved').rename(base/'data')
task(uid,'delete');sync();assert len(cal.todos(include_completed=True))==0
print('PASS empty-replica guard preserves Nextcloud task; fixture cleaned')
