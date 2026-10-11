"""Offline safety checks; no provider requests or private credentials."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

spec = importlib.util.spec_from_file_location('gmail_file', Path(__file__).with_name('gmail-file.py'))
filing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(filing)


class FilingGuards(unittest.TestCase):
    def setUp(self):
        self.row = {'id': 5, 'source_id': 2, 'source_message_id': 'abc123',
                    'delete': False, 'keep_inbox': False, 'pending': False,
                    'topic': 'Germany/Finance & Taxes'}
        self.plan = {'source_id': 2, 'account': 'reviewed@example.com', 'messages': [self.row]}
        self.provider = {'id': 'abc123', 'threadId': '123abc', 'sizeEstimate': 100,
                         'payload': {'headers': [{'name': 'Subject', 'value': 'Invoice'}]},
                         'labelIds': ['Label_Tax', 'Label_Existing', 'UNREAD']}

    def test_mixed_account_and_duplicate_ids_rejected(self):
        mixed = copy.deepcopy(self.plan)
        mixed['messages'][0]['source_id'] = 1
        with self.assertRaises(ValueError):
            filing.validate_plan(mixed)
        duplicated = copy.deepcopy(self.plan)
        duplicated['messages'].append(copy.deepcopy(self.row))
        with self.assertRaises(ValueError):
            filing.validate_plan(duplicated)
        with self.assertRaises(ValueError):
            filing.guard_profile({'emailAddress': 'other@example.com'}, self.plan)

    def test_pending_must_remain_inbox_and_deleted_cannot_be_filed(self):
        self.row['pending'] = True
        with self.assertRaises(ValueError):
            filing.validate_plan(self.plan)
        self.row['pending'] = False
        self.row['delete'] = True
        with self.assertRaises(ValueError):
            filing.validate_plan(self.plan)

    def test_archive_identity_guard(self):
        connection = sqlite3.connect(':memory:')
        connection.executescript('CREATE TABLE sources(id, source_type, identifier); '
                                 'CREATE TABLE messages(id, source_id, source_message_id);')
        connection.execute('INSERT INTO sources VALUES(2, ?, ?)', ('gmail', self.plan['account']))
        connection.execute('INSERT INTO messages VALUES(5, 2, ?)', ('abc123',))
        filing.guard_source(connection, self.plan)
        connection.execute('UPDATE messages SET source_id=1')
        with self.assertRaises(ValueError):
            filing.guard_source(connection, self.plan)

    def test_final_topic_inbox_and_trash_are_verified(self):
        labels = {'Germany/Finance & Taxes': 'Label_Tax', 'Action Required': 'Label_Action'}
        filing.verify_provider([self.row], {5: self.provider}, labels)
        self.provider['labelIds'].append('INBOX')
        with self.assertRaises(ValueError):
            filing.verify_provider([self.row], {5: self.provider}, labels)
        self.row.update(delete=True, topic=None)
        with self.assertRaises(ValueError):
            filing.verify_provider([self.row], {5: self.provider}, labels)
        self.provider['labelIds'] = ['TRASH']
        filing.verify_provider([self.row], {5: self.provider}, labels)

    def test_drafts_are_never_filed(self):
        self.provider['labelIds'].append('DRAFT')
        with self.assertRaises(ValueError):
            filing.verify_provider([self.row], {5: self.provider})

    def test_content_and_unrelated_labels_preserved(self):
        baseline = {'5': copy.deepcopy(self.provider)}
        self.provider['labelIds'].remove('UNREAD')
        filing.verify_preserved([self.row], baseline, {5: self.provider})
        self.provider['labelIds'].remove('Label_Existing')
        with self.assertRaises(ValueError):
            filing.verify_preserved([self.row], baseline, {5: self.provider})
        self.provider['labelIds'].append('Label_Existing')
        self.provider['payload']['headers'][0]['value'] = 'Changed'
        with self.assertRaises(ValueError):
            filing.verify_preserved([self.row], baseline, {5: self.provider})

    def test_only_idempotent_operations_retry_rate_limits(self):
        client = filing.Gmail.__new__(filing.Gmail)
        client.access = 'offline-test-token'
        client.pace = lambda: None
        def forbidden():
            body = json.dumps({'error': {'errors': [{'reason': 'userRateLimitExceeded'}]}}).encode()
            return urllib.error.HTTPError('https://gmail.googleapis.com/', 403, 'rate limit', {}, io.BytesIO(body))
        with patch.object(filing.urllib.request, 'urlopen', side_effect=[forbidden(), io.BytesIO(b'{}')]) as request, patch.object(filing.time, 'sleep'):
            self.assertEqual(client.request('messages/abc123'), {})
            self.assertEqual(request.call_count, 2)
        with patch.object(filing.urllib.request, 'urlopen', side_effect=forbidden()) as request, patch.object(filing.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                client.request('labels', 'POST', {'name': 'New topic'})
            self.assertEqual(request.call_count, 1)

    def test_apply_requires_existing_preflight_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            connection = sqlite3.connect(home / 'msgvault.db')
            connection.executescript('CREATE TABLE sources(id, source_type, identifier); '
                                     'CREATE TABLE messages(id, source_id, source_message_id);')
            connection.execute('INSERT INTO sources VALUES(2, ?, ?)', ('gmail', self.plan['account']))
            connection.execute('INSERT INTO messages VALUES(5, 2, ?)', ('abc123',))
            connection.commit()
            connection.close()
            path = home / 'plan.json'
            path.write_text(json.dumps(self.plan))
            with patch.object(sys, 'argv', ['gmail-file.py', str(path), '--home', directory, '--apply']), patch.object(filing, 'Gmail') as gmail:
                gmail.return_value.request.return_value = {'emailAddress': self.plan['account']}
                gmail.return_value.inspect.return_value = {5: self.provider}
                with self.assertRaisesRegex(ValueError, 'read-only preflight'):
                    filing.main()
                self.assertFalse((home / 'provider-before.json').exists())
                gmail.return_value.request.assert_called_once_with('profile')


if __name__ == '__main__':
    unittest.main()
