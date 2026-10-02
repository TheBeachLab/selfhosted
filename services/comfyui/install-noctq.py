#!/usr/bin/env python3
"""Download pinned Noct Q V4 weights with hf; verify before placing in ComfyUI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def verify(path, entry):
    if path.stat().st_size != entry["size"]:
        raise RuntimeError(f"Unexpected size: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != entry["sha256"]:
        raise RuntimeError(f"SHA-256 mismatch: {path}")
    print(f"Verified {path.name}: {digest.hexdigest()}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfyui", type=Path, default=Path("/opt/comfyui"))
    parser.add_argument("--hf", default="hf")
    args = parser.parse_args()
    source = Path(__file__).resolve().parent
    manifest = json.loads((source / "noctq-models.json").read_text())
    models = args.comfyui / "models"
    stage = models / ".noctq-download"
    stage.mkdir(parents=True, exist_ok=True)
    missing_bytes = sum(item["size"] for item in manifest["files"]
                        if not (models / item["destination"]).exists()
                        and not (stage / item["repo"].replace("/", "--") / item["file"]).exists())
    if shutil.disk_usage(stage).free < missing_bytes + 5 * 1024**3:
        raise RuntimeError("Not enough disk space for weights and a 5 GiB margin")
    for item in manifest["files"]:
        destination = models / item["destination"]
        if destination.exists():
            verify(destination, item)
            continue
        repo_stage = stage / item["repo"].replace("/", "--")
        print(f"Downloading {item['repo']}/{item['file']}", flush=True)
        subprocess.run([args.hf, "download", item["repo"], item["file"],
                        "--revision", item["revision"], "--local-dir", str(repo_stage),
                        "--max-workers", "2"], check=True)
        downloaded = repo_stage / item["file"]
        verify(downloaded, item)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Same filesystem: publish the verified file without replacing an existing one.
        os.link(downloaded, destination)
        downloaded.unlink()
    info = args.comfyui / "user/default/model-info/NoctQ-V4"
    info.mkdir(parents=True, exist_ok=True)
    for name in ["noctq-models.json", "NoctQ-LICENSE.txt", "NoctQ-NOTICE.txt"]:
        target = info / name
        if target.exists() and target.read_bytes() != (source / name).read_bytes():
            raise RuntimeError(f"Refusing to replace different metadata: {target}")
        shutil.copy2(source / name, target)
    print("All three pinned model files installed and verified.", flush=True)


if __name__ == "__main__":
    main()
