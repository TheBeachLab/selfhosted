#!/usr/bin/env python3
"""Reviewed, integrity-pinned npm security backports. Run on a stopped/private tree."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import urllib.request

# Exact vendor npm dist.integrity values, reviewed 2026-10-26. Keep majors separate.
PATCHES = {
    ("body-parser", 1): ("1.20.9", "FISIQxV5u91Y9gvuFq3q/tA/qTqLJn3AhRcEvyozyhJTh5OBFFtv827AdHU7Rbyct4r+Ba1/99oFa1Y3yuFsdw=="),
    ("multer", 2): ("2.5.0", "BsqOzYGVq49JcW2IzoSAxeKYRevb+dGGPPWleOR8Lrlk4igwxu1/9pwSXlByhCb7MVZDrNJFC0IBP5/O5nLYRw=="),
    ("undici", 6): ("6.29.1", "EvRlUt/QqAEvXdQeRMYUfwOQsfzpDztykrG2owGEE/rBOBoYv9uF39ZzsNDh4lTFHhTr2XOZjKkYgueD12ZmGA=="),
    ("undici", 8): ("8.12.2", "XtuDWVdqTLr3NAxm2ly9/hU6kUsJOgGh1RASzMBbsw6aWCOaQzHdW+QQDfdERjfJ2V5vL5pRPa4RetO9UfivDg=="),
    ("zod", 4): ("4.6.6", "4UmzQUF5fxvfcYHlbjBmejU+w+hbDnWFx4aS8kBx7nPBHcO2SqPbpAG8snbdg+Xse4pRefR98hgjFgIMCI/UhA=="),
    ("ip-address", 10): ("10.7.4", "DWBMKyeM25D70nrIiTkgQth59/G+naKOTep6huF9j+GmeK3DMD60Zvxg5d5qQnz+38AHgou6ean2LECX+lrKDg=="),
    ("brace-expansion", 5): ("5.0.12", "YovQ3rzhaLMIrDjNDMkNS01tea93qhEhG5xy8f6+R0l+dw3Ki+5sCoIoI942iuLZTHWogWktgwVDhU09iNEimQ=="),
    ("postcss-selector-parser", 7): ("7.1.6", "7qASPzhKF2l2KLboRZux8CCTRMdGiV08vWmyKzPz22qZ7ZjQBOeY7rNzNoCLSUiftJ7HUq0GERHmxw/t0dCdMw=="),
}


def version(value):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value)
    return tuple(map(int, match.groups())) if match else None


def manifests(root, transaction=False):
    if not transaction and (root / ".security-backport-in-progress").exists():
        raise ValueError("Interrupted security backport; restore the protected package backup")
    for directory, children, files in os.walk(root, followlinks=False):
        if any(n.endswith((".security-old", ".security-new")) for n in children):
            raise ValueError("Unfinished package replacement in " + str(directory))
        children[:] = [n for n in children if not Path(directory, n).is_symlink()]
        if "package.json" in files:
            p = Path(directory, "package.json")
            if not p.is_symlink():
                yield p, json.loads(p.read_text())


def pending(root):
    changes = []
    for path, data in manifests(root):
        current = version(data.get("version", ""))
        target = PATCHES.get((data.get("name"), current[0])) if current else None
        if target and current < version(target[0]):
            changes.append((path.parent, data, target))
    return changes


def unpack(raw, destination, expected_name, expected_version, old):
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            parts = Path(member.name).parts
            if not parts or parts[0] != "package" or ".." in parts or member.name.startswith("/"):
                raise ValueError("Unsafe npm archive path")
            if not (member.isdir() or member.isfile()):
                raise ValueError("Links/devices in npm archive are not accepted")
        archive.extractall(destination)
    package = destination / "package"
    metadata = json.loads((package / "package.json").read_text())
    if (metadata.get("name"), metadata.get("version")) != (expected_name, expected_version):
        raise ValueError("Unexpected package identity")
    for field in ("dependencies", "optionalDependencies", "peerDependencies"):
        if metadata.get(field, {}) != old.get(field, {}):
            raise ValueError("Dependency contract changed: " + field)
    return package


def apply(root, cache):
    changes = pending(root)
    replacements = []
    # Validate every download and dependency contract before editing any package.
    with tempfile.TemporaryDirectory(prefix="node-security-") as temporary:
        temporary = Path(temporary)
        for index, (path, old, (target, integrity)) in enumerate(changes):
            name = old["name"]
            filename = name + "-" + target + ".tgz"
            cached = cache / filename if cache else None
            if cached and cached.exists():
                raw = cached.read_bytes()
            else:
                url = "https://registry.npmjs.org/" + name + "/-/" + filename
                with urllib.request.urlopen(url, timeout=60) as response:
                    raw = response.read(25 * 1024 * 1024 + 1)
            if len(raw) > 25 * 1024 * 1024 or base64.b64encode(hashlib.sha512(raw).digest()).decode() != integrity:
                raise ValueError("npm tarball integrity mismatch: " + filename)
            if cached:
                cache.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(raw)
            target_dir = temporary / str(index)
            target_dir.mkdir()
            package = unpack(raw, target_dir, name, target, old)
            replacements.append((path, old, target, package))
        # These backports keep library dependency maps unchanged. Preserve nested
        # resolutions, and update only exact consumer pins for replaced versions.
        pins = {(old["name"], old["version"]): target for _, old, target, _ in replacements}
        marker = root / ".security-backport-in-progress"
        if replacements:
            with marker.open("x") as stream:
                stream.write("Restore the protected package backup if this transaction is interrupted.\n")
        for path, old, target, package in replacements:
            nested = path / "node_modules"
            if nested.exists():
                shutil.copytree(nested, package / "node_modules", symlinks=True)
            incoming = path.with_name("." + path.name + ".security-new")
            previous = path.with_name("." + path.name + ".security-old")
            if incoming.exists() or previous.exists():
                raise ValueError("Unfinished prior replacement: " + str(path))
            shutil.copytree(package, incoming, symlinks=True)
            path.rename(previous)
            try:
                incoming.rename(path)
            except BaseException:
                previous.rename(path)
                raise
            shutil.rmtree(previous)
            print(str(path.relative_to(root)) + ": " + old["version"] + " -> " + target)
        for path, data in manifests(root, transaction=True):
            changed = False
            for field in ("dependencies", "optionalDependencies"):
                for name, spec in data.get(field, {}).items():
                    replacement = pins.get((name, spec))
                    if replacement:
                        data[field][name] = replacement
                        changed = True
            if changed:
                path.write_text(json.dumps(data, indent=2) + "\n")
        if replacements:
            marker.unlink()
    if pending(root):
        raise ValueError("Security backport did not complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if not (root / "package.json").is_file():
        parser.error("Expected an installed npm application root")
    if args.apply:
        apply(root, args.cache)
        return 0
    changes = pending(root)
    for path, old, (target, _) in changes:
        print(str(path.relative_to(root)) + ": " + old["name"] + " " + old["version"] + " -> " + target)
    return 10 if changes else 0


if __name__ == "__main__":
    raise SystemExit(main())
