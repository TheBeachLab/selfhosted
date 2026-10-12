import json

from .db import canonical, identity, now
from .models import RecordInput


def total(data):
    return sum(line["net_cents"] + line["tax_cents"] for line in data["lines"])


def sign(kind):
    return 1 if kind in ("invoice", "income", "tax_refund") else -1


def record_view(db, row):
    value = dict(row)
    value["data"] = json.loads(value["data"])
    value["total"] = total(value["data"])
    value["net"] = sum(line["net_cents"] for line in value["data"]["lines"])
    value["tax"] = sum(line["tax_cents"] for line in value["data"]["lines"])
    value["paid"] = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE record_id=? AND reversed_by IS NULL", (row["id"],)).fetchone()[0]
    value["documents"] = [dict(item) for item in db.execute(
        "SELECT d.id,d.filename,d.media_type,rd.role FROM documents d JOIN record_documents rd ON rd.document_id=d.id WHERE rd.record_id=?", (row["id"],))]
    return value


class Ledger:
    def __init__(self, database, documents):
        self.database = database
        self.documents = documents

    def get(self, record_id, db=None):
        if db is None:
            with self.database.connect() as connection:
                return self.get(record_id, connection)
        row = db.execute("SELECT * FROM records WHERE id=?", (record_id,)).fetchone()
        if not row:
            raise KeyError("Registro no encontrado.")
        return record_view(db, row)

    def list(self, kind=None, start="0000", end="9999"):
        with self.database.connect() as db:
            query = "SELECT * FROM records WHERE date BETWEEN ? AND ?"
            params = [start, end]
            if kind == "expenses":
                query += " AND kind IN ('expense','income','credit_note','asset','tax_payment','tax_refund')"
            elif kind:
                query += " AND kind=?"
                params.append(kind)
            return [record_view(db, row) for row in db.execute(query + " ORDER BY date DESC,created DESC LIMIT 5000", params)]

    def save(self, payload: RecordInput, record_id=None):
        data = payload.model_dump(mode="json", exclude={"revision", "document_ids"})
        with self.database.transaction() as db:
            revision = 1
            if record_id:
                current = self.get(record_id, db)
                if current["state"] not in ("draft", "needs_review"):
                    raise ValueError("El registro está cerrado. Crea una rectificación conservando el original.")
                if payload.revision != current["revision"]:
                    raise ValueError("El registro cambió. Recarga antes de guardar.")
                if payload.kind != current["kind"]:
                    allowed = ({"expense", "asset", "tax_payment"}, {"income", "tax_refund"})
                    if current["state"] not in ("draft","needs_review") or not any({payload.kind,current["kind"]} <= group for group in allowed):
                        raise ValueError("El tipo de registro no puede cambiar.")
                if current["paid"] > total(data):
                    raise ValueError("El total no puede quedar por debajo de los pagos importados. Revisa el reparto profesional mediante porcentajes.")
                if current["source"]:
                    # An imported issued invoice is never rewritten as if it had
                    # been newly issued here. Only its local fiscal classification
                    # may be reviewed; the original PDF/XML/raw snapshot is fixed.
                    if current["kind"] == "invoice":
                        old = current["data"]
                        if (data["date"] != old["date"] or data["party_id"] != old["party_id"]
                                or len(data["lines"]) != len(old["lines"])
                                or any((new["net_cents"],new["tax_cents"],new["description"]) != (prior["net_cents"],prior["tax_cents"],prior["description"]) for new,prior in zip(data["lines"],old["lines"]))):
                            raise ValueError("La factura original de sevdesk es inmutable. Revisa solo actividad y tratamiento fiscal.")
                    data.update({key: value for key,value in current["data"].items() if key.startswith("source_")})
                    if data.get("source_unsupported") == "Centro de coste sin actividad reconocida.":
                        # Explicit local activity choices resolve this one issue;
                        # the original missing centre remains in source JSON.
                        data["source_unsupported"] = ""
                revision = current["revision"] + 1
                db.execute("UPDATE records SET data=?,date=?,kind=?,revision=?,updated=? WHERE id=?",
                           (canonical(data), str(payload.date), payload.kind, revision, now(), record_id))
            else:
                record_id = identity("rec")
                db.execute("INSERT INTO records(id,kind,date,state,data,created,updated) VALUES(?,?,?,?,?,?,?)",
                           (record_id, payload.kind, str(payload.date), "draft", canonical(data), now(), now()))
            for doc_id in payload.document_ids:
                if not db.execute("SELECT 1 FROM documents WHERE id=?", (doc_id,)).fetchone():
                    raise ValueError("Documento no encontrado.")
                db.execute("INSERT OR IGNORE INTO record_documents VALUES(?,?,?)", (record_id, doc_id, "original"))
            self.database.audit(db, "record.saved", record_id, {"revision": revision, "snapshot": data})
            return self.get(record_id, db)

    def review(self, record_id, expected_revision):
        with self.database.transaction() as db:
            current = self.get(record_id, db)
            if current["state"] not in ("draft", "needs_review") or current["revision"] != expected_revision:
                raise ValueError("El registro cambió o ya está revisado.")
            if current["kind"] == "invoice" and not current["source"]:
                raise ValueError("Emite el borrador de factura con validación XRechnung.")
            if current["source"] and current["data"].get("source_status") in ("50", "750"):
                raise ValueError("Es un borrador o anulación en sevdesk. Verifica el estado original antes de incluirlo en declaraciones.")
            # Revalidate imported lines: the source is preserved even when its classification changes.
            data = dict(current["data"])
            source = {key: data.pop(key) for key in list(data) if key.startswith("source_")}
            RecordInput.model_validate(data)
            if any(line["tax_code"] == "unclassified" or line["category"] == "unclassified" for line in data["lines"]):
                raise ValueError("Clasifica todas las líneas y categorías antes de cerrar.")
            if not any(doc["role"] in ("original", "invoice_pdf", "invoice_xml") for doc in current["documents"]):
                raise ValueError("Falta el justificante original.")
            if source.get("source_unsupported"):
                raise ValueError("El origen contiene un caso no soportado; revisa su rectificación antes de cerrar.")
            db.execute("UPDATE records SET state='reviewed',updated=? WHERE id=?", (now(), record_id))
            self.database.audit(db, "record.reviewed", record_id, {"revision": current["revision"]})
            return self.get(record_id, db)

    def payment(self, record_id, payload, bank_id=None, source=None, db=None):
        if db is None:
            with self.database.transaction() as connection:
                return self.payment(record_id, payload, bank_id, source, connection)
        current = self.get(record_id, db)
        if current["state"] not in ("issued", "reviewed", "needs_review"):
            raise ValueError("Cierra el documento antes de registrar el pago.")
        if current["state"] == "needs_review" and not source:
            raise ValueError("Revisa el documento importado antes de conciliar.")
        if current["paid"] + payload.amount > current["total"]:
            raise ValueError("El pago supera el saldo pendiente del documento.")
        bank_id = bank_id or payload.bank_id
        if bank_id:
            transaction = db.execute("SELECT * FROM bank_transactions WHERE id=?", (bank_id,)).fetchone()
            if not transaction:
                raise KeyError("Movimiento no encontrado.")
            if transaction["classification"] in ("private", "transfer", "excluded"):
                raise ValueError("El movimiento está marcado como privado, traslado o excluido.")
            if sign(current["kind"]) * transaction["amount"] <= 0:
                raise ValueError("El sentido del movimiento no corresponde al documento.")
            used = db.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE bank_id=? AND reversed_by IS NULL", (bank_id,)).fetchone()[0]
            if used + payload.amount > abs(transaction["amount"]):
                raise ValueError("Ese importe del movimiento ya está conciliado.")
            if str(payload.date) != transaction["date"]:
                raise ValueError("Usa la fecha de contabilización del movimiento.")
        payment_id = identity("pay")
        db.execute("INSERT INTO payments(id,record_id,bank_id,date,amount,source,created) VALUES(?,?,?,?,?,?,?)",
                   (payment_id, record_id, bank_id, str(payload.date), payload.amount, source, now()))
        self.database.audit(db, "payment.recorded", payment_id, {"record": record_id, "bank": bank_id, "date": str(payload.date), "amount": payload.amount}, "sevdesk-import" if source else "fran")
        return payment_id

    def reverse_payment(self, payment_id):
        with self.database.transaction() as db:
            row = db.execute("SELECT * FROM payments WHERE id=? AND reversed_by IS NULL", (payment_id,)).fetchone()
            if not row:
                raise ValueError("El pago no existe o ya se revirtió.")
            reversal = identity("reversal")
            db.execute("UPDATE payments SET reversed_by=? WHERE id=?", (reversal, payment_id))
            self.database.audit(db, "payment.reversed", reversal, {"payment": payment_id})
            return reversal
