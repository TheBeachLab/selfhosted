#!/usr/bin/env python3
"""Install verified official KoSIT artifacts. No third-party invoice SaaS.

Release: https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/tag/v2026-08-31
SHA-256 below was computed from the official downloads on 2026-10-12.
"""
import argparse
import hashlib
import io
from pathlib import Path
from urllib.request import Request, urlopen
import zipfile

ARTIFACTS = [
    ("validator.jar", "https://repo1.maven.org/maven2/org/kosit/validator/1.6.3/validator-1.6.3-standalone.jar", "799e64befca97d4080e03608c80b85dd5a5ecc5f4ae4f35d1116ec2855b9a7c9"),
    ("configuration.zip", "https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/download/v2026-08-31/xrechnung-3.0.2-validator-configuration-2026-08-31.zip", "2530cd107c414511c5d0462ec10f886910395abfca820db82e83d70bf01221a8"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parent / "vendor/xrechnung")
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    for name, url, expected in ARTIFACTS:
        path = args.destination / name
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            raw = path.read_bytes()
        else:
            with urlopen(Request(url, headers={"User-Agent":"BeachLab-Buchhaltung/0.1"}), timeout=45) as response:
                raw = response.read()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise SystemExit("Official artifact checksum differs; inspect before updating the pin.")
            path.write_bytes(raw)
        if name.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if any(Path(n).is_absolute() or ".." in Path(n).parts for n in archive.namelist()):
                    raise SystemExit("Unsafe archive path.")
                archive.extractall(args.destination)
    print("KoSIT Validator 1.6.3 / XRechnung 3.0.2 configuration v2026-08-31: checksums verified.")


if __name__ == "__main__":main()
