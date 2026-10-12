import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile
from dataclasses import replace

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .config import Config
from .db import Database, canonical
from .documents import Documents
from .ledger import Ledger
from .sevdesk import Importer, ReadOnlyClient


def load_environment(path):
    if path:
        location = Path(path)
        if location.stat().st_mode & 0o007:
            raise SystemExit("Private env must not be readable by others.")
        for line in location.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value.strip().strip('"').strip("'")


def backup(config, database, documents, destination):
    """SQLite online backup plus encrypted originals, with a restored integrity check.

    Restore key is separate from the archive. Off-host copying is an operator step;
    a local archive alone is not disaster recovery.
    """
    destination = Path(destination)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="backup-", dir=config.data) as temp:
        snapshot = Path(temp) / "buchhaltung.sqlite3"
        with database.connect() as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
        with sqlite3.connect(snapshot) as restored:
            if restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup database integrity failed.")
            ids = [row[0] for row in restored.execute("SELECT id FROM documents")]
        for document_id in ids:
            documents.read(document_id)
        archive_path = Path(temp) / "snapshot.tar.gz"
        with tarfile.open(archive_path, mode="w:gz") as tar:
            tar.add(snapshot, arcname="buchhaltung.sqlite3")
            # Only files referred to by the consistent database snapshot.
            with sqlite3.connect(snapshot) as restored:
                hashes = [row[0] for row in restored.execute("SELECT sha256 FROM documents")]
            for digest in hashes:
                tar.add(config.data / "documents" / (digest + ".enc"), arcname="documents/" + digest + ".enc")
        nonce = os.urandom(12)
        encryptor = Cipher(algorithms.AES(config.document_key),modes.GCM(nonce)).encryptor()
        encryptor.authenticate_additional_data(b"buchhaltung-backup-v2")
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output_file, archive_path.open('rb') as source:
            output_file.write(b"BLB2"+nonce)
            while chunk := source.read(1024*1024):
                output_file.write(encryptor.update(chunk))
            output_file.write(encryptor.finalize())
            output_file.write(encryptor.tag)
            output_file.flush()
            os.fsync(output_file.fileno())
        restored = restore(config, destination, Path(temp)/"restored")
    digest = hashlib.sha256()
    with destination.open('rb') as source:
        while chunk := source.read(1024*1024):digest.update(chunk)
    return {"path": str(destination), "documents": len(ids), "sha256": digest.hexdigest(), "verified": True, "restore": restored}


def restore(config, archive, destination):
    """Restore into a NEW isolated directory; never replace a live ledger."""
    destination = Path(destination)
    if destination.exists() or destination.resolve() == config.data.resolve():
        raise ValueError("La restauración exige un directorio nuevo fuera de los datos activos.")
    destination.mkdir(mode=0o700,parents=True)
    with tempfile.TemporaryDirectory(prefix="restore-",dir=config.data) as temp:
        opened=Path(temp)/"opened.tar.gz"
        with Path(archive).open('rb') as source:
            header=source.read(16)
            if len(header)!=16 or header[:4]!=b'BLB2':
                raise ValueError("Formato de backup no reconocido.")
            source.seek(-16,2);tag=source.read(16)
            remaining=source.tell()-32
            source.seek(16)
            decryptor=Cipher(algorithms.AES(config.document_key),modes.GCM(header[4:],tag)).decryptor()
            decryptor.authenticate_additional_data(b"buchhaltung-backup-v2")
            with opened.open('wb') as target:
                while remaining:
                    chunk=source.read(min(remaining,1024*1024))
                    if not chunk:raise ValueError("Backup truncado.")
                    target.write(decryptor.update(chunk));remaining-=len(chunk)
                target.write(decryptor.finalize())
        with tarfile.open(opened,'r:gz') as tar:
            import re
            for member in tar.getmembers():
                if not member.isfile() or not (member.name=='buchhaltung.sqlite3' or re.fullmatch(r'documents/[a-f0-9]{64}\.enc',member.name)):
                    raise ValueError("Ruta no permitida en el backup.")
                path=destination/member.name
                path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                path.write_bytes(tar.extractfile(member).read());path.chmod(0o600)
    restored=Database(destination)
    with restored.connect() as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('La copia restaurada no supera SQLite integrity_check.')
        records=db.execute('SELECT COUNT(*) FROM records').fetchone()[0]
    return {"records":records,"documents":Documents(replace(config,data=destination),restored).verify_all(),"audit":restored.verify_audit()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file")
    commands = parser.add_subparsers(dest="command", required=True)
    migration = commands.add_parser("import-sevdesk")
    migration.add_argument("--year", type=int, default=2026)
    migration.add_argument("--accept-cost-centre", action="append", default=[], metavar="VOUCHER_ID:CENTRE_ID",
                           help="Accept an explicitly authorized centre change only when financial data/payments match.")
    migration.add_argument("--accept-source-metadata", action="append", default=[], metavar="VOUCHER_ID:SHA256",
                           help="Copy a verified source taxRule/comment revision; keep tax treatment unclassified and cash identical.")
    classification = commands.add_parser("classify-imported")
    classification.add_argument("--record-id", required=True)
    classification.add_argument("--classification", choices=("private", "tax_refund"), required=True)
    classification.add_argument("--reason", required=True)
    commands.add_parser("verify")
    commands.add_parser("init-profile")
    archive = commands.add_parser("backup")
    archive.add_argument("--output", required=True)
    recovery=commands.add_parser("restore")
    recovery.add_argument("--archive",required=True)
    recovery.add_argument("--destination",required=True)
    args = parser.parse_args()
    load_environment(args.env_file)
    os.umask(0o077)
    config = Config.environment()
    database, documents = Database(config.data), None
    documents = Documents(config, database)
    if args.command == "init-profile":
        client = ReadOnlyClient(os.environ.get("SEVDESK_API_KEY"))
        try:
            clients, countries = client.list("SevClient"), client.list("StaticCountry")
        finally:
            client.close()
        if len(clients) != 1:
            raise ValueError("No se puede elegir el emisor automáticamente: varios o ningún SevClient.")
        row = clients[0]
        country_id = str((row.get("addressCountry") or {}).get("id", ""))
        country = next((item.get("code") or item.get("code2") for item in countries if str(item["id"]) == country_id), "")
        country = str(country or "").upper()
        if country != "DE":
            raise ValueError("El emisor no está confirmado en Alemania; revisa el perfil antes de configurar fiscalidad alemana.")
        with database.transaction() as db:
            settings = database.setting(db=db)
            if settings.get("seller"):
                raise ValueError("El perfil ya existe; no se sobrescribe.")
            settings["seller"] = {"name": row.get("name") or "", "street": row.get("addressStreet") or "",
                                  "city": row.get("addressCity") or "", "postcode": row.get("addressZip") or "", "country": country,
                                  "email": row.get("contactEmail") or "", "phone": row.get("contactPhone") or "", "vat_id": row.get("vatNumber") or "",
                                  "tax_number": row.get("taxNumber") or "", "iban": row.get("bankIban") or "", "buyer_reference": ""}
            database.set_setting(db,"settings",settings)
            database.audit(db,"seller.profile_initialized","settings",{"source":"sevdesk/SevClient","history_imported":False,"fiscal_reviewed":False},"sevdesk-import")
        print(canonical({"profile_initialized":True,"history_imported":False,"fiscal_reviewed":False}))
    elif args.command == "import-sevdesk":
        import re
        approvals = {}
        metadata_approvals = {}
        for value in args.accept_cost_centre:
            if not re.fullmatch(r"\d+:\d+", value):
                raise ValueError("Usa --accept-cost-centre VOUCHER_ID:CENTRE_ID.")
            voucher, centre = value.split(":")
            approvals["sevdesk/Voucher/" + voucher] = centre
        for value in args.accept_source_metadata:
            if not re.fullmatch(r"\d+:[a-f0-9]{64}", value):
                raise ValueError("Usa --accept-source-metadata VOUCHER_ID:SHA256 verificado.")
            voucher, digest = value.split(":")
            metadata_approvals["sevdesk/Voucher/" + voucher] = digest
        client = ReadOnlyClient(os.environ.get("SEVDESK_API_KEY"))
        try:
            result = Importer(config, database, documents, Ledger(database, documents), client, approvals, metadata_approvals).run(args.year)
        finally:
            client.close()
        print(canonical(result))
        raise SystemExit(0 if result["state"] == "complete" else 2)
    elif args.command == "classify-imported":
        record = Ledger(database, documents).classify_imported(args.record_id, args.classification, args.reason)
        print(canonical({"id": record["id"], "kind": record["kind"], "state": record["state"], "revision": record["revision"], "total": record["total"], "paid": record["paid"]}))
    elif args.command == "verify":
        with database.connect() as db:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError("Database integrity failed.")
            counts = {table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in ("records", "bank_transactions", "payments", "contacts", "documents", "source_revisions")}
        print(canonical({"database": integrity, "counts": counts, "audit": database.verify_audit(), "documents_verified": documents.verify_all()}))
    elif args.command == "backup":
        print(canonical(backup(config, database, documents, args.output)))
    elif args.command == "restore":
        print(canonical(restore(config,args.archive,args.destination)))


if __name__ == "__main__":
    main()
