"""Streaming SHA-256 for backup scripts on the server's Python 3.10."""

import argparse
import hashlib
from os import PathLike
from pathlib import Path
import sys
from typing import Optional, Sequence, Union


def file_sha256(path: Union[str, PathLike[str]]) -> str:
    """Return a file's SHA-256 hex digest, reading at most 1 MiB at a time."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Calculate a file's SHA-256.")
    parser.add_argument("file", type=Path)
    arguments = parser.parse_args(argv)
    try:
        checksum = file_sha256(arguments.file)
    except OSError as error:
        print("selfhosted_hash: " + str(error), file=sys.stderr)
        return 1
    print(checksum + "  " + str(arguments.file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
