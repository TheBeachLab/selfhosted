"""Read-only, resumable migration. Allowed network verbs: GET only.

Public specification: https://api.sevdesk.de/ (downloaded 2026-10-12).
Document/download and transaction-log shapes were additionally observed through
authenticated GET requests on 2026-10-12; these legacy endpoints are not listed
in the current public OpenAPI file. Preserve raw responses; refuse silent guesses.
"""
import base64
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time

import httpx

from .bank import bank_date
from .db import canonical, identity, now
from .documents import media_type
from .models import ACTIVITIES, PaymentInput, cents

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

    def archive(self, db, source, payload, record_id=None):
        raw = canonical(payload).encode()
        digest = hashlib.sha256(raw).hexdigest()
        doc_id = self.documents.store(db, raw, source.replace("/", "-") + ".json", "application/json", record_id, "source_json")
        db.execute("INSERT OR IGNORE INTO source_revisions VALUES(?,?,?,?)", (source, digest, doc_id, now()))
        return digest

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
                # Do not overwrite a locally edited contact on a second import.
                db.execute("INSERT OR IGNORE INTO contacts(id,data,source) VALUES(?,?,?)", ("sev_contact_" + str(row["id"]), canonical(party), source))
            for row in accounts:
                db.execute("INSERT OR IGNORE INTO bank_accounts VALUES(?,?,?,?)", ("sev_account_" + str(row["id"]), row.get("name") or ("Cuenta sevdesk " + str(row["id"])), row.get("currency") or "EUR", "sevdesk/CheckAccount/" + str(row["id"])))
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
        if existing:
            if existing["date"] != data["date"] or existing["amount"] != data["amount"]:
                self.summary["source_drift"].append(source)
            return existing["id"]
        transaction_id = "sev_bank_" + str(obj["id"])
        # Only explicit source private status is imported as private. Transfers,
        # deleted/zero transactions stay archived but cannot be booked as income.
        classification = "excluded" if obj.get("deletedAt") or not data["amount"] else "private" if str(obj.get("status")) == "300" else "unreviewed"
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
        with self.database.transaction() as db:
            digest = hashlib.sha256(canonical(bundle).encode()).hexdigest()
            existing = db.execute("SELECT * FROM records WHERE source=?", (source,)).fetchone()
            record_id = existing["id"] if existing else "sev_" + model.lower() + "_" + str(obj["id"])
            prior = db.execute("SELECT 1 FROM source_revisions WHERE source=? AND sha256=?", (source, digest)).fetchone()
            if existing and not prior:
                self.summary["source_drift"].append(source)
            if not existing:
                state = "void" if str(obj.get("hidden", "0")) in ("1", "true") else "needs_review"
                db.execute("INSERT INTO records(id,kind,date,number,state,data,source,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                           (record_id, kind, record_date, obj.get("invoiceNumber") if model == "Invoice" else None, state, canonical(data), source, now(), now()))
                self.database.audit(db, "record.source_imported", record_id, {"source": source}, "sevdesk-import")
            self.archive(db, source, bundle, record_id)
            for transaction in transactions:
                self.transaction(transaction, db)
        # Preserve all originals, not rendered previews, and attach immutable revisions.
        if model in ("Invoice", "CreditNote"):
            try:
                pdf, filename = download_bytes(self.client.get(model + "/" + str(obj["id"]) + "/getPdf", {"preventSendBy": "true"}))
                if media_type(pdf) != "application/pdf":
                    raise SourceError("No se obtuvo un PDF original.")
                with self.database.transaction() as db:
                    self.documents.store(db, pdf, filename, "application/pdf", record_id, "invoice_pdf")
                self.summary["documents"] += 1
            except (SourceError, ValueError) as error:
                self.summary["errors"].append(source + ": " + str(error))
            if model == "Invoice":
                try:
                    xml = self.client.get("Invoice/" + str(obj["id"]) + "/getXml")["objects"]
                    if not isinstance(xml, str) or media_type(xml.encode()) != "application/xml":
                        raise SourceError("No se obtuvo XML válido.")
                    with self.database.transaction() as db:
                        self.documents.store(db, xml.encode(), (obj.get("invoiceNumber") or str(obj["id"])) + ".xml", "application/xml", record_id, "invoice_xml")
                    self.summary["documents"] += 1
                except SourceError as error:
                    if not str(error).endswith("HTTP 400") and not str(error).endswith("HTTP 404"):
                        self.summary["errors"].append(source + ": " + str(error))
                except ValueError as error:
                    self.summary["errors"].append(source + ": " + str(error))
        elif object_id(obj.get("document")):
            try:
                doc_source = "Document/" + object_id(obj["document"])
                metadata = self.client.get(doc_source)
                raw, filename = download_bytes(self.client.get(doc_source + "/download"))
                with self.database.transaction() as db:
                    self.archive(db, "sevdesk/" + doc_source, metadata)
                    self.documents.store(db, raw, filename, media_type(raw), record_id, "original")
                self.summary["documents"] += 1
            except (SourceError, ValueError) as error:
                self.summary["errors"].append(source + ": " + str(error))
        else:
            self.summary["errors"].append(source + ": justificante ausente en sevdesk.")
        # Booking logs contain signed amounts. A reset/reversal is not a new payment.
        # Validate their sum against paidAmount; ambiguous histories stay unbooked.
        paid = abs(cents(obj.get("paidAmount") or 0))
        signed_sum = sum(cents(log.get("amountPaid") or 0) for log in logs)
        expected_sign = 1 if kind in ("invoice", "income") else -1
        valid_logs = all(cents(log.get("amountPaid") or 0) * expected_sign >= 0 for log in logs)
        if logs and (not valid_logs or abs(signed_sum) != paid):
            self.summary["errors"].append(source + ": historial de pagos/reversiones ambiguo; se conserva sin conciliar automáticamente.")
        elif logs:
            for log in logs:
                amount = abs(cents(log.get("amountPaid") or 0))
                if not amount:
                    continue
                payment_source = "sevdesk/CheckAccountTransactionLog/" + str(log["id"])
                try:
                    with self.database.transaction() as db:
                        self.archive(db, payment_source, log, record_id)
                        if db.execute("SELECT 1 FROM payments WHERE source=?", (payment_source,)).fetchone():
                            continue
                        bank_id = "sev_bank_" + object_id(log.get("checkAccountTransaction"))
                        movement = db.execute("SELECT * FROM bank_transactions WHERE id=?", (bank_id,)).fetchone()
                        if not movement:
                            raise SourceError("El movimiento de un pago no aparece en la exportación.")
                        payment = PaymentInput(bank_id=bank_id, date=movement["date"], amount=amount)
                        self.ledger.payment(record_id, payment, source=payment_source, db=db)
                    self.summary["payments"] += 1
                except (SourceError, ValueError) as error:
                    self.summary["errors"].append(source + ": " + str(error))
        elif paid:
            self.summary["errors"].append(source + ": importe pagado sin movimientos/logs; requiere reconstrucción verificada.")
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
            with self.database.transaction() as db:
                for obj in year_bank:
                    self.transaction(obj, db)
            self.summary["counts"]["CheckAccountTransaction"] = len(year_bank)
            for model, position_model, foreign_key, date_field in (("Invoice", "InvoicePos", "invoice", "invoiceDate"),
                                                                 ("Voucher", "VoucherPos", "voucher", "voucherDate"),
                                                                 ("CreditNote", "CreditNotePos", "creditNote", "creditNoteDate")):
                rows = self.client.list(model)
                chosen = 0
                for obj in rows:
                    source = "sevdesk/" + model + "/" + str(obj["id"])
                    try:
                        logs = self.client.get(model + "/" + str(obj["id"]) + "/getCheckAccountTransactionLogs")["objects"] or []
                        record_year = source_date(obj.get(date_field) or obj.get("create"))[:4]
                        relevant = record_year == str(year) or any(source_date(log.get("bookingDate") or log.get("create"))[:4] == str(year) for log in logs)
                        if not relevant:
                            continue
                        chosen += 1
                        positions = self.client.list(position_model, {foreign_key + "[id]": obj["id"], foreign_key + "[objectName]": model})
                        transactions = self.client.get(model + "/" + str(obj["id"]) + "/getCheckAccountTransactions")["objects"] or []
                        self.record(model, obj, positions, logs, transactions)
                    except (SourceError, ValueError) as error:
                        self.summary["errors"].append(source + ": " + str(error))
                self.summary["counts"][model] = chosen
            self.summary["audit"] = self.database.verify_audit()
            self.summary["verified_documents"] = self.documents.verify_all()
            self.summary["source_drift"] = sorted(set(self.summary["source_drift"]))
            state = "needs_attention" if self.summary["errors"] or self.summary["source_drift"] else "complete"
        except BaseException as error:
            self.summary["errors"].append(type(error).__name__ + ": " + str(error)[:250])
            state = "failed"
        finally:
            with self.database.transaction() as db:
                db.execute("UPDATE imports SET state=?,finished=?,summary=? WHERE id=?", (state, now(), canonical(self.summary), import_id))
                self.database.audit(db, "import.finished", import_id, {"state": state, "summary": self.summary}, "sevdesk-import")
                if self.summary["source_drift"]:
                    self.database.set_setting(db, "source_drift", self.summary["source_drift"])
            lock.close()
        return {"id": import_id, "state": state, **self.summary}
