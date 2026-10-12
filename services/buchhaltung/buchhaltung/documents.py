import hashlib
import os
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .db import identity, now

MAX_DOCUMENT = 24 * 1024 * 1024
ALLOWED = {"application/pdf", "application/xml", "image/png", "image/jpeg", "application/json", "text/csv"}


def media_type(data):
    head = data.lstrip()
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"<"):
        from defusedxml.ElementTree import fromstring
        fromstring(data)  # Reject DTDs/entities and malformed XML before storing.
        return "application/xml"
    raise ValueError("Solo PDF, XML, PNG o JPEG; el contenido debe corresponder al formato.")


class Documents:
    def __init__(self, config, database):
        self.root = config.data / "documents"
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.key = config.document_key
        self.database = database

    def store(self, db, data: bytes, filename: str, media: str, record_id=None, role="original"):
        if not data or len(data) > MAX_DOCUMENT or media not in ALLOWED:
            raise ValueError("Documento vacío, no permitido o mayor de 24 MB.")
        digest = hashlib.sha256(data).hexdigest()
        row = db.execute("SELECT id FROM documents WHERE sha256=?", (digest,)).fetchone()
        if row:
            document_id = row[0]
        else:
            document_id = identity("doc")
            nonce = os.urandom(12)
            sealed = b"BLD1" + nonce + AESGCM(self.key).encrypt(nonce, data, digest.encode())
            # Atomic file replacement; an interrupted transaction can leave an orphan,
            # but never a half-written original or a missing committed document.
            fd, temp = tempfile.mkstemp(prefix=".new-", dir=self.root)
            try:
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as output:
                    output.write(sealed)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temp, self.root / (digest + ".enc"))
                dir_fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?)",
                       (document_id, digest, Path(filename).name[:180], media, len(data), now()))
            self.database.audit(db, "document.stored", document_id, {"sha256": digest, "size": len(data), "media": media})
        if record_id:
            db.execute("INSERT OR IGNORE INTO record_documents VALUES(?,?,?)", (record_id, document_id, role))
        return document_id

    def read(self, document_id):
        with self.database.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if not row:
            raise KeyError("Documento no encontrado.")
        sealed = (self.root / (row["sha256"] + ".enc")).read_bytes()
        if sealed[:4] != b"BLD1":
            raise ValueError("Formato de archivo cifrado no reconocido.")
        data = AESGCM(self.key).decrypt(sealed[4:16], sealed[16:], row["sha256"].encode())
        if len(data) != row["size"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("La integridad del original no coincide.")
        return dict(row), data

    def verify_all(self):
        with self.database.connect() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM documents")]
        for document_id in ids:
            self.read(document_id)
        return len(ids)
