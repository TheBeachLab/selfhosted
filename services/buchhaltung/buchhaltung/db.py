from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def identity(prefix):
    return prefix + "_" + uuid.uuid4().hex


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, date TEXT NOT NULL, number TEXT,
 state TEXT NOT NULL, data TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 source TEXT UNIQUE, created TEXT NOT NULL, updated TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS invoice_number ON records(number) WHERE kind='invoice' AND number IS NOT NULL;
CREATE INDEX IF NOT EXISTS records_date ON records(date,kind);
CREATE TABLE IF NOT EXISTS contacts (id TEXT PRIMARY KEY, data TEXT NOT NULL, source TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS bank_accounts (id TEXT PRIMARY KEY, name TEXT NOT NULL, currency TEXT NOT NULL, source TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS bank_transactions (
 id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES bank_accounts(id),
 date TEXT NOT NULL, amount INTEGER NOT NULL, purpose TEXT NOT NULL, party TEXT NOT NULL,
 reference TEXT NOT NULL, source TEXT UNIQUE, fingerprint TEXT, occurrence INTEGER,
 classification TEXT NOT NULL DEFAULT 'unreviewed', data TEXT NOT NULL,
 UNIQUE(account_id,fingerprint,occurrence)
);
CREATE INDEX IF NOT EXISTS bank_date ON bank_transactions(date);
CREATE TABLE IF NOT EXISTS payments (
 id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES records(id),
 bank_id TEXT REFERENCES bank_transactions(id), date TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(amount>0), source TEXT UNIQUE,
 reversed_by TEXT UNIQUE, created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS payments_date ON payments(date);
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, filename TEXT NOT NULL,
 media_type TEXT NOT NULL, size INTEGER NOT NULL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS record_documents (
 record_id TEXT NOT NULL REFERENCES records(id), document_id TEXT NOT NULL REFERENCES documents(id),
 role TEXT NOT NULL, PRIMARY KEY(record_id,document_id,role)
);
CREATE TABLE IF NOT EXISTS source_revisions (
 source TEXT NOT NULL, sha256 TEXT NOT NULL, document_id TEXT NOT NULL REFERENCES documents(id),
 imported TEXT NOT NULL, PRIMARY KEY(source,sha256)
);
CREATE TABLE IF NOT EXISTS imports (
 id TEXT PRIMARY KEY, started TEXT NOT NULL, finished TEXT, state TEXT NOT NULL,
 year INTEGER NOT NULL, summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS returns (
 id TEXT PRIMARY KEY, type TEXT NOT NULL, period TEXT NOT NULL, activity TEXT,
 snapshot TEXT NOT NULL, sha256 TEXT NOT NULL, state TEXT NOT NULL, created TEXT NOT NULL,
 receipt_document TEXT REFERENCES documents(id)
);
CREATE TABLE IF NOT EXISTS audit (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
 event TEXT NOT NULL, entity TEXT NOT NULL, payload TEXT NOT NULL,
 previous TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS source_no_update BEFORE UPDATE ON source_revisions BEGIN SELECT RAISE(ABORT,'source is append-only'); END;
CREATE TRIGGER IF NOT EXISTS source_no_delete BEFORE DELETE ON source_revisions BEGIN SELECT RAISE(ABORT,'source is append-only'); END;
CREATE TRIGGER IF NOT EXISTS records_no_delete BEFORE DELETE ON records BEGIN SELECT RAISE(ABORT,'records cannot be deleted'); END;
CREATE TRIGGER IF NOT EXISTS issued_immutable BEFORE UPDATE OF data,date,number,kind ON records
 WHEN OLD.state IN ('issued','reviewed','cancelled')
 BEGIN SELECT RAISE(ABORT,'booked snapshot is immutable'); END;
CREATE TRIGGER IF NOT EXISTS documents_no_update BEFORE UPDATE ON documents BEGIN SELECT RAISE(ABORT,'original is immutable'); END;
CREATE TRIGGER IF NOT EXISTS documents_no_delete BEFORE DELETE ON documents BEGIN SELECT RAISE(ABORT,'original is immutable'); END;
CREATE TRIGGER IF NOT EXISTS payments_no_delete BEFORE DELETE ON payments BEGIN SELECT RAISE(ABORT,'reverse the payment'); END;
CREATE TRIGGER IF NOT EXISTS payment_snapshot BEFORE UPDATE OF record_id,bank_id,date,amount,source ON payments
 BEGIN SELECT RAISE(ABORT,'payment is immutable'); END;
CREATE TRIGGER IF NOT EXISTS bank_snapshot BEFORE UPDATE OF account_id,date,amount,purpose,party,reference,source,data ON bank_transactions
 BEGIN SELECT RAISE(ABORT,'bank original is immutable'); END;
"""


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class Database:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        self.path = root / "buchhaltung.sqlite3"
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO meta VALUES('schema','1')")
            defaults = {
                "settings": {"seller": {}, "vat_method": "unconfirmed", "number_prefix": "BL-{year}-",
                             "next_number": 1, "fiscal_reviewed": False},
                "import_schedule": {"at": "2026-10-12T20:00:00+02:00", "year": 2026},
            }
            for key, value in defaults.items():
                db.execute("INSERT OR IGNORE INTO meta VALUES(?,?)", (key, canonical(value)))
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, factory=Connection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def setting(self, key="settings", db=None):
        if db is not None:
            row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None
        with self.connect() as connection:
            return self.setting(key, connection)

    def set_setting(self, db, key, value):
        db.execute("INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, canonical(value)))

    def audit(self, db, event, entity, payload, actor="fran"):
        last = db.execute("SELECT sha256 FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous = last[0] if last else "0" * 64
        timestamp = now()
        body = canonical(payload)
        digest = hashlib.sha256(canonical([timestamp, actor, event, entity, body, previous]).encode()).hexdigest()
        db.execute("INSERT INTO audit(at,actor,event,entity,payload,previous,sha256) VALUES(?,?,?,?,?,?,?)",
                   (timestamp, actor, event, entity, body, previous, digest))

    def verify_audit(self):
        previous = "0" * 64
        with self.connect() as db:
            rows = db.execute("SELECT * FROM audit ORDER BY seq").fetchall()
            for row in rows:
                expected = hashlib.sha256(canonical([row["at"], row["actor"], row["event"], row["entity"],
                                                     row["payload"], previous]).encode()).hexdigest()
                if row["previous"] != previous or row["sha256"] != expected:
                    raise ValueError("Audit chain verification failed.")
                previous = row["sha256"]
        return {"events": len(rows), "head": previous}
