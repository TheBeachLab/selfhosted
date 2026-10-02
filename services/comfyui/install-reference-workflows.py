#!/usr/bin/env python3
"""Install Noct Q reference editors and verify their pinned public examples."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request


def publish(data, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != data:
            raise RuntimeError(f'Refusing to replace a different file: {target}')
        return
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as staged:
        staged.write(data)
        name = Path(staged.name)
    try:
        os.chmod(name, 0o644)
        os.link(name, target)
    finally:
        name.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--comfyui', type=Path, default=Path('/opt/comfyui'))
    parser.add_argument('--asset-cache', type=Path, help='Optional folder containing the example images')
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    manifest = json.loads((source / 'noctq-reference-assets.json').read_text())
    for role, item in manifest['assets'].items():
        target = args.comfyui / 'input' / item['destination']
        cached = args.asset_cache / item['file'] if args.asset_cache else None
        if target.exists():
            data = target.read_bytes()
        elif cached and cached.exists():
            data = cached.read_bytes()
        else:
            with urllib.request.urlopen(item['source'], timeout=60) as response:
                data = response.read(item['size'] + 1)
        if len(data) != item['size'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise RuntimeError(f'Example size/hash mismatch: {role} ({target})')
        publish(data, target)
        print(f'Verified {role}: {target}', flush=True)
    info = args.comfyui / 'user/default/model-info/NoctQ-References'
    publish((source / 'noctq-reference-assets.json').read_bytes(), info / 'noctq-reference-assets.json')
    for item in manifest['workflows']:
        publish((source / 'workflows' / item['ui']).read_bytes(),
                args.comfyui / 'user/default/workflows/NoctQ-Edit' / item['ui'])
        publish((source / 'workflows' / item['api']).read_bytes(), info / item['api'])
    print('Installed All, Face, Pose and Clothing reference editors. No extra nodes or models.', flush=True)


if __name__ == '__main__':
    main()
