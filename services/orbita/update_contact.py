#!/usr/bin/env python3
"""Apply the approved contact and project attribution to the published HTML."""
import argparse
import json
import os
import shutil
from pathlib import Path


def transform(text):
    updated = text.replace('hello@orbita.you', 'fran@arroyo.ing')
    updated = updated.replace('Beach Lab', 'Arroyo Ingenieurbüro')
    updated = updated.replace('https://beachlab.org', 'https://arroyo.ing')
    updated = updated.replace('a <a href="https://arroyo.ing">Arroyo Ingenieurbüro</a> project',
                              'an <a href="https://arroyo.ing">Arroyo Ingenieurbüro</a> project')
    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/var/www/orbita.you')
    parser.add_argument('--backup', required=True)
    args = parser.parse_args()
    root = Path(args.root)
    backup = Path(args.backup)
    assert not backup.exists(), 'Use a fresh backup directory'
    changes = []
    for path in root.rglob('*.html'):
        before = path.read_text()
        after = transform(before)
        if before == after:
            continue
        assert not path.with_name(path.name + '.gz').exists(), 'Review precompressed HTML first'
        assert not path.with_name(path.name + '.br').exists(), 'Review precompressed HTML first'
        changes.append((path, after))
    backup.mkdir(parents=True, mode=0o700)
    for path, after in changes:
        relative = path.relative_to(root)
        saved = backup / relative
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)
        info = path.stat()
        temporary = path.with_name(path.name + '.contact-tmp')
        temporary.write_text(after)
        os.chmod(temporary, info.st_mode & 0o777)
        os.chown(temporary, info.st_uid, info.st_gid)
        temporary.replace(path)
    (backup / 'manifest.json').write_text(json.dumps([str(p.relative_to(root)) for p, _ in changes], indent=2))
    print('Updated', len(changes), 'HTML pages')


if __name__ == '__main__':
    main()
