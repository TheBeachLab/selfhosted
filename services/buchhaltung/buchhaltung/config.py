from dataclasses import dataclass
import base64
import os
from pathlib import Path


@dataclass(frozen=True)
class Config:
    data: Path
    origin: str
    proxy_secret: str
    document_key: bytes
    owner: str = "fran"
    dist: Path = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    validator: Path = Path("/opt/buchhaltung/vendor/xrechnung")

    @classmethod
    def environment(cls):
        # No insecure dev fallback. Tests pass an explicit isolated Config.
        secret = os.environ.get("BUCHHALTUNG_PROXY_SECRET", "")
        key = os.environ.get("BUCHHALTUNG_DOCUMENT_KEY", "")
        if len(secret) < 32:
            raise RuntimeError("Missing private proxy credential.")
        try:
            decoded = base64.b64decode(key, validate=True)
        except ValueError:
            raise RuntimeError("Invalid document encryption key.") from None
        if len(decoded) != 32:
            raise RuntimeError("Missing 256-bit document encryption key.")
        return cls(Path(os.environ.get("BUCHHALTUNG_DATA", "/var/lib/buchhaltung")),
                   os.environ.get("BUCHHALTUNG_ORIGIN", "https://buchhaltung.beachlab.org"),
                   secret, decoded,
                   validator=Path(os.environ.get("BUCHHALTUNG_VALIDATOR", "/opt/buchhaltung/vendor/xrechnung")))
