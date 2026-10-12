from collections import Counter
from datetime import date, datetime
import csv
import hashlib
import io
import json
import re

from defusedxml.ElementTree import fromstring

from .db import canonical, identity
from .models import cents


def bank_date(value):
    value = str(value).strip()
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value[:10], pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError("Fecha bancaria no reconocida: usa AAAA-MM-DD o DD.MM.AAAA.")


def csv_rows(raw):
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";" if ";" in text.splitlines()[0] else ",")
    aliases = {"date": ("date", "Fecha", "Buchungstag", "Buchungsdatum", "Datum"),
               "amount": ("amount", "Importe", "Betrag"),
               "purpose": ("purpose", "Concepto", "Verwendungszweck"),
               "party": ("party", "Nombre", "Beguenstigter/Zahlungspflichtiger", "Begünstigter/Zahlungspflichtiger"),
               "reference": ("reference", "Referencia", "EndToEndId", "Transaktions-ID")}
    headers = reader.fieldnames or []
    fields = {key: next((name for name in names if name in headers), None) for key, names in aliases.items()}
    if not fields["date"] or not fields["amount"]:
        raise ValueError("CSV: faltan columnas date/Fecha/Buchungstag y amount/Importe/Betrag.")
    rows = []
    for row in reader:
        number = row[fields["amount"]].strip().replace(" ", "")
        if "," in number:
            if "." in number and number.rfind(".") > number.rfind(","):
                number = number.replace(",", "")
            else:
                number = number.replace(".", "").replace(",", ".")
        if not re.fullmatch(r"[+-]?\d+(?:\.\d{1,2})?",number):
            raise ValueError("Importe CSV ambiguo: usa decimales con hasta dos cifras, por ejemplo -1234,56.")
        value = {key: str(row.get(field, "") or "").strip() if field else "" for key, field in fields.items()}
        value.update(date=bank_date(value["date"]), amount=cents(number))
        if not value["amount"]:
            raise ValueError("Un movimiento bancario tiene importe cero.")
        rows.append(value)
    return rows


def camt_rows(raw):
    root = fromstring(raw)
    ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
    if not root.tag.endswith("Document"):
        raise ValueError("No es un documento CAMT.")
    def value(element, path):
        node = element.find("/".join(ns + part for part in path.split("/")))
        return (node.text or "").strip() if node is not None else ""
    rows = []
    for entry in root.iter(ns + "Ntry"):
        amount = entry.find(ns + "Amt")
        if amount is None or amount.get("Ccy") != "EUR":
            raise ValueError("CAMT: solo movimientos EUR; convierte otros importes con evidencia del cambio.")
        status = value(entry, "Sts/Cd") or value(entry, "Sts")
        if status and status != "BOOK":
            continue  # Never book a pending bank entry.
        detail = entry.find(".//" + ns + "TxDtls")
        text = " / ".join((node.text or "") for node in entry.iter(ns + "Ustrd"))
        party = ""
        if detail is not None:
            party = value(detail, "RltdPties/Cdtr/Nm") or value(detail, "RltdPties/Dbtr/Nm")
        rows.append({"date": bank_date(value(entry, "BookgDt/Dt") or value(entry, "BookgDt/DtTm")),
                     "amount": cents(amount.text) * (-1 if value(entry, "CdtDbtInd") == "DBIT" else 1),
                     "purpose": text[:4000], "party": party[:160],
                     "reference": value(entry, "AcctSvcrRef") or value(entry, "NtryRef")})
    if not rows:
        raise ValueError("El CAMT no contiene movimientos contabilizados.")
    return rows


def import_bank(database, documents, account_id, raw, filename):
    if not raw or len(raw) > 24 * 1024 * 1024:
        raise ValueError("Archivo vacío o mayor de 24 MB.")
    is_xml = raw.lstrip().startswith(b"<")
    rows = camt_rows(raw) if is_xml else csv_rows(raw)
    if len(rows) > 20000:
        raise ValueError("Divide extractos de más de 20 000 movimientos.")
    counts = Counter()
    added = 0
    with database.transaction() as db:
        account = db.execute("SELECT * FROM bank_accounts WHERE id=?", (account_id,)).fetchone()
        if not account or account["currency"] != "EUR":
            raise ValueError("Selecciona una cuenta EUR.")
        document_id = documents.store(db, raw, filename, "application/xml" if is_xml else "text/csv")
        for row in rows:
            # Identical same-day transactions remain distinct using multiplicity.
            # With no bank reference, overlapping exports of a subset of identical
            # entries cannot be distinguished; expose this limitation in the UI.
            fingerprint = hashlib.sha256(canonical(row).encode()).hexdigest()
            counts[fingerprint] += 1
            cursor = db.execute("INSERT OR IGNORE INTO bank_transactions(id,account_id,date,amount,purpose,party,reference,fingerprint,occurrence,data) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                (identity("bank"), account_id, row["date"], row["amount"], row["purpose"], row["party"], row["reference"], fingerprint, counts[fingerprint], canonical(row)))
            added += cursor.rowcount
        database.audit(db, "bank.imported", account_id, {"rows": len(rows), "added": added, "document": document_id})
    return {"rows": len(rows), "added": added, "duplicates": len(rows) - added}
