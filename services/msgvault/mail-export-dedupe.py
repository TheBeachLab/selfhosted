#!/usr/bin/env python3
"""Compare disconnected mail exports with complete Msgvault MIME snapshots.

No provider writes. Private indexes/plans contain hashes and identifiers only.
Mbox transport: https://docs.python.org/3.14/library/mailbox.html#mailbox.mbox
EMLX consists of a byte-count line, that many MIME bytes, then Apple metadata.
"""
import argparse
import collections
import datetime
from email import policy
from email.parser import BytesParser, BytesHeaderParser
from email.utils import parsedate_to_datetime
import hashlib
import json
import mailbox
import os
from pathlib import Path
import sqlite3
import stat
import unicodedata
import zlib

HEADERS = ('from', 'sender', 'to', 'cc', 'bcc', 'reply-to', 'subject',
           'in-reply-to', 'references', 'resent-from', 'resent-to')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.chmod(0o600)
    temp.replace(path)


def normalized(value):
    return unicodedata.normalize('NFC', str(value)).replace('\r\n', '\n').replace('\r', '\n')


def message_id(message):
    return str(message.get('Message-ID', '')).strip().strip('<>').strip()


def core(message):
    values = {key: [normalized(v) for v in message.get_all(key, [])] for key in HEADERS}
    date = str(message.get('Date', ''))
    try:
        parsed = parsedate_to_datetime(date)
        if parsed.tzinfo:
            date = parsed.astimezone(datetime.timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    values.update(date=date, message_id=message_id(message))
    return sha(json.dumps(values, sort_keys=True, ensure_ascii=False).encode())


def mime_tree(part):
    content_type = part.get_content_type().lower()
    disposition = part.get_content_disposition()
    filename = normalized(part.get_filename() or '')
    cid = str(part.get('Content-ID', '')).strip().strip('<>')
    parameters = sorted([str(k).lower(), normalized(v)]
                        for k, v in (part.get_params() or [])[1:]
                        if str(k).lower() not in ('boundary', 'charset', 'name'))
    node = {'type': content_type, 'disposition': disposition, 'filename': filename,
            'cid': cid, 'parameters': parameters}
    if content_type == 'message/rfc822' and isinstance(part.get_payload(), list):
        node['nested'] = [{'core': core(child), 'mime': mime_tree(child)} for child in part.get_payload()]
    elif part.is_multipart():
        node['children'] = [mime_tree(child) for child in part.get_payload()]
    else:
        data = part.get_payload(decode=True)
        if data is None:
            data = str(part.get_payload()).encode('utf-8', errors='surrogateescape')
        node['bytes'] = len(data)
        node['raw_sha256'] = sha(data)
        # Normalize text encoding and transport line endings, never trim spaces.
        try:
            content = normalized(data.decode(part.get_content_charset() or 'ascii')).encode('utf-8')
        except (UnicodeError, LookupError):
            content = data
        if part.get_content_maintype() != 'text' or disposition == 'attachment' or filename:
            content = data
        else:
            # mbox and SMTP may append terminal separator newlines. Attachments
            # retain exact decoded bytes, including all whitespace.
            content = content.rstrip(b'\n')
        node['sha256'] = sha(content)
        node['attachment'] = bool(filename or disposition == 'attachment'
                                  or (part.get_content_maintype() != 'text'
                                      and (cid or disposition == 'inline')))
    return node


def inspect_mime(raw):
    message = BytesParser(policy=policy.default).parsebytes(raw)
    tree = mime_tree(message)
    defects = [type(d).__name__ for p in message.walk() for d in p.defects]
    if defects:
        raise ValueError('Malformed MIME: ' + ','.join(sorted(set(defects))))
    return {'message_id': message_id(message), 'core': core(message), 'mime': tree}


def leaves(node):
    if 'children' in node:
        return [leaf for child in node['children'] for leaf in leaves(child)]
    if 'nested' in node:
        return [leaf for child in node['nested'] for leaf in leaves(child['mime'])]
    return [node]


def equivalent(local, archived, partial=False):
    if local['message_id'] != archived['message_id'] or local['core'] != archived['core']:
        return False
    def same(a, b):
        structural = ('type', 'disposition', 'filename', 'cid', 'parameters')
        if any(a.get(key) != b.get(key) for key in structural):
            return False
        if 'children' in a or 'children' in b:
            return (len(a.get('children', [])) == len(b.get('children', []))
                    and all(same(x, y) for x, y in zip(a.get('children', []), b.get('children', []))))
        if 'nested' in a or 'nested' in b:
            return a == b
        if a['sha256'] == b['sha256']:
            return True
        # Apple's explicit partial cache has empty attachment placeholders.
        # The complete archived MIME must contain that same named/CID part.
        return (partial and a['bytes'] == 0 and a.get('attachment')
                and bool(a.get('filename') or a.get('cid')) and b['bytes'] > 0)
    return same(local['mime'], archived['mime'])


def build_index(db):
    connection = sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True)
    connection.execute('BEGIN')
    attachments = collections.defaultdict(set)
    for mid, digest, size in connection.execute('SELECT message_id,content_hash,size FROM attachments'):
        attachments[mid].add((digest, size))
    records, rejected = [], []
    query = ('SELECT m.id,m.source_id,m.rfc822_message_id,r.raw_data,r.raw_format,r.compression,r.encryption_version '
             'FROM messages m JOIN message_raw r ON r.message_id=m.id '
             'WHERE m.deleted_at IS NULL AND m.deleted_from_source_at IS NULL ORDER BY m.id')
    for mid, source, rfcid, data, fmt, compression, encryption in connection.execute(query):
        raw = None
        try:
            if fmt != 'mime' or encryption:
                raise ValueError('Unsupported or encrypted MIME snapshot.')
            raw = zlib.decompress(data) if compression == 'zlib' else data
            if compression not in ('zlib', None, ''):
                raise ValueError('Unsupported compression.')
            record = inspect_mime(raw)
            if not record['message_id'] or record['message_id'] != str(rfcid).strip().strip('<>').strip():
                raise ValueError('Snapshot Message-ID does not match archive.')
            parts = [leaf for leaf in leaves(record['mime']) if leaf.get('attachment') and leaf['bytes']]
            if any((part['raw_sha256'], part['bytes']) not in attachments[mid] for part in parts):
                raise ValueError('A MIME attachment is not present in archive attachment rows.')
            records.append(dict(record, id=mid, source_id=source, raw_sha256=sha(raw)))
        except Exception as error:
            rejected.append({'id': mid, 'reason': str(error)[:180]})
            # Exact full-MIME byte equality remains proof even if parsing or a
            # derived attachment row is incomplete. Never allow fuzzy matching.
            if raw is not None and fmt == 'mime' and not encryption:
                records.append({'id': mid, 'source_id': source, 'message_id':str(rfcid).strip().strip('<>').strip(),
                                'raw_sha256':sha(raw), 'raw_only':True})
    sources = connection.execute('SELECT id,source_type,identifier FROM sources ORDER BY id').fetchall()
    connection.close()
    return {'version': 1, 'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'sources': sources, 'messages': records, 'rejected': rejected}


def read_emlx(path):
    data = path.read_bytes()
    prefix, separator, rest = data.partition(b'\n')
    if not separator or not prefix.strip().isdigit():
        raise ValueError('Invalid EMLX byte count.')
    count = int(prefix)
    if count <= 0 or len(rest) < count:
        raise ValueError('Truncated EMLX MIME payload.')
    return rest[:count]


def guard_path(path, roots):
    path = path.absolute()
    if not any(path.is_relative_to(root) for root in roots):
        raise ValueError('File is outside the authorized roots.')
    if path.resolve() != path or path.is_symlink() or not path.is_file():
        raise ValueError('Symlink, redirected path or non-file.')
    if '/Library/Mail/' in str(path):
        raise ValueError('Live Apple Mail stores are excluded.')
    return path


def match(raw, index, partial=False):
    header_id = message_id(BytesHeaderParser(policy=policy.default).parsebytes(raw))
    if not header_id:
        return {'matched': False, 'reason': 'missing-message-id'}
    candidates = index.get(header_id, [])
    raw_hash = sha(raw)
    for candidate in candidates:
        if raw_hash == candidate['raw_sha256']:
            return {'matched':True, 'archive_id':candidate['id'], 'source_id':candidate['source_id'],
                    'message_id':header_id, 'method':'exact-full-mime'}
    signature = inspect_mime(raw)
    for candidate in candidates:
        if not candidate.get('raw_only') and equivalent(signature, candidate, partial):
            return {'matched': True, 'archive_id': candidate['id'], 'source_id': candidate['source_id'],
                    'message_id': signature['message_id'], 'method':'complete-content',
                    'attachment_parts':sum(p.get('attachment', False) for p in leaves(signature['mime']))}
    return {'matched': False, 'reason': 'content-differs' if candidates else 'not-in-live-archive',
            'message_id': signature['message_id']}


def scan(index_path, paths, roots):
    archived = json.loads(index_path.read_text())
    by_id = collections.defaultdict(list)
    for record in archived['messages']:
        by_id[record['message_id']].append(record)
    output = []
    for path in paths:
        try:
            path = guard_path(path, roots)
            data = path.read_bytes()
            record = {'path': str(path), 'sha256': sha(data), 'bytes': len(data), 'items': []}
            if path.name == 'mbox' or path.suffix.lower() == '.mbox':
                record['kind'] = 'mbox'
                box = mailbox.mbox(path, create=False)
                try:
                    # Public get_bytes reads the MIME; offsets retain unmatched bytes exactly.
                    keys = list(box.iterkeys())
                    starts = [box._toc[key][0] for key in keys]
                    for ordinal, key in enumerate(keys):
                        raw = box.get_bytes(key)
                        try:
                            result = match(raw, by_id)
                        except Exception as error:
                            result = {'matched': False, 'reason': str(error)[:180]}
                        result.update(ordinal=ordinal, start=starts[ordinal],
                                      stop=starts[ordinal+1] if ordinal+1<len(starts) else len(data))
                        record['items'].append(result)
                    if keys and starts[0] != 0:
                        raise ValueError('Unparsed data before first mbox envelope.')
                    if not keys and data.strip():
                        raise ValueError('Non-empty mbox has no message envelopes.')
                finally:
                    box.close()
            else:
                record['kind'] = 'emlx' if path.suffix.lower() == '.emlx' else 'eml'
                raw = read_emlx(path) if record['kind'] == 'emlx' else data
                record['items'] = [match(raw, by_id, path.name.endswith('.partial.emlx'))]
            output.append(record)
        except Exception as error:
            output.append({'path': str(path), 'error': str(error)[:200], 'items': []})
    return {'version': 1, 'index_sha256': sha(index_path.read_bytes()),
            'roots': [str(root) for root in roots], 'files': output}


def scan_cache_attachments(index_path, mail_plan_path, mail_receipt_path):
    """Inspect sidecar attachments only for EMLX copies already removed.

    Apple's cache layout is Data/.../Messages/ID[.partial].emlx alongside
    Data/.../Attachments/ID/PART/FILENAME. An attachment must have identical
    decoded bytes in that specific matched archive message, not just elsewhere.
    """
    mail_plan = json.loads(mail_plan_path.read_text())
    if sha(index_path.read_bytes()) != mail_plan['index_sha256']:
        raise ValueError('Archive index changed after the mail plan was reviewed.')
    receipt = json.loads(mail_receipt_path.read_text())
    records = {record['path']: record for record in mail_plan['files']}
    archived = {record['id']: record for record in json.loads(index_path.read_text())['messages']}
    roots = [Path(root) for root in mail_plan['roots']]
    output, seen = [], set()
    for removed in receipt['removed_files']:
        record = records[removed['path']]
        if record.get('kind') != 'emlx':
            continue
        path = Path(record['path'])
        if path.exists() or path.is_symlink() or len(record['items']) != 1 or not record['items'][0]['matched']:
            raise ValueError('Cache attachments require an already removed, verified EMLX copy.')
        identifier = path.name.split('.')[0]
        if path.parent.name != 'Messages' or not identifier.isdigit():
            continue
        message = archived[record['items'][0]['archive_id']]
        parts = {(part['raw_sha256'], part['bytes']) for part in leaves(message['mime'])
                 if part.get('attachment') and part['bytes']} if 'mime' in message else set()
        folder = path.parent.parent / 'Attachments' / identifier
        for attachment in folder.rglob('*'):
            if not attachment.is_file() or attachment in seen:
                continue
            seen.add(attachment)
            try:
                attachment = guard_path(attachment, roots)
                data = attachment.read_bytes()
                digest = sha(data)
                matched = (digest, len(data)) in parts
                item = {'matched': matched}
                if matched:
                    item.update(archive_id=message['id'], source_id=message['source_id'],
                                method='exact-attachment-bytes')
                else:
                    item['reason'] = 'attachment-not-in-matched-archive-message'
                output.append({'path': str(attachment), 'sha256': digest, 'bytes': len(data),
                               'kind': 'cache-attachment', 'cache_message_path': str(path), 'items': [item]})
            except Exception as error:
                output.append({'path': str(attachment), 'error': str(error)[:200], 'items': []})
    return {'version': 1, 'index_sha256': mail_plan['index_sha256'], 'roots': mail_plan['roots'],
            'mail_plan_sha256': sha(mail_plan_path.read_bytes()),
            'mail_receipt_sha256': sha(mail_receipt_path.read_bytes()), 'files': output}


def apply(plan, receipt_path, index_path):
    if sha(index_path.read_bytes()) != plan['index_sha256']:
        raise ValueError('Archive index changed after the plan was reviewed.')
    archive_ids = {r['id'] for r in json.loads(index_path.read_text())['messages']}
    if any(item.get('archive_id') not in archive_ids for record in plan['files']
           for item in record['items'] if item['matched']):
        raise ValueError('Deletion plan references an unverified archive message.')
    roots = [Path(root) for root in plan['roots']]
    receipt = {'removed_files': [], 'compacted_files': [], 'preserved_files': [], 'errors': []}
    for record in plan['files']:
        if record.get('error') or not record['items'] or not any(x['matched'] for x in record['items']):
            receipt['preserved_files'].append(record['path']); continue
        locked_box = None
        try:
            path = guard_path(Path(record['path']), roots)
            if record['kind'] == 'mbox':
                locked_box = mailbox.mbox(path, create=False)
                locked_box.lock()
            data = path.read_bytes()
            if sha(data) != record['sha256']:
                raise ValueError('File changed after inspection.')
            kept = [x for x in record['items'] if not x['matched']]
            if not kept:
                path.unlink()
                receipt['removed_files'].append({'path': str(path), 'bytes': len(data), 'messages':len(record['items'])})
            else:
                if record['kind'] != 'mbox':
                    raise ValueError('Partial removal only supports mbox containers.')
                payload = b''.join(data[x['start']:x['stop']] for x in kept)
                temp = path.with_name(path.name + '.msgvault-compacting')
                if temp.exists():
                    raise ValueError('Unowned compaction temporary already exists.')
                with temp.open('xb') as stream:
                    os.chmod(temp, stat.S_IMODE(path.stat().st_mode))
                    stream.write(payload); stream.flush(); os.fsync(stream.fileno())
                # Reparse before replacing, retaining every unmatched message byte block.
                box = mailbox.mbox(temp, create=False)
                try:
                    if len(box) != len(kept):
                        raise ValueError('Compaction altered unmatched message boundaries.')
                finally:
                    box.close()
                if sha(path.read_bytes()) != record['sha256']:
                    raise ValueError('Mbox changed while compacting.')
                temp.replace(path)
                receipt['compacted_files'].append({'path': str(path), 'before':len(data), 'after':len(payload),
                                                   'removed_messages':len(record['items'])-len(kept), 'kept_messages':len(kept),
                                                   'kept_sha256':sha(payload)})
            if record['kind'] == 'mbox':
                sidecar = path.parent / 'table_of_contents'
                if sidecar.is_file() and not sidecar.is_symlink():
                    sidecar.unlink()  # Offsets are invalid after compaction; mbox import reconstructs them.
            private_json(receipt_path, receipt)
        except Exception as error:
            receipt['errors'].append({'path':record['path'], 'reason':str(error)[:200]})
            private_json(receipt_path, receipt)
        finally:
            if locked_box is not None:
                locked_box.close()
    private_json(receipt_path, receipt)
    return receipt


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    index = commands.add_parser('index'); index.add_argument('--db', type=Path, required=True); index.add_argument('--output', type=Path, required=True)
    scanning = commands.add_parser('scan'); scanning.add_argument('--index', type=Path, required=True); scanning.add_argument('--files-nul', type=Path, required=True); scanning.add_argument('--root', type=Path, action='append', required=True); scanning.add_argument('--output', type=Path, required=True)
    cache = commands.add_parser('scan-cache-attachments'); cache.add_argument('--index', type=Path, required=True); cache.add_argument('--mail-plan', type=Path, required=True); cache.add_argument('--mail-receipt', type=Path, required=True); cache.add_argument('--output', type=Path, required=True)
    applying = commands.add_parser('apply'); applying.add_argument('--plan', type=Path, required=True); applying.add_argument('--index', type=Path, required=True); applying.add_argument('--receipt', type=Path, required=True); applying.add_argument('--yes', action='store_true')
    args = parser.parse_args()
    if args.command == 'index':
        value = build_index(args.db); private_json(args.output, value)
        print(json.dumps({'full_mime_snapshots':len(value['messages']), 'exact_only_snapshots':len(value['rejected'])}))
    elif args.command in ('scan', 'scan-cache-attachments'):
        if args.command == 'scan':
            paths = [Path(os.fsdecode(x)) for x in args.files_nul.read_bytes().split(b'\0') if x]
            value = scan(args.index, paths, [root.absolute() for root in args.root])
        else:
            value = scan_cache_attachments(args.index, args.mail_plan, args.mail_receipt)
        private_json(args.output, value)
        items = [item for f in value['files'] for item in f['items']]
        item_name = 'messages' if args.command == 'scan' else 'attachments'
        print(json.dumps({'files':len(value['files']), item_name:len(items), 'matched':sum(x['matched'] for x in items),
                          'kept':sum(not x['matched'] for x in items), 'file_errors':sum('error' in f for f in value['files'])}))
    else:
        if not args.yes:
            raise SystemExit('Explicit --yes required for the reviewed exact-file plan.')
        value = apply(json.loads(args.plan.read_text()), args.receipt, args.index)
        print(json.dumps({key:len(values) for key,values in value.items()}))


if __name__ == '__main__':
    main()
