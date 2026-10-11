#!/usr/bin/env python3
"""File an owner-reviewed, exact-message Gmail plan; never delete messages.

Gmail contracts (read 2026-10-11):
https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/batchModify
https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels/create
https://developers.google.com/workspace/gmail/api/guides/handle-errors
Use native Msgvault stage-delete/delete-staged separately for approved Trash.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


def validate_plan(plan):
    rows = plan['messages']
    if not rows or not plan['account'] or plan['source_id'] <= 0:
        raise ValueError('Empty plan or invalid account/source.')
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate archive IDs.')
    if len({r['source_message_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate Gmail IDs.')
    for row in rows:
        if (row['source_id'] != plan['source_id'] or row['id'] <= 0
                or not re.fullmatch(r'[0-9a-f]+', row['source_message_id'])):
            raise ValueError('Mixed source or invalid message ID.')
        if (type(row['delete']) is not bool or type(row['keep_inbox']) is not bool
                or type(row.get('pending', False)) is not bool):
            raise ValueError('Invalid lifecycle flags.')
        if row['delete']:
            if row.get('topic') or row['keep_inbox'] or row.get('pending'):
                raise ValueError('Deleted mail cannot be filed or kept in Inbox.')
        elif not isinstance(row.get('topic'), str) or not row['topic'].strip():
            raise ValueError('Every retained message needs a topic.')
        if row.get('pending') and not row['keep_inbox']:
            raise ValueError('Pending mail must stay in Inbox.')
    return rows


def guard_source(connection, plan):
    source = connection.execute(
        'SELECT source_type, identifier FROM sources WHERE id=?',
        (plan['source_id'],)).fetchone()
    if source != ('gmail', plan['account']):
        raise ValueError('Archive source does not match the approved Gmail account.')
    for row in plan['messages']:
        actual = connection.execute(
            'SELECT source_id, source_message_id FROM messages WHERE id=?',
            (row['id'],)).fetchone()
        if actual != (plan['source_id'], row['source_message_id']):
            raise ValueError('Archive identity changed for message ' + str(row['id']))


def guard_profile(profile, plan):
    if profile.get('emailAddress') != plan['account']:
        raise ValueError('Google credential belongs to another mailbox.')


def private_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


class Gmail:
    def __init__(self, home, account):
        if not re.fullmatch(r'[^/\\]+@[^/\\]+', account):
            raise ValueError('Invalid credential account filename.')
        token = json.loads((home / 'tokens' / (account + '.json')).read_text())
        self.client = json.loads((home / 'tokens/google-client-msgvault-nuc.json').read_text())['installed']
        self.token = token
        self.access = token['access_token']
        self.lock = threading.Lock()
        self.pacing_lock = threading.Lock()
        self.next_request = 0.0

    def pace(self):
        with self.pacing_lock:
            delay = self.next_request - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.next_request = time.monotonic() + 0.35

    def refresh(self, previous):
        with self.lock:
            if self.access != previous:
                return
            body = urllib.parse.urlencode({
                'client_id': self.client['client_id'],
                'client_secret': self.client['client_secret'],
                'refresh_token': self.token['refresh_token'],
                'grant_type': 'refresh_token',
            }).encode()
            request = urllib.request.Request('https://oauth2.googleapis.com/token',
                                             data=body, method='POST')
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    self.access = json.load(response)['access_token']
            except urllib.error.HTTPError as error:
                raise RuntimeError('Google token refresh failed: HTTP ' + str(error.code)) from None

    def request(self, path, method='GET', data=None):
        for attempt in range(5):
            self.pace()
            previous = self.access
            request = urllib.request.Request(
                'https://gmail.googleapis.com/gmail/v1/users/me/' + path,
                data=None if data is None else json.dumps(data).encode(), method=method,
                headers={'Authorization': 'Bearer ' + previous,
                         'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = response.read()
                    return json.loads(payload) if payload else {}
            except urllib.error.HTTPError as error:
                if error.code == 401 and attempt == 0:
                    self.refresh(previous)
                    continue
                try:
                    detail = json.load(error).get('error', {})
                    reasons = {item.get('reason') for item in detail.get('errors', [])}
                except (ValueError, AttributeError):
                    reasons = set()
                rate_limited = (error.code == 429 or
                                (error.code == 403 and reasons.intersection(
                                    {'rateLimitExceeded', 'userRateLimitExceeded'})))
                # Reads and label batch updates are idempotent; label creation is not.
                if (attempt < 4 and (method == 'GET' or path == 'messages/batchModify')
                        and (rate_limited or error.code in (500, 502, 503, 504))):
                    time.sleep(2 ** attempt)
                    continue
                reason = ','.join(sorted(r for r in reasons if r)) or 'unspecified'
                raise RuntimeError('Gmail operation failed: HTTP ' + str(error.code)
                                   + ' (' + reason + ')') from None

    def inspect(self, rows):
        def get(row):
            return self.request('messages/' + row['source_message_id']
                                + '?format=metadata&metadataHeaders=Message-ID&metadataHeaders=Subject')
        with ThreadPoolExecutor(max_workers=3) as pool:
            return dict(zip((row['id'] for row in rows), pool.map(get, rows)))


def verify_provider(rows, snapshots, labels=None):
    for row in rows:
        actual = snapshots[row['id']]
        if actual['id'] != row['source_message_id']:
            raise ValueError('Gmail message identity mismatch.')
        present = set(actual.get('labelIds', []))
        if 'DRAFT' in present or 'DRAFTS' in present:
            raise ValueError('Drafts are outside this filing plan.')
        if row['delete']:
            if labels is not None and ('TRASH' not in present or 'INBOX' in present):
                raise ValueError('Approved deletion has not reached Gmail Trash.')
            continue
        if present.intersection({'TRASH', 'SPAM'}):
            raise ValueError('Retained message left the active mailbox.')
        if labels is not None:
            if labels[row['topic']] not in present:
                raise ValueError('Missing topic label on retained message.')
            if ('INBOX' in present) != row['keep_inbox']:
                raise ValueError('Inbox state differs from the reviewed plan.')
            if row.get('pending') and labels['Action Required'] not in present:
                raise ValueError('Missing Action Required label.')


def verify_preserved(rows, baseline, snapshots):
    for row in rows:
        before, after = baseline[str(row['id'])], snapshots[row['id']]
        for field in ('id', 'threadId', 'internalDate', 'sizeEstimate', 'payload'):
            if before.get(field) != after.get(field):
                raise ValueError('Provider message content changed during filing.')
        if not row['delete']:
            # User reads can change UNREAD concurrently; only INBOX is archived.
            retained_labels = set(before.get('labelIds', [])) - {'INBOX', 'UNREAD'}
            if not retained_labels.issubset(after.get('labelIds', [])):
                raise ValueError('An unrelated retained label was removed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--home', type=Path, default=Path('/var/lib/msgvault'))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--verify-only', action='store_true',
                      help='Verify an applied plan without modifying Gmail.')
    args = parser.parse_args()
    os.umask(0o077)
    plan = json.loads(args.plan.read_text())
    rows = validate_plan(plan)
    with sqlite3.connect('file:' + str(args.home / 'msgvault.db') + '?mode=ro', uri=True) as connection:
        guard_source(connection, plan)
    gmail = Gmail(args.home, plan['account'])
    profile = gmail.request('profile')
    guard_profile(profile, plan)
    before = gmail.inspect(rows)
    verify_provider(rows, before)
    plan_hash = hashlib.sha256(args.plan.read_bytes()).hexdigest()
    receipt = args.plan.parent / 'provider-before.json'
    if receipt.exists():
        if json.loads(receipt.read_text())['plan_sha256'] != plan_hash:
            raise ValueError('A different plan already owns this receipt directory.')
    else:
        if args.apply or args.verify_only:
            raise ValueError('Run read-only preflight before applying or verifying a plan.')
        private_json(receipt, {'plan_sha256': plan_hash, 'profile': profile,
                              'messages': before, 'labels': gmail.request('labels')})
    retained = [row for row in rows if not row['delete']]
    deleted = [row for row in rows if row['delete']]
    summary = {'account': plan['account'], 'reviewed': len(rows),
               'delete': len(deleted), 'file': len(retained),
               'keep_inbox': sum(row['keep_inbox'] for row in retained)}
    if args.verify_only:
        existing = {label['name']: label['id'] for label in gmail.request('labels')['labels']}
        verify_provider(rows, before, existing)
        verify_preserved(rows, json.loads(receipt.read_text())['messages'], before)
        private_json(args.plan.parent / 'provider-after.json', {
            'plan_sha256': plan_hash, 'profile': profile,
            'messages': before, 'label_ids': existing, 'summary': summary,
            'inbox': gmail.request('messages?labelIds=INBOX&maxResults=500')})
        print(json.dumps(dict(summary, mode='verified without provider writes')))
        return
    if not args.apply:
        print(json.dumps(dict(summary, mode='read-only preflight')))
        return
    if any('TRASH' not in before[row['id']].get('labelIds', []) for row in deleted):
        raise ValueError('Execute and verify the exact native Trash batch before filing.')
    existing = {label['name']: label['id'] for label in gmail.request('labels')['labels']}
    topics = set(row['topic'] for row in retained) | set(plan.get('reserve_topics', []))
    if any(row.get('pending') for row in retained):
        topics.add('Action Required')
    names = set(topics)
    for name in topics:
        parts = name.split('/')
        names.update('/'.join(parts[:i]) for i in range(1, len(parts)))
    for name in sorted(names, key=lambda name: (name.count('/'), name)):
        if name not in existing:
            result = gmail.request('labels', 'POST', {'name': name,
                'labelListVisibility': 'labelShow', 'messageListVisibility': 'show'})
            existing[name] = result['id']
    for topic in sorted(set(row['topic'] for row in retained)):
        for keep_inbox in (True, False):
            selected = [row for row in retained
                        if row['topic'] == topic and row['keep_inbox'] == keep_inbox]
            if not selected:
                continue
            gmail.request('messages/batchModify', 'POST', {
                'ids': [row['source_message_id'] for row in selected],
                'addLabelIds': [existing[topic]] + (['INBOX'] if keep_inbox else []),
                'removeLabelIds': [] if keep_inbox else ['INBOX']})
    pending = [row['source_message_id'] for row in retained if row.get('pending')]
    if pending:
        gmail.request('messages/batchModify', 'POST', {
            'ids': pending, 'addLabelIds': [existing['Action Required']], 'removeLabelIds': []})
    after = gmail.inspect(rows)
    verify_provider(rows, after, existing)
    verify_preserved(rows, json.loads(receipt.read_text())['messages'], after)
    private_json(args.plan.parent / 'provider-after.json', {
        'plan_sha256': plan_hash, 'profile': gmail.request('profile'),
        'messages': after, 'label_ids': existing, 'summary': summary,
        'inbox': gmail.request('messages?labelIds=INBOX&maxResults=500')})
    print(json.dumps(dict(summary, mode='filed and verified')))


if __name__ == '__main__':
    main()
