#!/usr/bin/env python3
"""Pinned syncall 1.8.8 adapter for Nextcloud. See doc/taskserver.md.

Use syncall's state/matching engine, but address collections by URI and serialize
valid VTODOs. Upstream: https://github.com/bergercookie/syncall (1.8.8).
"""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import sys
import tarfile
import uuid

import caldav
from bubop import logger
from syncall.aggregator import Aggregator
from syncall.app_utils import get_resolution_strategy
from syncall.caldav.caldav_side import CaldavSide
from syncall.taskwarrior.taskwarrior_side import TaskWarriorSide

UTC = dt.timezone.utc
FIELDS = ('summary', 'description', 'status', 'due', 'completed', 'priority', 'categories')


def normalize_date(value):
    if isinstance(value, dt.datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time(), UTC)
    return value


def read_todo(component):
    item = {'id': str(component['UID'])}
    for name in ('summary', 'description'):
        item[name] = str(component.get(name, ''))
    item['status'] = str(component.get('STATUS', 'NEEDS-ACTION')).lower()
    item['priority'] = int(component.get('PRIORITY', 0))
    item['categories'] = []
    cats = component.get('CATEGORIES', [])
    for cat in cats if isinstance(cats, list) else [cats]:
        item['categories'].extend(str(c) for c in cat.cats)
    item['categories'].sort()
    for name in ('due', 'created', 'completed', 'last-modified'):
        if name in component:
            item[name] = normalize_date(component[name].dt)
    due = component.get('DUE')
    item['dateonly'] = bool(due and isinstance(due.dt, dt.date) and not isinstance(due.dt, dt.datetime))
    return item


def to_tw(item):
    status = item['status']
    out = {'description': item['summary'], 'status': 'completed' if status in ('completed', 'cancelled') else 'pending',
           'annotations': [item['description']] if item['description'] else [],
           'tags': item['categories'], 'priority': None, 'ncallday': 'yes' if item['dateonly'] else 'no'}
    p = item['priority']
    if p:
        out['priority'] = 'H' if p <= 4 else 'M' if p == 5 else 'L'
    for src, dst in (('due', 'due'), ('created', 'entry'), ('completed', 'end')):
        if src in item:
            out[dst] = item[src]
    return out


def to_dav(item):
    out = {'summary': item['description'], 'description': '\n'.join(item.get('annotations', [])),
           'status': 'completed' if item['status'] == 'completed' else 'needs-action',
           'priority': {'H': 1, 'M': 5, 'L': 9}.get((item.get('priority') or '').upper(), 0),
           'categories': sorted(item.get('tags', [])), 'dateonly': item.get('ncallday') == 'yes'}
    for src, dst in (('due', 'due'), ('entry', 'created'), ('end', 'completed')):
        if item.get(src):
            out[dst] = normalize_date(item[src])
    return out


class NextcloudSide(CaldavSide):
    _identical_comparison_keys = (*FIELDS, 'dateonly')

    def __init__(self, client, entry):
        # Avoid upstream name-based discovery: duplicate display names exist.
        self._entry = entry
        self._davclient = client
        from syncall.sync_side import SyncSide
        SyncSide.__init__(self, name='caldav', fullname='Nextcloud')
        self._items_cache = {}
        self._raw = {}

    def start(self):
        self._calendar = caldav.Calendar(client=self._davclient, url=self._entry['url'])
        if 'VTODO' not in self._calendar.get_supported_components():
            raise RuntimeError('Configured collection is missing or no longer supports tasks')

    def get_all_items(self, **kwargs):
        result = []
        self._raw = {}
        for todo in self._calendar.todos(include_completed=True):
            comp = todo.icalendar_component
            uid = str(comp['UID'])
            if uid in self._entry.get('excluded_uids', []):
                continue
            if 'RRULE' in comp or 'RECURRENCE-ID' in comp:
                raise RuntimeError('New recurring task detected; review exclusions before syncing')
            if uid in self._raw:
                raise RuntimeError('Duplicate VTODO UID')
            self._raw[uid] = todo
            item = read_todo(comp)
            self._items_cache[uid] = item
            result.append(item)
        return result

    def _find_todo_by_id_raw(self, item_id):
        return self._raw.get(str(item_id))

    def _find_todo_by_id(self, item_id):
        todo = self._find_todo_by_id_raw(item_id)
        return read_todo(todo.icalendar_component) if todo else None

    def update_item(self, item_id, **changes):
        todo = self._raw[str(item_id)]
        comp = todo.icalendar_component
        # Preserve alarms, Apple properties, relations, and unsupported metadata.
        for key in FIELDS:
            comp.pop(key, None)
        for key in FIELDS:
            value = changes.get(key)
            if value is None or value == '' or value == []:
                continue
            if key == 'due' and changes.get('dateonly'):
                value = value.date()
            if key == 'status':
                value = value.upper()
            comp.add(key, value)
        comp.pop('LAST-MODIFIED', None)
        comp.add('LAST-MODIFIED', dt.datetime.now(UTC))
        comp.pop('PERCENT-COMPLETE', None)
        comp.add('PERCENT-COMPLETE', 100 if changes['status'] == 'completed' else 0)
        todo.save()

    def add_item(self, item):
        from icalendar import Calendar, Todo
        container = Calendar()
        container.add('version', '2.0')
        container.add('prodid', '-//The Beach Lab//Taskwarrior syncall adapter//EN')
        comp = Todo()
        uid = str(uuid.uuid4())
        comp.add('uid', uid)
        comp.add('dtstamp', dt.datetime.now(UTC))
        container.add_component(comp)
        todo = self._calendar.save_todo(container.to_ical().decode())
        self._raw[uid] = todo
        self.update_item(uid, **item)
        return read_todo(todo.icalendar_component)


class TaskSide(TaskWarriorSide):
    @classmethod
    def items_are_identical(cls, a, b, ignore_keys=()):
        if not super().items_are_identical(a, b, ignore_keys):
            return False
        return all(a.get(k, default) == b.get(k, default) for k, default in
                   (('priority', ''), ('tags', []), ('ncallday', 'no')))

    def update_item(self, item_id, **changes):
        # Explicit empty values remove fields when cleared in Nextcloud.
        for key in ('due', 'end'):
            changes.setdefault(key, '')
        original = self._tw.get_task(uuid=uuid.UUID(item_id))[-1]
        removed_tags = set(original.get('tags', [])) - set(changes.get('tags', []))
        super().update_item(item_id, **changes)
        if removed_tags:
            self._tw._execute(item_id, 'modify', *('-' + tag for tag in sorted(removed_tags)))


def run(config_path, only=None):
    config = json.loads(Path(config_path).read_text())
    base = Path(config['base'])
    os.environ['TASKRC'] = str(base / 'taskrc')
    os.environ['XDG_CONFIG_HOME'] = str(base / 'config')
    logger.remove()
    logger.add(sys.stderr, level='ERROR')
    with (base / 'sync.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        backups = base / 'backups'
        backups.mkdir(mode=0o700, exist_ok=True)
        snapshot = backups / (dt.date.today().isoformat() + '.tar.gz')
        if not snapshot.exists():
            with tarfile.open(str(snapshot) + '.tmp', 'w:gz') as archive:
                for name in ('data', 'config', 'taskrc', 'settings.json'):
                    if (base / name).exists():
                        archive.add(base / name, arcname=name)
            Path(str(snapshot) + '.tmp').replace(snapshot)
            for old in sorted(backups.glob('*.tar.gz'))[:-14]:
                old.unlink()
        client = caldav.DAVClient(url=config['dav_url'], username=config['username'],
                                 password=Path(config['password_file']).read_text().strip(), timeout=60)
        for entry in config['calendars']:
            if only and entry['project'] != only:
                continue
            remote = NextcloudSide(client, entry)
            local = TaskSide(project=entry['project'], tw_filter='project.is:' + entry['project'], config_file_override=base / 'taskrc')
            # If both sides changed, prefer Nextcloud; do not guess from TW import times.
            with Aggregator(side_A=remote, side_B=local, converter_A_to_B=to_tw,
                            converter_B_to_A=to_dav,
                            resolution_strategy=get_resolution_strategy('AlwaysFirstRS', side_A_type=type(remote), side_B_type=type(local)),
                            config_fname=entry['key'], catch_exceptions=False) as agg:
                agg.sync()
            print('Synced', entry['project'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('config')
    parser.add_argument('--project')
    args = parser.parse_args()
    run(args.config, args.project)
