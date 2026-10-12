"""Read-only, resumable migration. Allowed network verbs: GET only.

Public specification: https://api.sevdesk.de/ (downloaded 2026-10-12).
Document/download and transaction-log shapes were additionally observed through
authenticated GET requests on 2026-10-12; these legacy endpoints are not listed
in the current public OpenAPI file. Preserve raw responses; refuse silent guesses.
"""
import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import time

import httpx

from .bank import bank_date
from .db import canonical, identity, now
from .documents import media_type
from .models import ACTIVITIES, cents

BASE = "https://my.sevdesk.de/api/v1/"
MODELS = {"Invoice", "InvoicePos", "Voucher", "VoucherPos", "CreditNote", "CreditNotePos", "Contact",
          "ContactAddress", "CommunicationWay", "CostCentre", "CheckAccount", "CheckAccountTransaction", "SevClient", "StaticCountry"}
PATH = re.compile(r"^(?:" + "|".join(MODELS) + r")(?:/\d+(?:/(?:getPdf|getXml|getCheckAccountTransactions|getCheckAccountTransactionLogs))?)?$|^Document/\d+(?:/download)?$")


class SourceError(ValueError):
    pass


class ReadOnlyClient:
    def __init__(self, token):
        if not token:
            raise SourceError("Falta SEVDESK_API_KEY en el entorno privado del NUC.")
        self.client = httpx.Client(base_url=BASE, headers={"Authorization": token,
                                  "User-Agent": "BeachLab-Buchhaltung/0.1 migration-readonly",
                                  "Accept": "application/json"}, timeout=45, follow_redirects=False)

    def close(self):
        self.client.close()

    def get(self, path, params=None):
        if not PATH.fullmatch(path):
            raise SourceError("Ruta fuera de la lista de lectura permitida.")
        for attempt in range(4):
            response = self.client.get(path, params=params)
            if response.status_code not in (429, 502, 503, 504):
                break
            time.sleep(min(2 ** attempt, 8))
        if response.status_code != 200:
            raise SourceError(f"GET {path}: HTTP {response.status_code}")
        result = response.json()
        if not isinstance(result, dict) or "objects" not in result:
            raise SourceError(f"GET {path}: formato inesperado.")
        return result

    def list(self, model, params=None):
        if model not in MODELS:
            raise SourceError("Modelo no permitido.")
        values, seen = [], set()
        for offset in range(0, 100000, 100):
            result = self.get(model, {**(params or {}), "limit": 100, "offset": offset, "orderBy": "id", "orderSeq": "ASC", "countAll": "true"})
            page = result["objects"]
            if page is None:
                page = []
            if not isinstance(page, list):
                raise SourceError(f"GET {model}: no devuelve una lista.")
            for item in page:
                key = str(item["id"])
                if key in seen:
                    raise SourceError(f"GET {model}: paginación repite un identificador; no se declara completa.")
                seen.add(key)
                values.append(item)
            if len(page) < 100:
                expected = result.get("total")
                if expected is not None and int(expected) != len(values):
                    raise SourceError(f"GET {model}: el recuento no coincide con total.")
                return values
        raise SourceError("Límite de inventario excedido.")


def object_id(value):
    return str(value.get("id", "")) if isinstance(value, dict) else ""


def source_date(value):
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit() and len(value) > 9):
        return datetime.fromtimestamp(int(value), timezone.utc).date().isoformat()
    return bank_date(value)


def source_amount(obj, name):
    # Foreign currency originals remain untouched. Accounting sums are in the
    # account's home currency; if unavailable, require review of conversion.
    accounting = obj.get(name + "Accounting")
    return abs(cents(accounting if accounting is not None else obj.get(name, 0)))


def download_bytes(result):
    obj = result.get("objects", result)
    if not isinstance(obj, dict):
        raise SourceError("Descarga: formato no reconocido.")
    encoded = obj.get("base64Encoded", obj.get("base64encoded"))
    if encoded is not True:
        raise SourceError("Descarga: el proveedor no confirma base64; no se interpreta como URL.")
    try:
        raw = base64.b64decode(obj["content"], validate=True)
    except (ValueError, KeyError):
        raise SourceError("Descarga: contenido base64 no válido.") from None
    return raw, str(obj.get("filename") or "original")


class Importer:
    def __init__(self, config, database, documents, ledger, client):
        self.config, self.database, self.documents, self.ledger, self.client = config, database, documents, ledger, client
        self.summary = {"counts": {}, "documents": 0, "payments": 0, "errors": [], "source_drift": []}
        self.countries, self.activities, self.contacts = {}, {}, {}
        self.resolved_sources = set()
        self.refreshed_centres, self.refreshed_metadata, self.refreshed_sources = set(), set(), set()

    @staticmethod
    def classification_basis(bundle):
        """Evidence supporting an owner classification, without amount guesses."""
        obj = bundle["object"]
        return (obj.get("creditDebit"), object_id(obj.get("taxRule")),
                [(object_id(p.get("accountDatev")), p.get("taxRate"), p.get("isAsset"))
                 for p in bundle["positions"]])

    @staticmethod
    def source_facts(bundle):
        # Generated timestamps and replacement log IDs do not create a second
        # current version of the same financial facts.
        clean = lambda obj: {k: v for k, v in obj.items() if k not in ("create", "update")}
        logs = sorted((object_id(log.get("checkAccountTransaction")), cents(log.get("amountPaid") or 0),
                       source_date(log.get("bookingDate") or log.get("create")))
                      for log in bundle["payment_logs"] if cents(log.get("amountPaid") or 0))
        return {"object": clean(bundle["object"]), "positions": [clean(p) for p in bundle["positions"]], "payments": logs}

    def sync_payments(self, db, record_id, kind, bundle, digest):
        """One current payment projection; superseded cash rows are audit only.

        Latest sevdesk logs are authoritative. Unchanged bank/date/amount tuples
        reuse the same cash row, even when sevdesk generated a different log ID.
        Changed or removed payments are superseded, never counted twice.
        """
        obj, logs = bundle["object"], bundle["payment_logs"]
        paid = abs(cents(obj.get("paidAmount") or 0))
        direction = 1 if kind in ("invoice", "income", "tax_refund") else -1
        expected, issues, seen = [], [], set()
        for log in logs:
            amount = cents(log.get("amountPaid") or 0)
            if not amount:
                continue
            source = "sevdesk/CheckAccountTransactionLog/" + str(log["id"])
            self.archive(db, source, log, record_id)
            bank_id = "sev_bank_" + object_id(log.get("checkAccountTransaction"))
            bank = db.execute("SELECT * FROM bank_transactions WHERE id=?", (bank_id,)).fetchone()
            if source in seen or amount * direction < 0:
                issues.append("Historial de pagos/reversiones ambiguo en sevdesk.")
            elif not bank or bank["amount"] * direction <= 0 or bank["classification"] == "excluded" or abs(amount)>abs(bank["amount"]):
                issues.append("El movimiento del pago falta o tiene un sentido incompatible.")
            elif source_date(log.get("bookingDate") or log.get("create")) != bank["date"]:
                issues.append("La fecha del pago no coincide con la del movimiento original.")
            else:
                expected.append((source, bank_id, bank["date"], abs(amount)))
            seen.add(source)
        if sum(abs(cents(log.get("amountPaid") or 0)) for log in logs) != paid:
            issues.append("Los logs no cuadran con paidAmount de sevdesk.")
        if paid > source_amount(obj, "sumGross"):
            issues.append("El importe pagado supera el total de sevdesk.")
        if issues:
            expected = []  # Never retain stale reconciliation as current evidence.
        current = [dict(p) for p in db.execute("SELECT * FROM payments WHERE record_id=? AND reversed_by IS NULL", (record_id,))]
        old_mapping = {p["source"]: p["payment_id"] for p in db.execute(
            "SELECT c.* FROM payment_source_current c JOIN payments p ON p.id=c.payment_id WHERE p.record_id=?", (record_id,))}
        db.execute("DELETE FROM payment_source_current WHERE payment_id IN (SELECT id FROM payments WHERE record_id=?)", (record_id,))
        used, mapped, aliases = set(), [], []
        for source, bank_id, date, amount in expected:
            matching = [p for p in current if p["id"] not in used and (p["bank_id"], p["date"], p["amount"]) == (bank_id, date, amount)]
            matching.sort(key=lambda p: (p["id"] != old_mapping.get(source), p["source"] != source, p["id"]))
            if matching:
                payment = matching[0]
                payment_id = payment["id"]
                known = db.execute("SELECT id FROM payments WHERE source=? UNION SELECT payment_id FROM payment_source_aliases WHERE source=?", (source, source)).fetchone()
                if payment["source"] != source and not known:
                    db.execute("INSERT INTO payment_source_aliases VALUES(?,?,?,?,?)", (source, payment_id, payment["source"], digest, now()))
                    aliases.append(source)
            else:
                payment_id = identity("pay")
                # Reused provider IDs may carry corrected amounts/dates. Keep the
                # immutable old row, and map that ID only to its current revision.
                original_source = source
                if db.execute("SELECT 1 FROM payments WHERE source=?", (source,)).fetchone():
                    original_source += "@" + digest + ":" + payment_id
                db.execute("INSERT INTO payments(id,record_id,bank_id,date,amount,source,created) VALUES(?,?,?,?,?,?,?)",
                           (payment_id, record_id, bank_id, date, amount, original_source, now()))
                self.database.audit(db, "payment.source_imported", payment_id,
                                    {"record": record_id, "source": source, "bank": bank_id, "date": date, "amount": amount, "snapshot": digest}, "sevdesk-import")
                self.summary["payments"] += 1
            used.add(payment_id)
            db.execute("INSERT INTO payment_source_current VALUES(?,?,?)", (source, payment_id, digest))
            mapped.append([source, payment_id])
        superseded = [p["id"] for p in current if p["id"] not in used]
        for payment_id in superseded:
            db.execute("UPDATE payments SET reversed_by=? WHERE id=?", (identity("source_superseded"), payment_id))
        if superseded or aliases or old_mapping != dict(mapped):
            self.database.audit(db, "payment.source_projection_refreshed", record_id,
                                {"snapshot": digest, "current": mapped, "superseded": superseded, "aliases": aliases}, "sevdesk-import")
        return sorted(set(issues))

    def originals(self, model, obj, record_id):
        """Select only documents returned by this read as current originals."""
        source = "sevdesk/" + model + "/" + str(obj["id"])
        selected, errors = [], []
        def save(raw, filename, media, role):
            with self.database.transaction() as db:
                doc = self.documents.store(db, raw, filename, media, record_id, role)
            selected.append(doc)
            self.summary["documents"] += 1
        if model in ("Invoice", "CreditNote"):
            try:
                pdf, filename = download_bytes(self.client.get(model + "/" + str(obj["id"]) + "/getPdf", {"preventSendBy": "true"}))
                if media_type(pdf) != "application/pdf":
                    raise SourceError("No se obtuvo un PDF original.")
                save(pdf, filename, "application/pdf", "invoice_pdf")
            except (SourceError, ValueError) as error:
                errors.append(str(error))
            if model == "Invoice":
                try:
                    xml = self.client.get("Invoice/" + str(obj["id"]) + "/getXml")["objects"]
                    if not isinstance(xml, str) or media_type(xml.encode()) != "application/xml":
                        raise SourceError("No se obtuvo XML válido.")
                    save(xml.encode(), (obj.get("invoiceNumber") or str(obj["id"])) + ".xml", "application/xml", "invoice_xml")
                except SourceError as error:
                    if not str(error).endswith(("HTTP 400", "HTTP 404")):
                        errors.append(str(error))
                except ValueError as error:
                    errors.append(str(error))
        elif object_id(obj.get("document")):
            try:
                path = "Document/" + object_id(obj["document"])
                metadata = self.client.get(path)
                raw, filename = download_bytes(self.client.get(path + "/download"))
                with self.database.transaction() as db:
                    self.archive(db, "sevdesk/" + path, metadata)
                save(raw, filename, media_type(raw), "original")
            except (SourceError, ValueError) as error:
                errors.append(str(error))
        else:
            errors.append("Justificante ausente en sevdesk.")
        self.summary["errors"].extend(source + ": " + error for error in errors)
        return sorted(set(selected)), errors

    def archive(self, db, source, payload, record_id=None):
        raw = canonical(payload).encode()
        digest = hashlib.sha256(raw).hexdigest()
        doc_id = self.documents.store(db, raw, source.replace("/", "-") + ".json", "application/json", record_id, "source_json")
        db.execute("INSERT OR IGNORE INTO source_revisions VALUES(?,?,?,?)", (source, digest, doc_id, now()))
        return digest

    def retire_missing(self, model, present):
        """Remove absent source entries from the current projection, not audit."""
        prefix = "sevdesk/" + model + "/"
        with self.database.transaction() as db:
            for record in db.execute("SELECT * FROM records WHERE source LIKE ?", (prefix + "%",)).fetchall():
                if record["source"] in present:
                    continue
                old = json.loads(record["data"])
                if old.get("source_missing"):
                    self.resolved_sources.add(record["source"])
                    continue
                data = {**old, "lines": [], "source_expected_gross": 0, "source_paid_amount": 0,
                        "source_documents": [], "source_snapshot_document": None, "source_missing": True,
                        "source_status": "missing", "source_sync_error": "No aparece en el inventario completo actual de sevdesk."}
                if record["state"] in ("reviewed", "issued", "cancelled"):
                    db.execute("UPDATE records SET state='needs_review' WHERE id=?", (record["id"],))
                db.execute("UPDATE records SET data=?,state='void',number=NULL,revision=revision+1,updated=? WHERE id=?",
                           (canonical(data), now(), record["id"]))
                self.sync_payments(db, record["id"], record["kind"], {"object": {"paidAmount": "0", "sumGross": "0"}, "payment_logs": []}, "missing-from-source")
                self.database.audit(db, "record.absent_from_source", record["id"],
                                    {"source": record["source"], "before": old, "current": "absent"}, "sevdesk-import")
                self.summary.setdefault("source_removed", []).append(record["source"])
                self.resolved_sources.add(record["source"])

    def country(self, source):
        country = self.countries.get(object_id(source), {})
        return str(country.get("code") or country.get("code2") or "").upper()

    def context(self):
        countries = self.client.list("StaticCountry")
        self.countries = {str(row["id"]): row for row in countries}
        centres = self.client.list("CostCentre")
        self.activities = {str(row["id"]): next((key for key, name in ACTIVITIES.items() if row.get("name") == name), None) for row in centres}
        clients = self.client.list("SevClient")
        if len(clients) != 1 or (clients[0].get("defaultCurrency") or "EUR") != "EUR":
            raise SourceError("Se requiere un único SevClient con moneda base EUR; no se convierten importes sin verificar.")
        contacts = self.client.list("Contact")
        addresses = self.client.list("ContactAddress")
        communication = self.client.list("CommunicationWay")
        accounts = self.client.list("CheckAccount")
        with self.database.transaction() as db:
            for model, rows in (("StaticCountry", countries), ("CostCentre", centres), ("SevClient", clients), ("Contact", contacts), ("ContactAddress", addresses), ("CommunicationWay", communication), ("CheckAccount", accounts)):
                for row in rows:
                    archived = dict(row)
                    if model == "CheckAccount":
                        # Banking credentials are not accounting history and are
                        # not needed for CSV/CAMT reconciliation in this app.
                        for field in ("pin", "password", "token", "apiKey"):
                            if field in archived:
                                archived[field] = "[credential omitted]"
                    self.archive(db, "sevdesk/" + model + "/" + str(row["id"]), archived)
                self.summary["counts"][model] = len(rows)
            for row in contacts:
                source = "sevdesk/Contact/" + str(row["id"])
                address = next((item for item in addresses if object_id(item.get("contact")) == str(row["id"])), {})
                email = next((item.get("value", "") for item in communication if object_id(item.get("contact")) == str(row["id"]) and (item.get("type") == "EMAIL" or item.get("key") == "EMAIL")), "")
                party = {"name": row.get("name") or " ".join(filter(None, [row.get("surename"), row.get("familyname")])),
                         "street": address.get("street") or "", "city": address.get("city") or "", "postcode": address.get("zip") or "",
                         "country": self.country(address.get("country")), "email": email,
                         "vat_id": row.get("vatNumber") or "", "tax_number": row.get("taxNumber") or "", "phone": "", "iban": "",
                         "buyer_reference": row.get("buyerReference") or ""}
                self.contacts[str(row["id"])] = party
                # Imported contacts always reflect the latest sevdesk version.
                db.execute("INSERT INTO contacts(id,data,source) VALUES(?,?,?) ON CONFLICT(source) DO UPDATE SET data=excluded.data", ("sev_contact_" + str(row["id"]), canonical(party), source))
            for row in accounts:
                db.execute("INSERT INTO bank_accounts VALUES(?,?,?,?) ON CONFLICT(source) DO UPDATE SET name=excluded.name,currency=excluded.currency", ("sev_account_" + str(row["id"]), row.get("name") or ("Cuenta sevdesk " + str(row["id"])), row.get("currency") or "EUR", "sevdesk/CheckAccount/" + str(row["id"])))
            settings = self.database.setting(db=db)
            if clients and not settings.get("seller"):
                row = clients[0]
                settings["seller"] = {"name": row.get("name") or "", "street": row.get("addressStreet") or "",
                                       "city": row.get("addressCity") or "", "postcode": row.get("addressZip") or "",
                                       "country": self.country(row.get("addressCountry")) or "DE", "email": row.get("contactEmail") or "",
                                       "phone": row.get("contactPhone") or "", "vat_id": row.get("vatNumber") or "",
                                       "tax_number": row.get("taxNumber") or "", "iban": row.get("bankIban") or "", "buyer_reference": ""}
                # The API accountingSystem is not interpreted as Ist/Soll without
                # a verified enum. Require the owner's fiscal confirmation.
                self.database.set_setting(db, "settings", settings)
                self.database.audit(db, "seller.imported", "settings", {"source": "sevdesk/SevClient", "fiscal_reviewed": False}, "sevdesk-import")

    def transaction(self, obj, db):
        source = "sevdesk/CheckAccountTransaction/" + str(obj["id"])
        self.archive(db, source, obj)
        existing = db.execute("SELECT * FROM bank_transactions WHERE source=?", (source,)).fetchone()
        account_id = "sev_account_" + object_id(obj.get("checkAccount"))
        data = {"date": source_date(obj.get("entryDate") or obj.get("valueDate")), "amount": cents(obj["amount"]),
                "purpose": obj.get("paymtPurpose") or "", "party": obj.get("payeePayerName") or "",
                "reference": obj.get("externalId") or obj.get("primaNotaNo") or ""}
        # Only explicit source private status is imported as private. Transfers,
        # deleted/zero transactions stay archived but cannot be booked as income.
        classification = "excluded" if obj.get("deletedAt") or not data["amount"] else "private" if str(obj.get("status")) == "300" else "unreviewed"
        if existing:
            old = json.loads(existing["data"])
            material = lambda row: {k: v for k, v in row.items() if k not in ("update", "create")}
            if material(old) == material(obj):
                classification = existing["classification"]
            projection = (account_id, data["date"], data["amount"], data["purpose"], data["party"], str(data["reference"]), classification, canonical(obj))
            previous = tuple(existing[k] for k in ("account_id", "date", "amount", "purpose", "party", "reference", "classification", "data"))
            if projection != previous:
                db.execute("UPDATE bank_transactions SET account_id=?,date=?,amount=?,purpose=?,party=?,reference=?,classification=?,data=? WHERE id=?",
                           (*projection, existing["id"]))
                self.database.audit(db, "bank.source_refreshed", existing["id"],
                                    {"source": source, "before": old, "after": obj}, "sevdesk-import")
            self.resolved_sources.add(source)
            return existing["id"]
        transaction_id = "sev_bank_" + str(obj["id"])
        db.execute("INSERT INTO bank_transactions(id,account_id,date,amount,purpose,party,reference,source,classification,data) VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (transaction_id, account_id, data["date"], data["amount"], data["purpose"], data["party"], str(data["reference"]), source, classification, canonical(obj)))
        self.database.audit(db, "bank.source_imported", transaction_id, {"source": source}, "sevdesk-import")
        return transaction_id

    def record(self, model, obj, positions, logs, transactions):
        source = "sevdesk/" + model + "/" + str(obj["id"])
        bundle = {"object": obj, "positions": positions, "payment_logs": logs}
        date_field = {"Invoice": "invoiceDate", "Voucher": "voucherDate", "CreditNote": "creditNoteDate"}[model]
        record_date = source_date(obj.get(date_field) or obj.get("create"))
        activity = self.activities.get(object_id(obj.get("costCentre")))
        unsupported = []
        if not activity:
            unsupported.append("Centro de coste sin actividad reconocida.")
        if model == "Invoice":
            kind = "invoice"
        elif model == "CreditNote":
            kind = "credit_note"
            unsupported.append("Abono: conserva el original; requiere integración de rectificaciones.")
        else:
            # Observed expense vouchers use C and negative payment-log amounts.
            kind = "expense" if obj.get("creditDebit") == "C" else "income"
        lines = []
        rule = object_id(obj.get("taxRule"))
        for pos in positions:
            net = source_amount(pos, "sumNet")
            tax = source_amount(pos, "sumTax")
            rate = str(pos.get("taxRate") or "0").split(".")[0]
            normal = rule == "1" or (not rule and obj.get("taxType") == "default")
            tax_code = {"19": "de19", "7": "de7"}.get(rate, "unclassified") if normal else "unclassified"
            asset = str(pos.get("isAsset")).lower() in ("true", "1")
            if asset:
                unsupported.append("Activo de sevdesk: falta importar/verificar su cuadro de amortización.")
            lines.append({"description": pos.get("name") or pos.get("comment") or obj.get("description") or "Leistung / Beleg",
                          "activity": activity or "freiberufler", "net_cents": net, "tax_cents": tax, "tax_code": tax_code,
                          "category": "asset" if asset else "other" if model == "Invoice" else "unclassified", "deduct_percent": 100})
        if not lines:
            lines = [{"description": obj.get("description") or "Beleg", "activity": activity or "freiberufler",
                      "net_cents": source_amount(obj, "sumNet"), "tax_cents": source_amount(obj, "sumTax"),
                      "tax_code": "unclassified", "category": "unclassified", "deduct_percent": 100}]
        expected = source_amount(obj, "sumGross")
        if sum(line["net_cents"] + line["tax_cents"] for line in lines) != expected:
            unsupported.append("Las posiciones no cuadran con el total original (descuento, redondeo o moneda).")
        if (obj.get("currency") or "EUR") != "EUR":
            unsupported.append("Moneda extranjera: verifica conversión a EUR y fecha del cambio.")
        if obj.get("discount") not in (None, "0", 0, "0.0"):
            unsupported.append("Descuento por pronto pago: verifica importes y ajustes de IVA.")
        if obj.get("invoiceType") not in (None, "RE", "WKR"):
            unsupported.append("Tipo de factura especial: verifica anticipos/rectificaciones.")
        party_id = "sev_contact_" + object_id(obj.get("contact")) if object_id(obj.get("contact")) else None
        from datetime import date, timedelta
        due = (date.fromisoformat(record_date) + timedelta(days=int(obj.get("timeToPay") or 14))).isoformat()
        data = {"kind": kind, "date": record_date, "due_date": due if model == "Invoice" else None,
                "service_date": source_date(obj["deliveryDate"]) if obj.get("deliveryDate") else record_date,
                "party_id": party_id, "party_name": obj.get("supplierName") or obj.get("addressName") or "",
                "reference": obj.get("description") or obj.get("invoiceNumber") or obj.get("creditNoteNumber") or "",
                "buyer_reference": obj.get("einvoiceReference") or "", "note": "", "exemption_reason": "", "lines": lines,
                "asset_life_months": None, "asset_start": None, "source_status": str(obj.get("status")),
                "source_currency": obj.get("currency") or "EUR", "source_tax_rule": rule,
                "source_expected_gross": expected, "source_unsupported": "; ".join(sorted(set(unsupported)))}
        data.update(source_cost_centre_id=object_id(obj.get("costCentre")), source_paid_amount=abs(cents(obj.get("paidAmount") or 0)),
                    source_position_ids=[str(p["id"]) for p in positions], source_activity_pending=not bool(activity),
                    source_booking_accounts=[object_id(p.get("accountDatev")) for p in positions])
        digest = hashlib.sha256(canonical(bundle).encode()).hexdigest()
        data["source_bundle_sha256"] = digest
        with self.database.transaction() as db:
            existing = db.execute("SELECT * FROM records WHERE source=?", (source,)).fetchone()
            record_id = existing["id"] if existing else "sev_" + model.lower() + "_" + str(obj["id"])
            if not existing:
                data["source_documents"] = []
                db.execute("INSERT INTO records(id,kind,date,number,state,data,source,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                           (record_id, kind, record_date, obj.get("invoiceNumber") if model == "Invoice" else None,
                            "needs_review", canonical(data), source, now(), now()))
        selected, document_errors = self.originals(model, obj, record_id)
        data["source_documents"] = selected
        with self.database.transaction() as db:
            current = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
            old = json.loads(current["data"])
            accepted = old.get("source_bundle_sha256")
            prior_row = db.execute("SELECT sha256,document_id FROM source_revisions WHERE source=? " +
                                   ("AND sha256=?" if accepted else "ORDER BY imported ASC LIMIT 1"),
                                   (source, accepted) if accepted else (source,)).fetchone()
            prior = json.loads(self.documents.read(prior_row["document_id"])[1]) if prior_row else None
            changed = prior is None or self.source_facts(prior) != self.source_facts(bundle)
            changed = changed or old.get("source_missing", False)
            if "source_documents" in old and selected != old["source_documents"]:
                changed = True
            state = "void" if str(obj.get("hidden", "0")).lower() in ("1", "true") or str(obj.get("status")) == "750" else "needs_review"
            if existing and not changed:
                # Keep reviewed LOCAL tax mappings only while their source basis
                # is unchanged. All money, dates, references and known centres
                # below still come from the latest source, never local edits.
                for new, previous in zip(data["lines"], old["lines"]):
                    for key in ("tax_code", "category", "deduct_percent"):
                        new[key] = previous[key]
                    if not activity:
                        new["activity"] = previous["activity"]
                for key in ("note", "exemption_reason", "asset_life_months", "asset_start", "source_classification_reason", "source_private"):
                    if key in old:
                        data[key] = old[key]
                kind = data["kind"] = current["kind"]
                state = current["state"] if state != "void" else state
                if old.get("source_unsupported") == "":
                    data["source_unsupported"] = ""
                    data["source_activity_pending"] = old.get("source_activity_pending", not bool(activity))
            same_basis = prior is not None and self.classification_basis(prior) == self.classification_basis(bundle)
            simple = all(not line["tax_cents"] and line["category"] != "asset" for line in data["lines"])
            if existing and same_basis and simple and state != "void":
                if current["state"] == "private" and kind == "expense":
                    state, data["source_private"] = "private", True
                    for line in data["lines"]:
                        line["deduct_percent"] = 0
                    if data["source_unsupported"] == "Centro de coste sin actividad reconocida.":
                        data["source_unsupported"] = ""
                if current["kind"] == "tax_refund" and kind in ("income", "tax_refund"):
                    kind = data["kind"] = "tax_refund"
                    for line in data["lines"]:
                        line["tax_code"], line["category"] = "none", "vat_refund"
                    if not activity:
                        data["source_activity_pending"] = True
                        data["source_unsupported"] = "Devolución de IVA: falta un reparto verificado entre actividades."
                if "source_classification_reason" in old:
                    data["source_classification_reason"] = old["source_classification_reason"]
            if changed and prior:
                if object_id(prior["object"].get("costCentre")) != data["source_cost_centre_id"]:
                    self.refreshed_centres.add(source)
                if (object_id(prior["object"].get("taxRule")) != rule or
                        [p.get("comment") for p in prior["positions"]] != [p.get("comment") for p in positions]):
                    self.refreshed_metadata.add(source)
            self.archive(db, source, bundle, record_id)
            data["source_snapshot_document"] = db.execute("SELECT document_id FROM source_revisions WHERE source=? AND sha256=?", (source, digest)).fetchone()[0]
            for transaction in transactions:
                self.transaction(transaction, db)
            payment_errors = self.sync_payments(db, record_id, kind, bundle, digest)
            issues = document_errors + payment_errors
            if sum(line["net_cents"] + line["tax_cents"] for line in data["lines"]) != expected:
                issues.append("Las posiciones no cuadran con el total de sevdesk.")
            data["source_sync_error"] = "; ".join(sorted(set(issues)))
            if issues:
                state = "needs_review" if state != "void" else state
                self.summary["source_drift"].append(source)
                self.summary["errors"].extend(source + ": " + error for error in payment_errors)
            else:
                self.resolved_sources.add(source)
            number = obj.get("invoiceNumber") if model == "Invoice" else None
            updated = old != data or (current["kind"], current["date"], current["number"], current["state"]) != (kind, record_date, number, state)
            if updated:
                # A source projection is reopened before replacing its reviewed
                # local snapshot; the source original itself is never edited.
                if current["state"] in ("reviewed", "issued", "cancelled"):
                    db.execute("UPDATE records SET state='needs_review' WHERE id=?", (record_id,))
                revision = current["revision"] + (1 if existing else 0)
                db.execute("UPDATE records SET data=?,date=?,kind=?,number=?,state=?,revision=?,updated=? WHERE id=?",
                           (canonical(data), record_date, kind, number, state, revision, now(), record_id))
                self.database.audit(db, "record.source_refreshed" if existing else "record.source_imported", record_id,
                                    {"source": source, "snapshot_sha256": digest, "before": old if existing else None, "after": data,
                                     "review_invalidated": bool(changed and current["state"] == "reviewed")}, "sevdesk-import")
                if existing:
                    self.refreshed_sources.add(source)
        return record_id

    def run(self, year):
        schedule = self.database.setting("import_schedule")
        if schedule and datetime.now(timezone.utc) < datetime.fromisoformat(schedule["at"]):
            raise SourceError("La importación está programada para las 20:00; todavía no se ejecuta.")
        lock = open(self.config.data / "sevdesk-import.lock", "a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise SourceError("Ya hay una importación en curso.") from None
        import_id = identity("import")
        try:
            with self.database.transaction() as db:
                db.execute("INSERT INTO imports(id,started,state,year,summary) VALUES(?,?,'running',?,?)", (import_id, now(), year, canonical(self.summary)))
                self.database.audit(db, "import.started", import_id, {"year": year}, "sevdesk-import")
            self.context()
            all_bank = self.client.list("CheckAccountTransaction")
            year_bank = [row for row in all_bank if source_date(row.get("entryDate") or row.get("valueDate"))[:4] == str(year)]
            year_bank_ids = {str(row["id"]) for row in year_bank}
            with self.database.transaction() as db:
                known = {row[0] for row in db.execute("SELECT source FROM bank_transactions WHERE source LIKE 'sevdesk/CheckAccountTransaction/%'")}
                for obj in all_bank:
                    if str(obj["id"]) not in year_bank_ids and "sevdesk/CheckAccountTransaction/" + str(obj["id"]) not in known:
                        continue
                    self.transaction(obj, db)
                present = {"sevdesk/CheckAccountTransaction/" + str(obj["id"]) for obj in all_bank}
                for source in known - present:
                    old = db.execute("SELECT * FROM bank_transactions WHERE source=?", (source,)).fetchone()
                    if json.loads(old["data"]).get("source_missing"):
                        continue
                    db.execute("UPDATE bank_transactions SET amount=0,classification='excluded',data=? WHERE source=?", (canonical({"source_missing": True}), source))
                    self.database.audit(db, "bank.absent_from_source", old["id"], {"source": source, "before": json.loads(old["data"]), "current": "absent"}, "sevdesk-import")
                    self.resolved_sources.add(source)
            self.summary["counts"]["CheckAccountTransaction"] = len(year_bank)
            for model, position_model, foreign_key, date_field in (("Invoice", "InvoicePos", "invoice", "invoiceDate"),
                                                                 ("Voucher", "VoucherPos", "voucher", "voucherDate"),
                                                                 ("CreditNote", "CreditNotePos", "creditNote", "creditNoteDate")):
                rows = self.client.list(model)
                with self.database.connect() as db:
                    known = {row[0] for row in db.execute("SELECT source FROM records WHERE source LIKE ?", ("sevdesk/" + model + "/%",))}
                chosen = 0
                for obj in rows:
                    source = "sevdesk/" + model + "/" + str(obj["id"])
                    try:
                        logs = self.client.get(model + "/" + str(obj["id"]) + "/getCheckAccountTransactionLogs")["objects"] or []
                        record_year = source_date(obj.get(date_field) or obj.get("create"))[:4]
                        relevant = record_year == str(year) or any(source_date(log.get("bookingDate") or log.get("create"))[:4] == str(year) for log in logs)
                        if not relevant and source not in known:
                            continue
                        chosen += 1
                        positions = self.client.list(position_model, {foreign_key + "[id]": obj["id"], foreign_key + "[objectName]": model})
                        transactions = self.client.get(model + "/" + str(obj["id"]) + "/getCheckAccountTransactions")["objects"] or []
                        self.record(model, obj, positions, logs, transactions)
                    except (SourceError, ValueError) as error:
                        self.summary["errors"].append(source + ": " + str(error))
                        self.summary["source_drift"].append(source)
                self.summary["counts"][model] = chosen
                self.retire_missing(model, {"sevdesk/" + model + "/" + str(obj["id"]) for obj in rows})
            # Shared payments may be replaced in either order. Check the final
            # projection, never reject a temporary intermediate bank allocation.
            with self.database.connect() as db:
                for row in db.execute("SELECT b.source,ABS(b.amount) AS amount,SUM(p.amount) AS matched FROM bank_transactions b JOIN payments p ON p.bank_id=b.id WHERE p.reversed_by IS NULL GROUP BY b.id HAVING matched>ABS(b.amount)"):
                    self.summary["errors"].append(row["source"] + ": los pagos superan el movimiento actual de sevdesk.")
                    self.summary["source_drift"].append(row["source"])
            self.summary["audit"] = self.database.verify_audit()
            self.summary["verified_documents"] = self.documents.verify_all()
            self.summary["source_drift"] = sorted(set(self.summary["source_drift"]))
            pending = set(self.database.setting("source_drift") or []) - self.resolved_sources
            self.summary["source_drift"] = sorted(pending | set(self.summary["source_drift"]))
            self.summary["cost_centres_refreshed"] = sorted(self.refreshed_centres)
            self.summary["source_metadata_refreshed"] = sorted(self.refreshed_metadata)
            self.summary["source_refreshed"] = sorted(self.refreshed_sources)
            self.summary["authority"] = "latest_sevdesk"
            state = "needs_attention" if self.summary["errors"] or self.summary["source_drift"] else "complete"
        except BaseException as error:
            self.summary["errors"].append(type(error).__name__ + ": " + str(error)[:250])
            state = "failed"
        finally:
            with self.database.transaction() as db:
                db.execute("UPDATE imports SET state=?,finished=?,summary=? WHERE id=?", (state, now(), canonical(self.summary), import_id))
                self.database.audit(db, "import.finished", import_id, {"state": state, "summary": self.summary}, "sevdesk-import")
                if self.summary["source_drift"] or self.resolved_sources:
                    self.database.set_setting(db, "source_drift", self.summary["source_drift"])
            lock.close()
        return {"id": import_id, "state": state, **self.summary}
