import copy
from email.message import EmailMessage
from email import policy
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zlib

spec = importlib.util.spec_from_file_location('dedupe', Path(__file__).parents[1] / 'services/msgvault/mail-export-dedupe.py')
dedupe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dedupe)


def message(identifier='one@example.org', body='Body preserved.\n', attachment=None):
    msg = EmailMessage()
    msg['Message-ID'] = '<' + identifier + '>'
    msg['From'] = 'Sender <sender@example.org>'
    msg['To'] = 'recipient@example.org'
    msg['Subject'] = 'Same subject'
    msg['Date'] = 'Mon, 12 Oct 2026 10:00:00 +0200'
    msg.set_content(body)
    if attachment is not None:
        msg.add_attachment(attachment, maintype='application', subtype='pdf', filename='invoice.pdf')
    return msg.as_bytes(policy=policy.SMTP)


class DedupeGuards(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name).resolve()
        self.raw = message()
        self.index = self.root / 'index.json'
        self.record = dict(dedupe.inspect_mime(self.raw), id=1, source_id=1, raw_sha256=dedupe.sha(self.raw))
        dedupe.private_json(self.index, {'messages': [self.record]})

    def tearDown(self):
        self.directory.cleanup()

    def test_same_message_id_does_not_hide_body_or_recipient_changes(self):
        altered = dedupe.inspect_mime(message(body='Unique content.\n'))
        self.assertFalse(dedupe.equivalent(altered, self.record))
        raw = self.raw.replace(b'recipient@example.org', b'other@example.org')
        self.assertFalse(dedupe.equivalent(dedupe.inspect_mime(raw), self.record))

    def test_attachment_bytes_must_match(self):
        one = dedupe.inspect_mime(message(attachment=b'one'))
        two = dedupe.inspect_mime(message(attachment=b'two'))
        self.assertFalse(dedupe.equivalent(one, two))

    def test_mime_parameters_survive_index_json_round_trip(self):
        msg = EmailMessage()
        msg['Message-ID'] = '<params@example.org>'
        msg.set_content('Full body.')
        msg.add_attachment(b'invoice', maintype='application', subtype='pdf', filename='invoice.pdf', params={'x-unix-mode':'0644'})
        local = dedupe.inspect_mime(msg.as_bytes())
        archived = json.loads(json.dumps(local))
        self.assertTrue(dedupe.equivalent(local, archived))

    def test_transport_terminal_newlines_are_not_attachment_normalization(self):
        self.assertTrue(dedupe.equivalent(dedupe.inspect_mime(message(body='Same\n')), dedupe.inspect_mime(message(body='Same\n\n'))))
        self.assertFalse(dedupe.equivalent(dedupe.inspect_mime(message(attachment=b'pdf\n')), dedupe.inspect_mime(message(attachment=b'pdf\n\n'))))

    def test_only_explicit_partial_attachment_placeholder_is_allowed(self):
        full = dedupe.inspect_mime(message(attachment=b'complete invoice'))
        partial = dedupe.inspect_mime(message(attachment=b''))
        self.assertFalse(dedupe.equivalent(partial, full))
        self.assertTrue(dedupe.equivalent(partial, full, partial=True))
        partial['mime']['children'][0]['sha256'] = dedupe.sha(b'missing body')
        self.assertFalse(dedupe.equivalent(partial, full, partial=True))

    def test_inline_text_body_is_not_an_attachment(self):
        msg = EmailMessage()
        msg.set_content('Full body.')
        msg['Content-Disposition'] = 'inline'
        msg['Content-ID'] = '<body>'
        tree = dedupe.mime_tree(msg)
        self.assertFalse(tree['attachment'])

    def test_symlink_and_live_mail_store_are_rejected(self):
        path = self.root / 'mail.eml'; path.write_bytes(self.raw)
        link = self.root / 'link.eml'; link.symlink_to(path)
        with self.assertRaises(ValueError):
            dedupe.guard_path(link, [self.root])
        live = self.root / 'Library/Mail/V10/mail.emlx'; live.parent.mkdir(parents=True); live.write_bytes(self.raw)
        with self.assertRaises(ValueError):
            dedupe.guard_path(live, [self.root])

    def test_truncated_emlx_is_preserved(self):
        path = self.root / 'mail.partial.emlx'; path.write_bytes(b'500\nshort')
        plan = dedupe.scan(self.index, [path], [self.root])
        self.assertIn('Truncated', plan['files'][0]['error'])
        receipt = dedupe.apply(plan, self.root / 'receipt.json', self.index)
        self.assertEqual(len(receipt['preserved_files']), 1)
        self.assertTrue(path.exists())

    def test_mbox_compaction_keeps_unmatched_blocks_byte_for_byte(self):
        path = self.root / 'mail.mbox'; path.mkdir(); path = path / 'mbox'
        first = b'From sender Mon Oct 12 10:00:00 2026\n' + self.raw.replace(b'\r\n', b'\n') + b'\n'
        second = b'From sender Mon Oct 12 10:01:00 2026\n' + message('two@example.org', body='Unique body.\n').replace(b'\r\n', b'\n') + b'\n'
        path.write_bytes(first + second)
        sidecar = path.parent / 'table_of_contents'; sidecar.write_bytes(b'old offsets')
        plan = dedupe.scan(self.index, [path], [self.root])
        self.assertEqual([x['matched'] for x in plan['files'][0]['items']], [True, False])
        receipt = dedupe.apply(plan, self.root / 'receipt.json', self.index)
        self.assertEqual(path.read_bytes(), second)
        self.assertFalse(sidecar.exists())
        self.assertEqual(receipt['compacted_files'][0]['kept_messages'], 1)

    def test_changed_file_or_index_is_never_deleted(self):
        path = self.root / 'mail.eml'; path.write_bytes(self.raw)
        plan = dedupe.scan(self.index, [path], [self.root])
        path.write_bytes(self.raw + b'new bytes')
        receipt = dedupe.apply(plan, self.root / 'receipt.json', self.index)
        self.assertEqual(len(receipt['errors']), 1)
        self.assertTrue(path.exists())
        self.index.write_text('{}')
        with self.assertRaises(ValueError):
            dedupe.apply(plan, self.root / 'receipt2.json', self.index)

    def test_archive_index_requires_real_attachment_rows_and_active_message(self):
        path = self.root / 'db.sqlite'
        c = sqlite3.connect(path)
        c.executescript('CREATE TABLE messages(id,source_id,rfc822_message_id,deleted_at,deleted_from_source_at); '
                       'CREATE TABLE message_raw(message_id,raw_data,raw_format,compression,encryption_version); '
                       'CREATE TABLE attachments(message_id,content_hash,size); '
                       'CREATE TABLE sources(id,source_type,identifier);')
        c.execute('INSERT INTO sources VALUES(1,"imap","reviewed@example.org")')
        raw = message(attachment=b'whole invoice')
        c.execute('INSERT INTO messages VALUES(1,1,"<one@example.org>",NULL,NULL)')
        c.execute('INSERT INTO message_raw VALUES(1,?,"mime","zlib",0)', (zlib.compress(raw),))
        c.commit()
        self.assertTrue(dedupe.build_index(path)['messages'][0]['raw_only'])
        c.execute('INSERT INTO attachments VALUES(1,?,?)', (dedupe.sha(b'whole invoice'), len(b'whole invoice')))
        c.commit()
        self.assertEqual(len(dedupe.build_index(path)['messages']), 1)
        self.assertNotIn('raw_only', dedupe.build_index(path)['messages'][0])
        c.execute('UPDATE messages SET deleted_from_source_at="deleted"'); c.commit()
        self.assertEqual(len(dedupe.build_index(path)['messages']), 0)
        c.close()

    def test_cache_attachments_match_only_the_already_removed_message(self):
        raw = message(attachment=b'complete attachment')
        archive = dict(dedupe.inspect_mime(raw), id=2, source_id=1, raw_sha256=dedupe.sha(raw))
        dedupe.private_json(self.index, {'messages': [archive, self.record]})
        path = self.root / 'cache/Data/Messages/123.partial.emlx'
        path.parent.mkdir(parents=True)
        path.write_bytes(str(len(raw)).encode() + b'\n' + raw)
        plan = dedupe.scan(self.index, [path], [self.root])
        plan_path = self.root / 'mail-plan.json'; dedupe.private_json(plan_path, plan)
        receipt_path = self.root / 'mail-receipt.json'
        dedupe.apply(plan, receipt_path, self.index)
        folder = path.parent.parent / 'Attachments/123/2'; folder.mkdir(parents=True)
        matching = folder / 'invoice.pdf'; matching.write_bytes(b'complete attachment')
        unmatched = folder / 'unique.pdf'; unmatched.write_bytes(b'other attachment')
        other_folder = path.parent.parent / 'Attachments/124/2'; other_folder.mkdir(parents=True)
        unrelated = other_folder / 'same.pdf'; unrelated.write_bytes(b'complete attachment')
        attachment_plan = dedupe.scan_cache_attachments(self.index, plan_path, receipt_path)
        results = {item['path']: item for item in attachment_plan['files']}
        self.assertTrue(results[str(matching)]['items'][0]['matched'])
        self.assertFalse(results[str(unmatched)]['items'][0]['matched'])
        self.assertNotIn(str(unrelated), results)
        receipt = dedupe.apply(attachment_plan, self.root / 'attachments-receipt.json', self.index)
        self.assertFalse(matching.exists())
        self.assertTrue(unmatched.exists())
        self.assertTrue(unrelated.exists())
        self.assertFalse(receipt['errors'])

    def test_cache_attachments_require_removed_emlx_and_unchanged_index(self):
        path = self.root / 'cache/Data/Messages/123.emlx'; path.parent.mkdir(parents=True)
        path.write_bytes(str(len(self.raw)).encode() + b'\n' + self.raw)
        plan = dedupe.scan(self.index, [path], [self.root])
        plan_path = self.root / 'mail-plan.json'; dedupe.private_json(plan_path, plan)
        receipt_path = self.root / 'mail-receipt.json'
        dedupe.private_json(receipt_path, {'removed_files': [{'path': str(path)}]})
        with self.assertRaises(ValueError):
            dedupe.scan_cache_attachments(self.index, plan_path, receipt_path)
        path.unlink()
        self.index.write_text('{}')
        with self.assertRaises(ValueError):
            dedupe.scan_cache_attachments(self.index, plan_path, receipt_path)


if __name__ == '__main__':
    unittest.main()
